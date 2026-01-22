from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from src.services.gmail_bulk import (
    gmail_batch_delete_messages,
    gmail_batch_modify_labels,
    gmail_get_message_headers,
    gmail_list_message_ids_page,
)


logger = logging.getLogger("jarvis.gmail_delete_flow")


_PENDING_GMAIL_DELETE: Dict[str, Dict[str, Any]] = {}
_PENDING_LOCK = Lock()
_PENDING_FILE = Path("data") / "pending_gmail_delete.json"


def _load_pending_from_disk() -> None:
    try:
        _PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not _PENDING_FILE.exists():
            return
        raw = _PENDING_FILE.read_text(encoding="utf-8")
        if not raw.strip():
            return
        data = json.loads(raw)
        if not isinstance(data, dict):
            return
        _PENDING_GMAIL_DELETE.clear()
        for k, v in data.items():
            if isinstance(k, str) and isinstance(v, dict):
                _PENDING_GMAIL_DELETE[k] = v
    except Exception:
        return


def _save_pending_to_disk() -> None:
    try:
        _PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PENDING_FILE.write_text(json.dumps(_PENDING_GMAIL_DELETE), encoding="utf-8")
    except Exception:
        return


with _PENDING_LOCK:
    _load_pending_from_disk()


def _get_pending(uid: str) -> Optional[Dict[str, Any]]:
    with _PENDING_LOCK:
        pending = _PENDING_GMAIL_DELETE.get(uid)
        if not isinstance(pending, dict):
            return None
        return dict(pending)


def _set_pending(uid: str, pending: Dict[str, Any]) -> None:
    with _PENDING_LOCK:
        _PENDING_GMAIL_DELETE[uid] = pending
        _save_pending_to_disk()


def _clear_pending(uid: str) -> None:
    with _PENDING_LOCK:
        _PENDING_GMAIL_DELETE.pop(uid, None)
        _save_pending_to_disk()


