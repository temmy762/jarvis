"""Gmail bulk primitives.

This module provides *single-call* Gmail primitives required for bulk operations:
- One message list page fetch (IDs only)
- One batchModify call (apply/remove labels)

These functions are intentionally minimal and deterministic:
- No loops over pagination
- No eager fetching of all IDs
- No per-message GET reads
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import asyncio
import httpx

from src.services.gmail import _gmail_auth_headers, _gmail_user_id


async def gmail_list_message_ids_page(
    *,
    query: str,
    max_results: int,
    page_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch exactly ONE Gmail message list page (IDs only).

    Args:
        query: Gmail search query string.
        max_results: Max results for this page.
        page_token: Optional page token from previous call.

    Returns:
        {
          "success": bool,
          "data": {
             "message_ids": [str, ...],
             "next_page_token": str|None,
             "result_size_estimate": int|None,
          }
        }

    Notes:
        - This function performs at most ONE HTTP request.
        - It does not fetch message details.
    """

    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}

    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages"

    params: Dict[str, Any] = {"q": query, "maxResults": max_results}
    if page_token:
        params["pageToken"] = page_token

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"API_ERROR: {exc.response.status_code}",
            "status_code": exc.response.status_code,
            "body": exc.response.text,
        }
    except httpx.RequestError as exc:
        return {"success": False, "error": f"HTTP_ERROR: {exc!r}"}

    payload = resp.json()
    message_ids: List[str] = [m["id"] for m in (payload.get("messages") or [])]

    return {
        "success": True,
        "data": {
            "message_ids": message_ids,
            "next_page_token": payload.get("nextPageToken"),
            "result_size_estimate": payload.get("resultSizeEstimate"),
        },
    }


async def gmail_batch_modify_labels(
    *,
    message_ids: List[str],
    add_label_ids: List[str],
    remove_label_ids: List[str],
) -> Dict[str, Any]:
    """Apply/remove labels for many messages with ONE batchModify call.

    Args:
        message_ids: Gmail message IDs.
        add_label_ids: Label IDs to add.
        remove_label_ids: Label IDs to remove.

    Returns:
        {"success": bool, "data"|"error": ...}

    Notes:
        - This function performs at most ONE HTTP request.
        - Gmail batchModify does not provide per-message status. If the request
          fails, the caller should mark each message as failed with the same error.
    """

    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}

    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages/batchModify"

    payload: Dict[str, Any] = {
        "ids": message_ids,
        "addLabelIds": add_label_ids,
        "removeLabelIds": remove_label_ids,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"API_ERROR: {exc.response.status_code}",
            "status_code": exc.response.status_code,
            "body": exc.response.text,
        }
    except httpx.RequestError as exc:
        return {"success": False, "error": f"HTTP_ERROR: {exc!r}"}

    return {"success": True, "data": {"modified": len(message_ids)}}


async def gmail_batch_delete_messages(*, message_ids: List[str]) -> Dict[str, Any]:
    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}

    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages/batchDelete"

    payload: Dict[str, Any] = {
        "ids": message_ids,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"API_ERROR: {exc.response.status_code}",
            "status_code": exc.response.status_code,
            "body": exc.response.text,
        }
    except httpx.RequestError as exc:
        return {"success": False, "error": f"HTTP_ERROR: {exc!r}"}

    return {"success": True, "data": {"deleted": len(message_ids)}}


async def gmail_get_message_headers(*, message_id: str) -> Dict[str, Any]:
    headers = await _gmail_auth_headers()
    if not headers:
        return {"success": False, "error": "MISSING_GMAIL_API_TOKEN"}

    user_id = _gmail_user_id()
    url = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages/{message_id}"

    params: Dict[str, Any] = {
        "format": "metadata",
        "metadataHeaders": ["Subject", "From", "Date"],
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"API_ERROR: {exc.response.status_code}",
            "status_code": exc.response.status_code,
            "body": exc.response.text,
        }
    except httpx.RequestError as exc:
        return {"success": False, "error": f"HTTP_ERROR: {exc!r}"}

    payload = resp.json() or {}
    header_list = ((payload.get("payload") or {}).get("headers") or [])
    out: Dict[str, str] = {}
    for h in header_list:
        if not isinstance(h, dict):
            continue
        name = h.get("name")
        value = h.get("value")
        if isinstance(name, str) and isinstance(value, str):
            out[name] = value

    return {"success": True, "data": out}


async def gmail_get_message_metadata_batch(*, message_ids: List[str]) -> List[Dict[str, Any]]:
    """Get metadata for multiple messages efficiently.
    
    Args:
        message_ids: List of Gmail message IDs
        
    Returns:
        List of metadata dictionaries, one per message ID
    """
    headers = await _gmail_auth_headers()
    if not headers:
        return [{"error": "MISSING_GMAIL_API_TOKEN"} for _ in message_ids]

    user_id = _gmail_user_id()
    url_base = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages"

    # Keep concurrency modest to reduce rate-limit spikes.
    sem = asyncio.Semaphore(10)

    async def _fetch_one(client: httpx.AsyncClient, msg_id: str) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "format": "metadata",
            "metadataHeaders": ["Subject", "From", "Date"],
        }
        async with sem:
            try:
                resp = await client.get(f"{url_base}/{msg_id}", headers=headers, params=params)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                return {"id": msg_id, "error": f"API_ERROR: {exc.response.status_code}"}
            except httpx.RequestError as exc:
                return {"id": msg_id, "error": f"HTTP_ERROR: {exc!r}"}

        payload = resp.json() or {}
        header_list = ((payload.get("payload") or {}).get("headers") or [])
        header_map: Dict[str, str] = {}
        for h in header_list:
            if not isinstance(h, dict):
                continue
            name = h.get("name")
            value = h.get("value")
            if isinstance(name, str) and isinstance(value, str):
                header_map[name] = value

        return {
            "id": msg_id,
            "thread_id": payload.get("threadId", ""),
            "snippet": payload.get("snippet", ""),
            "labels": payload.get("labelIds", []),
            "subject": header_map.get("Subject", "No Subject"),
            "from": header_map.get("From", "Unknown"),
            "date": header_map.get("Date", "Unknown"),
        }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            results = await asyncio.gather(*[_fetch_one(client, mid) for mid in message_ids])
        return list(results)
    except Exception as exc:
        return [{"id": mid, "error": f"METADATA_BATCH_ERROR: {exc!r}"} for mid in message_ids]
