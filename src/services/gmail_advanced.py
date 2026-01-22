"""Advanced Gmail operations for Jarvis AI Agent.

This module provides comprehensive email management including fetching,
sorting, label management, forwarding, and composition with clean formatting.
All operations enforce Saara's identity and clean output rules.
"""

from __future__ import annotations

import base64
import re
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

import httpx
import logging

from src.services.gmail import _gmail_auth_headers, _gmail_user_id


logger = logging.getLogger("jarvis.gmail_advanced")

SAARA_SIGNATURE = "\n\nWarm regards,\nSaara"
SAARA_EMAIL = "saar@alaw.co.il"


def _decode_base64_body(data: str) -> str:
    try:
        decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        return decoded
    except Exception:
        return ""


def _extract_email_body(payload: Dict[str, Any]) -> str:
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                body_data = part.get("body", {}).get("data", "")
                if body_data:
                    return _decode_base64_body(body_data)
        for part in payload["parts"]:
            if "parts" in part:
                nested = _extract_email_body(part)
                if nested:
                    return nested
    
    body_data = payload.get("body", {}).get("data", "")
    if body_data:
        return _decode_base64_body(body_data)
    
    return ""


def _clean_email_body(body: str) -> str:
    body = re.sub(r'\r\n', '\n', body)
    body = re.sub(r'\n{3,}', '\n\n', body)
    body = body.strip()
    return body


def _parse_email_headers(headers: List[Dict[str, str]]) -> Dict[str, str]:
    parsed = {}
    for h in headers:
        name = h.get("name", "")
        value = h.get("value", "")
        if name:
            parsed[name] = value
    return parsed


async def gmail_fetch_by_keyword(keyword: str, limit: int = 20) -> Dict[str, Any]:
    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}
    
    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages"
    params = {"q": keyword, "maxResults": limit}
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"FETCH_ERROR: {exc!r}"}
    
    data = resp.json()
    message_ids = [m["id"] for m in data.get("messages", [])]
    
    emails = []
    for msg_id in message_ids:
        email_data = await _fetch_full_email(msg_id)
        if email_data:
            emails.append(email_data)
    
    return {"success": True, "data": emails}


async def gmail_get_thread(thread_id: str) -> Dict[str, Any]:
    """Get a specific Gmail thread by ID."""

    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}

    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/threads/{thread_id}"
    params = {"format": "full"}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"GET_THREAD_ERROR: {exc!r}"}

    return {"success": True, "data": resp.json()}


async def gmail_list_threads(query: str, limit: int = 20) -> Dict[str, Any]:
    """List Gmail threads matching a search query."""

    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}

    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/threads"
    params = {"q": query, "maxResults": limit}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"LIST_THREADS_ERROR: {exc!r}"}

    data = resp.json()
    threads = data.get("threads", []) or []
    return {"success": True, "data": threads}


async def gmail_reply_to_thread(thread_id: str, body: str) -> Dict[str, Any]:
    """Reply to an existing Gmail thread with a clean, signed message."""

    thread_result = await gmail_get_thread(thread_id)
    if not thread_result.get("success"):
        return {"success": False, "error": "GET_THREAD_FAILED", "details": thread_result}

    thread = thread_result.get("data", {})
    messages = thread.get("messages", []) or []
    if not messages:
        return {"success": False, "error": "NO_MESSAGES_IN_THREAD"}

    original = messages[0]
    payload = original.get("payload", {})
    headers_list = payload.get("headers", [])

    header_map: Dict[str, str] = {}
    for h in headers_list:
        name = h.get("name")
        value = h.get("value")
        if name:
            header_map[name] = value

    original_subject = header_map.get("Subject", "")
    original_from = header_map.get("From", "")
    original_to = header_map.get("To", "")

    if original_subject.startswith("Re:"):
        reply_subject = original_subject
    else:
        reply_subject = f"Re: {original_subject}" if original_subject else "Re: (no subject)"

    to_address = original_from or original_to or SAARA_EMAIL

    clean_body = _clean_composition(body)
    if not clean_body.endswith(SAARA_SIGNATURE):
        clean_body += SAARA_SIGNATURE

    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}

    msg = EmailMessage()
    msg["To"] = to_address
    msg["Subject"] = reply_subject
    msg["From"] = SAARA_EMAIL
    msg.set_content(clean_body)

    raw_bytes = msg.as_bytes()
    raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages/send"
    payload = {"raw": raw_b64, "threadId": thread_id}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"REPLY_THREAD_ERROR: {exc!r}"}

    return {"success": True, "data": resp.json()}


