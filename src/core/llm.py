"""LLM client abstraction for the Jarvis AI Agent.

This module wraps calls to the OpenAI API behind a clean interface that
supports plain text responses and tool-calling (function calling).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from openai import OpenAI
from pydantic import BaseModel


logger = logging.getLogger("jarvis.llm")


class LLMConfig(BaseModel):
    """Configuration for the LLM client."""

    model: str = "gpt-4o-mini"
    max_tokens: int = 1024  # Increased for better responses
    temperature: float = 0.1  # Lower for faster, more consistent responses
    request_timeout: int = 30  # Reduced timeout for faster failures


def _get_client() -> OpenAI:
    """Return a configured OpenAI client or raise if API key missing."""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY is not set; LLM calls will fail")
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key)


def _safe_json_loads(value: str) -> Any:
    """Safely parse a JSON string, returning None on failure."""

    try:
        return json.loads(value)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to parse JSON from model output", exc_info=True)
        return None


async def call_llm(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    config: Optional[LLMConfig] = None,
) -> Dict[str, Any]:
    """Call the OpenAI chat model with optional tool schemas.

    Returns a structured dict with one of the following shapes:

    - {"type": "message", "content": str}
    - {"type": "tool", "tool_calls": [{"id", "name", "arguments"}, ...]}
    - {"type": "error", "error": str}
    """

    cfg = config or LLMConfig()

    try:
        client = _get_client()
    except RuntimeError as exc:  # API key missing
        return {"type": "error", "error": str(exc)}

    # OpenAI Python SDK (>=2.x) chat completions API with tools.
    try:
        response = client.chat.completions.create(
            model=cfg.model,
            messages=messages,
            tools=tools or None,
            tool_choice="auto" if tools else None,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            timeout=cfg.request_timeout,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Error while calling OpenAI chat completion: %r", exc)
        return {"type": "error", "error": "LLM_CALL_FAILED"}

    if not response or not getattr(response, "choices", None):
        logger.warning("Empty response from LLM")
        return {"type": "error", "error": "EMPTY_RESPONSE"}

    choice = response.choices[0]
    message = choice.message

    # Tool call branch.
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        parsed_calls: List[Dict[str, Any]] = []
        for call in tool_calls:
            fn = call.function
            raw_args = fn.arguments or "{}"
            args = _safe_json_loads(raw_args) if isinstance(raw_args, str) else raw_args
            if args is None:
                args = {}
            parsed_calls.append(
                {
                    "id": call.id,
                    "name": fn.name,
                    "arguments": args,
                }
            )

        return {"type": "tool", "tool_calls": parsed_calls}

    # Normal text response branch.
    content = message.content or ""
    if isinstance(content, list):
        # Some models may return a list of content parts.
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))

    if not isinstance(content, str):
        content = str(content)

    return {"type": "message", "content": content}
