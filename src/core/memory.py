"""Memory subsystem for the Jarvis AI Agent.

This module defines helpers for long-term and short-term memory, backed by
Supabase. It is responsible for storing conversation history and maintaining
per-user long-term summaries that can be injected into the LLM context.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import asyncio
import json
import logging
import os

from pydantic import BaseModel

try:
    from supabase import Client, create_client  # type: ignore
except Exception:  # noqa: BLE001
    Client = object  # type: ignore[assignment]
    create_client = None  # type: ignore[assignment]

from src.core.llm import call_llm


logger = logging.getLogger("jarvis.memory")

_SUPABASE_CLIENT: Optional[Client] = None


def _get_supabase_client() -> Optional[Client]:
    """Return a cached Supabase client, or None if not configured.

    Reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY / SUPABASE_ANON_KEY from
    the environment. All operations are executed in a thread pool to avoid
    blocking the async event loop, since the Supabase Python client is
    synchronous.
    """

    global _SUPABASE_CLIENT

    if _SUPABASE_CLIENT is not None:
        return _SUPABASE_CLIENT

    if create_client is None:
        logger.warning("supabase-py is not installed; memory will be a no-op")
        return None

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        logger.warning(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY/ANON_KEY are not fully "
            "configured; memory will be a no-op.",
        )
        return None

    try:
        _SUPABASE_CLIENT = create_client(url, key)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to create Supabase client: %r", exc)
        _SUPABASE_CLIENT = None

    return _SUPABASE_CLIENT


# ---------------------------------------------------------------------------
# Supabase schema (for reference only; must exist in your Supabase project)
#
# Table: conversation_messages
#   id         uuid        primary key, default gen_random_uuid()
#   user_id    text        indexed
#   role       text        'user' | 'assistant' | 'tool'
#   content    text
#   metadata   jsonb       optional (tool name, etc.)
#   created_at timestamptz default now()
#
# Table: long_term_memory
#   user_id    text        primary key
#   summary    text        rolling summary of user history/preferences
#   updated_at timestamptz default now()
# ---------------------------------------------------------------------------


async def append_message(user_id: str, role: str, content: str, metadata: Dict[str, Any] | None = None) -> None:
    """Store a single message in conversation_messages with retry logic."""

    client = _get_supabase_client()
    if client is None:
        return

    payload: Dict[str, Any] = {"user_id": user_id, "role": role, "content": content}
    if metadata is not None:
        payload["metadata"] = metadata

    loop = asyncio.get_running_loop()

    def _insert() -> None:
        client.table("conversation_messages").insert(payload).execute()

    # Retry up to 3 times with exponential backoff
    for attempt in range(3):
        try:
            await loop.run_in_executor(None, _insert)
            return  # Success
        except Exception as exc:  # noqa: BLE001
            if attempt < 2:  # Don't sleep on last attempt
                await asyncio.sleep(0.1 * (2 ** attempt))  # 0.1s, 0.2s
            else:
                logger.error("Error inserting conversation message after 3 attempts: %r", exc)


async def get_recent_messages(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Fetch the most recent messages for this user in ascending order with retry logic.

    Returns a list of dicts with at least::

        {"role": "user" | "assistant" | "tool", "content": str}
    """

    client = _get_supabase_client()
    if client is None:
        return []

    loop = asyncio.get_running_loop()

    def _select() -> List[Dict[str, Any]]:
        resp = (
            client.table("conversation_messages")
            .select("user_id, role, content, metadata, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = getattr(resp, "data", None) or []
        # We requested desc order; reverse so the caller sees ascending.
        rows.reverse()
        return rows

    # Retry up to 3 times with exponential backoff
    for attempt in range(3):
        try:
            rows = await loop.run_in_executor(None, _select)
            break  # Success
        except Exception as exc:  # noqa: BLE001
            if attempt < 2:
                await asyncio.sleep(0.1 * (2 ** attempt))
            else:
                logger.error("Error fetching recent messages after 3 attempts: %r", exc)
                return []

    messages: List[Dict[str, Any]] = []
    for row in rows:
        role = row.get("role")
        content = row.get("content")
        if not role or content is None:
            continue
        messages.append({"role": role, "content": content})

    return messages


async def get_long_term_memory(user_id: str) -> Optional[str]:
    """Fetch the long_term_memory.summary for this user, if any."""

    client = _get_supabase_client()
    if client is None:
        return None

    loop = asyncio.get_running_loop()

    def _select() -> Optional[str]:
        resp = (
            client.table("long_term_memory")
            .select("user_id, summary")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = getattr(resp, "data", None) or []
        if not rows:
            return None
        return rows[0].get("summary")

    # Retry up to 3 times with exponential backoff
    for attempt in range(3):
        try:
            return await loop.run_in_executor(None, _select)
        except Exception as exc:  # noqa: BLE001
            if attempt < 2:
                await asyncio.sleep(0.1 * (2 ** attempt))
            else:
                logger.error("Error fetching long-term memory after 3 attempts: %r", exc)
                return None


async def update_long_term_memory(user_id: str, messages: List[Dict[str, Any]]) -> None:
    """Summarize conversation history into long-term memory and upsert it.

    This function relies on the LLM to extract stable preferences, profile,
    goals, and important facts from the provided messages. The caller controls
    when to invoke it (e.g., every N turns or when explicitly requested).
    """

    if not messages:
        return

    client = _get_supabase_client()
    if client is None:
        # If Supabase is not configured, skip LLM calls for summarization.
        return

    # Build a compact representation of the recent conversation.
    convo_payload = json.dumps(messages, ensure_ascii=False)

    system_prompt = (
        "You are an AI assistant responsible for maintaining long-term memory "
        "about a single user. Given the recent conversation messages below, "
        "summarize ONLY the user's stable preferences, profile details, "
        "recurring goals, and important facts you should remember for future "
        "conversations. Do not include transient small talk. Keep it concise. "
        "Always write the summary in English only, regardless of the input language "
        "of the conversation."
    )

    llm_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": convo_payload},
    ]

    try:
        llm_result = await call_llm(llm_messages, tools=None)
    except Exception as exc:  # noqa: BLE001
        logger.error("Error calling LLM for long-term memory update: %r", exc)
        return

    if llm_result.get("type") != "message":
        logger.warning("LLM did not return a normal message for memory update")
        return

    summary = (llm_result.get("content") or "").strip()
    if not summary:
        logger.warning("LLM returned empty summary for long-term memory; skipping")
        return

    payload = {"user_id": user_id, "summary": summary}
    loop = asyncio.get_running_loop()

    def _upsert() -> None:
        client.table("long_term_memory").upsert(payload, on_conflict="user_id").execute()

    try:
        await loop.run_in_executor(None, _upsert)
    except Exception as exc:  # noqa: BLE001
        logger.error("Error upserting long-term memory: %r", exc)


class MemoryConfig(BaseModel):
    """Configuration for the memory subsystem.

    Placeholder for future configuration values (e.g., Supabase project ids).
    """

    placeholder: Optional[str] = None


class MemoryManager:
    """Compatibility wrapper around the new memory helpers.

    Existing code can continue to use MemoryManager, while new code should
    prefer the module-level async helper functions directly.
    """

    def __init__(self, config: Optional[MemoryConfig] = None) -> None:
        self._config = config

    async def read_user_memory(self, user_id: str) -> Dict[str, Any]:
        summary = await get_long_term_memory(user_id)
        return {"summary": summary} if summary else {}

    async def write_user_memory(self, user_id: str, data: Dict[str, Any]) -> None:
        # Minimal compatibility: if last_user_message / last_agent_reply are
        # present, append them as separate conversation messages.
        last_user = data.get("last_user_message")
        last_agent = data.get("last_agent_reply")

        if last_user:
            await append_message(user_id, "user", str(last_user))
        if last_agent:
            await append_message(user_id, "assistant", str(last_agent))
