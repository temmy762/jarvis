"""
Gmail Agentic Service

This module provides intelligent Gmail fetching with pagination, session management,
and user interaction handling for large mailboxes.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
import asyncio
from datetime import datetime

from .gmail_bulk import (
    gmail_list_message_ids_page,
    gmail_get_message_metadata_batch,
    gmail_batch_modify_labels,
    gmail_batch_delete_messages,
)
from .gmail_advanced import gmail_get_message, gmail_resolve_label_id
from .gmail_session import (
    gmail_session_manager, 
    GmailSearchSession, 
    GmailEmailMetadata,
    format_email_list,
    parse_open_email_command,
    is_continue_command,
    DEFAULT_CHUNK_PAGES
)

logger = logging.getLogger("jarvis.gmail_agentic")

async def gmail_agentic_search(
    user_id: int,
    query: str = "",
    max_results: Optional[int] = None,
    user_message: str = ""
) -> Dict[str, Any]:
    """
    Main entry point for agentic Gmail search with pagination.
    
    Args:
        user_id: User identifier for session management
        query: Gmail search query (empty for inbox)
        max_results: Optional limit on total results
        user_message: The original user message for intent parsing
    
    Returns:
        Dict with response, session info, and action suggestions
    """
    
    # Check if this is a continuation or open email command
    session = gmail_session_manager.get_session(user_id)
    
    # Parse special commands
    open_index = parse_open_email_command(user_message) if user_message else None
    is_continue = is_continue_command(user_message) if user_message else False

    if open_index and not session:
        return {
            "response": "No active email list yet. Please run a search first, then use 'open email #N'.",
            "error": True,
        }

    if is_continue and not session:
        return {
            "response": "No active email list yet. Please run a search first, then reply 'continue' to see more.",
            "error": True,
        }
    
    # Handle "open email #N" command
    if open_index and session:
        return await handle_open_email(user_id, session, open_index)
    
    # Handle "continue" command
    if is_continue and session:
        return await handle_continue_pagination(user_id, session)
    
    # Start new search
    return await start_new_search(user_id, query, max_results)

async def start_new_search(
    user_id: int, 
    query: str, 
    max_results: Optional[int]
) -> Dict[str, Any]:
    """Start a new Gmail search with pagination"""
    
    # Create new session
    session = gmail_session_manager.create_session(user_id, query)
    
    try:
        # Fetch first chunk
        result = await fetch_email_chunk(session, pages=DEFAULT_CHUNK_PAGES)
        
        if result["error"]:
            return result
        
        # Update session
        gmail_session_manager.update_session(session)
        
        # Format response
        metadata_list = result["metadata_list"]
        session.displayed_indices = [email.index for email in metadata_list]
        
        response_text = format_email_list(metadata_list, show_continue=result["has_more"])
        
        if result["total_found"] == 0:
            response_text = f"No emails found matching query: '{query}'"
        elif result["has_more"]:
            end_idx = metadata_list[-1].index if metadata_list else 0
            response_text = (
                f"Found about {result['total_found']} emails. "
                f"Showing {len(metadata_list)} (1-{end_idx}):\n\n{response_text}"
            )
        else:
            end_idx = metadata_list[-1].index if metadata_list else 0
            response_text = f"Found {result['total_found']} emails (1-{end_idx}):\n\n{response_text}"
        
        return {
            "response": response_text,
            "session_id": user_id,
            "total_found": result["total_found"],
            "displayed_count": len(metadata_list),
            "has_more": result["has_more"],
            "action": "search_results"
        }
        
    except Exception as e:
        logger.error(f"Error in Gmail agentic search: {e}")
        return {
            "response": f"Error searching emails: {str(e)}",
            "error": True
        }

async def handle_continue_pagination(
    user_id: int, 
    session: GmailSearchSession
) -> Dict[str, Any]:
    """Handle user request to continue pagination"""
    
    if not session.next_page_token:
        return {
            "response": "No more emails to show.",
            "action": "no_more_results"
        }
    
    try:
        # Fetch next chunk
        result = await fetch_email_chunk(session, pages=DEFAULT_CHUNK_PAGES)
        
        if result["error"]:
            return result
        
        # Update session
        gmail_session_manager.update_session(session)
        
        # Format response
        metadata_list = result["metadata_list"]
        session.displayed_indices.extend([email.index for email in metadata_list])
        
        response_text = format_email_list(metadata_list, show_continue=result["has_more"])
        
        if result["has_more"]:
            start_idx = metadata_list[0].index if metadata_list else 0
            end_idx = metadata_list[-1].index if metadata_list else 0
            response_text = f"Showing {len(metadata_list)} more emails ({start_idx}-{end_idx}):\n\n{response_text}"
        else:
            start_idx = metadata_list[0].index if metadata_list else 0
            end_idx = metadata_list[-1].index if metadata_list else 0
            response_text = f"Showing final {len(metadata_list)} emails ({start_idx}-{end_idx}):\n\n{response_text}"
        
        return {
            "response": response_text,
            "session_id": user_id,
            "total_found": session.total_fetched,
            "displayed_count": len(session.displayed_indices),
            "has_more": result["has_more"],
            "action": "continue_results"
        }
        
    except Exception as e:
        logger.error(f"Error in continue pagination: {e}")
        return {
            "response": f"Error fetching more emails: {str(e)}",
            "error": True
        }

async def handle_open_email(
    user_id: int, 
    session: GmailSearchSession, 
    email_index: int
) -> Dict[str, Any]:
    """Handle user request to open a specific email"""
    
    # Get message ID from index
    message_id = session.get_message_id_by_index(email_index)
    if not message_id:
        if email_index > len(session.message_ids) and session.next_page_token:
            return {
                "response": (
                    f"Email #{email_index} hasn't been loaded yet. "
                    "Reply 'continue' to load more emails, then try again."
                ),
                "error": True,
            }
        return {
            "response": f"Email #{email_index} not found. Please choose from the displayed emails.",
            "error": True
        }
    
    try:
        # Fetch full email
        email_data = await gmail_get_message(message_id)
        
        if email_data.get("error"):
            return {
                "response": f"Error fetching email: {email_data.get('error', 'Unknown error')}",
                "error": True
            }
        
        # Format full email
        subject = email_data.get("subject", "No Subject")
        from_email = email_data.get("from", "Unknown")
        date = email_data.get("date", "Unknown")
        body = email_data.get("body", "No content")
        labels = email_data.get("labels", [])
        
        response = f"Email #{email_index}: {subject}\n"
        response += f"From: {from_email}\n"
        response += f"Date: {date}\n"
        if labels:
            response += f"Labels: {', '.join(labels)}\n"
        response += f"\n{body}\n\n"
        response += "You can continue browsing with 'continue' or open another email."
        
        # Update session activity
        gmail_session_manager.update_session(session)
        
        return {
            "response": response,
            "session_id": user_id,
            "email_index": email_index,
            "action": "open_email"
        }
        
    except Exception as e:
        logger.error(f"Error opening email #{email_index}: {e}")
        return {
            "response": f"Error opening email: {str(e)}",
            "error": True
        }

async def fetch_email_chunk(
    session: GmailSearchSession, 
    pages: int = 1
) -> Dict[str, Any]:
    """
    Fetch a chunk of emails using pagination.
    
    Args:
        session: Current search session
        pages: Number of pages to fetch (default 1)
    
    Returns:
        Dict with metadata_list, total_found, has_more, error
    """
    
    try:
        all_message_ids = []
        all_metadata = []
        next_token = session.current_page_token
        total_estimated = None
        
        # Fetch multiple pages
        for page in range(pages):
            if next_token is None and page > 0:
                break  # No more pages
            
            # Get message IDs for this page
            page_result = await gmail_list_message_ids_page(
                query=session.query,
                page_token=next_token,
                max_results=50  # Gmail API max per page
            )
            
            if not page_result.get("success"):
                return {"error": page_result.get("error", "Unknown error"), "metadata_list": []}
            
            data = page_result.get("data", {})
            message_ids = data.get("message_ids", [])
            if not message_ids:
                break
            
            all_message_ids.extend(message_ids)
            
            # Get metadata for these messages
            metadata_batch = await gmail_get_message_metadata_batch(message_ids=message_ids)
            
            # Convert to GmailEmailMetadata objects
            for msg_id, metadata in zip(message_ids, metadata_batch):
                if not metadata.get("error"):
                    email_meta = GmailEmailMetadata(
                        id=msg_id,
                        thread_id=metadata.get("thread_id", ""),
                        subject=metadata.get("subject", "No Subject"),
                        from_email=metadata.get("from", "Unknown"),
                        date=metadata.get("date", "Unknown"),
                        snippet=metadata.get("snippet", ""),
                        labels=metadata.get("labels", [])
                    )
                    all_metadata.append(email_meta)
            
            # Update pagination tokens
            next_token = data.get("next_page_token")
            if total_estimated is None:
                total_estimated = data.get("result_size_estimate", len(message_ids))
            
            # If this is the last page, break
            if not next_token:
                break
        
        # Update session state
        session.current_page_token = next_token
        session.add_emails(all_message_ids, all_metadata, next_token)
        
        return {
            "metadata_list": all_metadata,
            "total_found": total_estimated or len(all_message_ids),
            "has_more": next_token is not None,
            "error": None
        }
        
    except Exception as e:
        logger.error(f"Error fetching email chunk: {e}")
        return {
            "error": str(e),
            "metadata_list": [],
            "total_found": 0,
            "has_more": False
        }

async def gmail_agentic_bulk_action(
    user_id: int,
    action: str,
    query: str,
    action_params: Dict[str, Any],
    confirm: bool = False
) -> Dict[str, Any]:
    """
    Handle bulk actions (labeling, moving) with confirmation.
    
    Args:
        user_id: User identifier
        action: Action type (label, move, delete, etc.)
        query: Gmail query to find emails
        action_params: Parameters for the action
        confirm: Whether user has confirmed the action
    
    Returns:
        Dict with response and action status
    """
    
    def _format_action_summary(action_name: str, params: Dict[str, Any]) -> str:
        if action_name == "bulk_delete":
            return "delete"
        label_name = (params or {}).get("label_name")
        add_labels = (params or {}).get("add_labels")
        remove_labels = (params or {}).get("remove_labels")
        parts: List[str] = []
        if isinstance(label_name, str) and label_name.strip():
            parts.append(f"label '{label_name.strip()}'")
        if isinstance(add_labels, list) and add_labels:
            parts.append("add labels")
        if isinstance(remove_labels, list) and remove_labels:
            parts.append("remove labels")
        if action_name == "bulk_move" and not parts:
            return "move"
        if action_name == "bulk_label" and not parts:
            return "label"
        return ", ".join(parts) if parts else action_name

    async def _resolve_label_ids(labels: List[Any]) -> Tuple[Optional[List[str]], Optional[str]]:
        resolved: List[str] = []
        for raw in labels or []:
            if raw is None:
                continue
            name = str(raw).strip()
            if not name:
                continue
            upper = name.upper()
            if upper in {"INBOX", "UNREAD", "STARRED", "IMPORTANT", "SENT", "DRAFT", "SPAM", "TRASH"}:
                resolved.append(upper)
                continue
            if name.startswith("Label_"):
                resolved.append(name)
                continue
            resolve_result = await gmail_resolve_label_id(name)
            if not resolve_result.get("success"):
                return None, f"LABEL_NOT_FOUND: {name}"
            data = resolve_result.get("data") or {}
            label_id = data.get("id") if isinstance(data, dict) else None
            if not isinstance(label_id, str) or not label_id.strip():
                return None, f"LABEL_RESOLVE_FAILED: {name}"
            resolved.append(label_id)
        return resolved, None

    async def _collect_message_ids() -> Tuple[Optional[List[str]], Optional[int], Optional[str]]:
        message_ids: List[str] = []
        page_token: Optional[str] = None
        pages = 0
        max_pages = 20
        max_total = 2000
        last_estimate: Optional[int] = None
        while True:
            pages += 1
            if pages > max_pages:
                break
            page = await gmail_list_message_ids_page(query=query, max_results=500, page_token=page_token)
            if not page.get("success"):
                return None, None, str(page.get("error") or "UNKNOWN_ERROR")
            data = page.get("data") or {}
            ids = data.get("message_ids") or []
            if isinstance(data.get("result_size_estimate"), int):
                last_estimate = int(data.get("result_size_estimate"))
            for mid in ids:
                if mid and len(message_ids) < max_total:
                    message_ids.append(str(mid))
            page_token = data.get("next_page_token")
            if not page_token:
                break
            if len(message_ids) >= max_total:
                break
        return message_ids, last_estimate, None

    action = (action or "").strip()
    if action not in {"bulk_label", "bulk_move", "bulk_delete"}:
        return {"success": False, "error": "INVALID_ACTION"}

    if not confirm:
        count_result = await gmail_list_message_ids_page(query=query, max_results=1)
        if not count_result.get("success"):
            return {"success": False, "error": str(count_result.get("error") or "UNKNOWN_ERROR")}
        data = count_result.get("data") or {}
        estimated = data.get("result_size_estimate")
        if not isinstance(estimated, int):
            ids = data.get("message_ids") or []
            estimated = len(ids) if isinstance(ids, list) else 0

        action_summary = _format_action_summary(action, action_params)
        msg = f"This will {action_summary} for about {estimated} emails matching '{query}'. Confirm?"
        return {
            "status": "confirmation_required",
            "message": msg,
            "data": {
                "action": action,
                "query": query,
                "action_params": action_params,
                "confirm": True,
            },
        }

    message_ids, estimated, err = await _collect_message_ids()
    if err:
        return {"success": False, "error": err}
    if not message_ids:
        return {"success": True, "message": "No matching emails found."}

    if action == "bulk_delete":
        result = await gmail_batch_delete_messages(message_ids=message_ids)
        if not result.get("success"):
            return {"success": False, "error": str(result.get("error") or "DELETE_FAILED"), "details": result}
        deleted = ((result.get("data") or {}).get("deleted"))
        if isinstance(deleted, int) and deleted > 0:
            return {"success": True, "message": f"Deleted {deleted} email(s)."}
        return {"success": True, "message": f"Deleted {len(message_ids)} email(s)."}

    add_labels_raw: List[Any] = []
    remove_labels_raw: List[Any] = []
    label_name = (action_params or {}).get("label_name")
    if isinstance(label_name, str) and label_name.strip():
        add_labels_raw.append(label_name.strip())
    if isinstance((action_params or {}).get("add_labels"), list):
        add_labels_raw.extend((action_params or {}).get("add_labels") or [])
    if isinstance((action_params or {}).get("remove_labels"), list):
        remove_labels_raw.extend((action_params or {}).get("remove_labels") or [])
    if action == "bulk_move" and not remove_labels_raw:
        remove_labels_raw = ["INBOX"]

    add_label_ids, add_err = await _resolve_label_ids(add_labels_raw)
    if add_err:
        return {"success": False, "error": add_err}
    remove_label_ids, rem_err = await _resolve_label_ids(remove_labels_raw)
    if rem_err:
        return {"success": False, "error": rem_err}

    add_label_ids = add_label_ids or []
    remove_label_ids = remove_label_ids or []
    if not add_label_ids and not remove_label_ids:
        return {"success": False, "error": "NO_LABEL_CHANGES_SPECIFIED"}

    mod = await gmail_batch_modify_labels(
        message_ids=message_ids,
        add_label_ids=add_label_ids,
        remove_label_ids=remove_label_ids,
    )
    if not mod.get("success"):
        return {"success": False, "error": str(mod.get("error") or "MODIFY_FAILED"), "details": mod}
    modified = ((mod.get("data") or {}).get("modified"))
    if isinstance(modified, int) and modified > 0:
        return {"success": True, "message": f"Updated {modified} email(s)."}
    return {"success": True, "message": f"Updated {len(message_ids)} email(s)."}
