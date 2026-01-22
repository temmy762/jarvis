from __future__ import annotations

import json
import re
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional


_PENDING: Dict[str, Dict[str, Any]] = {}
_LOCK = Lock()
_FILE = Path("data") / "pending_gmail_send.json"


def _load() -> None:
    try:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        if not _FILE.exists():
            return
        raw = _FILE.read_text(encoding="utf-8")
        data = json.loads(raw) if raw else {}
        if isinstance(data, dict):
            with _LOCK:
                _PENDING.clear()
                _PENDING.update(data)
    except Exception:
        return


def _save() -> None:
    try:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            _FILE.write_text(json.dumps(_PENDING, ensure_ascii=False), encoding="utf-8")
    except Exception:
        return


_loaded = False


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    _load()
    _loaded = True


def _get(user_id: int) -> Optional[Dict[str, Any]]:
    _ensure_loaded()
    with _LOCK:
        state = _PENDING.get(str(user_id))
        return dict(state) if isinstance(state, dict) else None


def _set(user_id: int, state: Dict[str, Any]) -> None:
    _ensure_loaded()
    with _LOCK:
        _PENDING[str(user_id)] = state
    _save()


def _clear(user_id: int) -> None:
    _ensure_loaded()
    with _LOCK:
        _PENDING.pop(str(user_id), None)
    _save()


def _is_confirm(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in {"yes", "confirm", "proceed"}


def _is_cancel(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in {"cancel", "stop", "no"}


_EMAIL_RE = re.compile(r"([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})", re.IGNORECASE)


async def handle_gmail_send_turn(user_id: int, message: str, run_tool: Any) -> Optional[str]:
    state = _get(user_id)
    if not state:
        return None

    if state.get("executing") is True:
        return None

    if _is_cancel(message):
        _clear(user_id)
        return "Okay, I won't send anything."

    if state.get("intent") != "send":
        return None

    if not _is_confirm(message):
        return None

    tool_name = str(state.get("tool_name") or "").strip()
    tool_args = dict(state.get("tool_args") or {})
    if not tool_name:
        _clear(user_id)
        return "I couldn't send that because the pending request was lost. Please try again."

    state["executing"] = True
    state["locked"] = True
    _set(user_id, state)

    tool_args["confirm"] = True
    result = await run_tool(tool_name, tool_args, user_id)

    _clear(user_id)

    if isinstance(result, dict) and (result.get("success") is False or result.get("error")):
        msg = result.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
        return "I couldn't send that email due to an error."

    return "Sent."


def maybe_store_gmail_send_state_from_tool_result(user_id: int, tool_name: str, tool_result: Any) -> Optional[str]:
    if tool_name not in {"gmail_send_email", "gmail_send_draft"}:
        return None

    if not isinstance(tool_result, dict):
        return None

    if not tool_result.get("confirmation_required"):
        return None

    msg = tool_result.get("message")
    if not isinstance(msg, str) or not msg.strip():
        msg = "Please confirm." 

    existing = _get(user_id) or {}
    if existing.get("locked") is True:
        return msg

    data = tool_result.get("data") or {}
    if not isinstance(data, dict):
        data = {}

    _set(
        user_id,
        {
            "intent": "send",
            "tool_name": tool_name,
            "tool_args": data,
            "executing": False,
            "locked": True,
        },
    )

    return msg.strip() if isinstance(msg, str) else None
