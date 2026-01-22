"""Tool definitions and execution for the Jarvis AI Agent.

This module centralizes the definition and registration of all callable tools
(Gmail, calendar, web fetch, memory writer, etc.). For now, it exposes a
minimal but real tool pipeline that is safe to call from the agent loop.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.services.calendar import calendar_create_event, calendar_create_event_safe
from src.services.calendar import calendar_list_events
from src.services.calendar_advanced import (
    calendar_get_availability,
    calendar_check_slot_available,
    calendar_find_next_available_slots,
    calendar_create_meet_event,
    calendar_reschedule_meeting,
    calendar_cancel_meeting,
    calendar_update_attendees,
    calendar_add_note_to_meeting,
)
from src.services.gmail import gmail_create_label
from src.services.gmail import gmail_label
from src.services.gmail import gmail_read
from src.services.gmail import gmail_search
from src.services.gmail import gmail_send_email
from src.services.gmail import gmail_summarize
from src.services.gmail_batch_label import gmail_batch_label
from src.services.gmail_filter import gmail_create_filter
from src.services.gmail_advanced import (
    gmail_fetch_by_keyword,
    gmail_fetch_by_sender,
    gmail_fetch_by_subject,
    gmail_fetch_by_label,
    gmail_fetch_by_date_range,
    gmail_list_labels,
    gmail_delete_label,
    gmail_rename_label,
    gmail_move_to_label,
    gmail_remove_label,
    gmail_forward_email,
    gmail_compose_email,
    gmail_list_attachments,
    gmail_download_attachment,
    gmail_fetch_emails_with_attachments,
    gmail_create_draft,
    gmail_list_drafts,
    gmail_get_draft,
    gmail_update_draft,
    gmail_delete_draft,
    gmail_send_draft,
    gmail_get_thread,
    gmail_list_threads,
    gmail_reply_to_thread,
    gmail_archive_thread,
    gmail_resolve_label_id,
)
from src.services.gmail_agentic import (
    gmail_agentic_search,
    gmail_agentic_bulk_action,
)
from src.services.http import http_get
from src.services.http import http_post
from src.services.trello import trello_add_comment
from src.services.trello import trello_create_card
from src.services.trello import trello_get_boards
from src.services.trello import trello_get_lists
from src.services.trello_advanced import (
    trello_list_boards,
    trello_list_lists,
    trello_list_cards,
    trello_get_board_cards,
    trello_create_task,
    trello_add_comment_task,
    trello_dispatch,
    trello_get_card_link,
    trello_get_card,
    trello_get_card_status,
    trello_update_card,
    trello_move_card,
    trello_delete_card,
    trello_archive_card,
    trello_delete_task,
    trello_archive_list,
    trello_search_cards,
    trello_create_board,
    trello_create_list,
    trello_find_board_by_name,
    trello_find_card_by_name,
)
from src.services.tts import synthesize_speech
from src.services.whisper import transcribe_audio_tool
from src.services.time_service import (
    get_current_time,
    parse_human_time_expression,
    format_time_readable,
    calculate_time_until,
    validate_time_range,
)
from src.services.memory_engine import (
    save_memory,
    load_memory,
    delete_memory,
    list_memory,
    search_memory,
    classify_memory,
)


logger = logging.getLogger("jarvis.tools")

ToolExecutor = Callable[..., Awaitable[Any]]


_TOOL_EXECUTORS: Dict[str, ToolExecutor] = {}
_TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {}


def _register_tool(name: str, schema: Dict[str, Any], executor: ToolExecutor) -> None:
    """Register a tool with its OpenAI tool schema and async executor."""

    _TOOL_EXECUTORS[name] = executor
    _TOOL_SCHEMAS[name] = schema


async def _tool_echo(text: str) -> Dict[str, Any]:
    """Simple echo tool used for testing the tool pipeline."""

    return {"echo": text}


async def _tool_get_current_utc_time() -> Dict[str, Any]:
    """Return the current UTC time in ISO format."""

    now = datetime.now(tz=timezone.utc)
    return {"iso_timestamp": now.isoformat()}


async def _tool_move_to_label(message_id: str, target_label: str) -> Dict[str, Any]:
    """Move an email into a label by human-readable label name.

    Resolves the label name to a Gmail label ID, then moves it out of INBOX.
    Falls back to adding the label only if INBOX removal fails.
    """

    resolve_result = await gmail_resolve_label_id(target_label)
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

    # Try to move by removing INBOX; if that fails, just add the label.
    move_result = await gmail_move_to_label(message_id, [label_id], ["INBOX"])
    if move_result.get("success"):
        move_result.setdefault("message", f"Moved email to label '{target_label}'.")
        return move_result

    label_result = await gmail_move_to_label(message_id, [label_id], [])
    if label_result.get("success"):
        label_result.setdefault(
            "message",
            f"Added label '{target_label}' (could not remove INBOX).",
        )
        return label_result

    return move_result


def _init_default_tools() -> None:
    """Initialize a small set of safe, built-in tools."""

    if _TOOL_EXECUTORS:
        # Already initialized.
        return

    echo_schema = {
        "type": "function",
        "function": {
            "name": "echo",
            "description": "Echo back text. Useful for testing the tool pipeline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to echo back.",
                    }
                },
                "required": ["text"],
            },
        },
    }

    time_schema = {
        "type": "function",
        "function": {
            "name": "get_current_utc_time",
            "description": "Get the current UTC time as an ISO-8601 string.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }

    _register_tool("echo", echo_schema, _tool_echo)
    _register_tool("get_current_utc_time", time_schema, _tool_get_current_utc_time)

    # Gmail tools
    _register_tool(
        "gmail_send_email",
        {
            "type": "function",
            "function": {
                "name": "gmail_send_email",
                "description": "Send an email via Gmail.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["to", "subject", "body"],
                },
            },
        },
        gmail_send_email,
    )

    _register_tool(
        "gmail_search",
        {
            "type": "function",
            "function": {
                "name": "gmail_search",
                "description": "Search Gmail messages using a Gmail query string.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": ["query"],
                },
            },
        },
        gmail_search,
    )

    _register_tool(
        "gmail_read",
        {
            "type": "function",
            "function": {
                "name": "gmail_read",
                "description": "Read a Gmail message by its ID.",
                "parameters": {
                    "type": "object",
                    "properties": {"message_id": {"type": "string"}},
                    "required": ["message_id"],
                },
            },
        },
        gmail_read,
    )

    _register_tool(
        "gmail_label",
        {
            "type": "function",
            "function": {
                "name": "gmail_label",
                "description": "Add and/or remove labels from a Gmail message. Accepts both label names (e.g., 'Work', 'Personal') and system labels (e.g., 'UNREAD', 'STARRED').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message_id": {"type": "string", "description": "The Gmail message ID to modify."},
                        "labels": {
                            "type": "array",
                            "description": "Optional list of label names to add (e.g., ['Work', 'Important']).",
                            "items": {"type": "string"},
                        },
                        "remove_labels": {
                            "type": "array",
                            "description": "Optional list of label names to remove (e.g., ['UNREAD'] to mark as read).",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["message_id"],
                },
            },
        },
        gmail_label,
    )

    _register_tool(
        "assign_labels",
        {
            "type": "function",
            "function": {
                "name": "assign_labels",
                "description": "Assign and/or remove Gmail labels from a specific message by ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message_id": {
                            "type": "string",
                            "description": "The Gmail message ID to modify.",
                        },
                        "labels": {
                            "type": "array",
                            "description": "Optional list of Gmail label IDs to add.",
                            "items": {"type": "string"},
                        },
                        "remove_labels": {
                            "type": "array",
                            "description": "Optional list of Gmail label IDs to remove (e.g., ['UNREAD'] to mark as read).",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["message_id"],
                },
            },
        },
        gmail_label,
    )

    _register_tool(
        "gmail_summarize",
        {
            "type": "function",
            "function": {
                "name": "gmail_summarize",
                "description": "Summarize a Gmail message using the LLM.",
                "parameters": {
                    "type": "object",
                    "properties": {"message_id": {"type": "string"}},
                    "required": ["message_id"],
                },
            },
        },
        gmail_summarize,
    )

    _register_tool(
        "gmail_create_label",
        {
            "type": "function",
            "function": {
                "name": "gmail_create_label",
                "description": "Create a new Gmail label in the user's mailbox.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "label_name": {
                            "type": "string",
                            "description": "Name of the label to create",
                        }
                    },
                    "required": ["label_name"],
                },
            },
        },
        gmail_create_label,
    )

    _register_tool(
        "gmail_batch_label",
        {
            "type": "function",
            "function": {
                "name": "gmail_batch_label",
                "description": "Apply labels to multiple emails matching a search query. Use this for requests like 'label all emails from X', 'mark all emails about Y as read', or 'move all emails to <label>' (add label + remove INBOX).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Gmail search query (e.g., 'from:sender@example.com', 'subject:meeting', 'is:unread')",
                        },
                        "labels": {
                            "type": "array",
                            "description": "Optional list of label names to add to matching emails",
                            "items": {"type": "string"},
                        },
                        "remove_labels": {
                            "type": "array",
                            "description": "Optional list of label names to remove from matching emails (e.g., ['UNREAD'] to mark as read)",
                            "items": {"type": "string"},
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of emails to process (default 50, max 100)",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        gmail_batch_label,
    )

    _register_tool(
        "gmail_create_filter",
        {
            "type": "function",
            "function": {
                "name": "gmail_create_filter",
                "description": "Create a Gmail filter that automatically moves FUTURE emails to a label. Use this when user says 'create a filter' or 'automatically move emails'. IMPORTANT: Filters only affect future emails, not existing ones. After creating the filter, always ask if user wants to apply the rule to existing emails.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "from_sender": {
                            "type": "string",
                            "description": "Email address to filter by sender (e.g., 'sender@example.com'). Use this OR subject_contains, not both.",
                        },
                        "subject_contains": {
                            "type": "string",
                            "description": "Keyword to filter by subject line. Use this OR from_sender, not both.",
                        },
                        "target_label": {
                            "type": "string",
                            "description": "Human-readable label name to move matching emails to (e.g., 'Work', 'Important')",
                        },
                    },
                    "required": ["target_label"],
                },
            },
        },
        gmail_create_filter,
    )

    _register_tool(
        "gmail_fetch_by_keyword",
        {
            "type": "function",
            "function": {
                "name": "gmail_fetch_by_keyword",
                "description": "Search and fetch emails by keyword (searches full body and subject).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string"},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": ["keyword"],
                },
            },
        },
        gmail_fetch_by_keyword,
    )

    _register_tool(
        "gmail_fetch_by_sender",
        {
            "type": "function",
            "function": {
                "name": "gmail_fetch_by_sender",
                "description": "Fetch emails from a specific sender.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sender": {"type": "string"},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": ["sender"],
                },
            },
        },
        gmail_fetch_by_sender,
    )

    _register_tool(
        "gmail_fetch_by_subject",
        {
            "type": "function",
            "function": {
                "name": "gmail_fetch_by_subject",
                "description": "Fetch emails by subject line.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string"},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": ["subject"],
                },
            },
        },
        gmail_fetch_by_subject,
    )

    _register_tool(
        "gmail_fetch_by_label",
        {
            "type": "function",
            "function": {
                "name": "gmail_fetch_by_label",
                "description": "Fetch emails with a specific label.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": ["label"],
                },
            },
        },
        gmail_fetch_by_label,
    )

    _register_tool(
        "gmail_fetch_by_date_range",
        {
            "type": "function",
            "function": {
                "name": "gmail_fetch_by_date_range",
                "description": "Fetch emails within a date range (format: YYYY/MM/DD).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "after": {"type": "string"},
                        "before": {"type": "string"},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": ["after"],
                },
            },
        },
        gmail_fetch_by_date_range,
    )

    _register_tool(
        "gmail_list_labels",
        {
            "type": "function",
            "function": {
                "name": "gmail_list_labels",
                "description": "List all Gmail labels in the mailbox.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        gmail_list_labels,
    )

    _register_tool(
        "gmail_delete_label",
        {
            "type": "function",
            "function": {
                "name": "gmail_delete_label",
                "description": "Delete a Gmail label by its ID.",
                "parameters": {
                    "type": "object",
                    "properties": {"label_id": {"type": "string"}},
                    "required": ["label_id"],
                },
            },
        },
        gmail_delete_label,
    )

    _register_tool(
        "gmail_rename_label",
        {
            "type": "function",
            "function": {
                "name": "gmail_rename_label",
                "description": "Rename a Gmail label.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "label_id": {"type": "string"},
                        "new_name": {"type": "string"},
                    },
                    "required": ["label_id", "new_name"],
                },
            },
        },
        gmail_rename_label,
    )

    _register_tool(
        "gmail_move_to_label",
        {
            "type": "function",
            "function": {
                "name": "gmail_move_to_label",
                "description": "Move an email to a label (add labels and optionally remove others, e.g. remove INBOX to move out of Inbox).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message_id": {"type": "string"},
                        "add_label_ids": {"type": "array", "items": {"type": "string"}},
                        "remove_label_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["message_id", "add_label_ids"],
                },
            },
        },
        gmail_move_to_label,
    )

    _register_tool(
        "move_to_label",
        {
            "type": "function",
            "function": {
                "name": "move_to_label",
                "description": "Move an email out of Inbox into a specific label by human-readable label name. Falls back to just applying the label if Inbox removal fails.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message_id": {
                            "type": "string",
                            "description": "The Gmail message ID to move.",
                        },
                        "target_label": {
                            "type": "string",
                            "description": "The human-readable Gmail label name (e.g., 'Important', 'Work').",
                        },
                    },
                    "required": ["message_id", "target_label"],
                },
            },
        },
        _tool_move_to_label,
    )

    _register_tool(
        "gmail_remove_label",
        {
            "type": "function",
            "function": {
                "name": "gmail_remove_label",
                "description": "Remove labels from an email.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message_id": {"type": "string"},
                        "label_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["message_id", "label_ids"],
                },
            },
        },
        gmail_remove_label,
    )

    _register_tool(
        "gmail_forward_email",
        {
            "type": "function",
            "function": {
                "name": "gmail_forward_email",
                "description": "Forward an email to a recipient. Automatically includes Saara's signature.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message_id": {"type": "string"},
                        "recipient": {"type": "string"},
                    },
                    "required": ["message_id", "recipient"],
                },
            },
        },
        gmail_forward_email,
    )

    _register_tool(
        "gmail_compose_email",
        {
            "type": "function",
            "function": {
                "name": "gmail_compose_email",
                "description": "Compose and send a clean email with Saara's signature. No Markdown or formatting symbols.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["to", "subject", "body"],
                },
            },
        },
        gmail_compose_email,
    )

    _register_tool(
        "gmail_list_attachments",
        {
            "type": "function",
            "function": {
                "name": "gmail_list_attachments",
                "description": "List all attachments in a Gmail message. Returns attachment metadata including filename, size, and mimeType.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message_id": {"type": "string", "description": "The Gmail message ID"}
                    },
                    "required": ["message_id"],
                },
            },
        },
        gmail_list_attachments,
    )

    _register_tool(
        "gmail_download_attachment",
        {
            "type": "function",
            "function": {
                "name": "gmail_download_attachment",
                "description": "Download a specific attachment from a Gmail message. Returns base64-encoded attachment data.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message_id": {"type": "string", "description": "The Gmail message ID"},
                        "attachment_id": {"type": "string", "description": "The attachment ID from gmail_list_attachments"}
                    },
                    "required": ["message_id", "attachment_id"],
                },
            },
        },
        gmail_download_attachment,
    )

    _register_tool(
        "gmail_fetch_emails_with_attachments",
        {
            "type": "function",
            "function": {
                "name": "gmail_fetch_emails_with_attachments",
                "description": "Fetch emails that contain attachments. Returns full email data for messages with attachments.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "default": 20, "description": "Maximum number of emails to fetch"}
                    },
                    "required": [],
                },
            },
        },
        gmail_fetch_emails_with_attachments,
    )

    _register_tool(
        "gmail_create_draft",
        {
            "type": "function",
            "function": {
                "name": "gmail_create_draft",
                "description": "Create a new Gmail draft email with Saara's clean formatting and signature.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email address"},
                        "subject": {"type": "string", "description": "Email subject"},
                        "body": {"type": "string", "description": "Email body text (plain language, no Markdown)"},
                    },
                    "required": ["to", "subject", "body"],
                },
            },
        },
        gmail_create_draft,
    )

    _register_tool(
        "gmail_list_drafts",
        {
            "type": "function",
            "function": {
                "name": "gmail_list_drafts",
                "description": "List Gmail drafts, returning their IDs and basic metadata.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "default": 20, "description": "Maximum number of drafts to list"}
                    },
                    "required": [],
                },
            },
        },
        gmail_list_drafts,
    )

    _register_tool(
        "gmail_get_draft",
        {
            "type": "function",
            "function": {
                "name": "gmail_get_draft",
                "description": "Get a specific Gmail draft by its ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "draft_id": {"type": "string", "description": "The Gmail draft ID"}
                    },
                    "required": ["draft_id"],
                },
            },
        },
        gmail_get_draft,
    )

    _register_tool(
        "gmail_update_draft",
        {
            "type": "function",
            "function": {
                "name": "gmail_update_draft",
                "description": "Update an existing Gmail draft's recipient, subject, and body using Saara's formatting rules.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "draft_id": {"type": "string", "description": "The Gmail draft ID"},
                        "to": {"type": "string", "description": "Recipient email address"},
                        "subject": {"type": "string", "description": "Email subject"},
                        "body": {"type": "string", "description": "Email body text (plain language, no Markdown)"},
                    },
                    "required": ["draft_id", "to", "subject", "body"],
                },
            },
        },
        gmail_update_draft,
    )

    _register_tool(
        "gmail_delete_draft",
        {
            "type": "function",
            "function": {
                "name": "gmail_delete_draft",
                "description": "Delete a Gmail draft by its ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "draft_id": {"type": "string", "description": "The Gmail draft ID"}
                    },
                    "required": ["draft_id"],
                },
            },
        },
        gmail_delete_draft,
    )

    _register_tool(
        "gmail_send_draft",
        {
            "type": "function",
            "function": {
                "name": "gmail_send_draft",
                "description": "Send an existing Gmail draft by its ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "draft_id": {"type": "string", "description": "The Gmail draft ID"},
                        "confirm": {"type": "boolean", "default": False},
                    },
                    "required": ["draft_id"],
                },
            },
        },
        gmail_send_draft,
    )

    _register_tool(
        "gmail_get_thread",
        {
            "type": "function",
            "function": {
                "name": "gmail_get_thread",
                "description": "Get a specific Gmail thread by its ID, including all messages.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "thread_id": {"type": "string", "description": "The Gmail thread ID"},
                    },
                    "required": ["thread_id"],
                },
            },
        },
        gmail_get_thread,
    )

    _register_tool(
        "gmail_list_threads",
        {
            "type": "function",
            "function": {
                "name": "gmail_list_threads",
                "description": "List Gmail threads matching a search query (subject, sender, labels, etc.).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Gmail search query string, e.g. 'from:john is:unread'"},
                        "limit": {"type": "integer", "default": 20, "description": "Maximum number of threads to return"},
                    },
                    "required": ["query"],
                },
            },
        },
        gmail_list_threads,
    )

    _register_tool(
        "gmail_reply_to_thread",
        {
            "type": "function",
            "function": {
                "name": "gmail_reply_to_thread",
                "description": "Reply to an existing Gmail thread with a clean, signed message.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "thread_id": {"type": "string", "description": "The Gmail thread ID to reply to"},
                        "body": {"type": "string", "description": "Reply body text (plain language, no Markdown)"},
                    },
                    "required": ["thread_id", "body"],
                },
            },
        },
        gmail_reply_to_thread,
    )

    _register_tool(
        "gmail_archive_thread",
        {
            "type": "function",
            "function": {
                "name": "gmail_archive_thread",
                "description": "Archive a Gmail thread by removing it from the INBOX.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "thread_id": {"type": "string", "description": "The Gmail thread ID"},
                    },
                    "required": ["thread_id"],
                },
            },
        },
        gmail_archive_thread,
    )

    # Gmail Agentic Tools
    _register_tool(
        "gmail_agentic_search",
        {
            "type": "function",
            "function": {
                "name": "gmail_agentic_search",
                "description": "Search Gmail with intelligent pagination and session management. Shows metadata-only results with 'continue' prompts and 'open email #N' functionality. Handles large mailboxes efficiently.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "integer", "description": "User ID for session management"},
                        "query": {"type": "string", "description": "Gmail search query (empty for inbox)"},
                        "max_results": {"type": "integer", "description": "Optional maximum results limit"},
                        "user_message": {"type": "string", "description": "Original user message for intent parsing (e.g., 'continue', 'open email #5')"},
                    },
                    "required": ["user_id"],
                },
            },
        },
        _tool_gmail_agentic_search,
    )

    _register_tool(
        "gmail_agentic_bulk_action",
        {
            "type": "function",
            "function": {
                "name": "gmail_agentic_bulk_action",
                "description": "Perform bulk Gmail actions (label, move, delete) with confirmation prompts. Estimates affected emails before execution.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "integer", "description": "User ID for session management"},
                        "action": {"type": "string", "description": "Action type: 'bulk_label', 'bulk_move', 'bulk_delete'"},
                        "query": {"type": "string", "description": "Gmail query to find matching emails"},
                        "action_params": {"type": "object", "description": "Parameters for action (add_labels, remove_labels, etc.)"},
                        "confirm": {"type": "boolean", "description": "Whether user has confirmed action"},
                    },
                    "required": ["user_id", "action", "query"],
                },
            },
        },
        _tool_gmail_agentic_bulk_action,
    )

    # Calendar tools
    _register_tool(
        "calendar_list_events",
        {
            "type": "function",
            "function": {
                "name": "calendar_list_events",
                "description": "List upcoming events from the user's calendar.",
                "parameters": {
                    "type": "object",
                    "properties": {"max_results": {"type": "integer", "default": 10}},
                    "required": [],
                },
            },
        },
        calendar_list_events,
    )

    _register_tool(
        "calendar_create_event",
        {
            "type": "function",
            "function": {
                "name": "calendar_create_event",
                "description": "Create a new calendar event. Supports natural language time like 'tomorrow at 6am', 'Friday at 3pm', 'in 2 hours'. If only start_time is provided, end_time defaults to start + 1 hour. Returns clarification request if time cannot be parsed.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "Event title (required)"
                        },
                        "start_time": {
                            "type": "string",
                            "description": "Start time - ISO 8601 or natural language like 'tomorrow at 6am', 'Friday 3pm', 'in 2 hours'"
                        },
                        "end_time": {
                            "type": "string",
                            "description": "End time (optional) - if not provided, defaults to start + 1 hour"
                        },
                        "description": {
                            "type": "string",
                            "description": "Event description (optional)"
                        },
                        "location": {
                            "type": "string",
                            "description": "Event location (optional)"
                        },
                        "duration_minutes": {
                            "type": "integer",
                            "description": "Duration in minutes if end_time not specified (default: 60)"
                        },
                    },
                    "required": ["summary", "start_time"],
                },
            },
        },
        calendar_create_event_safe,
    )

    _register_tool(
        "calendar_check_slot_available",
        {
            "type": "function",
            "function": {
                "name": "calendar_check_slot_available",
                "description": "Check if a specific time slot is available or has conflicts.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_time": {"type": "string", "description": "ISO format datetime"},
                        "end_time": {"type": "string", "description": "ISO format datetime"},
                    },
                    "required": ["start_time", "end_time"],
                },
            },
        },
        calendar_check_slot_available,
    )

    _register_tool(
        "calendar_find_next_available_slots",
        {
            "type": "function",
            "function": {
                "name": "calendar_find_next_available_slots",
                "description": "Find the next available time slots for scheduling.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_search": {"type": "string", "description": "ISO format datetime to start searching from"},
                        "duration_minutes": {"type": "integer", "default": 30},
                        "num_slots": {"type": "integer", "default": 3},
                    },
                    "required": ["start_search"],
                },
            },
        },
        calendar_find_next_available_slots,
    )

    _register_tool(
        "calendar_create_meet_event",
        {
            "type": "function",
            "function": {
                "name": "calendar_create_meet_event",
                "description": "Create a calendar event with Google Meet link and send invitations to attendees. Supports natural language time like 'tomorrow at 6am'. If only start_time is provided, end_time defaults to start + 1 hour.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Event title"},
                        "start_time": {"type": "string", "description": "Start time - ISO 8601 or natural language like 'tomorrow at 6am'"},
                        "end_time": {"type": "string", "description": "End time (optional) - defaults to start + 1 hour if not provided"},
                        "attendees": {"type": "array", "items": {"type": "string"}, "description": "List of attendee email addresses"},
                        "description": {"type": "string", "description": "Event description"},
                    },
                    "required": ["title", "start_time"],
                },
            },
        },
        calendar_create_meet_event,
    )

    _register_tool(
        "calendar_reschedule_meeting",
        {
            "type": "function",
            "function": {
                "name": "calendar_reschedule_meeting",
                "description": "Reschedule an existing meeting to a new time.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string", "description": "Calendar event id (preferred if known)"},
                        "event_title": {"type": "string", "description": "Event title to search for (used if event_id not provided)"},
                        "date_str": {"type": "string", "description": "Event date to narrow search (YYYY-MM-DD)"},
                        "time_min": {"type": "string", "description": "Optional ISO 8601 timeMin to narrow search"},
                        "time_max": {"type": "string", "description": "Optional ISO 8601 timeMax to narrow search"},
                        "timezone_name": {"type": "string", "description": "IANA timezone (e.g. Africa/Lagos)"},
                        "new_start_time": {"type": "string", "description": "ISO format datetime"},
                        "new_end_time": {"type": "string", "description": "ISO format datetime"},
                    },
                    "required": ["new_start_time", "new_end_time"],
                },
            },
        },
        calendar_reschedule_meeting,
    )

    _register_tool(
        "calendar_cancel_meeting",
        {
            "type": "function",
            "function": {
                "name": "calendar_cancel_meeting",
                "description": "Cancel a meeting and notify all attendees.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string", "description": "Calendar event id (preferred if known)"},
                        "event_title": {"type": "string", "description": "Event title to search for (used if event_id not provided)"},
                        "date_str": {"type": "string", "description": "Event date to narrow search (YYYY-MM-DD)"},
                        "time_min": {"type": "string", "description": "Optional ISO 8601 timeMin to narrow search"},
                        "time_max": {"type": "string", "description": "Optional ISO 8601 timeMax to narrow search"},
                        "timezone_name": {"type": "string", "description": "IANA timezone (e.g. Africa/Lagos)"},
                        "confirm": {"type": "boolean", "description": "Must be true to perform the cancellation"},
                        "cancel_scope": {"type": "string", "enum": ["single", "series"], "description": "For recurring events: cancel one occurrence or the entire series"},
                        "delete": {"type": "boolean", "description": "If true, permanently delete the event instead of cancelling (default false)"}
                    },
                    "required": [],
                },
            },
        },
        calendar_cancel_meeting,
    )

    _register_tool(
        "calendar_update_attendees",
        {
            "type": "function",
            "function": {
                "name": "calendar_update_attendees",
                "description": "Update the attendee list for an existing meeting. Attendees must be valid email addresses.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string", "description": "Calendar event id (preferred if known)"},
                        "event_title": {"type": "string", "description": "Event title to search for (used if event_id not provided)"},
                        "date_str": {"type": "string", "description": "Event date to narrow search (YYYY-MM-DD)"},
                        "time_min": {"type": "string", "description": "Optional ISO 8601 timeMin to narrow search"},
                        "time_max": {"type": "string", "description": "Optional ISO 8601 timeMax to narrow search"},
                        "timezone_name": {"type": "string", "description": "IANA timezone (e.g. Africa/Lagos)"},
                        "attendees": {"type": "array", "items": {"type": "string"}, "description": "List of attendee email addresses"},
                    },
                    "required": ["attendees"],
                },
            },
        },
        calendar_update_attendees,
    )

    _register_tool(
        "calendar_add_note_to_meeting",
        {
            "type": "function",
            "function": {
                "name": "calendar_add_note_to_meeting",
                "description": "Add a note to an existing meeting by appending it to the meeting description.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "note": {"type": "string", "description": "The note text to add to the meeting"},
                        "event_id": {"type": "string", "description": "Calendar event id (preferred if known)"},
                        "event_title": {"type": "string", "description": "Event title to search for (used if event_id not provided)"},
                        "date_str": {"type": "string", "description": "Event date to narrow search (YYYY-MM-DD)"},
                        "time_min": {"type": "string", "description": "Optional ISO 8601 timeMin to narrow search"},
                        "time_max": {"type": "string", "description": "Optional ISO 8601 timeMax to narrow search"},
                        "timezone_name": {"type": "string", "description": "IANA timezone (e.g. Africa/Lagos)"},
                    },
                    "required": [],
                },
            },
        },
        calendar_add_note_to_meeting,
    )

    # Trello tools
    _register_tool(
        "trello_dispatch",
        {
            "type": "function",
            "function": {
                "name": "trello_dispatch",
                "description": "Unified Trello dispatcher. Prefer this for Trello requests: it routes create/update/move/comment/delete/archive, resolves names to IDs, enforces rules (status->move, comments use comment endpoint), and executes exactly one Trello operation or asks one clarification question if required.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": "Intent: create/update/move/comment/delete/archive (optional; can be inferred)."},
                        "card_id": {"type": "string", "description": "Trello card ID (24-char hex)."},
                        "card_name": {"type": "string", "description": "Task/card name (requires board)."},
                        "board_id": {"type": "string", "description": "Trello board ID (24-char hex) or board name."},
                        "board_name": {"type": "string", "description": "Trello board name (e.g. 'Missions')."},
                        "list_id": {"type": "string", "description": "List ID for create if known."},
                        "list_name": {"type": "string", "description": "List name for create if known (board required)."},
                        "to_list_id": {"type": "string", "description": "Destination list ID for move/status change."},
                        "to_list_name": {"type": "string", "description": "Destination list name for move/status change (board required)."},
                        "to_board_id": {"type": "string", "description": "Destination board ID for cross-board moves (optional)."},
                        "to_board_name": {"type": "string", "description": "Destination board name for cross-board moves (optional)."},
                        "status": {"type": "string", "description": "Alias for to_list_name when the user refers to status (e.g. 'To Do', 'In Progress', 'Done')."},
                        "fields": {"type": "object", "description": "Update fields. NOTE: status/list changes are treated as move; notes/comments are treated as comment."},
                        "comment_text": {"type": "string", "description": "Note/comment text to add (for comment intent)."},
                        "text": {"type": "string", "description": "Alias for comment_text."},
                        "title": {"type": "string", "description": "Task title for create/update."},
                        "description": {"type": "string", "description": "Task description for create/update."},
                        "due": {"type": "string", "description": "Due date/time (ISO8601 preferred)."},
                        "due_date": {"type": "string", "description": "Alias for due."},
                        "labels": {"type": "array", "items": {"type": "string"}, "description": "Label IDs to set (if known)."},
                        "members": {"type": "array", "items": {"type": "string"}, "description": "Member IDs to set (if known)."},
                        "archive": {"type": "boolean", "description": "For archive action: true to archive, false to unarchive."},
                        "confirm": {"type": "boolean", "description": "For delete/archive actions: set true only after the user confirms with YES/PROCEED."},
                    },
                    "required": [],
                },
            },
        },
        trello_dispatch,
    )

    _register_tool(
        "trello_create_task",
        {
            "type": "function",
            "function": {
                "name": "trello_create_task",
                "description": "Create a Trello task by resolving board/list names into IDs. Prefer this over trello_create_card unless you already have a Trello list_id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Task title"},
                        "description": {"type": "string", "description": "Optional task description"},
                        "due": {"type": "string", "description": "Optional due date/time (ISO8601 preferred)."},
                        "labels": {"type": "array", "items": {"type": "string"}, "description": "Optional label IDs."},
                        "members": {"type": "array", "items": {"type": "string"}, "description": "Optional member IDs."},
                        "board_id": {"type": "string", "description": "Trello board ID (24-char hex)"},
                        "board_name": {"type": "string", "description": "Trello board name (e.g. 'Missions')"},
                        "list_id": {"type": "string", "description": "Trello list ID (24-char hex). Do not pass list names here."},
                        "list_name": {"type": "string", "description": "Trello list name (e.g. 'Meetings')"},
                        "use_first_list": {"type": "boolean", "description": "If true, use the first list on the board"},
                        "list_index": {"type": "integer", "description": "1-based list index to pick from the board's lists"},
                    },
                    "required": ["name"],
                },
            },
        },
        trello_create_task,
    )

    _register_tool(
        "trello_create_card",
        {
            "type": "function",
            "function": {
                "name": "trello_create_card",
                "description": "Create a Trello card in a specific Trello list. Use only when you already have the Trello list_id. If you only know board/list names, use trello_create_task.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "list_id": {"type": "string", "description": "Trello list ID (not a list name)"},
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "due": {"type": "string", "description": "Optional due date/time (ISO8601 preferred)."},
                        "labels": {"type": "array", "items": {"type": "string"}, "description": "Optional label IDs."},
                        "members": {"type": "array", "items": {"type": "string"}, "description": "Optional member IDs."},
                    },
                    "required": ["list_id", "name"],
                },
            },
        },
        trello_create_card,
    )

    _register_tool(
        "trello_get_boards",
        {
            "type": "function",
            "function": {
                "name": "trello_get_boards",
                "description": "List Trello boards for the authorized user.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        trello_get_boards,
    )

    _register_tool(
        "trello_get_lists",
        {
            "type": "function",
            "function": {
                "name": "trello_get_lists",
                "description": "List lists on a Trello board.",
                "parameters": {
                    "type": "object",
                    "properties": {"board_id": {"type": "string"}},
                    "required": ["board_id"],
                },
            },
        },
        trello_get_lists,
    )

    _register_tool(
        "trello_add_comment",
        {
            "type": "function",
            "function": {
                "name": "trello_add_comment",
                "description": "Add a comment to a Trello card by card_id. If you only know the task name (and board), use trello_add_comment_task.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["card_id", "text"],
                },
            },
        },
        trello_add_comment,
    )

    _register_tool(
        "trello_add_comment_task",
        {
            "type": "function",
            "function": {
                "name": "trello_add_comment_task",
                "description": "Add a note/comment to a Trello task (card). This calls the Trello comments endpoint. Do NOT use trello_update_card for comments.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "string", "description": "Trello card ID (24-char hex)."},
                        "card_name": {"type": "string", "description": "Task/card name (requires board)."},
                        "board_id": {"type": "string", "description": "Trello board ID (24-char hex) or board name."},
                        "board_name": {"type": "string", "description": "Trello board name (e.g. 'Missions')."},
                        "comment_text": {"type": "string", "description": "The note/comment text to add."},
                        "text": {"type": "string", "description": "Alias for comment_text."},
                    },
                    "required": [],
                },
            },
        },
        trello_add_comment_task,
    )

    _register_tool(
        "trello_get_board_cards",
        {
            "type": "function",
            "function": {
                "name": "trello_get_board_cards",
                "description": "Get all cards on a Trello board.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "board_id": {
                            "type": "string",
                            "description": "Trello board ID (24-char hex). If unknown, provide board_name instead.",
                        },
                        "board_name": {
                            "type": "string",
                            "description": "Trello board name (e.g. 'Missions').",
                        },
                    },
                    "required": [],
                },
            },
        },
        trello_get_board_cards,
    )

    _register_tool(
        "trello_list_cards",
        {
            "type": "function",
            "function": {
                "name": "trello_list_cards",
                "description": "Get all cards in a specific list.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "list_id": {"type": "string", "description": "Optional Trello list ID (24-char hex). Prefer using list_name + board_name/board_id; do NOT ask the user for list_id."},
                        "list_name": {"type": "string", "description": "Trello list name (e.g. 'To Do'). Prefer this over list_id."},
                        "board_id": {"type": "string", "description": "Trello board ID to disambiguate list_name."},
                        "board_name": {"type": "string", "description": "Trello board name to disambiguate list_name."},
                    },
                    "required": [],
                },
            },
        },
        trello_list_cards,
    )

    _register_tool(
        "trello_get_card_status",
        {
            "type": "function",
            "function": {
                "name": "trello_get_card_status",
                "description": "Get the current Trello status (which list a task/card is in).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "string", "description": "Trello card ID (24-char hex)."},
                        "card_name": {"type": "string", "description": "Task/card name (used if card_id not provided)."},
                        "board_id": {"type": "string", "description": "Optional board ID to disambiguate card_name."},
                        "board_name": {"type": "string", "description": "Optional board name to disambiguate card_name."},
                    },
                    "required": [],
                },
            },
        },
        trello_get_card_status,
    )

    _register_tool(
        "trello_get_card",
        {
            "type": "function",
            "function": {
                "name": "trello_get_card",
                "description": "Get details of a specific Trello card.",
                "parameters": {
                    "type": "object",
                    "properties": {"card_id": {"type": "string"}},
                    "required": ["card_id"],
                },
            },
        },
        trello_get_card,
    )

    _register_tool(
        "trello_get_card_link",
        {
            "type": "function",
            "function": {
                "name": "trello_get_card_link",
                "description": "Get a shareable link (URL) to a Trello card by card_id or by card_name with its board.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "string", "description": "Trello card ID (preferred if known)."},
                        "card_name": {"type": "string", "description": "Card name/title (used if card_id not provided)."},
                        "board_id": {"type": "string", "description": "Board ID (24-char hex)."},
                        "board_name": {"type": "string", "description": "Board name (e.g. 'Missions')."},
                    },
                    "required": [],
                },
            },
        },
        trello_get_card_link,
    )

    _register_tool(
        "trello_update_card",
        {
            "type": "function",
            "function": {
                "name": "trello_update_card",
                "description": "Update a Trello card's fields (name, description, due date, labels, members). Do NOT use this to add notes/comments; use trello_add_comment_task.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "string"},
                        "fields": {"type": "object"},
                    },
                    "required": ["card_id", "fields"],
                },
            },
        },
        trello_update_card,
    )

    _register_tool(
        "trello_move_card",
        {
            "type": "function",
            "function": {
                "name": "trello_move_card",
                "description": "Move a card to a different list or board.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "string"},
                        "list_id": {"type": "string"},
                        "board_id": {"type": "string"},
                    },
                    "required": ["card_id", "list_id"],
                },
            },
        },
        trello_move_card,
    )

    _register_tool(
        "trello_delete_card",
        {
            "type": "function",
            "function": {
                "name": "trello_delete_card",
                "description": "Delete a Trello card permanently.",
                "parameters": {
                    "type": "object",
                    "properties": {"card_id": {"type": "string"}},
                    "required": ["card_id"],
                },
            },
        },
        trello_delete_card,
    )

    _register_tool(
        "trello_archive_card",
        {
            "type": "function",
            "function": {
                "name": "trello_archive_card",
                "description": "Archive (close) or unarchive a Trello task (card). Use this for 'archive task' requests. Requires confirmation via the 'confirm' flag.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "string", "description": "Trello card ID (24-char hex)."},
                        "card_name": {"type": "string", "description": "Trello task/card name (requires board)."},
                        "board_id": {"type": "string", "description": "Trello board ID (24-char hex) or board name."},
                        "board_name": {"type": "string", "description": "Trello board name (e.g. 'Missions')."},
                        "archive": {"type": "boolean", "description": "If true archive/close the task; if false unarchive."},
                        "confirm": {"type": "boolean", "description": "Set true only after the user confirms with YES/PROCEED."},
                    },
                    "required": [],
                },
            },
        },
        trello_archive_card,
    )

    _register_tool(
        "trello_delete_task",
        {
            "type": "function",
            "function": {
                "name": "trello_delete_task",
                "description": "Delete a Trello task (card). Prefer this over trello_delete_card when you only know the task name; this tool resolves the card ID first and requires confirmation via the 'confirm' flag.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "string", "description": "Trello card ID (24-char hex)."},
                        "card_name": {"type": "string", "description": "Trello task/card name (requires board)."},
                        "board_id": {"type": "string", "description": "Trello board ID (24-char hex) or board name."},
                        "board_name": {"type": "string", "description": "Trello board name (e.g. 'Missions')."},
                        "confirm": {"type": "boolean", "description": "Set true only after the user confirms with YES/PROCEED."},
                    },
                    "required": [],
                },
            },
        },
        trello_delete_task,
    )

    _register_tool(
        "trello_archive_list",
        {
            "type": "function",
            "function": {
                "name": "trello_archive_list",
                "description": "Archive (close) a Trello list. Use this to delete/remove a duplicate list. Supports confirmation via the 'confirm' flag.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "list_id": {"type": "string", "description": "Trello list ID (24-char hex)."},
                        "list_name": {"type": "string", "description": "Trello list name (e.g. 'Meetings (duplicate)')."},
                        "board_id": {"type": "string", "description": "Trello board ID (24-char hex)."},
                        "board_name": {"type": "string", "description": "Trello board name (e.g. 'Missions')."},
                        "archive": {"type": "boolean", "description": "If true archive/close the list; if false unarchive."},
                        "confirm": {"type": "boolean", "description": "Set true only after the user confirms with YES/PROCEED."},
                    },
                    "required": [],
                },
            },
        },
        trello_archive_list,
    )

    _register_tool(
        "trello_search_cards",
        {
            "type": "function",
            "function": {
                "name": "trello_search_cards",
                "description": "Search for Trello cards by keyword.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "board_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["query"],
                },
            },
        },
        trello_search_cards,
    )

    _register_tool(
        "trello_find_board_by_name",
        {
            "type": "function",
            "function": {
                "name": "trello_find_board_by_name",
                "description": "Find a Trello board by name (case-insensitive).",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
        },
        trello_find_board_by_name,
    )

    _register_tool(
        "trello_find_card_by_name",
        {
            "type": "function",
            "function": {
                "name": "trello_find_card_by_name",
                "description": "Find a Trello card by name on a board. Returns the card details including its shareable URL. Use this when the user asks for a link to a task.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "board_id": {"type": "string", "description": "Trello board ID or board name (e.g. 'Missions')"},
                        "name": {"type": "string", "description": "Card/task name to search for"},
                    },
                    "required": ["board_id", "name"],
                },
            },
        },
        trello_find_card_by_name,
    )

    _register_tool(
        "trello_create_board",
        {
            "type": "function",
            "function": {
                "name": "trello_create_board",
                "description": "Create a new Trello board.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
        },
        trello_create_board,
    )

    _register_tool(
        "trello_create_list",
        {
            "type": "function",
            "function": {
                "name": "trello_create_list",
                "description": "Create a new list on a Trello board.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "board_id": {"type": "string"},
                        "name": {"type": "string"},
                    },
                    "required": ["board_id", "name"],
                },
            },
        },
        trello_create_list,
    )

    # Time awareness tools
    _register_tool(
        "get_current_time",
        {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "description": "Get the REAL current system time in ISO 8601 format. Jarvis must ALWAYS call this when the user asks for the current time, date, or uses relative time expressions like 'in 2 hours', 'tomorrow', 'next week', etc. NEVER guess the time.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timezone_name": {"type": "string", "description": "Optional timezone (e.g., 'Europe/Berlin', 'America/New_York'). Defaults to Europe/Berlin."}
                    },
                    "required": [],
                },
            },
        },
        get_current_time,
    )

    _register_tool(
        "parse_human_time_expression",
        {
            "type": "function",
            "function": {
                "name": "parse_human_time_expression",
                "description": "Parse natural language time expressions like 'in 2 hours', 'tomorrow morning', 'next Friday at 3pm' into precise ISO 8601 timestamps. MUST be used with current_time from get_current_time().",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string", "description": "Natural language time expression"},
                        "current_time": {"type": "string", "description": "ISO 8601 current time from get_current_time()"},
                        "timezone": {"type": "string", "description": "Optional timezone"},
                        "default_duration_minutes": {"type": "integer", "description": "Default meeting duration in minutes (default: 60)"}
                    },
                    "required": ["expression", "current_time"],
                },
            },
        },
        parse_human_time_expression,
    )

    _register_tool(
        "format_time_readable",
        {
            "type": "function",
            "function": {
                "name": "format_time_readable",
                "description": "Convert ISO 8601 timestamp to human-readable format like 'Monday, January 21, 2025 at 03:00 PM'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "iso_time": {"type": "string", "description": "ISO 8601 timestamp"}
                    },
                    "required": ["iso_time"],
                },
            },
        },
        format_time_readable,
    )

    _register_tool(
        "calculate_time_until",
        {
            "type": "function",
            "function": {
                "name": "calculate_time_until",
                "description": "Calculate the duration between current time and a target time.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_time": {"type": "string", "description": "ISO 8601 target timestamp"},
                        "current_time": {"type": "string", "description": "ISO 8601 current timestamp"}
                    },
                    "required": ["target_time", "current_time"],
                },
            },
        },
        calculate_time_until,
    )

    _register_tool(
        "validate_time_range",
        {
            "type": "function",
            "function": {
                "name": "validate_time_range",
                "description": "Validate that a time range is logical (end time after start time).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_time": {"type": "string", "description": "ISO 8601 start timestamp"},
                        "end_time": {"type": "string", "description": "ISO 8601 end timestamp"}
                    },
                    "required": ["start_time", "end_time"],
                },
            },
        },
        validate_time_range,
    )

    # Long-term memory tools
    _register_tool(
        "save_memory",
        {
            "type": "function",
            "function": {
                "name": "save_memory",
                "description": "Save a key-value pair to long-term memory. Use this when the user shares preferences, habits, personal details, goals, or configuration. DO NOT use for temporary tasks or one-time instructions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Memory key (e.g., 'email_preference', 'assistant_name')"},
                        "value": {"type": "string", "description": "Memory value (e.g., 'short emails', 'David')"}
                    },
                    "required": ["key", "value"],
                },
            },
        },
        save_memory,
    )

    _register_tool(
        "load_memory",
        {
            "type": "function",
            "function": {
                "name": "load_memory",
                "description": "Load all stored memory entries. Returns a list of key-value pairs with user preferences, habits, and personal details.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        load_memory,
    )

    _register_tool(
        "delete_memory",
        {
            "type": "function",
            "function": {
                "name": "delete_memory",
                "description": "Delete a memory entry by key. Use when the user asks to forget something or when information is no longer relevant.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Memory key to delete"}
                    },
                    "required": ["key"],
                },
            },
        },
        delete_memory,
    )

    _register_tool(
        "list_memory",
        {
            "type": "function",
            "function": {
                "name": "list_memory",
                "description": "List all memory keys without their values. Useful for discovering what's stored in memory.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        list_memory,
    )

    _register_tool(
        "search_memory",
        {
            "type": "function",
            "function": {
                "name": "search_memory",
                "description": "Search memory by keyword in keys or values. Returns matching memory entries.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query string"}
                    },
                    "required": ["query"],
                },
            },
        },
        search_memory,
    )

    _register_tool(
        "classify_memory",
        {
            "type": "function",
            "function": {
                "name": "classify_memory",
                "description": "Analyze a user message to determine if it contains information worth storing in long-term memory. Returns whether to store, suggested key, and value.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_message": {"type": "string", "description": "The user's message to analyze"}
                    },
                    "required": ["user_message"],
                },
            },
        },
        classify_memory,
    )

    # Generic HTTP tools
    _register_tool(
        "http_get",
        {
            "type": "function",
            "function": {
                "name": "http_get",
                "description": "Perform an HTTP GET request and return status and body.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "params": {"type": "object"},
                        "headers": {"type": "object"},
                    },
                    "required": ["url"],
                },
            },
        },
        http_get,
    )

    _register_tool(
        "http_post",
        {
            "type": "function",
            "function": {
                "name": "http_post",
                "description": "Perform an HTTP POST request with an optional JSON body.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "json_body": {"type": "object"},
                        "headers": {"type": "object"},
                    },
                    "required": ["url"],
                },
            },
        },
        http_post,
    )

    # Whisper and TTS (optional tools)
    _register_tool(
        "transcribe_audio_tool",
        {
            "type": "function",
            "function": {
                "name": "transcribe_audio_tool",
                "description": "Transcribe an audio file from disk using Whisper.",
                "parameters": {
                    "type": "object",
                    "properties": {"file_path": {"type": "string"}},
                    "required": ["file_path"],
                },
            },
        },
        transcribe_audio_tool,
    )

    _register_tool(
        "synthesize_speech",
        {
            "type": "function",
            "function": {
                "name": "synthesize_speech",
                "description": "Generate speech audio from text using TTS.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "voice": {"type": "string", "default": "alloy"},
                    },
                    "required": ["text"],
                },
            },
        },
        synthesize_speech,
    )


def get_tool_schemas() -> List[Dict[str, Any]]:
    """Return OpenAI-compatible tool schemas for all registered tools."""

    _init_default_tools()
    return list(_TOOL_SCHEMAS.values())


async def _tool_gmail_agentic_search(user_id: int, query: str = "", max_results: Optional[int] = None, user_message: str = "") -> Dict[str, Any]:
    return await gmail_agentic_search(
        user_id=user_id,
        query=query,
        max_results=max_results,
        user_message=user_message
    )

async def _tool_gmail_agentic_bulk_action(user_id: int, action: str, query: str, action_params: Dict[str, Any], confirm: bool = False) -> Dict[str, Any]:
    return await gmail_agentic_bulk_action(
        user_id=user_id,
        action=action,
        query=query,
        action_params=action_params,
        confirm=confirm
    )

async def run_tool(name: str, args: Dict[str, Any], user_id: Optional[int] = None) -> Any:
    """Execute a named tool with the provided arguments.

    Returns tool output or an error structure if the call fails.
    """

    _init_default_tools()

    # Automatically inject user_id for Gmail agentic tools if not provided
    if name in ["gmail_agentic_search", "gmail_agentic_bulk_action"] and user_id is not None:
        args = dict(args)  # Make a copy to avoid modifying original
        if "user_id" not in args:
            args["user_id"] = user_id

    executor = _TOOL_EXECUTORS.get(name)
    if not executor:
        logger.error("Requested unknown tool: %s", name)
        return {"error": "UNKNOWN_TOOL", "tool": name}

    safe_args = args or {}

    if name == "trello_update_card":
        fields = safe_args.get("fields")

        top_level_note = ""
        for k in ["comment_text", "note_text", "comment", "note", "text"]:
            if isinstance(safe_args.get(k), str) and str(safe_args.get(k)).strip():
                top_level_note = str(safe_args.get(k)).strip()
                break

        if top_level_note:
            card_id = safe_args.get("card_id")
            if isinstance(card_id, str):
                card_id = card_id.strip()
            if not isinstance(card_id, str) or not card_id:
                return {
                    "success": False,
                    "error": "MISSING_CARD",
                    "message": "Which Trello task should I add the note to?",
                }
            result = await trello_add_comment(card_id=card_id, text=top_level_note)
            if not isinstance(result, dict) or not result.get("success"):
                return result
            return {
                "success": True,
                "message": "Note added to the task.",
                "data": result.get("data"),
            }

        if isinstance(fields, dict):
            note = ""
            for k in ["comment_text", "note_text", "comment", "note", "text"]:
                if isinstance(fields.get(k), str) and fields.get(k).strip():
                    note = str(fields.get(k)).strip()
                    break

            card_id = safe_args.get("card_id")
            if isinstance(card_id, str):
                card_id = card_id.strip()

            if any(k in fields for k in ["comment", "comment_text", "note", "note_text", "text"]):
                if not isinstance(card_id, str) or not card_id:
                    return {
                        "success": False,
                        "error": "MISSING_CARD",
                        "message": "Which Trello task should I add the note to?",
                    }

                if not note:
                    return {
                        "success": True,
                        "status": "comment_required",
                        "message": "What note should I add to that Trello task?",
                        "data": {"card_id": card_id},
                    }

                result = await trello_add_comment(card_id=card_id, text=note)
                if not isinstance(result, dict) or not result.get("success"):
                    return result

                return {
                    "success": True,
                    "message": "Note added to the task.",
                    "data": result.get("data"),
                }

        if not isinstance(fields, dict) or not fields:
            constructed: Dict[str, Any] = {}
            for k in [
                "due",
                "due_date",
                "name",
                "title",
                "description",
                "desc",
                "labels",
                "members",
                "closed",
            ]:
                if k in safe_args and safe_args.get(k) is not None:
                    constructed[k] = safe_args.get(k)
            if constructed:
                fields = constructed
                safe_args["fields"] = fields

        if isinstance(fields, dict) and "due_date" in fields and "due" not in fields:
            fields["due"] = fields.get("due_date")

        if not isinstance(fields, dict) or not fields:
            logger.error("[TOOL ERROR] trello_update_card called without non-empty fields")
            logger.error(f"[TOOL ERROR] Args received: {safe_args}")
            return {
                "success": False,
                "error": "MISSING_FIELDS",
                "message": "I can't update a Trello task without specifying at least one field to change.",
            }
    
    # Debug: Log all tool calls with their arguments
    logger.info(f"[TOOL CALL] {name} with args: {safe_args}")

    try:
        return await executor(**safe_args)
    except TypeError as exc:
        logger.error(f"[TOOL ERROR] Invalid arguments for tool {name}")
        logger.error(f"[TOOL ERROR] Args received: {safe_args}")
        logger.error(f"[TOOL ERROR] Exception: {exc!r}")
        return {"error": "INVALID_ARGUMENTS", "tool": name, "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.error("Error while executing tool %s: %r", name, exc)
        return {"error": "TOOL_EXECUTION_FAILED", "tool": name}