async def gmail_archive_thread(thread_id: str) -> Dict[str, Any]:
    """Archive a Gmail thread by removing it from the INBOX."""

    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}

    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/threads/{thread_id}/modify"
    payload = {"removeLabelIds": ["INBOX"]}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"ARCHIVE_THREAD_ERROR: {exc!r}"}

    return {"success": True, "data": resp.json()}


async def gmail_delete_thread(thread_id: str) -> Dict[str, Any]:
    """Permanently delete a Gmail thread by ID."""

    _ = thread_id
    return {
        "success": False,
        "error": "THREAD_DELETE_NOT_SUPPORTED",
    }


async def gmail_create_draft(to: str, subject: str, body: str) -> Dict[str, Any]:
    """Create a new Gmail draft with Saara's signature and clean formatting."""

    clean_body = _clean_composition(body)

    if not clean_body.endswith(SAARA_SIGNATURE):
        clean_body += SAARA_SIGNATURE

    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}

    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg["From"] = SAARA_EMAIL
    msg.set_content(clean_body)

    raw_bytes = msg.as_bytes()
    raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/drafts"
    payload = {
        "message": {
            "raw": raw_b64,
        }
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"CREATE_DRAFT_ERROR: {exc!r}"}

    return {"success": True, "data": resp.json()}


async def gmail_list_drafts(limit: int = 20) -> Dict[str, Any]:
    """List Gmail drafts with a maximum number of results."""

    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}

    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/drafts"
    params = {"maxResults": limit}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"LIST_DRAFTS_ERROR: {exc!r}"}

    data = resp.json()
    drafts = data.get("drafts", []) or []
    return {"success": True, "data": drafts}


async def gmail_get_draft(draft_id: str) -> Dict[str, Any]:
    """Get a specific Gmail draft by ID."""

    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}

    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/drafts/{draft_id}"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"GET_DRAFT_ERROR: {exc!r}"}

    return {"success": True, "data": resp.json()}


async def gmail_update_draft(draft_id: str, to: str, subject: str, body: str) -> Dict[str, Any]:
    """Update an existing Gmail draft with new recipient, subject, and body."""

    clean_body = _clean_composition(body)

    if not clean_body.endswith(SAARA_SIGNATURE):
        clean_body += SAARA_SIGNATURE

    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}

    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg["From"] = SAARA_EMAIL
    msg.set_content(clean_body)

    raw_bytes = msg.as_bytes()
    raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/drafts/{draft_id}"
    payload = {
        "id": draft_id,
        "message": {
            "raw": raw_b64,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.put(url, headers=headers, json=payload)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"UPDATE_DRAFT_ERROR: {exc!r}"}

    return {"success": True, "data": resp.json()}


async def gmail_delete_draft(draft_id: str) -> Dict[str, Any]:
    """Delete a Gmail draft by ID."""

    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}

    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/drafts/{draft_id}"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.delete(url, headers=headers)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"DELETE_DRAFT_ERROR: {exc!r}"}

    # Gmail returns empty body on successful delete
    return {"success": True, "data": {}}


async def gmail_send_draft(draft_id: str, confirm: bool = False, **kwargs) -> Dict[str, Any]:
    """Send an existing Gmail draft by ID."""

    if confirm is False and "confirm" in kwargs:
        try:
            confirm = bool(kwargs.get("confirm"))
        except Exception:
            confirm = False

    if not confirm:
        return {
            "success": True,
            "sent": False,
            "confirmation_required": True,
            "data": {"draft_id": draft_id},
            "message": "Do you want me to send that draft?",
        }

    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}

    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/drafts/send"
    payload = {"id": draft_id}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"SEND_DRAFT_ERROR: {exc!r}"}

    return {"success": True, "data": resp.json()}


async def gmail_fetch_by_sender(sender: str, limit: int = 20) -> Dict[str, Any]:
    query = f"from:{sender}"
    return await gmail_fetch_by_keyword(query, limit)


async def gmail_fetch_by_subject(subject: str, limit: int = 20) -> Dict[str, Any]:
    query = f"subject:{subject}"
    return await gmail_fetch_by_keyword(query, limit)


async def gmail_fetch_by_label(label: str, limit: int = 20) -> Dict[str, Any]:
    query = f"label:{label}"
    return await gmail_fetch_by_keyword(query, limit)


