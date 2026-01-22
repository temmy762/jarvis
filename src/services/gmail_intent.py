"""Gmail intent router for natural language commands.

This module detects user intent and routes to the appropriate Gmail function,
returning only clean, user-facing results with no system commentary.
"""

from typing import Any, Dict, Optional
import logging

from src.services.gmail_advanced import (
    gmail_fetch_by_keyword,
    gmail_fetch_by_sender,
    gmail_fetch_by_subject,
    gmail_fetch_by_label,
    gmail_fetch_by_date_range,
    gmail_sort_emails,
    gmail_list_labels,
    gmail_create_label,
    gmail_delete_label,
    gmail_rename_label,
    gmail_move_to_label,
    gmail_remove_label,
    gmail_forward_email,
    gmail_compose_email,
    gmail_resolve_label_id,
)
from src.services.gmail_agentic import (
    gmail_agentic_search,
    gmail_agentic_bulk_action,
)


logger = logging.getLogger("jarvis.gmail_intent")


async def execute_gmail_intent(
    action: str,
    keyword: Optional[str] = None,
    sender: Optional[str] = None,
    subject: Optional[str] = None,
    label: Optional[str] = None,
    after_date: Optional[str] = None,
    before_date: Optional[str] = None,
    message_id: Optional[str] = None,
    recipient: Optional[str] = None,
    to: Optional[str] = None,
    email_subject: Optional[str] = None,
    body: Optional[str] = None,
    label_name: Optional[str] = None,
    label_id: Optional[str] = None,
    new_label_name: Optional[str] = None,
    add_labels: Optional[list] = None,
    remove_labels: Optional[list] = None,
    limit: int = 20,
    user_id: Optional[int] = None,
    user_message: Optional[str] = None,
    confirm: bool = False,
) -> Dict[str, Any]:
    
    action = action.lower().strip()
    
    # Use agentic search for fetch operations that benefit from pagination
    if user_id is not None and action in ["fetch_by_keyword", "fetch_by_sender", "fetch_by_subject", "fetch_by_label", "fetch_by_date_range"]:
        # Build Gmail query based on action
        query_parts = []
        
        if action == "fetch_by_keyword" and keyword:
            query_parts.append(keyword)
        elif action == "fetch_by_sender" and sender:
            query_parts.append(f"from:{sender}")
        elif action == "fetch_by_subject" and subject:
            query_parts.append(f"subject:{subject}")
        elif action == "fetch_by_label" and label:
            query_parts.append(f"label:{label}")
        elif action == "fetch_by_date_range" and after_date:
            query_parts.append(f"after:{after_date}")
            if before_date:
                query_parts.append(f"before:{before_date}")
        
        if query_parts:
            query = " ".join(query_parts)
            return await gmail_agentic_search(
                user_id=user_id,
                query=query,
                max_results=limit,
                user_message=user_message or ""
            )
    
    # Handle bulk actions with confirmation
    if user_id is not None and action in ["bulk_label", "bulk_move", "bulk_delete"]:
        query_parts = []
        
        if keyword:
            query_parts.append(keyword)
        if sender:
            query_parts.append(f"from:{sender}")
        if subject:
            query_parts.append(f"subject:{subject}")
        if label:
            query_parts.append(f"label:{label}")
        if after_date:
            query_parts.append(f"after:{after_date}")
        if before_date:
            query_parts.append(f"before:{before_date}")
        
        query = " ".join(query_parts) if query_parts else ""
        
        action_params = {
            "add_labels": add_labels,
            "remove_labels": remove_labels,
            "label_name": label_name,
        }
        
        return await gmail_agentic_bulk_action(
            user_id=user_id,
            action=action,
            query=query,
            action_params=action_params,
            confirm=confirm
        )
    
    # Fallback to original implementations for non-agentic operations
    if action == "fetch_by_keyword" and keyword:
        return await gmail_fetch_by_keyword(keyword, limit)
    
    if action == "fetch_by_sender" and sender:
        return await gmail_fetch_by_sender(sender, limit)
    
    if action == "fetch_by_subject" and subject:
        return await gmail_fetch_by_subject(subject, limit)
    
    if action == "fetch_by_label" and label:
        return await gmail_fetch_by_label(label, limit)
    
    if action == "fetch_by_date_range" and after_date:
        return await gmail_fetch_by_date_range(after_date, before_date, limit)
    
    if action == "sort_emails":
        return {"success": False, "error": "SORT_REQUIRES_EMAIL_LIST"}
    
    if action == "list_labels":
        return await gmail_list_labels()
    
    if action == "create_label" and label_name:
        return await gmail_create_label(label_name)
    
    if action == "delete_label" and label_id:
        return await gmail_delete_label(label_id)
    
    if action == "rename_label" and label_id and new_label_name:
        return await gmail_rename_label(label_id, new_label_name)
    
    if action == "move_to_label" and message_id and label_name:
        # Resolve human-readable label name to label ID, then move message
        resolve_result = await gmail_resolve_label_id(label_name)
        if not resolve_result.get("success"):
            return {
                "success": False,
                "error": "LABEL_RESOLVE_FAILED",
                "details": resolve_result,
            }

        label_info = resolve_result.get("data", {})
        label_id = label_info.get("id")
        if not label_id:
            return {
                "success": False,
                "error": "LABEL_ID_MISSING_AFTER_RESOLVE",
                "details": resolve_result,
            }

        return await gmail_move_to_label(message_id, [label_id], remove_labels)

    if action == "move_to_label" and message_id and add_labels:
        # Backward-compatible path when label IDs are already provided
        return await gmail_move_to_label(message_id, add_labels, remove_labels)
    
    if action == "remove_label" and message_id and remove_labels:
        return await gmail_remove_label(message_id, remove_labels)
    
    if action == "forward_email" and message_id and recipient:
        return await gmail_forward_email(message_id, recipient)
    
    if action == "compose_email" and to and email_subject and body:
        return await gmail_compose_email(to, email_subject, body)
    
    return {"success": False, "error": "INVALID_ACTION_OR_MISSING_PARAMS"}
