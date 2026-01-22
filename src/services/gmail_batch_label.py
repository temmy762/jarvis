"""Gmail batch label operations for multiple emails matching a query."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.services.gmail_advanced import gmail_resolve_label_id
from src.services.gmail_bulk import gmail_batch_modify_labels, gmail_list_message_ids_page

logger = logging.getLogger("jarvis.gmail_batch")


def _resolve_label_ids_sync(labels: Optional[List[str]]) -> List[str]:
    # Kept for type symmetry; actual resolution is async via gmail_resolve_label_id.
    return [l for l in (labels or []) if isinstance(l, str) and l.strip()]


async def _resolve_label_ids(labels: Optional[List[str]]) -> Dict[str, Any]:
    """Resolve label names/ids into Gmail label IDs (and system labels)."""

    resolved: List[str] = []
    for label in _resolve_label_ids_sync(labels):
        name = label.strip()
        upper = name.upper()
        if upper in {"INBOX", "UNREAD", "STARRED", "IMPORTANT", "SENT", "DRAFT", "SPAM", "TRASH"}:
            resolved.append(upper)
            continue
        if name.startswith("Label_"):
            resolved.append(name)
            continue

        resolve_result = await gmail_resolve_label_id(name)
        if not resolve_result.get("success"):
            return {"success": False, "error": f"LABEL_NOT_FOUND: {name}", "details": resolve_result}

        label_id = (resolve_result.get("data") or {}).get("id")
        if not isinstance(label_id, str) or not label_id.strip():
            return {"success": False, "error": f"LABEL_ID_MISSING: {name}", "details": resolve_result}

        resolved.append(label_id.strip())

    return {"success": True, "data": resolved}


async def gmail_batch_label(
    query: str,
    labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
    max_results: int = 50,
) -> Dict[str, Any]:
    """Apply labels to multiple emails matching a search query.
    
    Args:
        query: Gmail search query (e.g., "from:sender@example.com", "subject:meeting")
        labels: Optional list of label names to add to matching emails
        remove_labels: Optional list of label names to remove from matching emails
        max_results: Maximum number of emails to process (default 50, max 100)
    
    Returns:
        Dict with success status, count of processed emails, and any errors
    """
    if max_results > 100:
        max_results = 100
    
    if not labels and not remove_labels:
        return {
            "success": False,
            "error": "Must specify at least one of 'labels' or 'remove_labels'"
        }
    
    # Fetch exactly one page of message IDs (fast; no per-message reads).
    list_result = await gmail_list_message_ids_page(query=query, max_results=max_results, page_token=None)
    
    if not list_result.get("success"):
        return {
            "success": False,
            "error": "SEARCH_FAILED",
            "details": list_result
        }
    
    data = list_result.get("data") or {}
    message_ids = data.get("message_ids") if isinstance(data, dict) else None
    if not isinstance(message_ids, list):
        message_ids = []
    
    if not message_ids:
        return {
            "success": True,
            "message": f"No emails found matching query: {query}",
            "processed": 0,
            "total": 0
        }

    add_res = await _resolve_label_ids(labels)
    if not add_res.get("success"):
        return add_res
    remove_res = await _resolve_label_ids(remove_labels)
    if not remove_res.get("success"):
        return remove_res

    add_label_ids: List[str] = add_res.get("data") or []
    remove_label_ids: List[str] = remove_res.get("data") or []

    op = await gmail_batch_modify_labels(
        message_ids=[str(mid) for mid in message_ids if isinstance(mid, str) and mid.strip()],
        add_label_ids=add_label_ids,
        remove_label_ids=remove_label_ids,
    )

    if not op.get("success"):
        logger.error("gmail_batch_label batchModify failed: %s", op.get("error"))
        return {"success": False, "error": "BATCH_MODIFY_FAILED", "details": op}

    processed = int((op.get("data") or {}).get("modified") or 0)
    total = len(message_ids)

    # Choose a user-friendly message.
    if "INBOX" in set(remove_label_ids) and labels and len(labels) == 1:
        msg = f"Moved {processed} email(s) to label '{labels[0]}'."
    elif labels and not remove_labels:
        msg = f"Added label(s) to {processed} email(s)."
    elif remove_labels and not labels:
        msg = f"Removed label(s) from {processed} email(s)."
    else:
        msg = f"Updated labels for {processed} email(s)."

    return {"success": True, "message": msg, "processed": processed, "total": total}
