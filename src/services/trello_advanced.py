"""Advanced Trello task management for Jarvis AI Agent.

This module provides comprehensive Trello operations including task creation,
updating, moving, deletion, retrieval, and organization with clean formatting
for Saara.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
import logging

from src.services.trello import _auth_params, _TRELLO_BASE_URL
from src.services.trello import trello_add_comment


logger = logging.getLogger("jarvis.trello_advanced")

SAARA_EMAIL = "saar@alaw.co.il"


_TRELLO_ID_RE = re.compile(r"^[0-9a-f]{24}$", re.IGNORECASE)


def _looks_like_trello_id(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    return bool(_TRELLO_ID_RE.match(v))


async def trello_list_boards() -> Dict[str, Any]:
    """List all boards for the authenticated user."""
    params = _auth_params()
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{_TRELLO_BASE_URL}/members/me/boards", params=params)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"LIST_BOARDS_ERROR: {exc!r}"}
    
    boards = resp.json()
    return {"success": True, "data": boards}


async def trello_list_lists(board_id: str) -> Dict[str, Any]:
    """List all lists on a board."""
    params = _auth_params()
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{_TRELLO_BASE_URL}/boards/{board_id}/lists", params=params)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"LIST_LISTS_ERROR: {exc!r}"}
    
    lists = resp.json()
    return {"success": True, "data": lists}


async def _resolve_list_id_any(list_id_or_name: str) -> Dict[str, Any]:
    candidate = (list_id_or_name or "").strip()
    if not candidate:
        return {
            "success": False,
            "error": "MISSING_LIST",
            "message": "Which Trello list should I check? You can reply with a list name (for example: 'To Do') and optionally the board name if you have multiple boards.",
        }

    if _looks_like_trello_id(candidate):
        return {"success": True, "data": {"list_id": candidate}}

    boards_result = await trello_list_boards()
    if not boards_result.get("success"):
        return boards_result
    boards = boards_result.get("data")
    if not isinstance(boards, list) or not boards:
        return {
            "success": False,
            "error": "NO_BOARDS",
            "message": "I couldn't find any Trello boards to search for that list.",
        }

    matches: List[Dict[str, str]] = []
    for board in boards:
        if not isinstance(board, dict):
            continue
        board_id = str(board.get("id") or "").strip()
        board_name = str(board.get("name") or "").strip()
        if not board_id or not _looks_like_trello_id(board_id):
            continue

        lists_result = await trello_list_lists(board_id)
        if not lists_result.get("success"):
            continue
        lists = lists_result.get("data")
        if not isinstance(lists, list) or not lists:
            continue

        picked = _pick_list_match(lists, candidate)
        if isinstance(picked, dict) and picked.get("id"):
            matches.append(
                {
                    "list_id": str(picked.get("id")),
                    "list_name": str(picked.get("name") or ""),
                    "board_id": board_id,
                    "board_name": board_name,
                }
            )

    if not matches:
        return {
            "success": False,
            "error": "LIST_NOT_FOUND",
            "message": f"I couldn't find a Trello list called '{candidate}'.",
        }

    if len(matches) > 1:
        lines: List[str] = []
        for i, m in enumerate(matches[:8], start=1):
            list_name = (m.get("list_name") or candidate).strip()
            board_name = (m.get("board_name") or m.get("board_id") or "").strip()
            if board_name:
                lines.append(f"{i}) {list_name} — board: {board_name}")
            else:
                lines.append(f"{i}) {list_name}")
        options = "\n".join(lines)
        return {
            "success": False,
            "error": "AMBIGUOUS_LIST_NAME",
            "message": (
                f"I found multiple Trello lists that match '{candidate}'.\n"
                f"Reply with the board name (or copy/paste the exact list name + board), for example: 'Missions / To Do'.\n\n"
                f"Options:\n{options}"
            ),
        }

    return {"success": True, "data": matches[0]}


async def trello_list_cards(
    list_id: str = "",
    board_id: str = "",
    board_name: Optional[str] = None,
    list_name: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """List all cards in a list."""
    _ = kwargs

    list_id = (list_id or "").strip()
    board_id = (board_id or "").strip()
    board_name = (board_name or "").strip() or None
    list_name = (list_name or "").strip() or None

    if board_id and not board_name and not _looks_like_trello_id(board_id):
        board_name = board_id
        board_id = ""

    resolved_board_id = board_id
    if board_name and not resolved_board_id:
        board_result = await trello_find_board_by_name(board_name)
        if not board_result.get("success"):
            msg = board_result.get("message")
            if not isinstance(msg, str) or not msg.strip():
                msg = f"Board '{board_name}' not found."
            return {"success": False, "error": "BOARD_NOT_FOUND", "message": msg}
        data = board_result.get("data")
        if not isinstance(data, dict) or not data.get("id"):
            return {"success": False, "error": "BOARD_ID_MISSING", "message": "I couldn't resolve that Trello board."}
        resolved_board_id = str(data.get("id"))

    effective_list_name = list_name
    if not effective_list_name and list_id and not _looks_like_trello_id(list_id):
        effective_list_name = list_id
        list_id = ""

    if effective_list_name and resolved_board_id:
        list_result = await trello_find_list_by_name(resolved_board_id, effective_list_name)
        if not list_result.get("success"):
            lists_result = await trello_list_lists(resolved_board_id)
            lists = lists_result.get("data") if isinstance(lists_result, dict) else None
            available_names: List[str] = []
            if isinstance(lists, list):
                for item in lists:
                    if isinstance(item, dict) and isinstance(item.get("name"), str) and item.get("name").strip():
                        available_names.append(item.get("name").strip())
                    if len(available_names) >= 8:
                        break
            board_label = board_name or resolved_board_id
            if available_names:
                numbered = "\n".join([f"{i}) {n}" for i, n in enumerate(available_names, start=1)])
                return {
                    "success": False,
                    "error": "LIST_NOT_FOUND",
                    "message": (
                        f"I couldn't find a list called '{effective_list_name}' on the Trello board '{board_label}'.\n\n"
                        f"Here are the lists I can see on that board:\n{numbered}"
                    ),
                }
            msg = list_result.get("message")
            if not isinstance(msg, str) or not msg.strip():
                msg = f"I couldn't find a list called '{effective_list_name}' on that board."
            return {"success": False, "error": "LIST_NOT_FOUND", "message": msg}
        data = list_result.get("data")
        if isinstance(data, dict) and isinstance(data.get("id"), str) and data.get("id").strip():
            list_id = data.get("id").strip()
        else:
            return {"success": False, "error": "LIST_ID_MISSING", "message": "I couldn't resolve that Trello list."}
    elif effective_list_name and not list_id:
        resolved = await _resolve_list_id_any(effective_list_name)
        if not resolved.get("success"):
            return resolved
        data = resolved.get("data")
        if isinstance(data, dict) and isinstance(data.get("list_id"), str):
            list_id = data.get("list_id")

    if not list_id:
        if resolved_board_id:
            lists_result = await trello_list_lists(resolved_board_id)
            lists = lists_result.get("data") if isinstance(lists_result, dict) else None
            if isinstance(lists, list) and lists:
                available_names: List[str] = []
                for item in lists:
                    if isinstance(item, dict) and isinstance(item.get("name"), str) and item.get("name").strip():
                        available_names.append(item.get("name").strip())
                    if len(available_names) >= 8:
                        break
                if available_names:
                    numbered = "\n".join([f"{i}) {n}" for i, n in enumerate(available_names, start=1)])
                    board_label = board_name or resolved_board_id
                    return {
                        "success": False,
                        "error": "MISSING_LIST",
                        "message": (
                            f"Which list on the Trello board '{board_label}' should I check?\n\n"
                            f"Here are the lists I can see:\n{numbered}"
                        ),
                    }

        boards_result = await trello_list_boards()
        boards = boards_result.get("data") if isinstance(boards_result, dict) else None
        board_names: List[str] = []
        if isinstance(boards, list):
            for b in boards:
                if isinstance(b, dict) and isinstance(b.get("name"), str) and b.get("name").strip():
                    board_names.append(b.get("name").strip())
                if len(board_names) >= 6:
                    break
        board_hint = ""
        if board_names:
            numbered_boards = "\n".join([f"{i}) {n}" for i, n in enumerate(board_names, start=1)])
            board_hint = f"\n\nIf it helps, here are your boards:\n{numbered_boards}"
        return {
            "success": False,
            "error": "MISSING_LIST",
            "message": "Which Trello list should I check? Tell me the list name (like 'To Do') and, if needed, the board name." + board_hint,
        }
    if not _looks_like_trello_id(list_id):
        return {
            "success": False,
            "error": "INVALID_LIST_ID",
            "message": "I couldn't resolve that as a Trello list. Please reply with the list name (and optionally the board name).",
        }

    params = _auth_params()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{_TRELLO_BASE_URL}/lists/{list_id}/cards", params=params)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        return {
            "success": False,
            "error": f"LIST_CARDS_ERROR:HTTP_{status}",
            "message": "Trello returned an error while listing cards.",
        }
    except httpx.RequestError:
        return {
            "success": False,
            "error": "LIST_CARDS_HTTP_ERROR",
            "message": "Network error while contacting Trello.",
        }
    except Exception:
        return {
            "success": False,
            "error": "LIST_CARDS_ERROR",
            "message": "Unexpected error while listing Trello cards.",
        }

    cards = resp.json()
    return {"success": True, "data": cards}


async def trello_get_board_cards(board_id: str = "", board_name: Optional[str] = None) -> Dict[str, Any]:
    """Get all cards on a board."""
    board_id = (board_id or "").strip()
    board_name = (board_name or "").strip() or None

    if board_id and not board_name and not _looks_like_trello_id(board_id):
        board_name = board_id
        board_id = ""

    if board_name and not board_id:
        board_result = await trello_find_board_by_name(board_name)
        if not board_result.get("success"):
            msg = board_result.get("message")
            if not isinstance(msg, str) or not msg.strip():
                msg = f"Board '{board_name}' not found."
            return {"success": False, "error": "BOARD_NOT_FOUND", "message": msg}
        data = board_result.get("data")
        if not isinstance(data, dict) or not data.get("id"):
            return {"success": False, "error": "BOARD_ID_MISSING", "message": "I couldn't resolve that Trello board."}
        board_id = str(data.get("id"))

    if not board_id:
        return {
            "success": False,
            "error": "MISSING_BOARD",
            "message": "Please provide a Trello board_id or board_name.",
        }

    params = _auth_params()
    params["fields"] = "id,name,desc,due,closed,labels,shortUrl,url"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{_TRELLO_BASE_URL}/boards/{board_id}/cards", params=params)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 404:
            return {
                "success": False,
                "error": "BOARD_NOT_FOUND",
                "message": "Trello board not found. Please provide a valid board_id or board_name.",
            }
        return {"success": False, "error": f"GET_BOARD_CARDS_ERROR: HTTP_{status}", "message": exc.response.text}
    except Exception as exc:
        return {"success": False, "error": f"GET_BOARD_CARDS_ERROR: {exc!r}"}

    cards = resp.json()
    return {"success": True, "data": cards}


async def trello_create_card(
    list_id: str,
    name: str,
    description: Optional[str] = None,
    due: Optional[str] = None,
    labels: Optional[List[str]] = None,
    members: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Create a new card with full details."""
    params = _auth_params()
    params.update({
        "idList": list_id,
        "name": name
    })
    
    if description:
        params["desc"] = description
    if due:
        params["due"] = due
    if labels:
        params["idLabels"] = ",".join(labels)
    if members:
        params["idMembers"] = ",".join(members)
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{_TRELLO_BASE_URL}/cards", params=params)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"CREATE_CARD_ERROR: {exc!r}"}
    
    card = resp.json()
    url = None
    if isinstance(card, dict):
        url = card.get("shortUrl") or card.get("url")
    msg = f"Task '{name}' has been created."
    if isinstance(url, str) and url.strip():
        msg = f"Task '{name}' has been created: {url.strip()}"
    return {"success": True, "message": msg, "data": card}


