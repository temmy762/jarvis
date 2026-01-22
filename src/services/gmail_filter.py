"""Gmail filter creation service for Jarvis AI Agent.

This module handles Gmail filter creation ONLY.
It is completely separate from bulk Gmail operations.

Filters apply ONLY to future emails, never retroactively.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from src.services.gmail import _gmail_auth_headers, _gmail_user_id
from src.services.gmail_advanced import gmail_resolve_label_id, gmail_create_label
from src.services.google_oauth import get_google_access_token

logger = logging.getLogger("jarvis.gmail_filter")


async def gmail_create_filter(
    from_sender: Optional[str] = None,
    subject_contains: Optional[str] = None,
    target_label: str = "",
) -> Dict[str, Any]:
    """Create a Gmail filter that applies to FUTURE emails only.
    
    This function creates a single Gmail filter with ONE criterion:
    - Either from_sender OR subject_contains (not both)
    
    The filter will:
    - Add the target label
    - Remove INBOX (this moves the email)
    
    Args:
        from_sender: Email address to filter by sender (e.g., "sender@example.com")
        subject_contains: Keyword to filter by subject line
        target_label: Human-readable label name to move emails to
    
    Returns:
        Dict with success status and filter details
        
    Note:
        - Filters apply ONLY to future emails
        - Does NOT affect existing emails
        - Creates label if it doesn't exist
        - Exactly ONE Gmail API call (users.settings.filters.create)
    """
    
    # Validation: exactly one criterion
    if not from_sender and not subject_contains:
        return {
            "success": False,
            "error": "MISSING_CRITERION",
            "message": "Must specify either from_sender or subject_contains"
        }
    
    if from_sender and subject_contains:
        return {
            "success": False,
            "error": "TOO_MANY_CRITERIA",
            "message": "Can only specify one criterion per filter (from_sender OR subject_contains)"
        }
    
    if not target_label:
        return {
            "success": False,
            "error": "MISSING_TARGET_LABEL",
            "message": "Must specify target_label"
        }
    
    # Auth check
    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}
    
    # Validate that token has gmail.settings.basic scope
    access_token = await get_google_access_token()
    if not access_token:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}
    
    try:
        from src.services.gmail_oauth_scopes import validate_gmail_scopes, get_reauth_instructions
        
        validation = await validate_gmail_scopes(access_token)
        
        if not validation["has_settings"]:
            logger.error(
                f"Gmail filter creation blocked: missing gmail.settings.basic scope\n"
                f"Message: {validation['message']}"
            )
            return {
                "success": False,
                "error": "MISSING_SCOPE_gmail.settings.basic",
                "message": (
                    "Gmail filter creation requires re-authorization. "
                    "Your OAuth token is missing the 'gmail.settings.basic' scope. "
                    "Email reading, sending, and labeling will continue to work, "
                    "but filter management is unavailable until you re-authorize."
                ),
                "reauth_required": True,
                "instructions": get_reauth_instructions()
            }
    except Exception as exc:
        logger.warning(f"Could not validate Gmail scopes: {exc!r}")
        # Continue anyway - let the API call fail naturally if scope is missing
    
    # Resolve or create target label
    label_result = await gmail_resolve_label_id(target_label)
    
    if not label_result.get("success"):
        # Label doesn't exist, create it
        logger.info(f"Label '{target_label}' not found, creating it")
        create_result = await gmail_create_label(target_label)
        
        if not create_result.get("success"):
            return {
                "success": False,
                "error": "LABEL_CREATION_FAILED",
                "message": f"Could not create label '{target_label}'",
                "details": create_result
            }
        
        # Get the newly created label ID
        new_label = create_result.get("data", {})
        label_id = new_label.get("id")
        
        if not label_id:
            return {
                "success": False,
                "error": "LABEL_ID_MISSING",
                "message": "Label created but ID not returned"
            }
    else:
        label_id = label_result["data"]["id"]
    
    # Build filter criteria (exactly one)
    criteria = {}
    if from_sender:
        criteria["from"] = from_sender
    elif subject_contains:
        criteria["subject"] = subject_contains
    
    # Build filter action (add label + remove INBOX = move)
    action = {
        "addLabelIds": [label_id],
        "removeLabelIds": ["INBOX"]
    }
    
    # Build complete filter payload
    filter_payload = {
        "criteria": criteria,
        "action": action
    }
    
    # Single Gmail API call to create filter
    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/settings/filters"
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=filter_payload)
        resp.raise_for_status()
    except httpx.RequestError as exc:
        return {
            "success": False,
            "error": "HTTP_ERROR",
            "message": f"Network error creating filter: {exc!r}"
        }
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"API_ERROR_{exc.response.status_code}",
            "message": "Gmail API rejected filter creation",
            "details": exc.response.text
        }
    
    filter_data = resp.json()
    
    return {
        "success": True,
        "data": filter_data,
        "message": f"Filter created successfully. It will apply to FUTURE emails only.",
        "label_name": target_label,
        "label_id": label_id,
        "criterion": "from" if from_sender else "subject",
        "criterion_value": from_sender or subject_contains
    }
