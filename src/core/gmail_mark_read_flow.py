from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from src.agents.bulk_intent_router import classify_bulk_intent
from src.services.gmail_bulk import (
    gmail_batch_modify_labels,
    gmail_get_message_headers,
    gmail_list_message_ids_page,
)


_PENDING: Dict[str, Dict[str, Any]] = {}
_LOCK = Lock()
_FILE = Path("data") / "pending_gmail_mark_read.json"


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
        return _PENDING.get(str(user_id))


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


_EMAIL_RE = re.compile(r"([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})", re.IGNORECASE)


def _parse_request(user_message: str) -> Optional[Dict[str, Any]]:
    text = (user_message or "").strip()
    if not text:
        return None

    lower = text.lower()

    if "mark" not in lower:
        return None
    if "read" not in lower:
        return None
    if "all" not in lower:
        return None

    m = _EMAIL_RE.search(text)
    if not m:
        return None

    sender = m.group(1)

    if "from" not in lower:
        return None

    return {"sender": sender}


def _build_query(sender: str) -> str:
    sender = (sender or "").strip()
    return f"from:{sender} is:unread"


async def _dry_run(user_id: int, sender: str) -> str:
    query = _build_query(sender)

    MAX_SCAN = 5000
    PAGE_SIZE = 500

    message_ids: List[str] = []
    page_token: Optional[str] = None
    capped = False

    while True:
        page = await gmail_list_message_ids_page(
            query=query,
            max_results=PAGE_SIZE,
            page_token=page_token,
        )
        if not page.get("success"):
            return "Error: Failed to search Gmail. Nothing was changed."

        data = page.get("data") or {}
        ids = list(data.get("message_ids") or [])
        if ids:
            remaining = MAX_SCAN - len(message_ids)
            if remaining <= 0:
                capped = True
                page_token = data.get("next_page_token")
                break
            if len(ids) > remaining:
                message_ids.extend(ids[:remaining])
                capped = True
                page_token = data.get("next_page_token")
                break
            message_ids.extend(ids)

        page_token = data.get("next_page_token")
        if not page_token:
            break

    total = len(message_ids)
    if total <= 0:
        return f"I found 0 unread messages from {sender}."

    count_text = f"at least {total}" if capped else str(total)

    desired_samples = min(5, total)
    sample_lines: List[str] = []
    sample_idx = 0

    for mid in message_ids[:50]:
        meta = await gmail_get_message_headers(message_id=mid)
        if not meta.get("success"):
            continue
        h = meta.get("data") or {}
        subj = (h.get("Subject") or "(no subject)").strip()
        frm = (h.get("From") or "(unknown sender)").strip()
        dt = (h.get("Date") or "").strip()
        sample_idx += 1
        if dt:
            sample_lines.append(f"Sample {sample_idx}: {subj} | {frm} | {dt}")
        else:
            sample_lines.append(f"Sample {sample_idx}: {subj} | {frm}")
        if len(sample_lines) >= desired_samples:
            break

    while len(sample_lines) < desired_samples:
        sample_idx += 1
        mid = message_ids[min(sample_idx - 1, len(message_ids) - 1)]
        sample_lines.append(f"Sample {sample_idx}: Message ID {mid}")

    _set(
        user_id,
        {
            "action_mode": "DRY_RUN",
            "confirm_token": uuid.uuid4().hex,
            "sender": sender,
            "query": query,
            "count_text": count_text,
            "count_is_capped": bool(capped),
            "page_token": page_token,
            "message_buffer": message_ids,
        },
    )

    lines: List[str] = []
    lines.append(f"Please confirm that you want to mark all messages from {sender} as read.")
    lines.append(f"I found {count_text} unread message(s) (query: {query}).")
    if sample_lines:
        lines.append("Sample:")
        lines.extend(sample_lines[:desired_samples])
    lines.append("Reply YES to proceed, or CANCEL.")
    return "\n".join(lines)


async def _execute(user_id: int, state: Dict[str, Any]) -> str:
    sender = state.get("sender") or ""
    query = state.get("query") or ""
    page_token = state.get("page_token")
    buffer_ids = list(state.get("message_buffer") or [])

    MAX_PER_TURN = 2000
    BATCH_SIZE = 500

    processed = 0
    errors = 0

    while processed < MAX_PER_TURN:
        if not buffer_ids and page_token is not None:
            page = await gmail_list_message_ids_page(
                query=query,
                max_results=500,
                page_token=page_token,
            )
            if not page.get("success"):
                _clear(user_id)
                return "Error: Failed to continue searching Gmail. Nothing was changed."
            data = page.get("data") or {}
            buffer_ids.extend(list(data.get("message_ids") or []))
            page_token = data.get("next_page_token")

        if not buffer_ids:
            break

        batch = buffer_ids[:BATCH_SIZE]
        buffer_ids = buffer_ids[len(batch) :]

        result = await gmail_batch_modify_labels(
            message_ids=batch,
            add_label_ids=[],
            remove_label_ids=["UNREAD"],
        )

        if not result.get("success"):
            errors += len(batch)
        processed += len(batch)

    remaining_est = len(buffer_ids)
    if page_token is not None:
        remaining_est += 1

    if remaining_est <= 0:
        _clear(user_id)
        if errors:
            return f"Done. Marked messages from {sender} as read, with {errors} item(s) that may have failed."
        return f"Done. Marked all unread messages from {sender} as read."

    state["action_mode"] = "EXECUTE"
    state["page_token"] = page_token
    state["message_buffer"] = buffer_ids
    _set(user_id, state)

    if errors:
        return (
            f"Marked {processed} message(s) from {sender} as read, but {errors} may have failed. "
            f"Reply CONTINUE to process more, or CANCEL."
        )

    return (
        f"Marked {processed} message(s) from {sender} as read. "
        f"Reply CONTINUE to process more, or CANCEL."
    )


async def handle_gmail_mark_read_turn(user_id: int, user_message: str) -> str:
    pending = _get(user_id)

    if pending:
        intent = classify_bulk_intent(user_message)
        if intent == "cancel":
            _clear(user_id)
            return "Cancelled. Nothing was changed."
        if intent == "continue":
            return await _execute(user_id, pending)
        return "Please reply YES/CONTINUE to proceed, or CANCEL."

    req = _parse_request(user_message)
    if not req:
        return ""

    return await _dry_run(user_id, req["sender"])