async def trello_add_comment_task(
    card_id: str = "",
    card_name: Optional[str] = None,
    board_id: str = "",
    board_name: Optional[str] = None,
    comment_text: Optional[str] = None,
    text: Optional[str] = None,
) -> Dict[str, Any]:
    card_id = (card_id or "").strip()
    board_id = (board_id or "").strip()
    board_name = (board_name or "").strip() or None
    card_name = (card_name or "").strip() or None

    note = (comment_text if isinstance(comment_text, str) else "")
    if not note.strip() and isinstance(text, str):
        note = text
    note = (note or "").strip()

    if card_id and not _looks_like_trello_id(card_id):
        card_name = card_id
        card_id = ""

    if board_id and not board_name and not _looks_like_trello_id(board_id):
        board_name = board_id
        board_id = ""

    if board_name and not board_id:
        board_result = await trello_find_board_by_name(board_name)
        if not board_result.get("success"):
            msg = board_result.get("message")
            if not isinstance(msg, str) or not msg.strip():
                msg = f"Board '{board_name}' not found."
            return {"success": False, "error": "BOARD_NOT_FOUND", "message": msg}
        data = board_result.get("data")
        if not isinstance(data, dict) or not data.get("id"):
            return {"success": False, "error": "BOARD_ID_MISSING", "message": "I couldn't resolve that Trello board."}
        board_id = str(data.get("id"))

    resolved_card_name: Optional[str] = None
    if card_name and not card_id:
        if not board_id:
            return {
                "success": False,
                "error": "MISSING_BOARD",
                "message": "Which Trello board is this task on?",
            }
        card_result = await trello_find_card_by_name(board_id, card_name)
        if not card_result.get("success"):
            msg = card_result.get("message")
            if not isinstance(msg, str) or not msg.strip():
                msg = f"I couldn't find a task called '{card_name}'."
            return {"success": False, "error": "CARD_NOT_FOUND", "message": msg}
        data = card_result.get("data")
        if isinstance(data, dict) and data.get("id"):
            card_id = str(data.get("id"))
            if isinstance(data.get("name"), str) and data.get("name").strip():
                resolved_card_name = data.get("name").strip()

    if not card_id:
        return {
            "success": False,
            "error": "MISSING_CARD",
            "message": "Which Trello task should I add the note to?",
        }

    if not note:
        payload: Dict[str, Any] = {}
        if card_id:
            payload["card_id"] = card_id
        if card_name:
            payload["card_name"] = card_name
        if board_id:
            payload["board_id"] = board_id
        if board_name:
            payload["board_name"] = board_name
        return {
            "success": True,
            "status": "comment_required",
            "message": "What note should I add to that Trello task?",
            "data": payload,
        }

    result = await trello_add_comment(card_id=card_id, text=note)
    if not result.get("success"):
        return result

    return {
        "success": True,
        "message": "Note added to the task.",
        "data": result.get("data"),
    }


def _normalize_dispatch_action(action: Optional[str]) -> str:
    a = (action or "").strip().lower()
    if not a:
        return ""

    aliases = {
        "add_comment": "comment",
        "add_note": "comment",
        "comment": "comment",
        "note": "comment",
        "notes": "comment",
        "create": "create",
        "create_task": "create",
        "create_card": "create",
        "new": "create",
        "update": "update",
        "edit": "update",
        "modify": "update",
        "move": "move",
        "status": "move",
        "set_status": "move",
        "update_status": "move",
        "delete": "delete",
        "remove": "delete",
        "delete_task": "delete",
        "archive": "archive",
        "archive_task": "archive",
        "unarchive": "archive",
        "close": "archive",
        "reopen": "archive",
    }
    return aliases.get(a, a)


def _dispatch_required(message: str, payload: Dict[str, Any], awaiting: str) -> Dict[str, Any]:
    return {
        "success": True,
        "status": "dispatch_required",
        "message": message,
        "data": {
            "tool_args": payload,
            "awaiting": awaiting,
        },
    }


def _normalize_match_text(value: Optional[str]) -> str:
    return " ".join((value or "").strip().lower().split())


def _pick_list_match(lists: List[Dict[str, Any]], requested_name: str) -> Optional[Dict[str, Any]]:
    req = _normalize_match_text(requested_name)
    if not req:
        return None

    # Exact match
    for item in lists:
        name = item.get("name")
        if isinstance(name, str) and _normalize_match_text(name) == req:
            return item

    # Substring match
    for item in lists:
        name = item.get("name")
        if isinstance(name, str) and req in _normalize_match_text(name):
            return item

    # Common status aliases
    status_aliases = {
        "pending": ["to do", "todo", "backlog"],
        "todo": ["to do", "todo"],
        "to-do": ["to do", "todo"],
        "in progress": ["in progress", "doing"],
        "in-progress": ["in progress", "doing"],
        "doing": ["in progress", "doing"],
        "done": ["done", "completed"],
        "completed": ["done", "completed"],
        "complete": ["done", "completed"],
        "on hold": ["on hold", "hold"],
        "hold": ["on hold", "hold"],
        "cancelled": ["cancelled", "canceled"],
        "canceled": ["cancelled", "canceled"],
        "cancel": ["cancelled", "canceled"],
    }
    candidates = status_aliases.get(req)
    if candidates:
        normalized_candidates = [_normalize_match_text(c) for c in candidates]
        for item in lists:
            name = item.get("name")
            if not isinstance(name, str):
                continue
            n = _normalize_match_text(name)
            if any(n == c or c in n for c in normalized_candidates):
                return item

    return None


def _infer_action(
    action: Optional[str],
    fields: Optional[Dict[str, Any]],
    note: str,
    to_list_id: str,
    to_list_name: Optional[str],
    title: Optional[str],
    description: Optional[str],
    due: Optional[str],
    due_date: Optional[str],
) -> str:
    resolved = _normalize_dispatch_action(action)

    if note.strip():
        if resolved in {"", "update", "move"}:
            return "comment"

    if (to_list_id or (to_list_name or "").strip()):
        if resolved in {"", "update", "move"}:
            return "move"

    if resolved == "" and isinstance(fields, dict) and fields:
        return "update"

    if resolved == "" and (title or description or due or due_date):
        return "update"

    return resolved


