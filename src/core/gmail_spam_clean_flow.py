from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from src.agents.bulk_intent_router import classify_bulk_intent
from src.services.gmail_bulk import (
    gmail_batch_delete_messages,
    gmail_batch_modify_labels,
    gmail_list_message_ids_page,
)


_PENDING: Dict[str, Dict[str, Any]] = {}
_LOCK = Lock()
_FILE = Path("data") / "pending_gmail_spam_clean.json"


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


def _is_spam_clean_request(user_message: str) -> bool:
    text = (user_message or "").strip().lower()
    if not text:
        return False

    if "spam" not in text:
        return False

    patterns = [
        r"\bclean\b.*\bspam\b",
        r"\bdelete\b.*\bspam\b",
        r"\bempty\b.*\bspam\b",
        r"\bclear\b.*\bspam\b",
        r"\bempty spam\b",
        r"\bclean spam\b",
        r"\bdelete spam\b",
    ]

    for p in patterns:
        if re.search(p, text):
            return True

    return False


def _is_spam_permanent_delete_request(user_message: str) -> bool:
    text = (user_message or "").strip().lower()
    if not text:
        return False

    if "spam" not in text:
        return False

    if "delete" not in text:
        return False

    return "permanent" in text


async def _dry_run(user_id: int, *, action: str) -> str:
    if action == "permanent_delete":
        query = "in:trash"
    else:
        query = "in:spam"

    first_page = await gmail_list_message_ids_page(query=query, max_results=500, page_token=None)
    if not first_page.get("success"):
        return "Error: Failed to search Gmail. Nothing was changed."

    data = first_page.get("data") or {}
    message_ids = list(data.get("message_ids") or [])
    page_token = data.get("next_page_token")
    estimate = data.get("result_size_estimate")

    total = int(estimate) if estimate is not None else len(message_ids)
    if total <= 0:
        _clear(user_id)
        if action == "permanent_delete":
            return "Your trash folder is already empty."
        return "Your spam folder is already empty."

    count_text = str(total)

    _set(
        user_id,
        {
            "actionMode": "AWAIT_CONFIRMATION",
            "confirmationRequired": True,
            "confirm_token": uuid.uuid4().hex,
            "action": action,
            "query": query,
            "count_text": count_text,
            "pageToken": page_token,
            "pendingMessageIds": message_ids,
        },
    )

    if action == "permanent_delete":
        return (
            f"I found {count_text} message(s) in Trash (query: {query}).\n"
            f"This will permanently delete messages from Trash.\n"
            f"Reply YES to confirm, or CANCEL."
        )

    return (
        f"I found {count_text} spam message(s) (query: {query}).\n"
        f"This will move spam messages to Trash.\n"
        f"Reply YES to confirm, or CANCEL."
    )


async def _execute(user_id: int, state: Dict[str, Any]) -> Any:
    action = state.get("action") or "move_to_trash"
    query = state.get("query") or "in:spam"
    page_token = state.get("pageToken")
    if page_token is None:
        page_token = state.get("page_token")

    buffer_ids = state.get("pendingMessageIds")
    if buffer_ids is None:
        buffer_ids = state.get("message_buffer")
    buffer_ids = list(buffer_ids or [])

    moved_total = 0
    deleted_total = 0
    BATCH_SIZE = 500

    while True:
        if not buffer_ids:
            if page_token is None:
                break
            page = await gmail_list_message_ids_page(query=query, max_results=500, page_token=page_token)
            if not page.get("success"):
                _clear(user_id)
                return "Error: Failed to search Gmail. Nothing was changed."
            data = page.get("data") or {}
            buffer_ids = list(data.get("message_ids") or [])
            page_token = data.get("next_page_token")
            if not buffer_ids:
                continue

        batch = buffer_ids[:BATCH_SIZE]
        buffer_ids = buffer_ids[len(batch) :]

        if action == "permanent_delete":
            result = await gmail_batch_delete_messages(message_ids=batch)
            if not result.get("success"):
                _clear(user_id)
                return "Error: Failed to permanently delete messages. Nothing was changed."
            deleted_total += len(batch)
        else:
            result = await gmail_batch_modify_labels(
                message_ids=batch,
                add_label_ids=["TRASH"],
                remove_label_ids=["SPAM"],
            )
            if result.get("success"):
                moved_total += len(batch)
            else:
                # Gmail batchModify does not provide per-message status.
                # On failure, retry each message individually up to 3 times.
                for mid in batch:
                    success = False
                    for _attempt in range(3):
                        r1 = await gmail_batch_modify_labels(
                            message_ids=[mid],
                            add_label_ids=["TRASH"],
                            remove_label_ids=["SPAM"],
                        )
                        if r1.get("success"):
                            moved_total += 1
                            success = True
                            break

                        status_code = r1.get("status_code")
                        if status_code == 403:
                            # Skip locked/protected messages
                            break

                    _ = success

    _clear(user_id)
    if action == "permanent_delete":
        return {"status": "completed", "deletedCount": deleted_total}
    return {"status": "completed", "movedCount": moved_total}


async def handle_gmail_spam_clean_turn(user_id: int, user_message: str) -> Any:
    pending = _get(user_id)

    if pending:
        intent = classify_bulk_intent(user_message)
        if intent == "cancel":
            _clear(user_id)
            return "Cancelled. Nothing was changed."
        if intent == "continue":
            return await _execute(user_id, pending)
        return "Please reply YES to confirm, or CANCEL."

    if not _is_spam_clean_request(user_message):
        if not _is_spam_permanent_delete_request(user_message):
            return ""

    action = "move_to_trash"
    if _is_spam_permanent_delete_request(user_message):
        action = "permanent_delete"

    return await _dry_run(user_id, action=action)
