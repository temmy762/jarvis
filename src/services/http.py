"""Generic HTTP client tools for Jarvis.

These helpers are exposed as tools via src.core.tools so the agent can
perform arbitrary HTTP GET/POST requests in a controlled way.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


async def http_get(url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Perform an HTTP GET request and return a normalized response dict."""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params, headers=headers)
    except httpx.RequestError as exc:  # network or protocol error
        return {"success": False, "status": None, "error": str(exc)}

    body: Any
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = resp.text

    return {"success": resp.is_success, "status": resp.status_code, "body": body}


async def http_post(
    url: str,
    json_body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Perform an HTTP POST request and return a normalized response dict."""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=json_body, headers=headers)
    except httpx.RequestError as exc:  # network or protocol error
        return {"success": False, "status": None, "error": str(exc)}

    body: Any
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = resp.text

    return {"success": resp.is_success, "status": resp.status_code, "body": body}