async def gmail_fetch_by_date_range(after: str, before: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    query = f"after:{after}"
    if before:
        query += f" before:{before}"
    return await gmail_fetch_by_keyword(query, limit)


async def _fetch_full_email(message_id: str) -> Optional[Dict[str, Any]]:
    headers = await _gmail_auth_headers()
    if not headers:
        return None
    
    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages/{message_id}"
    params = {"format": "full"}
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
    except Exception:
        return None
    
    msg = resp.json()
    payload = msg.get("payload", {})
    headers_list = payload.get("headers", [])
    parsed_headers = _parse_email_headers(headers_list)
    
    body = _extract_email_body(payload)
    body = _clean_email_body(body)
    
    return {
        "id": message_id,
        "subject": parsed_headers.get("Subject", ""),
        "from": parsed_headers.get("From", ""),
        "to": parsed_headers.get("To", ""),
        "date": parsed_headers.get("Date", ""),
        "snippet": msg.get("snippet", ""),
        "body": body,
        "labels": msg.get("labelIds", [])
    }


async def gmail_get_message(message_id: str) -> Dict[str, Any]:
    email_data = await _fetch_full_email(message_id)
    if not email_data:
        return {"error": "FAILED_TO_FETCH_EMAIL"}
    return email_data


async def gmail_sort_emails(emails: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    categories = {
        "Work": [],
        "Personal": [],
        "Urgent": [],
        "Follow Up": [],
        "Receipts": [],
        "Important": []
    }
    
    for email in emails:
        subject = email.get("subject", "").lower()
        body = email.get("body", "").lower()
        sender = email.get("from", "").lower()
        labels = email.get("labels", [])
        
        if "IMPORTANT" in labels or "urgent" in subject or "asap" in subject:
            categories["Urgent"].append(email)
        
        if any(word in subject or word in body for word in ["invoice", "receipt", "payment", "order"]):
            categories["Receipts"].append(email)
        
        if "STARRED" in labels or "important" in subject:
            categories["Important"].append(email)
        
        if any(word in subject or word in body for word in ["follow up", "reminder", "pending", "waiting"]):
            categories["Follow Up"].append(email)
        
        work_domains = ["company.com", "work.com", "corp.com"]
        if any(domain in sender for domain in work_domains):
            categories["Work"].append(email)
        else:
            categories["Personal"].append(email)
    
    return categories


async def gmail_list_labels() -> Dict[str, Any]:
    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}
    
    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/labels"
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"LIST_LABELS_ERROR: {exc!r}"}
    
    data = resp.json()
    labels = data.get("labels", [])
    
    return {"success": True, "data": labels}


async def gmail_resolve_label_id(label_name: str) -> Dict[str, Any]:
    """Resolve a human-readable Gmail label name to its label ID.

    Returns:
        {"success": True, "data": {"id": "...", "name": "..."}}
        or an error dict if the label cannot be resolved.
    """

    labels_result = await gmail_list_labels()
    if not labels_result.get("success"):
        return {
            "success": False,
            "error": "LIST_LABELS_FAILED",
            "details": labels_result,
        }

    labels = labels_result.get("data", []) or []
    target_lower = (label_name or "").strip().lower()

    for label in labels:
        name = (label.get("name") or "").strip()
        if name.lower() == target_lower:
            return {
                "success": True,
                "data": {
                    "id": label.get("id"),
                    "name": name,
                },
            }

    return {
        "success": False,
        "error": "LABEL_NOT_FOUND",
        "data": {"requested_name": label_name},
    }


async def gmail_create_label(label_name: str) -> Dict[str, Any]:
    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}
    
    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/labels"
    payload = {"name": label_name}
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"CREATE_LABEL_ERROR: {exc!r}"}
    
    return {"success": True, "data": resp.json()}


async def gmail_delete_label(label_id: str) -> Dict[str, Any]:
    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}
    
    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/labels/{label_id}"
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.delete(url, headers=headers)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"DELETE_LABEL_ERROR: {exc!r}"}
    
    return {"success": True, "data": {}}


async def gmail_rename_label(label_id: str, new_name: str) -> Dict[str, Any]:
    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}
    
    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/labels/{label_id}"
    payload = {"name": new_name}
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.patch(url, headers=headers, json=payload)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"RENAME_LABEL_ERROR: {exc!r}"}
    
    return {"success": True, "data": resp.json()}


async def gmail_move_to_label(message_id: str, add_label_ids: List[str], remove_label_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}
    
    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages/{message_id}/modify"
    
    payload = {"addLabelIds": add_label_ids}
    if remove_label_ids:
        payload["removeLabelIds"] = remove_label_ids
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"MOVE_LABEL_ERROR: {exc!r}"}
    
    return {"success": True, "data": resp.json()}


async def gmail_remove_label(message_id: str, label_ids: List[str]) -> Dict[str, Any]:
    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}
    
    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages/{message_id}/modify"
    payload = {"removeLabelIds": label_ids}
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"REMOVE_LABEL_ERROR: {exc!r}"}
    
    return {"success": True, "data": resp.json()}


