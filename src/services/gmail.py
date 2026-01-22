"""Gmail service integration for the Jarvis AI Agent.

This module defines tool-facing async helpers for sending and reading emails
through the Gmail REST API. These helpers are wired into the agent tools
layer in ``src.core.tools``.
"""

from __future__ import annotations

import base64
import os
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

import httpx
import logging

from src.core.llm import call_llm
from src.services.google_oauth import get_google_access_token


logger = logging.getLogger("jarvis.gmail")


class GmailService:
    """Wrapper around Gmail-related operations.

    Kept for backwards compatibility; new code should use the module-level
    async helpers defined below.
    """

    def __init__(self) -> None:
        """Initialize the Gmail service."""
        self._logger = logging.getLogger(self.__class__.__name__)

    async def send_email(self, data: Dict[str, Any]) -> None:  # pragma: no cover - legacy
        """Legacy wrapper around gmail_send_email."""

        await gmail_send_email(
            to=data.get("to", ""),
            subject=data.get("subject", ""),
            body=data.get("body", ""),
        )


async def _gmail_auth_headers() -> Dict[str, str]:
    """Return auth headers for Gmail, using refresh-token flow if needed."""

    # Prefer an explicit access token if it looks valid.
    token = os.getenv("GMAIL_API_TOKEN")
    # Many Google client secrets start with "GOCSPX-"; treat those as NOT access tokens.
    if not token or token.startswith("GOCSPX-"):
        token = await get_google_access_token()

    if not token:
        logger.error(
            "No valid Gmail access token; set GMAIL_API_TOKEN or "
            "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN.",
        )
        return {}

    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _gmail_user_id() -> str:
    return os.getenv("GMAIL_USER_ID", "me")


async def gmail_send_email(to: str, subject: str, body: str, confirm: bool = False, **kwargs) -> Dict[str, Any]:
    """Send an email via Gmail.

    Returns {"success": bool, "data"|"error": ...}.
    """

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
            "data": {"to": to, "subject": subject, "body": body},
            "message": f"Do you want me to send this email to {to} with subject '{subject}'?",
        }

    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}

    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg["From"] = _gmail_user_id()
    msg.set_content(body)

    raw_bytes = msg.as_bytes()
    raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages/send"

    payload = {"raw": raw_b64}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    except httpx.RequestError as exc:
        return {"success": False, "error": f"HTTP_ERROR: {exc!r}"}
    except httpx.HTTPStatusError as exc:
        return {"success": False, "error": f"API_ERROR: {exc.response.status_code}", "body": exc.response.text}

    return {"success": True, "data": resp.json()}


async def gmail_create_label(label_name: str) -> Dict[str, Any]:
    """Create a new Gmail label in the user's mailbox.

    Returns {"success": bool, "data"|"error": ...}.
    """

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
    except httpx.RequestError as exc:  # noqa: BLE001
        return {"success": False, "error": f"HTTP_ERROR: {exc!r}"}
    except httpx.HTTPStatusError as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": f"API_ERROR: {exc.response.status_code}",
            "body": exc.response.text,
        }

    return {"success": True, "data": resp.json()}


async def gmail_search(query: str, limit: int = 10) -> Dict[str, Any]:
    """Search Gmail messages using a Gmail query string.
    
    Returns lightweight metadata for each message including subject, sender,
    snippet, date, and labels. Internally calls gmail_read() for each result.
    """

    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}

    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages"
    params = {"q": query, "maxResults": limit}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
    except httpx.RequestError as exc:
        return {"success": False, "error": f"HTTP_ERROR: {exc!r}"}
    except httpx.HTTPStatusError as exc:
        return {"success": False, "error": f"API_ERROR: {exc.response.status_code}", "body": exc.response.text}

    data = resp.json()
    message_ids: List[str] = [m["id"] for m in data.get("messages", []) or []]
    
    # Fetch lightweight metadata for each message
    enriched_messages: List[Dict[str, Any]] = []
    
    for message_id in message_ids:
        read_result = await gmail_read(message_id)
        
        # Skip messages that fail to read
        if not read_result.get("success"):
            logger.warning(f"Failed to read message {message_id}, skipping")
            continue
        
        msg = read_result.get("data", {})
        payload = msg.get("payload", {})
        headers_list = payload.get("headers", [])
        
        # Extract headers into a dict for easy lookup
        headers_dict = {h.get("name"): h.get("value") for h in headers_list}
        
        # Build lightweight metadata
        enriched_messages.append({
            "id": message_id,
            "subject": headers_dict.get("Subject", "(no subject)"),
            "from": headers_dict.get("From", "(unknown sender)"),
            "date": headers_dict.get("Date", ""),
            "snippet": msg.get("snippet", ""),
            "labels": msg.get("labelIds", [])
        })
    
    return {"success": True, "data": enriched_messages}


