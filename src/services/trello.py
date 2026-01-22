"""Trello service integration for the Jarvis AI Agent.

This module exposes a small set of async helpers for working with Trello via
its REST API. These helpers are used by the agent tool layer.
"""

from __future__ import annotations

import os
from typing import Any, Dict

import httpx


_TRELLO_BASE_URL = "https://api.trello.com/1"


def _auth_params() -> Dict[str, str]:
    """Return Trello auth query parameters built from environment variables."""

    api_key = os.getenv("TRELLO_API_KEY")
    api_token = os.getenv("TRELLO_API_TOKEN")

    params: Dict[str, str] = {}
    if api_key:
        params["key"] = api_key
    if api_token:
        params["token"] = api_token
    return params


async def trello_create_card(list_id: str, name: str, description: str | None = None) -> Dict[str, Any]:
    """Create a Trello card in the given list.

    Returns a normalized result dict with success flag and card data.
    """

    params = _auth_params()
    params.update({"idList": list_id, "name": name})
    if description:
        params["desc"] = description

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{_TRELLO_BASE_URL}/cards", params=params)
        resp.raise_for_status()
    except httpx.RequestError as exc:
        return {"success": False, "error": f"HTTP_ERROR: {exc!r}"}
    except httpx.HTTPStatusError as exc:
        return {"success": False, "error": f"API_ERROR: {exc.response.status_code}", "body": exc.response.text}

    card = resp.json()
    url = None
    if isinstance(card, dict):
        url = card.get("shortUrl") or card.get("url")
    msg = f"Task '{name}' has been created."
    if isinstance(url, str) and url.strip():
        msg = f"Task '{name}' has been created: {url.strip()}"
    return {"success": True, "message": msg, "data": card}


async def trello_get_boards() -> Dict[str, Any]:
    """Return boards for the authorized Trello user."""

    params = _auth_params()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{_TRELLO_BASE_URL}/members/me/boards", params=params)
        resp.raise_for_status()
    except httpx.RequestError as exc:
        return {"success": False, "error": f"HTTP_ERROR: {exc!r}"}
    except httpx.HTTPStatusError as exc:
        return {"success": False, "error": f"API_ERROR: {exc.response.status_code}", "body": exc.response.text}

    return {"success": True, "data": resp.json()}


async def trello_get_lists(board_id: str) -> Dict[str, Any]:
    """List lists on a given Trello board."""

    params = _auth_params()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{_TRELLO_BASE_URL}/boards/{board_id}/lists", params=params)
        resp.raise_for_status()
    except httpx.RequestError as exc:
        return {"success": False, "error": f"HTTP_ERROR: {exc!r}"}
    except httpx.HTTPStatusError as exc:
        return {"success": False, "error": f"API_ERROR: {exc.response.status_code}", "body": exc.response.text}

    return {"success": True, "data": resp.json()}


async def trello_add_comment(card_id: str, text: str) -> Dict[str, Any]:
    """Add a comment to a Trello card."""

    params = _auth_params()
    params["text"] = text

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{_TRELLO_BASE_URL}/cards/{card_id}/actions/comments", params=params)
        resp.raise_for_status()
    except httpx.RequestError as exc:
        return {"success": False, "error": f"HTTP_ERROR: {exc!r}"}
    except httpx.HTTPStatusError as exc:
        return {"success": False, "error": f"API_ERROR: {exc.response.status_code}", "body": exc.response.text}

    return {"success": True, "data": resp.json()}