async def gmail_forward_email(message_id: str, recipient: str) -> Dict[str, Any]:
    email_data = await _fetch_full_email(message_id)
    if not email_data:
        return {"success": False, "error": "FAILED_TO_FETCH_ORIGINAL_EMAIL"}
    
    original_subject = email_data.get("subject", "")
    original_from = email_data.get("from", "")
    original_date = email_data.get("date", "")
    original_body = email_data.get("body", "")
    
    forward_subject = f"Fwd: {original_subject}" if not original_subject.startswith("Fwd:") else original_subject
    
    forward_body = f"---------- Forwarded message ---------\n"
    forward_body += f"From: {original_from}\n"
    forward_body += f"Date: {original_date}\n"
    forward_body += f"Subject: {original_subject}\n\n"
    forward_body += original_body
    forward_body += SAARA_SIGNATURE
    
    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}
    
    msg = EmailMessage()
    msg["To"] = recipient
    msg["Subject"] = forward_subject
    msg["From"] = SAARA_EMAIL
    msg.set_content(forward_body)
    
    raw_bytes = msg.as_bytes()
    raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")
    
    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages/send"
    payload = {"raw": raw_b64}
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"FORWARD_ERROR: {exc!r}"}
    
    return {"success": True, "data": resp.json()}


def _strip_markdown(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'~~(.+?)~~', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'#{1,6}\s+', '', text)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    return text


def _clean_composition(body: str) -> str:
    body = _strip_markdown(body)
    body = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]+', '', body)
    body = re.sub(r'\n{3,}', '\n\n', body)
    body = body.strip()
    return body


async def gmail_compose_email(to: str, subject: str, body: str) -> Dict[str, Any]:
    clean_body = _clean_composition(body)
    
    if not clean_body.endswith(SAARA_SIGNATURE):
        clean_body += SAARA_SIGNATURE
    
    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}
    
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg["From"] = SAARA_EMAIL
    msg.set_content(clean_body)
    
    raw_bytes = msg.as_bytes()
    raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")
    
    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages/send"
    payload = {"raw": raw_b64}
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"COMPOSE_ERROR: {exc!r}"}
    
    return {"success": True, "data": resp.json()}


async def gmail_list_attachments(message_id: str) -> Dict[str, Any]:
    """List all attachments in a Gmail message.
    
    Returns a list of attachment metadata including attachmentId, filename,
    mimeType, and size in bytes.
    """
    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}
    
    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages/{message_id}"
    params = {"format": "full"}
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"FETCH_MESSAGE_ERROR: {exc!r}"}
    
    msg = resp.json()
    payload = msg.get("payload", {})
    
    attachments = []
    
    def extract_attachments(part: Dict[str, Any]) -> None:
        """Recursively extract attachments from message parts."""
        if "parts" in part:
            for subpart in part["parts"]:
                extract_attachments(subpart)
        
        body = part.get("body", {})
        attachment_id = body.get("attachmentId")
        
        if attachment_id:
            filename = part.get("filename", "unknown")
            mime_type = part.get("mimeType", "application/octet-stream")
            size = body.get("size", 0)
            
            attachments.append({
                "attachmentId": attachment_id,
                "filename": filename,
                "mimeType": mime_type,
                "size": size
            })
    
    extract_attachments(payload)
    
    return {"success": True, "data": attachments}


async def gmail_download_attachment(message_id: str, attachment_id: str) -> Dict[str, Any]:
    """Download a specific attachment from a Gmail message.
    
    Returns the attachment data as base64-encoded bytes.
    """
    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}
    
    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages/{message_id}/attachments/{attachment_id}"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"DOWNLOAD_ATTACHMENT_ERROR: {exc!r}"}
    
    data = resp.json()
    attachment_data = data.get("data", "")
    size = data.get("size", 0)
    
    return {
        "success": True,
        "data": {
            "attachmentData": attachment_data,
            "size": size
        }
    }


async def gmail_fetch_emails_with_attachments(limit: int = 20) -> Dict[str, Any]:
    """Fetch emails that contain attachments.
    
    Uses Gmail search query 'has:attachment' to find emails with attachments,
    then fetches full email data for each.
    """
    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}
    
    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages"
    params = {"q": "has:attachment", "maxResults": limit}
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"FETCH_ERROR: {exc!r}"}
    
    data = resp.json()
    message_ids = [m["id"] for m in data.get("messages", [])]
    
    emails = []
    for msg_id in message_ids:
        email_data = await _fetch_full_email(msg_id)
        if email_data:
            emails.append(email_data)
    
    return {"success": True, "data": emails}
