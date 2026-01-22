"""Formatting helpers for the Jarvis AI Agent.

This module provides utilities for rendering model responses into
human-friendly text or markup.
TODO: Implement rich formatting for Telegram and other channels.
"""

from typing import Any, Dict, List, Optional


def safe_get(d: Dict[str, Any], path: List[Any], default: Optional[Any] = None) -> Any:
    """Safely traverse a nested dict using a list path.

    Similar to lodash's ``get`` helper. Returns ``default`` if any step in the
    path is missing or not a mapping.
    """

    current: Any = d
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def detect_type(message_dict: Dict[str, Any]) -> str:
    """Detect the high-level type of a Telegram message payload.

    Returns one of: "command", "text", "voice", "audio", "caption", or
    "unknown".
    """

    if not isinstance(message_dict, dict):
        return "unknown"

    text = message_dict.get("text") or ""

    if text.startswith("/"):
        return "command"

    if "voice" in message_dict:
        return "voice"

    if "audio" in message_dict:
        return "audio"

    if "caption" in message_dict and (
        "photo" in message_dict or "video" in message_dict or "document" in message_dict
    ):
        return "caption"

    if "text" in message_dict:
        return "text"

    if any(key in message_dict for key in ("photo", "video", "document")):
        return "caption"

    return "unknown"


class MessageFormatter:
    """Helper for turning structured agent outputs into displayable messages."""

    def __init__(self) -> None:
        """Initialize the formatter."""
        # Placeholder for any future configuration.
        pass

    def format_text(self, data: Any) -> str:
        """Format structured data into a text string.

        TODO: Implement formatting rules for different message types.
        """
        # Placeholder implementation for Phase 1.
        return str(data)
