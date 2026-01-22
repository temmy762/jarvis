from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from src.core.tools import run_tool


logger = logging.getLogger("jarvis.calendar_cancel_flow")


_PENDING: Dict[str, Dict[str, Any]] = {}
_LOCK = Lock()
_FILE = Path("data") / "pending_calendar_cancel.json"


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


def _is_confirm(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if re.search(r"\b(yes|confirm|proceed)\b", t):
        return True
    if "cancel them" in t:
        return True
    return False


def _is_cancel(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in {"cancel", "stop", "no"}


async def _execute_selected_cancellations(user_id: int, state: Dict[str, Any], selected_ids: List[str]) -> str:
    selected_ids = [str(eid) for eid in (selected_ids or []) if str(eid).strip()]
    if not selected_ids:
        # Abort: we should never execute with an empty selection.
        _clear(user_id)
        return "I couldn't cancel anything because no events were selected. Please select the events again."

    # Execution lock: once selected + confirmed, execute immediately and never re-list.
    state["confirmed"] = True
    state["executing"] = True
    state["locked"] = True
    _set(user_id, state)

    cancelled = 0
    for eid in selected_ids:
        tool_args: Dict[str, Any] = {
            "event_id": eid,
            "confirm": True,
            "cancel_scope": state.get("cancel_scope"),
            "delete": bool(state.get("delete") or False),
        }
        try:
            result = await run_tool("calendar_cancel_meeting", tool_args, user_id)
        except Exception:
            continue

        if isinstance(result, dict) and result.get("cancelled") is True:
            cancelled += 1

    _clear(user_id)
    if cancelled <= 0:
        return "I couldn't cancel any of the selected events. Please try again (they may have already been cancelled or I may not have access)."
    return f"Cancelled {cancelled} event(s)."


_NUM_RE = re.compile(r"\d+")


def _parse_selection(text: str, option_count: int) -> Optional[List[int]]:
    if option_count <= 0:
        return None

    t = (text or "").strip().lower()
    if not t:
        return None

    if any(phrase in t for phrase in ["cancel all", "all events", "all of them", "cancel them all"]):
        return list(range(1, option_count + 1))

    nums = [int(m.group(0)) for m in _NUM_RE.finditer(t)]
    if not nums:
        return None

    picked: List[int] = []
    for n in nums:
        if 1 <= n <= option_count and n not in picked:
            picked.append(n)

    return picked or None


async def handle_calendar_cancel_turn(user_id: int, message: str) -> Optional[str]:
    """Deterministic 2-phase cancellation flow for calendar_cancel_meeting.

    - Stores pending cancel task state across turns.
    - Accepts yes/confirm/proceed to execute immediately.
    - Clears state after execution or cancellation.

    Returns:
      - A user-facing string to reply with (if this handler handled the turn)
      - None if the agent should continue normal LLM flow
    """

    state = _get(user_id)

    if state:
        if state.get("executing") is True:
            return None

        if _is_cancel(message):
            _clear(user_id)
            return "Okay, I won't cancel anything."

        if state.get("intent") == "cancel":
            options = state.get("options") or []
            selected_ids = list(state.get("selected_event_ids") or [])

            # If we already have a confirmed selection stored, execute immediately.
            # This prevents re-entering listing/clarification after confirmation.
            if state.get("confirmed") is True:
                locked_ids = list(state.get("selected_event_ids") or [])
                if not locked_ids:
                    _clear(user_id)
                    return "I couldn't cancel anything because the selected events were lost. Please select the events again."
                return await _execute_selected_cancellations(user_id, state, locked_ids)

            if options and not selected_ids:
                picked = _parse_selection(message, option_count=len(options))
                if picked:
                    selected: List[str] = []
                    for idx in picked:
                        try:
                            ev = options[idx - 1]
                        except Exception:
                            continue
                        if isinstance(ev, dict) and ev.get("id"):
                            selected.append(str(ev.get("id")))

                    selected = [eid for eid in selected if eid]
                    if not selected:
                        return None

                    state["selected_event_ids"] = selected
                    state["locked"] = True
                    # Persist immediately after selection so we can't lose IDs between turns.
                    _set(user_id, state)

                    high_risk = bool(state.get("delete") is True) or (state.get("cancel_scope") == "series")

                    # Decisive behavior: selecting items is sufficient authorization for
                    # normal (medium-risk) cancellations.
                    if not high_risk:
                        return await _execute_selected_cancellations(user_id, state, selected)

                    # If the user selected AND confirmed in the same message,
                    # execute immediately (single confirmation step).
                    if _is_confirm(message):
                        return await _execute_selected_cancellations(user_id, state, selected)

                    state["confirmation_asked"] = True
                    state["confirmed"] = False
                    _set(user_id, state)
                    n = len(selected)
                    return f"Confirm cancellation of {n} event(s)?"

            # Single-event confirmation state
            if state.get("event_id") and not selected_ids:
                selected_ids = [str(state.get("event_id"))]

            if selected_ids and state.get("confirmation_asked") and _is_confirm(message):
                return await _execute_selected_cancellations(user_id, state, selected_ids)

            # If the user confirms but we don't have a selection, do not execute.
            if state.get("confirmation_asked") and _is_confirm(message) and not selected_ids:
                return "Please reply with the number(s) of the event(s) you want to cancel (e.g. 1, 2 and 3), or say 'cancel all'."

        # If user replies something else while a cancel is pending, let LLM handle it.
        return None

    return None


def maybe_store_calendar_cancel_state_from_tool_result(user_id: int, tool_name: str, tool_result: Any) -> Optional[str]:
    """If a calendar cancel tool result needs user input, persist state and return its message.

    This prevents the LLM from losing context across turns.
    """

    if tool_name != "calendar_cancel_meeting":
        return None

    if not isinstance(tool_result, dict):
        return None

    msg = tool_result.get("message")
    if not isinstance(msg, str) or not msg.strip():
        msg = None

    if tool_result.get("confirmation_required"):
        existing = _get(user_id) or {}
        if existing.get("locked") is True:
            return msg
        data = tool_result.get("data") or {}
        if isinstance(data, dict):
            event_id = data.get("event_id")
            if event_id:
                _set(
                    user_id,
                    {
                        "intent": "cancel",
                        "event_id": event_id,
                        "event_date": data.get("start"),
                        "confirmed": False,
                        "confirmation_asked": True,
                        "executing": False,
                        "locked": True,
                        "options": [],
                        "selected_event_ids": [str(event_id)],
                        "cancel_scope": data.get("cancel_scope"),
                        "delete": bool(data.get("delete") or False),
                    },
                )
        return msg

    if tool_result.get("scope_required"):
        existing = _get(user_id) or {}
        if existing.get("locked") is True:
            return msg
        # Store the chosen event; next user reply should specify single vs series.
        data = tool_result.get("data") or {}
        if isinstance(data, dict):
            event_id = data.get("event_id")
            if event_id:
                _set(
                    user_id,
                    {
                        "intent": "cancel",
                        "event_id": event_id,
                        "event_date": data.get("start"),
                        "confirmed": False,
                        "confirmation_asked": False,
                        "executing": False,
                        "locked": False,
                        "options": [],
                        "selected_event_ids": [str(event_id)],
                        "cancel_scope": None,
                        "delete": False,
                    },
                )
        return msg

    if tool_result.get("selection_required"):
        existing = _get(user_id) or {}
        if existing.get("locked") is True:
            return msg
        options = tool_result.get("options") or tool_result.get("matches") or []
        if isinstance(options, list) and options:
            safe_opts: List[Dict[str, Any]] = []
            for o in options:
                if isinstance(o, dict) and o.get("id"):
                    safe_opts.append({
                        "id": str(o.get("id")),
                        "title": o.get("title") or o.get("summary") or "",
                        "start": o.get("start"),
                        "end": o.get("end"),
                    })

            if safe_opts:
                _set(
                    user_id,
                    {
                        "intent": "cancel",
                        "event_id": "",
                        "event_date": None,
                        "confirmed": False,
                        "confirmation_asked": False,
                        "executing": False,
                        "locked": False,
                        "options": safe_opts,
                        "selected_event_ids": [],
                        "cancel_scope": None,
                        "delete": False,
                    },
                )
        return msg

    return None
