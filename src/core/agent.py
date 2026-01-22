"""Core agent module for the Jarvis AI Agent.

This module defines the main Jarvis agent loop responsible for coordinating
LLM calls, tools, memory, and external services.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional
from functools import lru_cache
from pathlib import Path
from threading import Lock

import logging

from src.core.context import build_context
from src.core.llm import call_llm
from src.core.memory import append_message
from src.core.memory import get_recent_messages
from src.core.memory import update_long_term_memory
from src.core.tools import run_tool
from src.core.gmail_delete_flow import handle_gmail_delete_turn
from src.core.gmail_mark_read_flow import handle_gmail_mark_read_turn
from src.core.gmail_spam_clean_flow import handle_gmail_spam_clean_turn
from src.core.gmail_send_flow import handle_gmail_send_turn
from src.core.gmail_send_flow import maybe_store_gmail_send_state_from_tool_result
from src.core.calendar_cancel_flow import handle_calendar_cancel_turn
from src.core.calendar_cancel_flow import maybe_store_calendar_cancel_state_from_tool_result
from src.core.calendar_note_flow import handle_calendar_note_turn
from src.core.calendar_note_flow import maybe_store_calendar_note_state_from_tool_result
from src.core.confidence import compute_tool_confidence, format_confidence_prefix
from src.utils.logger import get_logger
from src.utils.logger import log_error
from src.utils.logger import log_info
from src.utils.formatter import format_agent_response, strip_system_commentary

logger = logging.getLogger("jarvis.agent")

_PENDING_TOOL_CONFIRM: Dict[str, Dict[str, Any]] = {}
_PENDING_TOOL_CONFIRM_LOCK = Lock()
_PENDING_TOOL_CONFIRM_FILE = Path("data") / "pending_tool_confirm.json"

_PENDING_TRELLO_COMMENT: Dict[str, Dict[str, Any]] = {}
_PENDING_TRELLO_COMMENT_LOCK = Lock()
_PENDING_TRELLO_COMMENT_FILE = Path("data") / "pending_trello_comment.json"

_PENDING_TRELLO_DISPATCH: Dict[str, Dict[str, Any]] = {}
_PENDING_TRELLO_DISPATCH_LOCK = Lock()
_PENDING_TRELLO_DISPATCH_FILE = Path("data") / "pending_trello_dispatch.json"

_PENDING_CONFIDENCE_CLARIFY: Dict[str, Dict[str, Any]] = {}
_PENDING_CONFIDENCE_CLARIFY_LOCK = Lock()
_PENDING_CONFIDENCE_CLARIFY_FILE = Path("data") / "pending_confidence_clarify.json"


def _load_pending_tool_confirm() -> None:
    try:
        _PENDING_TOOL_CONFIRM_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not _PENDING_TOOL_CONFIRM_FILE.exists():
            return
        raw = _PENDING_TOOL_CONFIRM_FILE.read_text(encoding="utf-8")
        if not raw.strip():
            return
        data = json.loads(raw)
        if not isinstance(data, dict):
            return
        with _PENDING_TOOL_CONFIRM_LOCK:
            _PENDING_TOOL_CONFIRM.clear()
            for k, v in data.items():
                if isinstance(k, str) and isinstance(v, dict):
                    _PENDING_TOOL_CONFIRM[k] = v
    except Exception:
        return


def _load_pending_trello_comment() -> None:
    try:
        _PENDING_TRELLO_COMMENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not _PENDING_TRELLO_COMMENT_FILE.exists():
            return
        raw = _PENDING_TRELLO_COMMENT_FILE.read_text(encoding="utf-8")
        if not raw.strip():
            return
        data = json.loads(raw)
        if not isinstance(data, dict):
            return
        with _PENDING_TRELLO_COMMENT_LOCK:
            _PENDING_TRELLO_COMMENT.clear()
            for k, v in data.items():
                if isinstance(k, str) and isinstance(v, dict):
                    _PENDING_TRELLO_COMMENT[k] = v
    except Exception:
        return


def _load_pending_trello_dispatch() -> None:
    try:
        _PENDING_TRELLO_DISPATCH_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not _PENDING_TRELLO_DISPATCH_FILE.exists():
            return
        raw = _PENDING_TRELLO_DISPATCH_FILE.read_text(encoding="utf-8")
        if not raw.strip():
            return
        data = json.loads(raw)
        if not isinstance(data, dict):
            return
        with _PENDING_TRELLO_DISPATCH_LOCK:
            _PENDING_TRELLO_DISPATCH.clear()
            for k, v in data.items():
                if isinstance(k, str) and isinstance(v, dict):
                    if "tool_name" not in v or not isinstance(v.get("tool_name"), str) or not str(v.get("tool_name") or "").strip():
                        v = dict(v)
                        v["tool_name"] = "trello_dispatch"
                    _PENDING_TRELLO_DISPATCH[k] = v
    except Exception:
        return


def _load_pending_confidence_clarify() -> None:
    try:
        _PENDING_CONFIDENCE_CLARIFY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not _PENDING_CONFIDENCE_CLARIFY_FILE.exists():
            return
        raw = _PENDING_CONFIDENCE_CLARIFY_FILE.read_text(encoding="utf-8")
        if not raw.strip():
            return
        data = json.loads(raw)
        if not isinstance(data, dict):
            return
        with _PENDING_CONFIDENCE_CLARIFY_LOCK:
            _PENDING_CONFIDENCE_CLARIFY.clear()
            for k, v in data.items():
                if isinstance(k, str) and isinstance(v, dict):
                    awaiting = v.get("awaiting")
                    if isinstance(awaiting, str) and awaiting.strip().lower() == "details":
                        continue
                    _PENDING_CONFIDENCE_CLARIFY[k] = v
    except Exception:
        return


def _save_pending_tool_confirm() -> None:
    try:
        _PENDING_TOOL_CONFIRM_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _PENDING_TOOL_CONFIRM_LOCK:
            _PENDING_TOOL_CONFIRM_FILE.write_text(json.dumps(_PENDING_TOOL_CONFIRM), encoding="utf-8")
    except Exception:
        return


def _save_pending_trello_comment() -> None:
    try:
        _PENDING_TRELLO_COMMENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _PENDING_TRELLO_COMMENT_LOCK:
            _PENDING_TRELLO_COMMENT_FILE.write_text(json.dumps(_PENDING_TRELLO_COMMENT), encoding="utf-8")
    except Exception:
        return


def _save_pending_trello_dispatch() -> None:
    try:
        _PENDING_TRELLO_DISPATCH_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _PENDING_TRELLO_DISPATCH_LOCK:
            _PENDING_TRELLO_DISPATCH_FILE.write_text(json.dumps(_PENDING_TRELLO_DISPATCH), encoding="utf-8")
    except Exception:
        return


def _save_pending_confidence_clarify() -> None:
    try:
        _PENDING_CONFIDENCE_CLARIFY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _PENDING_CONFIDENCE_CLARIFY_LOCK:
            _PENDING_CONFIDENCE_CLARIFY_FILE.write_text(json.dumps(_PENDING_CONFIDENCE_CLARIFY), encoding="utf-8")
    except Exception:
        return


_load_pending_tool_confirm()
_load_pending_trello_comment()
_load_pending_trello_dispatch()
_load_pending_confidence_clarify()


def _get_pending_tool_confirm(user_id: int) -> Optional[Dict[str, Any]]:
    with _PENDING_TOOL_CONFIRM_LOCK:
        pending = _PENDING_TOOL_CONFIRM.get(str(user_id))
        if not isinstance(pending, dict):
            return None
        return dict(pending)


def _get_pending_trello_comment(user_id: int) -> Optional[Dict[str, Any]]:
    with _PENDING_TRELLO_COMMENT_LOCK:
        pending = _PENDING_TRELLO_COMMENT.get(str(user_id))
        if not isinstance(pending, dict):
            return None
        return dict(pending)


def _get_pending_trello_dispatch(user_id: int) -> Optional[Dict[str, Any]]:
    with _PENDING_TRELLO_DISPATCH_LOCK:
        pending = _PENDING_TRELLO_DISPATCH.get(str(user_id))
        if not isinstance(pending, dict):
            return None
        return dict(pending)


def _get_pending_confidence_clarify(user_id: int) -> Optional[Dict[str, Any]]:
    with _PENDING_CONFIDENCE_CLARIFY_LOCK:
        pending = _PENDING_CONFIDENCE_CLARIFY.get(str(user_id))
        if not isinstance(pending, dict):
            return None
        return dict(pending)


def _set_pending_tool_confirm(user_id: int, pending: Dict[str, Any]) -> None:
    with _PENDING_TOOL_CONFIRM_LOCK:
        _PENDING_TOOL_CONFIRM[str(user_id)] = pending
    _save_pending_tool_confirm()


def _set_pending_trello_comment(user_id: int, pending: Dict[str, Any]) -> None:
    with _PENDING_TRELLO_COMMENT_LOCK:
        _PENDING_TRELLO_COMMENT[str(user_id)] = pending
    _save_pending_trello_comment()


def _set_pending_trello_dispatch(user_id: int, pending: Dict[str, Any]) -> None:
    with _PENDING_TRELLO_DISPATCH_LOCK:
        _PENDING_TRELLO_DISPATCH[str(user_id)] = pending
    _save_pending_trello_dispatch()


def _set_pending_confidence_clarify(user_id: int, pending: Dict[str, Any]) -> None:
    with _PENDING_CONFIDENCE_CLARIFY_LOCK:
        _PENDING_CONFIDENCE_CLARIFY[str(user_id)] = pending
    _save_pending_confidence_clarify()


def _clear_pending_tool_confirm(user_id: int) -> None:
    with _PENDING_TOOL_CONFIRM_LOCK:
        _PENDING_TOOL_CONFIRM.pop(str(user_id), None)
    _save_pending_tool_confirm()


def _clear_pending_trello_comment(user_id: int) -> None:
    with _PENDING_TRELLO_COMMENT_LOCK:
        _PENDING_TRELLO_COMMENT.pop(str(user_id), None)
    _save_pending_trello_comment()


def _clear_pending_trello_dispatch(user_id: int) -> None:
    with _PENDING_TRELLO_DISPATCH_LOCK:
        _PENDING_TRELLO_DISPATCH.pop(str(user_id), None)
    _save_pending_trello_dispatch()


def _clear_pending_confidence_clarify(user_id: int) -> None:
    with _PENDING_CONFIDENCE_CLARIFY_LOCK:
        _PENDING_CONFIDENCE_CLARIFY.pop(str(user_id), None)
    _save_pending_confidence_clarify()


def _is_confirm_text(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in {"yes", "proceed"}


def _is_cancel_text(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in {"cancel"}


def _extract_tool_url(tool_result: Any) -> Optional[str]:
    if not isinstance(tool_result, dict):
        return None

    data = tool_result.get("data")
    if isinstance(data, dict):
        url = data.get("url") or data.get("shortUrl")
        if isinstance(url, str) and url.strip():
            return url.strip()

    msg = tool_result.get("message")
    if isinstance(msg, str):
        for part in msg.split():
            if part.startswith("https://") or part.startswith("http://"):
                return part.strip()

    return None


async def agent(user_id: int, message: str, request_id: str | None = None) -> str:
    """Main agent entrypoint for a single user turn.

    Builds context, calls the LLM (with tools), optionally executes tools,
    and returns the final natural-language reply.
    """

    log_info("Agent started", user_id=str(user_id), request_id=request_id)

    pending_confirm = _get_pending_tool_confirm(user_id)
    if pending_confirm:
        if _is_cancel_text(message):
            _clear_pending_tool_confirm(user_id)
            return "Cancelled."
        if _is_confirm_text(message):
            tool_name = pending_confirm.get("tool_name") or ""
            tool_args = pending_confirm.get("tool_args")
            if not isinstance(tool_name, str) or not tool_name.strip() or not isinstance(tool_args, dict):
                _clear_pending_tool_confirm(user_id)
                return "No pending confirmation found. Please start again."
            tool_args = dict(tool_args)
            tool_args["confirm"] = True
            try:
                tool_result = await run_tool(tool_name.strip(), tool_args, user_id)
            except Exception as exc:  # noqa: BLE001
                _clear_pending_tool_confirm(user_id)
                log_error(
                    "pending_tool_confirmation_execution_failed",
                    user_id=str(user_id),
                    request_id=request_id,
                    tool=tool_name,
                    error=str(exc),
                )
                return "Sorry, I ran into an error while executing that confirmed action."

            _clear_pending_tool_confirm(user_id)
            if isinstance(tool_result, dict):
                msg = tool_result.get("message")
                if isinstance(msg, str) and msg.strip():
                    asyncio.create_task(
                        _update_memory_background(
                            user_id=user_id,
                            message=message,
                            final_text=msg.strip(),
                            request_id=request_id,
                        )
                    )
                    return msg.strip()
            return "Done."

        msg = pending_confirm.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
        return "Please confirm by replying YES or PROCEED, or say CANCEL."

    pending_clarify = _get_pending_confidence_clarify(user_id)
    if pending_clarify:
        if _is_cancel_text(message):
            _clear_pending_confidence_clarify(user_id)
            return "Cancelled."

        tool_name = str(pending_clarify.get("tool_name") or "").strip()
        tool_args = pending_clarify.get("tool_args")
        awaiting = str(pending_clarify.get("awaiting") or "").strip()
        one_shot = bool(pending_clarify.get("one_shot") is True)

        if not tool_name or not isinstance(tool_args, dict) or not awaiting:
            _clear_pending_confidence_clarify(user_id)
            return "No pending request found. Please start again."

        if awaiting.strip().lower() == "details":
            _clear_pending_confidence_clarify(user_id)
            return "Please repeat the request with the missing detail (for Trello: include the list name and, if needed, the board name)."

        args = dict(tool_args)
        user_value = str(message or "").strip()
        if user_value:
            args[awaiting] = user_value

        assessment = compute_tool_confidence(tool_name=tool_name, tool_args=args, tool_schema=None)
        if not one_shot and assessment.score < 70:
            _set_pending_confidence_clarify(
                user_id,
                {
                    "tool_name": tool_name,
                    "tool_args": args,
                    "awaiting": assessment.awaiting or awaiting,
                    "one_shot": False,
                },
            )
            if isinstance(assessment.question, str) and assessment.question.strip():
                return assessment.question.strip()
            _clear_pending_confidence_clarify(user_id)
            return "Please provide one more specific detail so I can proceed."

        confidence_score = assessment.score
        try:
            tool_result = await run_tool(tool_name, args, user_id)
        except Exception as exc:  # noqa: BLE001
            _clear_pending_confidence_clarify(user_id)
            log_error(
                "confidence_clarify_execution_failed",
                user_id=str(user_id),
                request_id=request_id,
                tool=tool_name,
                error=str(exc),
            )
            return "Sorry, I ran into an error while executing that request."

        _clear_pending_confidence_clarify(user_id)

        cancel_state_msg = maybe_store_calendar_cancel_state_from_tool_result(
            user_id=user_id,
            tool_name=tool_name,
            tool_result=tool_result,
        )
        if isinstance(cancel_state_msg, str) and cancel_state_msg.strip():
            return cancel_state_msg.strip()

        note_state_msg = maybe_store_calendar_note_state_from_tool_result(
            user_id=user_id,
            tool_name=tool_name,
            tool_result=tool_result,
        )
        if isinstance(note_state_msg, str) and note_state_msg.strip():
            return note_state_msg.strip()

        send_state_msg = maybe_store_gmail_send_state_from_tool_result(
            user_id=user_id,
            tool_name=tool_name,
            tool_result=tool_result,
        )
        if isinstance(send_state_msg, str) and send_state_msg.strip():
            return send_state_msg.strip()

        if isinstance(tool_result, dict):
            msg = tool_result.get("message")
            if isinstance(msg, str) and msg.strip():
                asyncio.create_task(
                    _update_memory_background(
                        user_id=user_id,
                        message=message,
                        final_text=msg.strip(),
                        request_id=request_id,
                    )
                )
                return msg.strip()
        return "Done."

    pending_dispatch = _get_pending_trello_dispatch(user_id)
    if pending_dispatch:
        if _is_cancel_text(message):
            _clear_pending_trello_dispatch(user_id)
            return "Cancelled."

        pending_tool_name = pending_dispatch.get("tool_name")
        if not isinstance(pending_tool_name, str) or not pending_tool_name.strip():
            pending_tool_name = "trello_dispatch"

        tool_args = pending_dispatch.get("tool_args")
        awaiting = pending_dispatch.get("awaiting")
        if not isinstance(tool_args, dict) or not isinstance(awaiting, str) or not awaiting.strip():
            _clear_pending_trello_dispatch(user_id)
            return "No pending Trello request found. Please start again."

        args = dict(tool_args)
        user_value = str(message or "").strip()

        if awaiting.strip() == "board_name":
            args["board_name"] = user_value
        elif awaiting.strip() == "card_name":
            args["card_name"] = user_value
        elif awaiting.strip() == "title":
            args["title"] = user_value
        elif awaiting.strip() == "list_name":
            args["list_name"] = user_value
        elif awaiting.strip() == "to_list_name":
            args["to_list_name"] = user_value
        else:
            _clear_pending_trello_dispatch(user_id)
            return "No pending Trello request found. Please start again."

        try:
            tool_result = await run_tool(pending_tool_name, args, user_id)
        except Exception as exc:  # noqa: BLE001
            _clear_pending_trello_dispatch(user_id)
            log_error(
                "pending_trello_dispatch_execution_failed",
                user_id=str(user_id),
                request_id=request_id,
                tool=str(pending_tool_name),
                error=str(exc),
            )
            return "Sorry, I ran into an error while continuing that Trello request."

        _clear_pending_trello_dispatch(user_id)

        if isinstance(tool_result, dict) and tool_result.get("status") == "dispatch_required":
            msg = tool_result.get("message")
            data = tool_result.get("data")
            if isinstance(data, dict) and isinstance(data.get("tool_args"), dict) and isinstance(data.get("awaiting"), str):
                _set_pending_trello_dispatch(
                    user_id,
                    {
                        "tool_name": pending_tool_name,
                        "tool_args": data.get("tool_args"),
                        "awaiting": data.get("awaiting"),
                        "message": str(msg or "").strip(),
                    },
                )
            if isinstance(msg, str) and msg.strip():
                return msg.strip()
            return "I need one more detail to complete that Trello request."

        if isinstance(tool_result, dict) and tool_result.get("status") == "comment_required":
            msg = tool_result.get("message")
            data = tool_result.get("data")
            if isinstance(data, dict):
                _set_pending_trello_comment(
                    user_id,
                    {
                        "tool_args": data,
                        "message": str(msg or "").strip(),
                    },
                )
            if isinstance(msg, str) and msg.strip():
                return msg.strip()
            return "What note should I add to that Trello task?"

        if isinstance(tool_result, dict):
            msg = tool_result.get("message")
            if isinstance(msg, str) and msg.strip():
                asyncio.create_task(
                    _update_memory_background(
                        user_id=user_id,
                        message=message,
                        final_text=msg.strip(),
                        request_id=request_id,
                    )
                )
                return msg.strip()
        return "Done."

    pending_comment = _get_pending_trello_comment(user_id)
    if pending_comment:
        if _is_cancel_text(message):
            _clear_pending_trello_comment(user_id)
            return "Cancelled."
        tool_args = pending_comment.get("tool_args")
        if not isinstance(tool_args, dict):
            _clear_pending_trello_comment(user_id)
            return "No pending comment found. Please start again."
        args = dict(tool_args)
        args["comment_text"] = str(message or "").strip()
        try:
            tool_result = await run_tool("trello_add_comment_task", args, user_id)
        except Exception as exc:  # noqa: BLE001
            _clear_pending_trello_comment(user_id)
            log_error(
                "pending_trello_comment_execution_failed",
                user_id=str(user_id),
                request_id=request_id,
                tool="trello_add_comment_task",
                error=str(exc),
            )
            return "Sorry, I ran into an error while adding that Trello note."

        _clear_pending_trello_comment(user_id)
        if isinstance(tool_result, dict):
            msg = tool_result.get("message")
            if isinstance(msg, str) and msg.strip():
                asyncio.create_task(
                    _update_memory_background(
                        user_id=user_id,
                        message=message,
                        final_text=msg.strip(),
                        request_id=request_id,
                    )
                )
                return msg.strip()
        return "Done."

    # Deterministic guard for destructive Gmail delete flows.
    # This enforces a strict two-phase model (DRY_RUN -> explicit confirmation -> EXECUTE)
    # and avoids LLM loops/crashes for destructive requests.
    try:
        delete_flow_reply = await handle_gmail_delete_turn(user_id, message)
    except Exception as exc:  # noqa: BLE001
        log_error(
            "gmail_delete_flow_failed",
            user_id=str(user_id),
            request_id=request_id,
            error=str(exc),
        )
        return "Error during Gmail delete handling. Nothing was changed."

    if isinstance(delete_flow_reply, str) and delete_flow_reply.strip():
        asyncio.create_task(_update_memory_background(
            user_id=user_id,
            message=message,
            final_text=delete_flow_reply.strip(),
            request_id=request_id,
        ))
        return delete_flow_reply.strip()

    # Deterministic guard for Gmail mark-as-read bulk flows.
    # This enforces a strict two-phase model (DRY_RUN -> explicit confirmation -> EXECUTE)
    # to avoid LLM re-calling tools with missing arguments on follow-up confirmations.
    try:
        mark_read_reply = await handle_gmail_mark_read_turn(user_id, message)
    except Exception as exc:  # noqa: BLE001
        log_error(
            "gmail_mark_read_flow_failed",
            user_id=str(user_id),
            request_id=request_id,
            error=str(exc),
        )
        return "Error during Gmail mark-as-read handling. Nothing was changed."

    if isinstance(mark_read_reply, str) and mark_read_reply.strip():
        asyncio.create_task(
            _update_memory_background(
                user_id=user_id,
                message=message,
                final_text=mark_read_reply.strip(),
                request_id=request_id,
            )
        )
        return mark_read_reply.strip()

    # Deterministic guard for Gmail spam cleaning.
    # Must only operate on messages (users.messages.list + users.messages.batchDelete).
    try:
        spam_clean_reply = await handle_gmail_spam_clean_turn(user_id, message)
    except Exception as exc:  # noqa: BLE001
        log_error(
            "gmail_spam_clean_flow_failed",
            user_id=str(user_id),
            request_id=request_id,
            error=str(exc),
        )
        return "Error during Gmail spam cleaning. Nothing was changed."

    if isinstance(spam_clean_reply, dict):
        if spam_clean_reply.get("status") == "completed":
            if spam_clean_reply.get("movedCount") is not None:
                moved = int(spam_clean_reply.get("movedCount") or 0)
                final_text = f"Moved {moved} spam emails to Trash."
            else:
                deleted = int(spam_clean_reply.get("deletedCount") or 0)
                final_text = f"Completed. Permanently deleted {deleted} message(s)."
            asyncio.create_task(
                _update_memory_background(
                    user_id=user_id,
                    message=message,
                    final_text=final_text,
                    request_id=request_id,
                )
            )
            return final_text

        return "Error during Gmail spam cleaning. Nothing was changed."

    if isinstance(spam_clean_reply, str) and spam_clean_reply.strip():
        asyncio.create_task(
            _update_memory_background(
                user_id=user_id,
                message=message,
                final_text=spam_clean_reply.strip(),
                request_id=request_id,
            )
        )
        return spam_clean_reply.strip()

    try:
        send_reply = await handle_gmail_send_turn(user_id, message, run_tool)
    except Exception as exc:  # noqa: BLE001
        log_error(
            "gmail_send_flow_failed",
            user_id=str(user_id),
            request_id=request_id,
            error=str(exc),
        )
        send_reply = None

    if isinstance(send_reply, str) and send_reply.strip():
        asyncio.create_task(
            _update_memory_background(
                user_id=user_id,
                message=message,
                final_text=send_reply.strip(),
                request_id=request_id,
            )
        )
        return send_reply.strip()

    try:
        note_reply = await handle_calendar_note_turn(user_id, message)
    except Exception as exc:  # noqa: BLE001
        log_error(
            "calendar_note_flow_failed",
            user_id=str(user_id),
            request_id=request_id,
            error=str(exc),
        )
        note_reply = None

    if isinstance(note_reply, str) and note_reply.strip():
        asyncio.create_task(
            _update_memory_background(
                user_id=user_id,
                message=message,
                final_text=note_reply.strip(),
                request_id=request_id,
            )
        )
        return note_reply.strip()

    # Deterministic guard for calendar cancellations.
    # This persists confirmation state across turns so the LLM doesn't loop asking
    # for the same parameters.
    try:
        cancel_reply = await handle_calendar_cancel_turn(user_id, message)
    except Exception as exc:  # noqa: BLE001
        log_error(
            "calendar_cancel_flow_failed",
            user_id=str(user_id),
            request_id=request_id,
            error=str(exc),
        )
        cancel_reply = None

    if isinstance(cancel_reply, str) and cancel_reply.strip():
        asyncio.create_task(
            _update_memory_background(
                user_id=user_id,
                message=message,
                final_text=cancel_reply.strip(),
                request_id=request_id,
            )
        )
        return cancel_reply.strip()

    try:
        ctx = await build_context(user_id, message)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to build context: %r", exc)
        log_error(
            "Failed to build context",
            user_id=str(user_id),
            request_id=request_id,
            error=str(exc),
        )
        return "Sorry, I had trouble preparing your conversation context."

    messages: List[Dict[str, Any]] = ctx["messages"]
    tool_schemas = ctx["tool_schemas"]

    log_info("Context built", user_id=str(user_id), request_id=request_id)

    max_steps = 10

    last_time_parse_start: Optional[str] = None

    msg_lower = (message or "").lower()
    looks_like_trello_comment_intent = any(
        phrase in msg_lower
        for phrase in [
            "add note",
            "add a note",
            "add comment",
            "add a comment",
            "comment on",
            "leave a comment",
        ]
    )

    def _extract_note_text(raw: str) -> Optional[str]:
        text = (raw or "").strip()
        if not text:
            return None
        if ":" in text:
            after = text.split(":", 1)[1].strip()
            if after:
                return after
        lowered = text.lower()
        for token in ["note:", "comment:"]:
            idx = lowered.find(token)
            if idx != -1:
                after = text[idx + len(token) :].strip()
                if after:
                    return after
        return None

    for _step in range(max_steps):
        log_info("Calling LLM", user_id=str(user_id), request_id=request_id)
        llm_result = await call_llm(messages, tools=tool_schemas)

        result_type = llm_result.get("type")
        if result_type == "error":
            logger.error("LLM error: %s", llm_result.get("error"))
            log_error(
                "LLM error",
                user_id=str(user_id),
                request_id=request_id,
                error=str(llm_result.get("error")),
            )
            return "Error: I couldn't complete that request. Please try again."

        if result_type == "message":
            final_text = llm_result.get("content", "")
            if not final_text:
                final_text = "I don't have a good answer for that yet."

            # Persist this turn into Supabase-backed memory and update the
            # long-term summary. Run in background for speed - don't block response.
            asyncio.create_task(_update_memory_background(
                user_id=user_id,
                message=message,
                final_text=final_text,
                request_id=request_id
            ))

            log_info("Agent finished", user_id=str(user_id), request_id=request_id)

            return final_text

        if result_type == "tool":
            tool_calls = llm_result.get("tool_calls") or []

            if not tool_calls:
                logger.warning("Tool result type without tool_calls payload")
                return "Sorry, I could not understand the tool request."

            # Handle only the first tool call for now.
            call = tool_calls[0]
            tool_id = call.get("id", "tool-call-0")
            tool_name = call.get("name", "")
            tool_args = call.get("arguments") or {}

            original_tool_name = tool_name
            original_tool_args = tool_args

            # Special-case: user intent looks like a comment, but the model chose update.
            # Force the Trello comment endpoint.
            if looks_like_trello_comment_intent and original_tool_name == "trello_update_card" and isinstance(original_tool_args, dict):
                note_text = _extract_note_text(message)
                rerouted_args: Dict[str, Any] = {}
                for k in ["card_id", "card_name", "board_id", "board_name"]:
                    if k in original_tool_args and original_tool_args.get(k) is not None:
                        rerouted_args[k] = original_tool_args.get(k)
                if note_text:
                    rerouted_args["comment_text"] = note_text
                rerouted_args["action"] = "comment"
                tool_name = "trello_dispatch"
                tool_args = rerouted_args

            # General Trello robustness: route low-level Trello tools into trello_dispatch.
            elif original_tool_name in {
                "trello_update_card",
                "trello_move_card",
                "trello_delete_task",
                "trello_archive_card",
                "trello_delete_card",
            } and isinstance(original_tool_args, dict):
                rerouted_args = {}
                if original_tool_name == "trello_update_card":
                    rerouted_args["action"] = "update"
                    rerouted_args["card_id"] = original_tool_args.get("card_id") or ""
                    rerouted_args["fields"] = original_tool_args.get("fields")
                elif original_tool_name == "trello_move_card":
                    rerouted_args["action"] = "move"
                    rerouted_args["card_id"] = original_tool_args.get("card_id") or ""
                    rerouted_args["to_list_id"] = original_tool_args.get("list_id") or ""
                    if original_tool_args.get("board_id"):
                        rerouted_args["board_id"] = original_tool_args.get("board_id")
                elif original_tool_name == "trello_archive_card":
                    rerouted_args["action"] = "archive"
                    for k in ["card_id", "card_name", "board_id", "board_name", "archive", "confirm"]:
                        if k in original_tool_args and original_tool_args.get(k) is not None:
                            rerouted_args[k] = original_tool_args.get(k)
                elif original_tool_name == "trello_delete_task":
                    rerouted_args["action"] = "delete"
                    for k in ["card_id", "card_name", "board_id", "board_name", "confirm"]:
                        if k in original_tool_args and original_tool_args.get(k) is not None:
                            rerouted_args[k] = original_tool_args.get(k)
                elif original_tool_name == "trello_delete_card":
                    rerouted_args["action"] = "delete"
                    rerouted_args["card_id"] = original_tool_args.get("card_id") or ""

                tool_name = "trello_dispatch"
                tool_args = rerouted_args

            tool_schema = None
            if isinstance(tool_schemas, list):
                for s in tool_schemas:
                    try:
                        fn = s.get("function") if isinstance(s, dict) else None
                        if isinstance(fn, dict) and fn.get("name") == tool_name:
                            tool_schema = s
                            break
                    except Exception:
                        continue

            confidence_score = 100
            if tool_name not in {"get_current_utc_time", "echo", "parse_human_time_expression"} and isinstance(tool_args, dict):
                assessment = compute_tool_confidence(tool_name=tool_name, tool_args=tool_args, tool_schema=tool_schema)
                confidence_score = assessment.score
                if (not isinstance(assessment.awaiting, str) or not assessment.awaiting.strip()) or (not isinstance(assessment.question, str) or not assessment.question.strip()):
                    confidence_score = 90

                if confidence_score < 70 and tool_name != "trello_dispatch":
                    awaiting = assessment.awaiting or ""
                    question = (assessment.question or "").strip()
                    if not awaiting or not question:
                        confidence_score = 90
                        awaiting = ""
                        question = ""
                    if confidence_score >= 90:
                        awaiting = ""
                        question = ""
                    else:
                        _set_pending_confidence_clarify(
                            user_id,
                            {
                                "tool_name": tool_name,
                                "tool_args": dict(tool_args),
                                "awaiting": awaiting,
                                "one_shot": False,
                            },
                        )
                        return question

                if 70 <= confidence_score <= 89 and tool_name != "trello_dispatch":
                    awaiting = assessment.awaiting or ""
                    question = (assessment.question or "").strip()
                    if not awaiting or not question:
                        confidence_score = 90
                        awaiting = ""
                        question = ""
                    if confidence_score >= 90:
                        awaiting = ""
                        question = ""
                    else:
                        _set_pending_confidence_clarify(
                            user_id,
                            {
                                "tool_name": tool_name,
                                "tool_args": dict(tool_args),
                                "awaiting": awaiting,
                                "one_shot": True,
                            },
                        )
                        return question

            log_info(
                "LLM requested tool",
                user_id=str(user_id),
                request_id=request_id,
                tool_name=tool_name,
            )

            try:
                tool_result = await run_tool(tool_name, tool_args, user_id=user_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("Error while running tool %s: %r", tool_name, exc)
                log_error(
                    "Tool execution failed",
                    user_id=str(user_id),
                    request_id=request_id,
                    tool=tool_name,
                    error=str(exc),
                )
                return "Sorry, I ran into an error while executing a tool for you."

            if isinstance(tool_result, dict) and tool_result.get("status") == "comment_required":
                msg = tool_result.get("message")
                data = tool_result.get("data")
                if isinstance(data, dict):
                    _set_pending_trello_comment(
                        user_id,
                        {
                            "tool_args": data,
                            "message": str(msg or "").strip(),
                        },
                    )
                if isinstance(msg, str) and msg.strip():
                    return msg.strip()
                return "What note should I add to that Trello task?"

            if isinstance(tool_result, dict) and tool_result.get("status") == "confirmation_required":
                msg = tool_result.get("message")
                data = tool_result.get("data")
                if isinstance(data, dict):
                    _set_pending_tool_confirm(
                        user_id,
                        {
                            "tool_name": tool_name,
                            "tool_args": data,
                            "message": str(msg or "").strip(),
                        },
                    )
                if isinstance(msg, str) and msg.strip():
                    return msg.strip()
                return "Please confirm by replying YES or PROCEED, or say CANCEL."

            if isinstance(tool_result, dict) and tool_result.get("success") is True:
                url = _extract_tool_url(tool_result)
                if url and tool_name in {
                    "trello_get_card_link",
                    "trello_find_card_by_name",
                    "trello_create_card",
                    "trello_create_task",
                }:
                    msg = tool_result.get("message")
                    if isinstance(msg, str) and ("https://" in msg or "http://" in msg):
                        return msg.strip()

                    card_name = None
                    data = tool_result.get("data")
                    if isinstance(data, dict) and isinstance(data.get("name"), str):
                        card_name = data.get("name")

                    if isinstance(card_name, str) and card_name.strip():
                        return f"Here is the link to '{card_name.strip()}': {url}"
                    return f"Here is the link: {url}"

            # Append the tool call and its result to the conversation per
            # OpenAI's tool-calling message format.
            messages.append(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": tool_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_args),
                            },
                        }
                    ],
                }
            )

            # Truncate large tool outputs before sending back to the LLM to
            # avoid context length issues, while still preserving the full
            # result in logs and side effects.
            raw_tool_content = json.dumps(tool_result)
            MAX_TOOL_CONTENT_CHARS = 8000
            if len(raw_tool_content) > MAX_TOOL_CONTENT_CHARS:
                raw_tool_content = raw_tool_content[:MAX_TOOL_CONTENT_CHARS] + "...[truncated]"

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": raw_tool_content,
                }
            )

            continue

        logger.warning("Unexpected LLM result type: %r", result_type)
        log_error(
            "Unexpected LLM result type",
            user_id=str(user_id),
            request_id=request_id,
            result_type=str(result_type),
        )
        return "Sorry, I received an unexpected response from my reasoning engine."

    # Infinite loop protection.
    return (
        "I got stuck while trying to complete that request. Please rephrase or "
        "break it into a smaller step and I'll try again."
    )


async def _update_memory_background(
    user_id: int,
    message: str,
    final_text: str,
    request_id: str | None = None
) -> None:
    """Update memory in background without blocking the response.
    
    Uses sequential writes with retry logic to avoid overwhelming connection pool.
    """
    try:
        user_id_str = str(user_id)

        # Sequential writes with built-in retry logic (more reliable than parallel)
        await append_message(user_id_str, "user", message)
        await append_message(user_id_str, "assistant", final_text)

        # Update long-term memory summary
        recent_for_summary = await get_recent_messages(user_id_str, limit=30)
        await update_long_term_memory(user_id_str, recent_for_summary)
    except Exception as exc:  # noqa: BLE001
        logger.error("Error updating memory in background: %r", exc)
        log_error(
            "Error updating memory in background",
            user_id=str(user_id),
            request_id=request_id,
            error=str(exc),
        )


async def process_normalized_message(normalized: Dict[str, Any]) -> None:
    """Process a normalized message, potentially transcribing voice messages."""
    logger = get_logger("jarvis.whisper")

    # Only handle voice messages in this phase.
    if normalized.get("type") != "voice":
        return

    file_id = normalized.get("file_id")
    if not file_id:
        logger.warning("[JARVIS-WHISPER] Missing file_id for voice message")
        return

    # Local imports to avoid circular import at module load time.
    from src.services.telegram import download_telegram_file
    from src.services.whisper import transcribe_audio

    try:
        audio_bytes = download_telegram_file(str(file_id))
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[JARVIS-WHISPER] Error downloading file: {exc!r}")
        return

    if not audio_bytes:
        logger.error("[JARVIS-WHISPER] No audio bytes received from Telegram")
        return

    text = transcribe_audio(audio_bytes)
    if not text:
        logger.error("[JARVIS-WHISPER] Empty transcription text")
        return

    # Mutate the normalized message to look like a text message.
    normalized["message"] = text
    normalized["type"] = "text"

    logger.info(f"[JARVIS-WHISPER] Transcription complete: {text}")

    # TODO (later phases): forward normalized text to JarvisAgent.handle_message
    # and downstream reasoning, tools, and memory.