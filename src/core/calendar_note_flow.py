from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from src.core.tools import run_tool


logger = logging.getLogger("jarvis.calendar_note_flow")


_PENDING: Dict[str, Dict[str, Any]] = {}
_LOCK = Lock()
_FILE = Path("data") / "pending_calendar_note.json"


def _load() -> None:
    try:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        if not _FILE.exists():
            return
        raw = _FILE.read_text(encoding="utf-8")
        if not raw.strip():
            return
        data = json.loads(raw)
        if not isinstance(data, dict):
            return
        with _LOCK:
            _PENDING.clear()
            for k, v in data.items():
                if isinstance(k, str) and isinstance(v, dict):
                    _PENDING[k] = v
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
        if not isinstance(state, dict):
            return None
        return dict(state)


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


_NUM_RE = re.compile(r"\d+")


def _is_cancel(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in {"cancel", "stop", "no"}


def _parse_selection(text: str, option_count: int) -> Optional[int]:
    if option_count <= 0:
        return None

    t = (text or "").strip().lower()
    if not t:
        return None

    nums = [int(m.group(0)) for m in _NUM_RE.finditer(t)]
    if not nums:
        return None

    n = nums[0]
    if 1 <= n <= option_count:
        return n

    return None


def _looks_like_event_selection_text(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if "pick" in t or "choose" in t or "select" in t:
        return True
    if "event" in t and any(k in t for k in ["tomorrow", "today", "at "]):
        return True
    return False


async def handle_calendar_note_turn(user_id: int, message: str) -> Optional[str]:
    state = _get(user_id)
    if not state:
        return None

    if state.get("executing") is True:
        return None

    if _is_cancel(message):
        _clear(user_id)
        return "Okay, I won't add any note."

    if state.get("intent") != "note":
        return None

    options = state.get("options") or []
    if options and not state.get("event_id"):
        picked = _parse_selection(message, option_count=len(options))
        if picked is None:
            return "Please reply with the number of the event you want to add a note to."

        try:
            ev = options[picked - 1]
        except Exception:
            return "Please reply with the number of the event you want to add a note to."

        if not isinstance(ev, dict) or not ev.get("id"):
            return "Please reply with the number of the event you want to add a note to."

        state["event_id"] = str(ev.get("id"))
        state["options"] = []
        _set(user_id, state)

        if state.get("note"):
            state["executing"] = True
            _set(user_id, state)
            result = await run_tool(
                "calendar_add_note_to_meeting",
                {"event_id": state.get("event_id"), "note": state.get("note")},
                user_id,
            )
            _clear(user_id)
            if isinstance(result, dict):
                msg = result.get("message")
                if isinstance(msg, str) and msg.strip():
                    return msg.strip()
            return "Note added to the meeting."

        return "What note should I add to the meeting?"

    if not state.get("event_id"):
        return None

    if _looks_like_event_selection_text(message):
        return "Please send the note text you want to add to the meeting."

    note = (message or "").strip()
    if not note:
        return "Please send the note text you want to add to the meeting."

    state["note"] = note
    state["executing"] = True
    _set(user_id, state)

    result = await run_tool(
        "calendar_add_note_to_meeting",
        {"event_id": state.get("event_id"), "note": note},
        user_id,
    )
    _clear(user_id)

    if isinstance(result, dict):
        msg = result.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()

    return "Note added to the meeting."


def maybe_store_calendar_note_state_from_tool_result(
    user_id: int, tool_name: str, tool_result: Any
) -> Optional[str]:
    if tool_name != "calendar_add_note_to_meeting":
        return None

    if not isinstance(tool_result, dict):
        return None

    msg = tool_result.get("message")
    if not isinstance(msg, str) or not msg.strip():
        msg = None

    if tool_result.get("selection_required"):
        existing = _get(user_id) or {}
        if existing.get("locked") is True:
            return msg

        options = tool_result.get("options") or []
        note = None
        data = tool_result.get("data")
        if isinstance(data, dict) and isinstance(data.get("note"), str):
            note = data.get("note")

        safe_opts: List[Dict[str, Any]] = []
        for o in options:
            if isinstance(o, dict) and o.get("id"):
                safe_opts.append(
                    {
                        "id": str(o.get("id")),
                        "title": o.get("title") or o.get("summary") or "",
                        "start": o.get("start"),
                        "end": o.get("end"),
                    }
                )

        if safe_opts:
            _set(
                user_id,
                {
                    "intent": "note",
                    "event_id": "",
                    "options": safe_opts,
                    "note": (note or "").strip() or None,
                    "executing": False,
                    "locked": False,
                },
            )
        return msg

    if tool_result.get("note_required"):
        existing = _get(user_id) or {}
        if existing.get("locked") is True:
            return msg

        data = tool_result.get("data") or {}
        event_id = data.get("event_id") if isinstance(data, dict) else None
        if event_id:
            _set(
                user_id,
                {
                    "intent": "note",
                    "event_id": str(event_id),
                    "options": [],
                    "note": None,
                    "executing": False,
                    "locked": True,
                },
            )
        return msg

    return None