def _is_confirm(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in {"yes", "proceed"}


def _is_continue(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in {"continue", "yes", "proceed"}


def _is_cancel(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in {"cancel", "stop", "no"}


def _parse_delete_request(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    t = text.strip()
    lowered = t.lower()

    if not any(w in lowered for w in ["delete", "remove", "purge", "trash"]):
        return None

    m = re.search(r"older\s+than\s+(\d+)\s+days", lowered)
    if not m:
        m = re.search(r"older\s+than\s+(\d+)\s+day", lowered)
    if not m:
        m = re.search(r"(\d+)\s+days\s+old", lowered)

    if not m:
        return None

    days_raw = m.group(1)
    try:
        days = int(days_raw)
    except Exception:
        return {"error": "INVALID_DAYS"}

    if days <= 0:
        return {"error": "INVALID_DAYS"}

    permanent = "permanent" in lowered or "permanently" in lowered

    sender = None
    sm = re.search(r"\bfrom\s+([^\s]+@[^\s]+)", t, flags=re.IGNORECASE)
    if sm:
        sender = sm.group(1).strip()

    subject = None
    subj_m = re.search(r"\bsubject\s*[:=]\s*([^\n]+)$", t, flags=re.IGNORECASE)
    if subj_m:
        subject = subj_m.group(1).strip().strip('"').strip("'")

    label = None
    label_m = re.search(r"\blabel\s*[:=]\s*([^\n]+)$", t, flags=re.IGNORECASE)
    if label_m:
        label = label_m.group(1).strip().strip('"').strip("'")

    return {
        "days": days,
        "sender": sender,
        "subject": subject,
        "label": label,
        "permanent": permanent,
    }


def _quote_if_needed(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if " " in v and not (v.startswith('"') and v.endswith('"')):
        return f'"{v}"'
    return v


def _build_query(req: Dict[str, Any]) -> str:
    days = int(req["days"])
    parts: List[str] = [f"older_than:{days}d"]

    sender = req.get("sender")
    if sender:
        parts.append(f"from:{sender}")

    subject = req.get("subject")
    if subject:
        parts.append(f"subject:{_quote_if_needed(str(subject))}")

    label = req.get("label")
    if label:
        parts.append(f"label:{_quote_if_needed(str(label))}")

    return " ".join([p for p in parts if p])


async def _dry_run(user_id: int, req: Dict[str, Any]) -> str:
    query = _build_query(req)

    logger.info("Gmail delete DRY_RUN query=%s", query)

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
            return _format_phase_error(
                phase="DRY_RUN",
                processed=0,
                message=f"Failed to search Gmail. {page.get('error') or 'Unknown error'}",
            )

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
        return f"I found 0 emails older than {int(req['days'])} days (query: {query})."

    count_text = f"at least {total}" if capped else str(total)

    desired_samples = min(5, total)
    sample_lines: List[str] = []
    sample_idx = 0
    # Try to fetch up to 5 real samples; never show only 1 sample when total > 1.
    # We attempt more IDs to compensate for occasional metadata fetch failures.
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

    # Fallback samples if metadata fetch failed; ensure we don't show only 1 sample
    # when total > 1.
    while len(sample_lines) < desired_samples:
        sample_idx += 1
        mid = message_ids[min(sample_idx - 1, len(message_ids) - 1)]
        sample_lines.append(f"Sample {sample_idx}: Message ID {mid}")

    uid = str(user_id)
    _set_pending(
        uid,
        {
            "action_mode": "DRY_RUN",
            "confirm_token": uuid.uuid4().hex,
            "query": query,
            "days": int(req["days"]),
            "permanent": bool(req.get("permanent")),
            "total_estimated": int(total),
            "count_text": count_text,
            "count_is_capped": bool(capped),
            "lastQuery": query,
            "lastCount": count_text,
            "lastMessageIds": message_ids,
            "actionMode": "DRY_RUN",
            "processed_total": 0,
            "page_token": page_token,
            "message_buffer": message_ids,
        },
    )

    lines: List[str] = []
    lines.append(
        f"I found {count_text} emails older than {int(req['days'])} days (query: {query}). Say YES to move them to Trash, or CANCEL."
    )
    if sample_lines:
        lines.append("Sample:")
        lines.extend(sample_lines[:desired_samples])

    return "\n".join(lines)


def _format_phase_error(*, phase: str, processed: int, message: str) -> str:
    msg = (message or "").strip()
    if not msg:
        msg = "Unknown error"
    return (
        f"Error during {phase}.\n"
        f"Processed: {processed}\n"
        f"Details: {msg}\n"
        f"Nothing else was changed."
    )


async def _execute(user_id: int, *, allow_continue: bool) -> str:
    uid = str(user_id)
    pending = _get_pending(uid)
    if not pending:
        return "No pending delete request found. Please start again."

    if pending.get("action_mode") not in {"DRY_RUN", "EXECUTE"}:
        _clear_pending(uid)
        return "No pending delete request found. Please start again."

    confirm_token = pending.get("confirm_token")
    if not isinstance(confirm_token, str) or not confirm_token.strip():
        _clear_pending(uid)
        return "No pending delete request found. Please start again."

    if pending.get("action_mode") == "DRY_RUN" and not allow_continue:
        return "Please confirm by replying YES or PROCEED, or say CANCEL."

    total_estimated = int(pending.get("total_estimated") or 0)
    if total_estimated <= 0:
        _clear_pending(uid)
        return "I found 0 emails to process."

    processed_total = int(pending.get("processed_total") or 0)

    pending["action_mode"] = "EXECUTE"

    query = str(pending.get("query") or "")
    if not query:
        _clear_pending(uid)
        return "No pending delete request found. Please start again."

    permanent = bool(pending.get("permanent"))
    page_token = pending.get("page_token")
    message_buffer: List[str] = list(pending.get("message_buffer") or [])

    processed_this_turn = 0
    max_per_turn = 1000
    batch_size = 500

    try:
        while processed_this_turn < max_per_turn:
            if not message_buffer:
                if page_token is None:
                    break

                page = await gmail_list_message_ids_page(
                    query=query,
                    max_results=batch_size,
                    page_token=page_token,
                )
                if not page.get("success"):
                    _clear_pending(uid)
                    return _format_phase_error(
                        phase="EXECUTE",
                        processed=processed_total,
                        message=f"Failed to list Gmail messages. {page.get('error') or 'Unknown error'}",
                    )

                pdata = page.get("data") or {}
                page_token = pdata.get("next_page_token")
                message_buffer = list(pdata.get("message_ids") or [])

                if not message_buffer:
                    break

            batch_ids = message_buffer[:batch_size]
            message_buffer = message_buffer[len(batch_ids) :]

            if not batch_ids:
                break

            if permanent:
                op = await gmail_batch_delete_messages(message_ids=batch_ids)
            else:
                op = await gmail_batch_modify_labels(
                    message_ids=batch_ids,
                    add_label_ids=["TRASH"],
                    remove_label_ids=["INBOX"],
                )

            if not op.get("success"):
                _clear_pending(uid)
                return _format_phase_error(
                    phase="EXECUTE",
                    processed=processed_total,
                    message=f"Batch failed. {op.get('error') or 'Unknown error'}",
                )

            processed_total += len(batch_ids)
            processed_this_turn += len(batch_ids)

            if processed_total >= total_estimated and page_token is None and not message_buffer:
                break

            if processed_this_turn >= max_per_turn:
                break

        pending["processed_total"] = processed_total
        pending["page_token"] = page_token
        pending["message_buffer"] = message_buffer

        remaining_est = max(total_estimated - processed_total, 0)

        if remaining_est <= 0 or (page_token is None and not message_buffer):
            _clear_pending(uid)
            if permanent:
                return f"Done. Permanently deleted {processed_total} emails."
            return f"Done. Moved {processed_total} emails to Trash."

        pending["processed_total"] = processed_total
        pending["page_token"] = page_token
        pending["message_buffer"] = message_buffer
        _set_pending(uid, pending)

        if permanent:
            base = f"Processed {processed_total} of about {total_estimated}. Permanently deleted so far: {processed_total}."
        else:
            base = f"Processed {processed_total} of about {total_estimated}. Moved to Trash so far: {processed_total}."

        return base + "\nSay CONTINUE to keep going, or say CANCEL."

    except Exception as exc:
        _clear_pending(uid)
        return _format_phase_error(
            phase="EXECUTE",
            processed=processed_total,
            message=str(exc),
        )


async def handle_gmail_delete_turn(user_id: int, text: str) -> Optional[str]:
    uid = str(user_id)
    pending = _get_pending(uid)

    if pending:
        if _is_cancel(text):
            _clear_pending(uid)
            return "Cancelled."

        if pending.get("action_mode") == "DRY_RUN":
            if _is_confirm(text):
                return await _execute(user_id, allow_continue=True)
            return "Please confirm by replying YES or PROCEED, or say CANCEL."

        if pending.get("action_mode") == "EXECUTE":
            if _is_continue(text):
                return await _execute(user_id, allow_continue=True)
            if _is_cancel(text):
                _clear_pending(uid)
                return "Cancelled."
            _clear_pending(uid)
            return "Confirmation not received. Cancelled."

        _clear_pending(uid)
        return "No pending delete request found. Please start again."

    req = _parse_delete_request(text)
    if req is None:
        return None

    if req.get("error") == "INVALID_DAYS":
        return "Please provide a valid number of days, like: delete emails older than 30 days."

    return await _dry_run(user_id, req)
