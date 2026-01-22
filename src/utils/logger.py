"""Logging utilities for the Jarvis AI Agent.

This module centralizes logger configuration for the application.
TODO: Implement file-based handlers.
"""

import json
import logging
import uuid
from typing import Optional


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a configured logger instance.

    TODO: Add log formatting and levels.
    TODO: Add log formatting, levels, and handlers.
    """
    logger_name = name or "jarvis"
    logger = logging.getLogger(logger_name)

    # Configure a basic console handler once so logs are visible during
    # development. In later phases this can be replaced with structured
    # logging and file-based handlers.
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    return logger


def generate_request_id() -> str:
    """Generate a unique request identifier for correlating logs."""

    return str(uuid.uuid4())


def _format_telegram_message(msg: str) -> str:
    """Prefix a log message with the Jarvis Telegram tag.

    TODO: Generalize prefixes for other channels and subsystems.
    """

    return f"[JARVIS-TELEGRAM] {msg}"
def _format_structured_message(
    message: str,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> str:
    """Format a log message as a JSON-like structured string."""

    payload: dict = {"message": message}
    if user_id is not None:
        payload["user_id"] = user_id
    if request_id is not None:
        payload["request_id"] = request_id
    if extra:
        payload["extra"] = extra
    return json.dumps(payload, default=str)


def log_info(
    msg: str,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    **extra: object,
) -> None:
    """Log an informational message for Telegram-related activity."""

    logger = get_logger("jarvis.telegram")
    logger.setLevel(logging.INFO)
    structured = _format_structured_message(
        _format_telegram_message(msg),
        user_id=user_id,
        request_id=request_id,
        extra=extra or None,
    )
    logger.info(structured)


def log_warn(
    msg: str,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    **extra: object,
) -> None:
    """Log a warning message for Telegram-related activity."""

    logger = get_logger("jarvis.telegram")
    logger.setLevel(logging.WARNING)
    structured = _format_structured_message(
        _format_telegram_message(msg),
        user_id=user_id,
        request_id=request_id,
        extra=extra or None,
    )
    logger.warning(structured)


def log_error(
    msg: str,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    **extra: object,
) -> None:
    """Log an error message for Telegram-related activity."""

    logger = get_logger("jarvis.telegram")
    logger.setLevel(logging.ERROR)
    structured = _format_structured_message(
        _format_telegram_message(msg),
        user_id=user_id,
        request_id=request_id,
        extra=extra or None,
    )
    logger.error(structured)