async def gmail_read(message_id: str) -> Dict[str, Any]:
    """Read a specific Gmail message by ID."""

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
    except httpx.RequestError as exc:
        return {"success": False, "error": f"HTTP_ERROR: {exc!r}"}
    except httpx.HTTPStatusError as exc:
        return {"success": False, "error": f"API_ERROR: {exc.response.status_code}", "body": exc.response.text}

    return {"success": True, "data": resp.json()}


async def gmail_label(
    message_id: str,
    labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Add and/or remove labels from a Gmail message by ID.

    Args:
        message_id: The Gmail message ID to modify.
        labels: List of label names or IDs to add to the message.
        remove_labels: Optional list of label names or IDs to remove from the message.

    Note: Accepts both label names (e.g., "Work") and label IDs (e.g., "Label_123").
          System labels like INBOX, UNREAD, STARRED are used as-is.
    """
    from src.services.gmail_advanced import gmail_resolve_label_id

    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}

    resolved_add_ids = []
    if labels:
        for label in labels:
            if label.upper() in ["INBOX", "UNREAD", "STARRED", "IMPORTANT", "SENT", "DRAFT", "SPAM", "TRASH"]:
                resolved_add_ids.append(label.upper())
            elif label.startswith("Label_"):
                resolved_add_ids.append(label)
            else:
                resolve_result = await gmail_resolve_label_id(label)
                if resolve_result.get("success"):
                    resolved_add_ids.append(resolve_result["data"]["id"])
                else:
                    return {"success": False, "error": f"LABEL_NOT_FOUND: {label}"}

    resolved_remove_ids = []
    if remove_labels:
        for label in remove_labels:
            if label.upper() in ["INBOX", "UNREAD", "STARRED", "IMPORTANT", "SENT", "DRAFT", "SPAM", "TRASH"]:
                resolved_remove_ids.append(label.upper())
            elif label.startswith("Label_"):
                resolved_remove_ids.append(label)
            else:
                resolve_result = await gmail_resolve_label_id(label)
                if resolve_result.get("success"):
                    resolved_remove_ids.append(resolve_result["data"]["id"])
                else:
                    return {"success": False, "error": f"LABEL_NOT_FOUND: {label}"}

    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages/{message_id}/modify"
    payload = {
        "addLabelIds": resolved_add_ids,
        "removeLabelIds": resolved_remove_ids,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    except httpx.RequestError as exc:
        return {"success": False, "error": f"HTTP_ERROR: {exc!r}"}
    except httpx.HTTPStatusError as exc:
        return {"success": False, "error": f"API_ERROR: {exc.response.status_code}", "body": exc.response.text}

    return {"success": True, "data": resp.json()}


async def gmail_summarize(message_id: str) -> Dict[str, Any]:
    """Summarize a Gmail message using the LLM wrapper."""

    read_result = await gmail_read(message_id)
    if not read_result.get("success"):
        return {"success": False, "error": "READ_FAILED", "details": read_result}

    msg = read_result["data"]
    snippet = msg.get("snippet", "")
    headers = {h.get("name"): h.get("value") for h in msg.get("payload", {}).get("headers", [])}
    subject = headers.get("Subject", "(no subject)")
    frm = headers.get("From", "(unknown sender)")

    content = f"Subject: {subject}\nFrom: {frm}\n\nSnippet: {snippet}"

    messages = [
        {"role": "system", "content": "Summarize the following email for the user in a few concise bullet points."},
        {"role": "user", "content": content},
    ]

    llm_result = await call_llm(messages, tools=None)
    if llm_result.get("type") != "message":
        return {"success": False, "error": "LLM_SUMMARY_FAILED", "details": llm_result}

    summary = llm_result.get("content", "")
    return {"success": True, "data": {"summary": summary}}
