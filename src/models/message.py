"""Message models for the Jarvis AI Agent.

This module defines normalized message representations used across services.
TODO: Extend with channel-specific metadata and validation.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class MessageType(str, Enum):
    """Types of messages that Jarvis can handle."""

    TEXT = "text"
    VOICE = "voice"
    COMMAND = "command"
    CAPTION = "caption"


class NormalizedMessage(BaseModel):
    """Universal incoming message format used by the agent.

    This model matches the normalization contract described in the system
    directive for the Telegram message normalizer.
    """

    user_id: int
    username: Optional[str]
    message: str
    type: str
    timestamp: datetime
    raw: dict


class RawTelegramUpdate(BaseModel):
    """Minimal representation of a raw Telegram update payload.

    This model will be used for validation of incoming webhook data in
    later phases.
    """

    update_id: int
    message: Optional[dict] = None
    callback_query: Optional[dict] = None


def normalize_message_placeholder(raw: Any) -> None:
    """Placeholder for future normalization entrypoint.

    TODO: Implement normalization and return NormalizedMessage.
    """
    # Placeholder implementation for Phase 1.
    pass