def _normalize_note(comment_text: Optional[str], text: Optional[str], fields: Optional[Dict[str, Any]]) -> str:
    note = (comment_text if isinstance(comment_text, str) else "")
    if not note.strip() and isinstance(text, str):
        note = text

    if isinstance(fields, dict) and not note.strip():
        for k in ["comment_text", "note_text", "comment", "note", "text"]:
            if isinstance(fields.get(k), str) and str(fields.get(k)).strip():
                note = str(fields.get(k)).strip()
                break

    return (note or "").strip()


def _normalize_field_key(key: str) -> str:
    if not isinstance(key, str) or not key:
        return ""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s


def _extract_status_target(fields: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(fields, dict) or not fields:
        return None
    for raw_key, value in fields.items():
        key = _normalize_field_key(raw_key)
        if key in {"status", "list", "list_name", "to_list", "to_list_name"}:
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _extract_to_list_id(fields: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(fields, dict) or not fields:
        return None
    for raw_key, value in fields.items():
        key = _normalize_field_key(raw_key)
        if key in {"idlist", "id_list", "list_id", "to_list_id"}:
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _build_update_fields(
    fields: Optional[Dict[str, Any]],
    title: Optional[str],
    description: Optional[str],
    due: Optional[str],
    due_date: Optional[str],
    labels: Optional[List[str]],
    members: Optional[List[str]],
) -> Dict[str, Any]:
    update_fields: Dict[str, Any] = {}
    if isinstance(fields, dict):
        update_fields.update(fields)
    if isinstance(title, str) and title.strip():
        update_fields["name"] = title.strip()
    if isinstance(description, str) and description.strip():
        update_fields["description"] = description.strip()
    if isinstance(due, str) and due.strip():
        update_fields["due"] = due.strip()
    if isinstance(due_date, str) and due_date.strip() and "due" not in update_fields:
        update_fields["due"] = due_date.strip()
    if isinstance(labels, list) and labels and "labels" not in update_fields:
        update_fields["labels"] = labels
    if isinstance(members, list) and members and "members" not in update_fields:
        update_fields["members"] = members

    forbidden = {
        "comment_text",
        "note_text",
        "comment",
        "note",
        "text",
        "status",
        "list",
        "list_name",
        "to_list",
        "to_list_name",
        "idlist",
        "id_list",
        "list_id",
        "to_list_id",
    }
    for k in list(update_fields.keys()):
        if _normalize_field_key(k) in forbidden:
            update_fields.pop(k, None)

    return update_fields


async def _resolve_board_id(board_id: str, board_name: Optional[str]) -> Dict[str, Any]:
    board_id = (board_id or "").strip()
    board_name = (board_name or "").strip() or None

    if board_id and not board_name and not _looks_like_trello_id(board_id):
        board_name = board_id
        board_id = ""

    if board_name and not board_id:
        board_result = await trello_find_board_by_name(board_name)
        if not board_result.get("success"):
            msg = board_result.get("message")
            if not isinstance(msg, str) or not msg.strip():
                msg = f"Board '{board_name}' not found."
            return {"success": False, "error": "BOARD_NOT_FOUND", "message": msg}
        data = board_result.get("data")
        if not isinstance(data, dict) or not data.get("id"):
            return {"success": False, "error": "BOARD_ID_MISSING", "message": "I couldn't resolve that Trello board."}
        board_id = str(data.get("id"))

    return {"success": True, "data": {"board_id": board_id, "board_name": board_name}}


async def _resolve_card_id(
    card_id: str,
    card_name: Optional[str],
    board_id: str,
    board_name: Optional[str],
) -> Dict[str, Any]:
    card_id = (card_id or "").strip()
    card_name = (card_name or "").strip() or None

    if card_id and not _looks_like_trello_id(card_id):
        card_name = card_id
        card_id = ""

    if card_id:
        return {"success": True, "data": {"card_id": card_id, "card_name": card_name}}

    if not card_name:
        return {"success": True, "data": {"card_id": "", "card_name": None}}

    if board_id:
        card_result = await trello_find_card_by_name(board_id, card_name)
        if not card_result.get("success"):
            msg = card_result.get("message")
            if not isinstance(msg, str) or not msg.strip():
                msg = f"I couldn't find a task called '{card_name}'."
            return {"success": False, "error": "CARD_NOT_FOUND", "message": msg}
        data = card_result.get("data")
        if not isinstance(data, dict) or not data.get("id"):
            return {"success": False, "error": "CARD_ID_MISSING", "message": "I couldn't resolve that Trello task."}
        resolved_name = data.get("name") if isinstance(data.get("name"), str) else card_name
        return {"success": True, "data": {"card_id": str(data.get("id")), "card_name": resolved_name}}

    search = await trello_search_cards(card_name)
    if search.get("success") is True and isinstance(search.get("data"), list):
        matches: List[Dict[str, Any]] = []
        needle = _normalize_match_text(card_name)
        for item in search.get("data"):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            n = item.get("name")
            if isinstance(n, str) and _normalize_match_text(n) == needle:
                matches.append(item)

        if len(matches) == 1:
            hit = matches[0]
            resolved_name = hit.get("name") if isinstance(hit.get("name"), str) else card_name
            return {
                "success": True,
                "data": {
                    "card_id": str(hit.get("id")),
                    "card_name": resolved_name,
                    "board_id": str(hit.get("idBoard")) if isinstance(hit.get("idBoard"), str) else "",
                },
            }

    payload: Dict[str, Any] = {"card_name": card_name, "board_id": board_id, "board_name": board_name}
    return _dispatch_required("Which Trello board is that task on?", payload, "board_name")


async def trello_dispatch(
    action: Optional[str] = None,
    card_id: str = "",
    card_name: Optional[str] = None,
    board_id: str = "",
    board_name: Optional[str] = None,
    list_id: str = "",
    list_name: Optional[str] = None,
    to_list_id: str = "",
    to_list_name: Optional[str] = None,
    to_board_id: str = "",
    to_board_name: Optional[str] = None,
    status: Optional[str] = None,
    fields: Optional[Dict[str, Any]] = None,
    comment_text: Optional[str] = None,
    text: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    due: Optional[str] = None,
    due_date: Optional[str] = None,
    labels: Optional[List[str]] = None,
    members: Optional[List[str]] = None,
    archive: Optional[bool] = None,
    confirm: bool = False,
    **kwargs: Any,
) -> Dict[str, Any]:
    raw_action = (action or "").strip().lower()
    implied_archive: Optional[bool] = None
    if raw_action in {"unarchive", "reopen"}:
        implied_archive = False
    elif raw_action in {"archive", "close"}:
        implied_archive = True

    card_id = (card_id or "").strip()
    board_id = (board_id or "").strip()
    list_id = (list_id or "").strip()
    to_list_id = (to_list_id or "").strip()
    to_board_id = (to_board_id or "").strip()

    card_name = (card_name or "").strip() or None
    board_name = (board_name or "").strip() or None
    list_name = (list_name or "").strip() or None
    to_list_name = (to_list_name or "").strip() or None
    to_board_name = (to_board_name or "").strip() or None

    note = _normalize_note(comment_text=comment_text, text=text, fields=fields)
    status_value = (status or "").strip() or _extract_status_target(fields)
    embedded_to_list_id = _extract_to_list_id(fields)
    if embedded_to_list_id and not to_list_id:
        to_list_id = embedded_to_list_id
    if raw_action not in {"status", "get_status", "check_status"} and status_value and not to_list_id and not to_list_name:
        to_list_name = status_value

    action = _infer_action(
        action=action,
        fields=fields,
        note=note,
        to_list_id=to_list_id,
        to_list_name=to_list_name,
        title=title,
        description=description,
        due=due,
        due_date=due_date,
    )

    if action not in {"create", "update", "move", "comment", "delete", "archive", "status"}:
        return {
            "success": False,
            "error": "UNKNOWN_ACTION",
            "message": "Please specify a Trello action: create, update, move, comment, delete, or archive.",
        }

    if action == "status":
        if not card_id and not card_name:
            payload = {"action": action, "card_id": card_id, "card_name": card_name, "board_id": board_id, "board_name": board_name}
            return _dispatch_required("Which Trello task should I check the status for?", payload, "card_name")
        return await trello_get_card_status(card_id=card_id, card_name=card_name, board_id=board_id, board_name=board_name)

    board_resolution = await _resolve_board_id(board_id=board_id, board_name=board_name)
    if board_resolution.get("success") is False:
        return board_resolution
    board_payload = board_resolution.get("data")
    resolved_board_id = ""
    if isinstance(board_payload, dict) and isinstance(board_payload.get("board_id"), str):
        resolved_board_id = board_payload.get("board_id")

    resolved_card_name: Optional[str] = None
    card_resolution = await _resolve_card_id(
        card_id=card_id,
        card_name=card_name,
        board_id=resolved_board_id,
        board_name=board_name,
    )
    if isinstance(card_resolution, dict) and card_resolution.get("status") == "dispatch_required":
        data = card_resolution.get("data")
        if isinstance(data, dict) and isinstance(data.get("tool_args"), dict):
            merged = dict(data.get("tool_args"))
            merged.update(
                {
                    "action": action,
                    "card_id": card_id,
                    "card_name": card_name,
                    "board_id": board_id,
                    "board_name": board_name,
                    "list_id": list_id,
                    "list_name": list_name,
                    "to_list_id": to_list_id,
                    "to_list_name": to_list_name,
                    "fields": fields,
                    "comment_text": note,
                    "title": title,
                    "description": description,
                    "due": due,
                    "due_date": due_date,
                    "archive": archive,
                    "confirm": confirm,
                }
            )
            data["tool_args"] = merged
        return card_resolution
    if card_resolution.get("success") is False:
        return card_resolution
    card_data = card_resolution.get("data")
    if isinstance(card_data, dict):
        if isinstance(card_data.get("card_id"), str):
            card_id = card_data.get("card_id")
        if isinstance(card_data.get("card_name"), str) and card_data.get("card_name").strip():
            resolved_card_name = card_data.get("card_name").strip()
        if not resolved_board_id and isinstance(card_data.get("board_id"), str) and card_data.get("board_id").strip():
            resolved_board_id = card_data.get("board_id").strip()

    # Cross-board move heuristic:
    # If the user provided board_name but did not explicitly set to_board_* and we already
    # resolved the card's board, treat board_name as destination if it resolves to a different board.
    if action == "move" and not to_board_id and not to_board_name and board_name and resolved_board_id:
        dest_guess = await _resolve_board_id(board_id="", board_name=board_name)
        if dest_guess.get("success") is True:
            dest_data = dest_guess.get("data")
            if isinstance(dest_data, dict) and isinstance(dest_data.get("board_id"), str):
                guessed_id = dest_data.get("board_id")
                if guessed_id and guessed_id != resolved_board_id:
                    to_board_id = guessed_id
                    to_board_name = board_name

    if action == "create":
        task_title = (title or "").strip()
        if not task_title and isinstance(fields, dict) and isinstance(fields.get("name"), str):
            task_title = str(fields.get("name")).strip()
        if not task_title and isinstance(fields, dict) and isinstance(fields.get("title"), str):
            task_title = str(fields.get("title")).strip()

        if not task_title:
            payload = {
                "action": action,
                "board_id": board_id,
                "board_name": board_name,
                "list_id": list_id,
                "list_name": list_name,
                "description": description,
            }
            return _dispatch_required("What should I name this Trello task?", payload, "title")

        if not resolved_board_id and not list_id:
            payload = {
                "action": action,
                "title": task_title,
                "description": description,
                "board_id": board_id,
                "board_name": board_name,
                "list_id": list_id,
                "list_name": list_name,
            }
            return _dispatch_required("Which Trello board should I add this task to?", payload, "board_name")

        return await trello_create_task(
            name=task_title,
            description=description,
            due=due or due_date,
            labels=labels,
            members=members,
            board_id=resolved_board_id,
            board_name=board_name,
            list_id=list_id,
            list_name=list_name,
            use_first_list=True,
        )

    if action == "comment":
        if not card_id:
            payload = {
                "action": action,
                "card_id": card_id,
                "card_name": card_name,
                "board_id": board_id,
                "board_name": board_name,
                "comment_text": note,
            }
            return _dispatch_required("Which Trello task should I add the note to?", payload, "card_name")
        return await trello_add_comment_task(
            card_id=card_id,
            card_name=card_name,
            board_id=resolved_board_id,
            board_name=board_name,
            comment_text=note,
        )

    if action == "update":
        if not card_id:
            payload = {
                "action": action,
                "card_id": card_id,
                "card_name": card_name,
                "board_id": board_id,
                "board_name": board_name,
                "fields": fields,
                "title": title,
                "description": description,
                "due": due,
                "due_date": due_date,
            }
            return _dispatch_required("Which Trello task should I update?", payload, "card_name")

        update_fields = _build_update_fields(
            fields=fields,
            title=title,
            description=description,
            due=due,
            due_date=due_date,
            labels=labels,
            members=members,
        )

        if not update_fields:
            return {
                "success": False,
                "error": "MISSING_FIELDS",
                "message": "I can't update a Trello task without specifying at least one field to change.",
            }

        return await trello_update_card(card_id, update_fields)

    if action == "move":
        if not card_id:
            payload = {
                "action": action,
                "card_id": card_id,
                "card_name": card_name,
                "board_id": board_id,
                "board_name": board_name,
                "to_list_id": to_list_id,
                "to_list_name": to_list_name,
            }
            return _dispatch_required("Which Trello task should I move?", payload, "card_name")

        if to_list_id and not _looks_like_trello_id(to_list_id):
            to_list_name = to_list_id
            to_list_id = ""

        destination_board_id = resolved_board_id
        if to_board_id or to_board_name:
            dest_resolution = await _resolve_board_id(board_id=to_board_id, board_name=to_board_name)
            if dest_resolution.get("success") is False:
                return dest_resolution
            dest_payload = dest_resolution.get("data")
            if isinstance(dest_payload, dict) and isinstance(dest_payload.get("board_id"), str) and dest_payload.get("board_id").strip():
                destination_board_id = dest_payload.get("board_id").strip()

        if not to_list_id and to_list_name:
            if not resolved_board_id:
                full = await trello_get_card(card_id)
                if full.get("success") and isinstance(full.get("data"), dict):
                    data = full.get("data")
                    if isinstance(data.get("idBoard"), str) and data.get("idBoard").strip():
                        resolved_board_id = data.get("idBoard").strip()
                    if not resolved_card_name and isinstance(data.get("name"), str) and data.get("name").strip():
                        resolved_card_name = data.get("name").strip()

            if not destination_board_id:
                destination_board_id = resolved_board_id

            if not resolved_board_id:
                payload = {
                    "action": action,
                    "card_id": card_id,
                    "card_name": resolved_card_name or card_name,
                    "board_id": board_id,
                    "board_name": board_name,
                    "to_list_name": to_list_name,
                }
                return _dispatch_required("Which Trello board is that task on?", payload, "board_name")

            lists_result = await trello_list_lists(destination_board_id)
            if not lists_result.get("success"):
                return lists_result
            lists_data = lists_result.get("data")
            if not isinstance(lists_data, list) or not lists_data:
                return {"success": False, "error": "NO_LISTS", "message": "This board has no lists."}

            picked = _pick_list_match(lists_data, to_list_name)
            if not isinstance(picked, dict) or not picked.get("id"):
                available_names: List[str] = []
                for item in lists_data:
                    n = item.get("name")
                    if isinstance(n, str) and n.strip():
                        available_names.append(n.strip())
                available_part = "\n".join([f"- {n}" for n in available_names])
                msg = f"I couldn't find a Trello list named '{to_list_name}'. Which list should I move it to?"
                if available_part:
                    msg = f"I couldn't find a Trello list named '{to_list_name}'. Available lists are:\n{available_part}\nWhich one should I use?"
                payload = {
                    "action": action,
                    "card_id": card_id,
                    "card_name": resolved_card_name or card_name,
                    "board_id": resolved_board_id,
                    "board_name": board_name,
                    "to_board_id": destination_board_id,
                    "to_board_name": to_board_name,
                }
                return _dispatch_required(msg, payload, "to_list_name")

            to_list_id = str(picked.get("id"))
            if isinstance(picked.get("name"), str) and picked.get("name").strip():
                to_list_name = picked.get("name").strip()

        if not to_list_id:
            payload = {
                "action": action,
                "card_id": card_id,
                "card_name": resolved_card_name or card_name,
                "board_id": board_id,
                "board_name": board_name,
                "to_board_id": destination_board_id if destination_board_id and destination_board_id != resolved_board_id else to_board_id,
                "to_board_name": to_board_name,
            }
            return _dispatch_required("Which Trello list should I move it to?", payload, "to_list_name")

        move_result = await trello_move_card(
            card_id=card_id,
            list_id=to_list_id,
            board_id=destination_board_id if destination_board_id and destination_board_id != resolved_board_id else None,
        )
        if not move_result.get("success"):
            return move_result
        name_part = resolved_card_name or card_name
        list_part = to_list_name
        if isinstance(name_part, str) and name_part.strip() and isinstance(list_part, str) and list_part.strip():
            return {"success": True, "message": f"Task '{name_part.strip()}' moved to '{list_part.strip()}'.", "data": move_result.get("data")}
        if isinstance(name_part, str) and name_part.strip():
            return {"success": True, "message": f"Task '{name_part.strip()}' moved.", "data": move_result.get("data")}
        return {"success": True, "message": "Task moved.", "data": move_result.get("data")}

    if action == "delete":
        result = await trello_delete_task(
            card_id=card_id,
            card_name=card_name,
            board_id=resolved_board_id,
            board_name=board_name,
            confirm=confirm,
        )

        if isinstance(result, dict) and result.get("status") == "confirmation_required":
            data = result.get("data")
            if isinstance(data, dict):
                wrapped = dict(data)
                wrapped["action"] = "delete"
                return {
                    "status": "confirmation_required",
                    "message": result.get("message"),
                    "data": wrapped,
                }
        return result

    if action == "archive":
        desired_archive = True
        if isinstance(archive, bool):
            desired_archive = archive
        elif isinstance(implied_archive, bool):
            desired_archive = implied_archive

        result = await trello_archive_card(
            card_id=card_id,
            card_name=card_name,
            board_id=resolved_board_id,
            board_name=board_name,
            archive=desired_archive,
            confirm=confirm,
        )

        if isinstance(result, dict) and result.get("status") == "confirmation_required":
            data = result.get("data")
            if isinstance(data, dict):
                wrapped = dict(data)
                wrapped["action"] = "archive"
                wrapped["archive"] = desired_archive
                return {
                    "status": "confirmation_required",
                    "message": result.get("message"),
                    "data": wrapped,
                }
        return result

    return {"success": False, "error": "UNREACHABLE", "message": "Unsupported Trello request."}


async def trello_create_task(
    name: str = "",
    description: Optional[str] = None,
    due: Optional[str] = None,
    labels: Optional[List[str]] = None,
    members: Optional[List[str]] = None,
    board_id: str = "",
    board_name: Optional[str] = None,
    list_id: str = "",
    list_name: Optional[str] = None,
    use_first_list: bool = False,
    list_index: Optional[int] = None,
) -> Dict[str, Any]:
    name = (name or "").strip()
    board_id = (board_id or "").strip()
    board_name = (board_name or "").strip() or None
    list_id = (list_id or "").strip()
    list_name = (list_name or "").strip() or None

    if not name:
        return {"success": False, "error": "MISSING_NAME", "message": "What should I name this task?"}

    if board_name and not board_id:
        board_result = await trello_find_board_by_name(board_name)
        if not board_result.get("success"):
            msg = board_result.get("message")
            if not isinstance(msg, str) or not msg.strip():
                msg = f"Board '{board_name}' not found."
            return {"success": False, "error": "BOARD_NOT_FOUND", "message": msg}
        data = board_result.get("data")
        if not isinstance(data, dict) or not data.get("id"):
            return {"success": False, "error": "BOARD_ID_MISSING", "message": "I couldn't resolve that Trello board."}
        board_id = str(data.get("id"))

    if not board_id and not list_id:
        return {
            "success": False,
            "error": "MISSING_BOARD",
            "message": "Please provide the board (board_id or board_name) for this task.",
        }

    if list_id and not _looks_like_trello_id(list_id):
        list_name = list_id
        list_id = ""

    if not list_id and board_id:
        lists_result = await trello_list_lists(board_id)
        if not lists_result.get("success"):
            return lists_result

        lists = lists_result.get("data")
        if not isinstance(lists, list) or not lists:
            return {"success": False, "error": "NO_LISTS", "message": "This board has no lists. Please create a list first."}

        if list_name:
            list_result = await trello_find_list_by_name(board_id, list_name)
            if not list_result.get("success"):
                msg = list_result.get("message")
                if not isinstance(msg, str) or not msg.strip():
                    msg = f"List '{list_name}' not found."
                return {"success": False, "error": "LIST_NOT_FOUND", "message": msg}
            data = list_result.get("data")
            if not isinstance(data, dict) or not data.get("id"):
                return {"success": False, "error": "LIST_ID_MISSING", "message": "I couldn't resolve that Trello list."}
            list_id = str(data.get("id"))
        elif isinstance(list_index, int) and 1 <= list_index <= len(lists):
            picked = lists[list_index - 1]
            if isinstance(picked, dict) and picked.get("id"):
                list_id = str(picked.get("id"))
            else:
                list_id = str(lists[0].get("id"))
        elif use_first_list is True:
            list_id = str(lists[0].get("id"))
        else:
            list_id = str(lists[0].get("id"))

    if not list_id:
        return {
            "success": False,
            "error": "MISSING_LIST",
            "message": "Please provide a Trello list (list_id or list_name) for this task.",
        }

    return await trello_create_card(
        list_id=list_id,
        name=name,
        description=description,
        due=due,
        labels=labels,
        members=members,
    )


async def trello_get_card_link(
    card_id: str = "",
    card_name: Optional[str] = None,
    board_id: str = "",
    board_name: Optional[str] = None,
) -> Dict[str, Any]:
    card_id = (card_id or "").strip()
    card_name = (card_name or "").strip() or None
    board_id = (board_id or "").strip()
    board_name = (board_name or "").strip() or None

    card: Optional[Dict[str, Any]] = None

    if card_id:
        result = await trello_get_card(card_id)
        if not result.get("success"):
            return result
        data = result.get("data")
        if isinstance(data, dict):
            card = data

    if not card and card_name:
        if not board_id and board_name:
            board_result = await trello_find_board_by_name(board_name)
            if not board_result.get("success"):
                msg = board_result.get("message")
                if not isinstance(msg, str) or not msg.strip():
                    msg = f"Board '{board_name}' not found."
                return {"success": False, "error": "BOARD_NOT_FOUND", "message": msg}
            board_data = board_result.get("data")
            if not isinstance(board_data, dict) or not board_data.get("id"):
                return {"success": False, "error": "BOARD_ID_MISSING", "message": "I couldn't resolve that Trello board."}
            board_id = str(board_data.get("id"))

        if not board_id:
            return {"success": False, "error": "MISSING_BOARD", "message": "Please provide the board (board_id or board_name) for that task."}

        card_result = await trello_find_card_by_name(board_id, card_name)
        if not card_result.get("success"):
            msg = card_result.get("message")
            if not isinstance(msg, str) or not msg.strip():
                msg = f"Task '{card_name}' not found."
            return {"success": False, "error": "CARD_NOT_FOUND", "message": msg}
        data = card_result.get("data")
        if isinstance(data, dict):
            card = data

    if not card:
        return {
            "success": False,
            "error": "MISSING_CARD",
            "message": "Please provide a Trello card_id, or a card_name with its board.",
        }

    url = card.get("shortUrl") or card.get("url")
    if not isinstance(url, str) or not url.strip():
        return {
            "success": False,
            "error": "CARD_URL_MISSING",
            "message": "I found the task, but Trello didn't return a shareable link.",
        }

    name = card.get("name") or card_name or "Untitled"
    return {
        "success": True,
        "message": f"Here is the link to '{name}': {url}",
        "data": {"card_id": str(card.get("id", "")), "name": name, "url": url},
    }


async def trello_get_list(list_id: str) -> Dict[str, Any]:
    """Get a Trello list by ID."""
    list_id = (list_id or "").strip()
    if not list_id or not _looks_like_trello_id(list_id):
        return {"success": False, "error": "INVALID_LIST_ID", "message": "Invalid Trello list id."}

    params = _auth_params()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{_TRELLO_BASE_URL}/lists/{list_id}", params=params)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        msg = "Trello returned an error while fetching that list."
        if status == 404:
            msg = "I couldn't find that Trello list (it may be archived or I don't have access)."
        return {"success": False, "error": f"GET_LIST_ERROR:{status}", "message": msg}
    except httpx.RequestError:
        return {"success": False, "error": "GET_LIST_HTTP_ERROR", "message": "Network error while contacting Trello."}
    except Exception:
        return {"success": False, "error": "GET_LIST_ERROR", "message": "Unexpected error while fetching the Trello list."}

    data = resp.json()
    return {"success": True, "data": data}


async def trello_get_card_status(
    card_id: str = "",
    card_name: Optional[str] = None,
    board_id: str = "",
    board_name: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Get the current status (list) of a Trello card."""
    _ = kwargs

    card_id = (card_id or "").strip()
    card_name = (card_name or "").strip() or None
    board_id = (board_id or "").strip()
    board_name = (board_name or "").strip() or None

    if board_name and not board_id:
        board_res = await _resolve_board_id(board_id=board_id, board_name=board_name)
        if board_res.get("success") is False:
            return board_res
        bdata = board_res.get("data")
        if isinstance(bdata, dict) and isinstance(bdata.get("board_id"), str):
            board_id = bdata.get("board_id")

    card_res = await _resolve_card_id(card_id=card_id, card_name=card_name, board_id=board_id, board_name=board_name)
    if card_res.get("status") == "dispatch_required":
        return card_res
    if card_res.get("success") is False:
        return card_res

    resolved = card_res.get("data")
    if not isinstance(resolved, dict) or not isinstance(resolved.get("card_id"), str) or not resolved.get("card_id"):
        payload: Dict[str, Any] = {"card_id": card_id, "card_name": card_name, "board_id": board_id, "board_name": board_name}
        return _dispatch_required("Which Trello task should I check the status for?", payload, "card_name")

    card_id = str(resolved.get("card_id") or "").strip()
    if isinstance(resolved.get("card_name"), str) and str(resolved.get("card_name") or "").strip():
        card_name = str(resolved.get("card_name") or "").strip()
    if isinstance(resolved.get("board_id"), str) and str(resolved.get("board_id") or "").strip() and not board_id:
        board_id = str(resolved.get("board_id") or "").strip()

    full = await trello_get_card(card_id)
    if not full.get("success"):
        return full
    card = full.get("data")
    if not isinstance(card, dict):
        return {"success": False, "error": "CARD_DATA_INVALID", "message": "I couldn't read the Trello card details."}

    list_id = str(card.get("idList") or "").strip()
    if not board_id:
        board_id = str(card.get("idBoard") or "").strip()

    if not list_id or not _looks_like_trello_id(list_id):
        return {"success": False, "error": "LIST_ID_MISSING", "message": "I found the card, but Trello didn't include its list."}

    list_result = await trello_get_list(list_id)
    list_name = None
    if list_result.get("success") is True and isinstance(list_result.get("data"), dict):
        ln = list_result.get("data").get("name")
        if isinstance(ln, str) and ln.strip():
            list_name = ln.strip()

    resolved_board_name = board_name
    if not resolved_board_name and board_id and _looks_like_trello_id(board_id):
        boards_result = await trello_list_boards()
        boards = boards_result.get("data") if isinstance(boards_result, dict) else None
        if isinstance(boards, list):
            for b in boards:
                if isinstance(b, dict) and str(b.get("id") or "").strip() == board_id:
                    bn = b.get("name")
                    if isinstance(bn, str) and bn.strip():
                        resolved_board_name = bn.strip()
                    break

    card_title = card.get("name")
    if isinstance(card_title, str) and card_title.strip():
        card_name = card_title.strip()

    status_label = list_name or list_id
    task_label = card_name or card_id
    if resolved_board_name:
        msg = f"Status: {status_label}. Task: {task_label}. Board: {resolved_board_name}."
    else:
        msg = f"Status: {status_label}. Task: {task_label}."

    return {
        "success": True,
        "message": msg,
        "data": {
            "card_id": card_id,
            "card_name": card_name,
            "board_id": board_id,
            "board_name": resolved_board_name,
            "list_id": list_id,
            "list_name": list_name,
            "status_label": status_label,
        },
    }


async def trello_get_card(card_id: str) -> Dict[str, Any]:
    """Get a single card by ID."""
    params = _auth_params()
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{_TRELLO_BASE_URL}/cards/{card_id}", params=params)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        msg = "Trello returned an error while fetching that card."
        if status == 404:
            msg = "I couldn't find that Trello card (it may not exist or I don't have access)."
        return {"success": False, "error": f"GET_CARD_ERROR:{status}", "message": msg}
    except httpx.RequestError:
        return {"success": False, "error": "GET_CARD_HTTP_ERROR", "message": "Network error while contacting Trello."}
    except Exception:
        return {"success": False, "error": "GET_CARD_ERROR", "message": "Unexpected error while fetching the Trello card."}
    
    card = resp.json()
    return {"success": True, "data": card}


async def trello_update_card(card_id: str, fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Update card fields."""
    card_id = (card_id or "").strip()
    if not isinstance(fields, dict) or not fields:
        return {
            "success": False,
            "error": "MISSING_FIELDS",
            "message": "Please provide at least one field to update.",
        }

    forbidden = {
        "comment_text",
        "note_text",
        "comment",
        "note",
        "text",
        "status",
        "list",
        "list_name",
        "to_list",
        "to_list_name",
        "idlist",
        "id_list",
        "list_id",
        "to_list_id",
    }
    cleaned_fields: Dict[str, Any] = {}
    for k, v in fields.items():
        if _normalize_field_key(k) in forbidden:
            continue
        cleaned_fields[k] = v
    fields = cleaned_fields

    if not fields:
        return {
            "success": False,
            "error": "MISSING_FIELDS",
            "message": "I can't update a Trello task without specifying at least one field to change.",
        }

    if "due_date" in fields and "due" not in fields:
        fields["due"] = fields.get("due_date")

    params = _auth_params()
    
    field_mapping = {
        "name": "name",
        "title": "name",
        "description": "desc",
        "desc": "desc",
        "due": "due",
        "due_date": "due",
        "labels": "idLabels",
        "members": "idMembers",
        "closed": "closed"
    }
    
    for key, value in fields.items():
        mapped_key = field_mapping.get(key, key)
        if mapped_key == "idLabels" and isinstance(value, list):
            params[mapped_key] = ",".join(value)
        elif mapped_key == "idMembers" and isinstance(value, list):
            params[mapped_key] = ",".join(value)
        else:
            params[mapped_key] = value
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.put(f"{_TRELLO_BASE_URL}/cards/{card_id}", params=params)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        msg = "Trello returned an error while updating that card."
        if status == 404:
            msg = "I couldn't find that Trello card (it may not exist or I don't have access)."
        return {"success": False, "error": f"UPDATE_CARD_ERROR:{status}", "message": msg}
    except httpx.RequestError:
        return {"success": False, "error": "UPDATE_CARD_HTTP_ERROR", "message": "Network error while contacting Trello."}
    except Exception:
        return {"success": False, "error": "UPDATE_CARD_ERROR", "message": "Unexpected error while updating the Trello card."}
    
    card = resp.json()
    name = None
    due = None
    if isinstance(card, dict):
        if isinstance(card.get("name"), str) and card.get("name").strip():
            name = card.get("name").strip()
        due = card.get("due")

    if "due" in fields or "due_date" in fields:
        due_str = str(due) if due is not None else ""
        if due_str.strip():
            msg = f"Task '{name or '(untitled task)'}' due date updated to {due_str.strip()}."
        else:
            msg = f"Task '{name or '(untitled task)'}' due date updated."
    else:
        msg = f"Task '{name or '(untitled task)'}' has been updated."

    return {"success": True, "message": msg, "data": card}


async def trello_move_card(card_id: str, list_id: str, board_id: Optional[str] = None) -> Dict[str, Any]:
    """Move a card to a different list or board."""
    card_id = (card_id or "").strip()
    list_id = (list_id or "").strip()

    if not _looks_like_trello_id(card_id):
        return {
            "success": False,
            "error": "INVALID_CARD_ID",
            "message": "That doesn't look like a valid Trello card ID.",
        }
    if not _looks_like_trello_id(list_id):
        return {
            "success": False,
            "error": "INVALID_LIST_ID",
            "message": "That doesn't look like a valid Trello list ID.",
        }

    params = _auth_params()
    params["idList"] = list_id
    
    if board_id:
        params["idBoard"] = board_id
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.put(f"{_TRELLO_BASE_URL}/cards/{card_id}", params=params)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        msg = "Trello returned an error while moving that card."
        if status == 404:
            msg = "I couldn't find that Trello card (it may not exist or I don't have access)."
        return {"success": False, "error": f"MOVE_CARD_ERROR:{status}", "message": msg}
    except httpx.RequestError:
        return {"success": False, "error": "MOVE_CARD_HTTP_ERROR", "message": "Network error while contacting Trello."}
    except Exception:
        return {"success": False, "error": "MOVE_CARD_ERROR", "message": "Unexpected error while moving the Trello card."}
    
    card = resp.json()
    return {"success": True, "data": card}


async def trello_delete_card(card_id: str) -> Dict[str, Any]:
    """Delete a card permanently."""
    card_id = (card_id or "").strip()
    if not _looks_like_trello_id(card_id):
        return {
            "success": False,
            "error": "INVALID_CARD_ID",
            "message": "That doesn't look like a valid Trello card ID. If you want to delete/archive a task by name, use trello_delete_task or trello_archive_card. If you're trying to delete/archive a list, use trello_archive_list instead.",
        }

    params = _auth_params()
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.delete(f"{_TRELLO_BASE_URL}/cards/{card_id}", params=params)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"DELETE_CARD_ERROR: {exc!r}"}
    
    return {"success": True, "data": {"message": "Card deleted successfully"}}


async def trello_archive_card(
    card_id: str = "",
    card_name: Optional[str] = None,
    board_id: str = "",
    board_name: Optional[str] = None,
    archive: bool = True,
    confirm: bool = False,
) -> Dict[str, Any]:
    card_id = (card_id or "").strip()
    card_name = (card_name or "").strip() or None
    board_id = (board_id or "").strip()
    board_name = (board_name or "").strip() or None

    if board_id and not board_name and not _looks_like_trello_id(board_id):
        board_name = board_id
        board_id = ""

    if board_name and not board_id:
        board_result = await trello_find_board_by_name(board_name)
        if not board_result.get("success"):
            msg = board_result.get("message")
            if not isinstance(msg, str) or not msg.strip():
                msg = f"Board '{board_name}' not found."
            return {"success": False, "error": "BOARD_NOT_FOUND", "message": msg}
        data = board_result.get("data")
        if not isinstance(data, dict) or not data.get("id"):
            return {"success": False, "error": "BOARD_ID_MISSING", "message": "I couldn't resolve that Trello board."}
        board_id = str(data.get("id"))

    resolved_card: Optional[Dict[str, Any]] = None
    if card_name and not card_id:
        if not board_id:
            return {
                "success": False,
                "error": "MISSING_BOARD",
                "message": "Please provide the board (board_id or board_name) to find that task.",
            }
        card_result = await trello_find_card_by_name(board_id, card_name)
        if not card_result.get("success"):
            msg = card_result.get("message")
            if not isinstance(msg, str) or not msg.strip():
                msg = f"Task '{card_name}' not found."
            return {"success": False, "error": "CARD_NOT_FOUND", "message": msg}
        data = card_result.get("data")
        if not isinstance(data, dict) or not data.get("id"):
            return {"success": False, "error": "CARD_ID_MISSING", "message": "I couldn't resolve that Trello task."}
        resolved_card = data
        card_id = str(data.get("id"))

    if not card_id:
        return {
            "success": False,
            "error": "MISSING_CARD",
            "message": "Please provide a Trello card_id or card_name.",
        }

    if resolved_card is None:
        full = await trello_get_card(card_id)
        if full.get("success") and isinstance(full.get("data"), dict):
            resolved_card = full.get("data")

    resolved_name = None
    url = None
    if isinstance(resolved_card, dict):
        if isinstance(resolved_card.get("name"), str) and resolved_card.get("name").strip():
            resolved_name = resolved_card.get("name").strip()
        url = resolved_card.get("shortUrl") or resolved_card.get("url")
        if isinstance(url, str):
            url = url.strip()

    if confirm is not True:
        action_word = "archive" if archive else "unarchive"
        name_part = f" '{resolved_name}'" if isinstance(resolved_name, str) and resolved_name.strip() else ""
        msg = f"To proceed with {action_word}ing the task{name_part}, please reply with YES or PROCEED."
        if isinstance(url, str) and url.strip():
            msg = f"To proceed with {action_word}ing the task{name_part}: {url.strip()}\nPlease reply with YES or PROCEED."
        return {
            "status": "confirmation_required",
            "message": msg,
            "data": {
                "card_id": card_id,
                "card_name": resolved_name,
                "board_id": board_id,
                "board_name": board_name,
                "archive": archive,
            },
        }

    update_result = await trello_update_card(card_id, {"closed": True if archive else False})
    if not update_result.get("success"):
        return update_result

    updated = update_result.get("data")
    action_word = "archived" if archive else "unarchived"
    name = resolved_name or (updated.get("name") if isinstance(updated, dict) else None) or "(untitled task)"
    url2 = None
    if isinstance(updated, dict):
        url2 = updated.get("shortUrl") or updated.get("url")
    final_url = url2 if isinstance(url2, str) and url2.strip() else url
    msg = f"Task '{name}' has been {action_word}."
    if isinstance(final_url, str) and final_url.strip():
        msg = f"Task '{name}' has been {action_word}: {final_url.strip()}"
    return {"success": True, "message": msg, "data": updated}


async def trello_delete_task(
    card_id: str = "",
    card_name: Optional[str] = None,
    board_id: str = "",
    board_name: Optional[str] = None,
    confirm: bool = False,
) -> Dict[str, Any]:
    card_id = (card_id or "").strip()
    card_name = (card_name or "").strip() or None
    board_id = (board_id or "").strip()
    board_name = (board_name or "").strip() or None

    if board_id and not board_name and not _looks_like_trello_id(board_id):
        board_name = board_id
        board_id = ""

    if board_name and not board_id:
        board_result = await trello_find_board_by_name(board_name)
        if not board_result.get("success"):
            msg = board_result.get("message")
            if not isinstance(msg, str) or not msg.strip():
                msg = f"Board '{board_name}' not found."
            return {"success": False, "error": "BOARD_NOT_FOUND", "message": msg}
        data = board_result.get("data")
        if not isinstance(data, dict) or not data.get("id"):
            return {"success": False, "error": "BOARD_ID_MISSING", "message": "I couldn't resolve that Trello board."}
        board_id = str(data.get("id"))

    resolved_card: Optional[Dict[str, Any]] = None
    if card_name and not card_id:
        if not board_id:
            return {
                "success": False,
                "error": "MISSING_BOARD",
                "message": "Please provide the board (board_id or board_name) to find that task.",
            }
        card_result = await trello_find_card_by_name(board_id, card_name)
        if not card_result.get("success"):
            msg = card_result.get("message")
            if not isinstance(msg, str) or not msg.strip():
                msg = f"Task '{card_name}' not found."
            return {"success": False, "error": "CARD_NOT_FOUND", "message": msg}
        data = card_result.get("data")
        if not isinstance(data, dict) or not data.get("id"):
            return {"success": False, "error": "CARD_ID_MISSING", "message": "I couldn't resolve that Trello task."}
        resolved_card = data
        card_id = str(data.get("id"))

    if not card_id:
        return {
            "success": False,
            "error": "MISSING_CARD",
            "message": "Please provide a Trello card_id or card_name.",
        }

    if not _looks_like_trello_id(card_id):
        return {
            "success": False,
            "error": "INVALID_CARD_ID",
            "message": "That doesn't look like a valid Trello card ID. Provide a card_name + board, or a valid card_id.",
        }

    if resolved_card is None:
        full = await trello_get_card(card_id)
        if full.get("success") and isinstance(full.get("data"), dict):
            resolved_card = full.get("data")

    resolved_name = None
    url = None
    if isinstance(resolved_card, dict):
        if isinstance(resolved_card.get("name"), str) and resolved_card.get("name").strip():
            resolved_name = resolved_card.get("name").strip()
        url = resolved_card.get("shortUrl") or resolved_card.get("url")
        if isinstance(url, str):
            url = url.strip()

    if confirm is not True:
        name_part = f" '{resolved_name}'" if isinstance(resolved_name, str) and resolved_name.strip() else ""
        msg = f"To proceed with deleting the task{name_part}, please reply with YES or PROCEED."
        if isinstance(url, str) and url.strip():
            msg = f"To proceed with deleting the task{name_part}: {url.strip()}\nPlease reply with YES or PROCEED."
        return {
            "status": "confirmation_required",
            "message": msg,
            "data": {
                "card_id": card_id,
                "card_name": resolved_name,
                "board_id": board_id,
                "board_name": board_name,
            },
        }

    result = await trello_delete_card(card_id)
    if not result.get("success"):
        return result

    name = resolved_name or "(untitled task)"
    msg = f"Task '{name}' has been deleted."
    return {"success": True, "message": msg, "data": result.get("data")}


async def trello_archive_list(
    list_id: str = "",
    list_name: Optional[str] = None,
    board_id: str = "",
    board_name: Optional[str] = None,
    archive: bool = True,
    confirm: bool = False,
) -> Dict[str, Any]:
    list_id = (list_id or "").strip()
    list_name = (list_name or "").strip() or None
    board_id = (board_id or "").strip()
    board_name = (board_name or "").strip() or None

    if board_id and not board_name and not _looks_like_trello_id(board_id):
        board_name = board_id
        board_id = ""

    if board_name and not board_id:
        board_result = await trello_find_board_by_name(board_name)
        if not board_result.get("success"):
            msg = board_result.get("message")
            if not isinstance(msg, str) or not msg.strip():
                msg = f"Board '{board_name}' not found."
            return {"success": False, "error": "BOARD_NOT_FOUND", "message": msg}
        data = board_result.get("data")
        if not isinstance(data, dict) or not data.get("id"):
            return {"success": False, "error": "BOARD_ID_MISSING", "message": "I couldn't resolve that Trello board."}
        board_id = str(data.get("id"))

    if list_name and not list_id:
        if not board_id:
            return {
                "success": False,
                "error": "MISSING_BOARD",
                "message": "Please provide the board (board_id or board_name) to find that list.",
            }
        list_result = await trello_find_list_by_name(board_id, list_name)
        if not list_result.get("success"):
            msg = list_result.get("message")
            if not isinstance(msg, str) or not msg.strip():
                msg = f"List '{list_name}' not found."
            return {"success": False, "error": "LIST_NOT_FOUND", "message": msg}
        data = list_result.get("data")
        if not isinstance(data, dict) or not data.get("id"):
            return {"success": False, "error": "LIST_ID_MISSING", "message": "I couldn't resolve that Trello list."}
        list_id = str(data.get("id"))

    if not list_id:
        return {
            "success": False,
            "error": "MISSING_LIST",
            "message": "Please provide a Trello list_id or list_name.",
        }

    resolved_name = list_name
    if not resolved_name:
        try:
            if board_id:
                lists_result = await trello_list_lists(board_id)
                if lists_result.get("success") and isinstance(lists_result.get("data"), list):
                    for li in lists_result.get("data"):
                        if isinstance(li, dict) and str(li.get("id", "")) == list_id:
                            if isinstance(li.get("name"), str) and li.get("name").strip():
                                resolved_name = li.get("name").strip()
                                break
        except Exception:
            resolved_name = resolved_name

    if confirm is not True:
        action_word = "archive" if archive else "unarchive"
        name_part = f" '{resolved_name}'" if isinstance(resolved_name, str) and resolved_name.strip() else ""
        return {
            "status": "confirmation_required",
            "message": f"To proceed with {action_word}ing the list{name_part}, please reply with YES or PROCEED.",
            "data": {
                "list_id": list_id,
                "list_name": resolved_name,
                "board_id": board_id,
                "board_name": board_name,
                "archive": archive,
            },
        }

    params = _auth_params()
    params["value"] = "true" if archive else "false"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.put(f"{_TRELLO_BASE_URL}/lists/{list_id}/closed", params=params)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {"success": False, "error": f"ARCHIVE_LIST_ERROR: HTTP_{exc.response.status_code}", "message": exc.response.text}
    except Exception as exc:
        return {"success": False, "error": f"ARCHIVE_LIST_ERROR: {exc!r}"}

    list_data = resp.json()
    url = None
    if isinstance(list_data, dict):
        url = list_data.get("url")
    action_word = "archived" if archive else "unarchived"
    name_part = resolved_name or (list_data.get("name") if isinstance(list_data, dict) else None) or "(unnamed list)"
    msg = f"List '{name_part}' has been {action_word}."
    if isinstance(url, str) and url.strip():
        msg = f"List '{name_part}' has been {action_word}: {url.strip()}"
    return {"success": True, "message": msg, "data": list_data}


async def trello_search_cards(query: str, board_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Search for cards by keyword."""
    params = _auth_params()
    params["query"] = query
    params["modelTypes"] = "cards"
    params["card_fields"] = "name,desc,due,idList,idBoard,labels,closed"

    if board_ids:
        resolved_board_ids: List[str] = []
        unresolved: List[str] = []
        for raw in board_ids:
            if raw is None:
                continue
            for part in str(raw).split(","):
                candidate = part.strip()
                if not candidate:
                    continue
                if _looks_like_trello_id(candidate):
                    resolved_board_ids.append(candidate)
                    continue

                resolved = await trello_find_board_by_name(candidate)
                if resolved.get("success") is True and isinstance(resolved.get("data"), dict) and resolved.get("data").get("id"):
                    resolved_board_ids.append(str(resolved.get("data").get("id")))
                else:
                    unresolved.append(candidate)

        if unresolved:
            missing = ", ".join(unresolved)
            return {
                "success": False,
                "error": "BOARD_NOT_FOUND",
                "message": f"I couldn't find these Trello boards: {missing}",
            }

        if resolved_board_ids:
            params["idBoards"] = ",".join(resolved_board_ids)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{_TRELLO_BASE_URL}/search", params=params)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        msg = "Trello returned an error while searching for cards."
        return {"success": False, "error": f"SEARCH_CARDS_ERROR:{status}", "message": msg}
    except httpx.RequestError:
        return {"success": False, "error": "SEARCH_CARDS_HTTP_ERROR", "message": "Network error while contacting Trello."}
    except Exception:
        return {"success": False, "error": "SEARCH_CARDS_ERROR", "message": "Unexpected error while searching Trello."}
    
    data = resp.json()
    cards = data.get("cards", [])
    return {"success": True, "data": cards}


async def trello_create_board(name: str, description: Optional[str] = None) -> Dict[str, Any]:
    """Create a new board."""
    params = _auth_params()
    params["name"] = name
    
    if description:
        params["desc"] = description
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{_TRELLO_BASE_URL}/boards", params=params)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"CREATE_BOARD_ERROR: {exc!r}"}
    
    board = resp.json()
    return {"success": True, "data": board}


async def trello_create_list(board_id: str, name: str) -> Dict[str, Any]:
    """Create a new list on a board."""
    params = _auth_params()
    params["name"] = name
    params["idBoard"] = board_id
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{_TRELLO_BASE_URL}/lists", params=params)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"CREATE_LIST_ERROR: {exc!r}"}
    
    list_data = resp.json()
    return {"success": True, "data": list_data}


async def trello_find_board_by_name(name: str) -> Dict[str, Any]:
    """Find a board by name (case-insensitive)."""
    result = await trello_list_boards()
    
    if not result.get("success"):
        return result
    
    boards = result["data"]
    name_lower = name.lower()
    
    for board in boards:
        if board.get("name", "").lower() == name_lower:
            return {"success": True, "data": board}
    
    for board in boards:
        if name_lower in board.get("name", "").lower():
            return {"success": True, "data": board}
    
    return {"success": False, "error": "BOARD_NOT_FOUND", "message": f"Board '{name}' not found"}


async def trello_find_list_by_name(board_id: str, name: str) -> Dict[str, Any]:
    """Find a list by name on a board (case-insensitive)."""
    result = await trello_list_lists(board_id)
    
    if not result.get("success"):
        return result
    
    lists = result["data"]
    name_lower = name.lower()
    
    for list_item in lists:
        if list_item.get("name", "").lower() == name_lower:
            return {"success": True, "data": list_item}
    
    for list_item in lists:
        if name_lower in list_item.get("name", "").lower():
            return {"success": True, "data": list_item}
    
    return {"success": False, "error": "LIST_NOT_FOUND", "message": f"List '{name}' not found"}


async def trello_find_card_by_name(board_id: str, name: str) -> Dict[str, Any]:
    """Find a card by name on a board (case-insensitive)."""
    result = await trello_get_board_cards(board_id)
    
    if not result.get("success"):
        return result
    
    cards = result["data"]
    name_lower = name.lower()
    
    found_card = None
    for card in cards:
        if card.get("name", "").lower() == name_lower:
            found_card = card
            break
    
    if not found_card:
        for card in cards:
            if name_lower in card.get("name", "").lower():
                found_card = card
                break
    
    if found_card:
        url = found_card.get("shortUrl") or found_card.get("url")
        if (not isinstance(url, str) or not url.strip()) and found_card.get("id"):
            full = await trello_get_card(str(found_card.get("id")))
            if full.get("success") is True:
                data = full.get("data")
                if isinstance(data, dict):
                    found_card = data
                    url = found_card.get("shortUrl") or found_card.get("url")
        card_name = found_card.get("name", name)
        msg = f"Found task '{card_name}'."
        if isinstance(url, str) and url.strip():
            msg = f"Found task '{card_name}': {url.strip()}"
        return {"success": True, "message": msg, "data": found_card}
    
    return {"success": False, "error": "CARD_NOT_FOUND", "message": f"Card '{name}' not found"}


def _format_card_readable(card: Dict[str, Any]) -> str:
    """Format a card in clean plain text."""
    name = card.get("name", "Untitled")
    desc = card.get("desc", "")
    due = card.get("due", "")
    closed = card.get("closed", False)
    labels = card.get("labels", [])
    
    output = f"Title: {name}\n"
    
    if desc:
        output += f"Description: {desc}\n"
    
    if due:
        try:
            due_dt = datetime.fromisoformat(due.replace('Z', '+00:00'))
            due_readable = due_dt.strftime("%B %d, %Y at %I:%M %p")
            output += f"Due: {due_readable}\n"
        except:
            output += f"Due: {due}\n"
    
    status = "Completed" if closed else "Active"
    output += f"Status: {status}\n"
    
    if labels:
        label_names = [label.get("name", "Unlabeled") for label in labels if label.get("name")]
        if label_names:
            output += f"Labels: {', '.join(label_names)}\n"
    
    return output.strip()


async def trello_sort_cards_by_due_date(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Sort cards by due date."""
    cards_with_due = [c for c in cards if c.get("due")]
    cards_without_due = [c for c in cards if not c.get("due")]
    
    cards_with_due.sort(key=lambda c: c.get("due", ""))
    
    sorted_cards = cards_with_due + cards_without_due
    
    return {"success": True, "data": sorted_cards}


async def trello_group_cards_by_status(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Group cards by completion status."""
    active = [c for c in cards if not c.get("closed", False)]
    completed = [c for c in cards if c.get("closed", False)]
    
    return {
        "success": True,
        "data": {
            "active": active,
            "completed": completed
        }
    }


async def trello_group_cards_by_label(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Group cards by label."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    unlabeled: List[Dict[str, Any]] = []
    
    for card in cards:
        labels = card.get("labels", [])
        if not labels:
            unlabeled.append(card)
        else:
            for label in labels:
                label_name = label.get("name", "Unlabeled")
                if label_name not in grouped:
                    grouped[label_name] = []
                grouped[label_name].append(card)
    
    if unlabeled:
        grouped["No Label"] = unlabeled
    
    return {"success": True, "data": grouped}


async def trello_filter_cards_by_due_date(
    cards: List[Dict[str, Any]],
    filter_type: str = "overdue"
) -> Dict[str, Any]:
    """Filter cards by due date (overdue, today, tomorrow, this_week)."""
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    week_end = today + timedelta(days=7)
    
    filtered = []
    
    for card in cards:
        due = card.get("due")
        if not due:
            continue
        
        try:
            due_dt = datetime.fromisoformat(due.replace('Z', '+00:00'))
            due_dt = due_dt.replace(tzinfo=None)
            
            if filter_type == "overdue":
                if due_dt < now:
                    filtered.append(card)
            elif filter_type == "today":
                if today <= due_dt < tomorrow:
                    filtered.append(card)
            elif filter_type == "tomorrow":
                if tomorrow <= due_dt < tomorrow + timedelta(days=1):
                    filtered.append(card)
            elif filter_type == "this_week":
                if today <= due_dt < week_end:
                    filtered.append(card)
        except:
            continue
    
    return {"success": True, "data": filtered}
