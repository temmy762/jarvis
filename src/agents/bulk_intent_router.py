"""Bulk operation intent router for the Jarvis AI Agent.

This module provides deterministic intent classification for bulk operation
control commands. It maps user text to explicit intents without fuzzy inference.

The router is stateless and has no side effects. It only classifies intent.
"""

from typing import Literal


BulkIntent = Literal["continue", "cancel", "unknown"]


def classify_bulk_intent(user_message: str) -> BulkIntent:
    """Classify user intent for bulk operation control.

    This function uses explicit keyword matching to determine if the user
    wants to continue, cancel, or if the intent is unclear.

    NO fuzzy inference. NO LLM calls. NO guessing.

    Args:
        user_message: The raw user text (case-insensitive matching applied).

    Returns:
        One of:
        - "continue": User explicitly wants to proceed with next batch
        - "cancel": User explicitly wants to stop the operation
        - "unknown": Intent is unclear or unrelated to bulk control

    Intent Detection Rules:
        Continue: "continue", "yes", "proceed", "go", "next", "go ahead", "keep going"
        Cancel: "cancel", "stop", "abort", "no", "halt", "quit", "end"

    Examples:
        >>> classify_bulk_intent("continue")
        'continue'
        >>> classify_bulk_intent("Yes, go ahead")
        'continue'
        >>> classify_bulk_intent("stop")
        'cancel'
        >>> classify_bulk_intent("what's the weather?")
        'unknown'
    """

    normalized = user_message.strip().lower()

    # Continue intents (explicit confirmation)
    continue_keywords = [
        "continue",
        "yes",
        "proceed",
        "go",
        "next",
        "go ahead",
        "keep going",
        "resume",
        "ok",
        "okay",
        "sure",
        "yep",
        "yeah",
    ]

    for keyword in continue_keywords:
        if keyword in normalized:
            return "continue"

    # Cancel intents (explicit stop)
    cancel_keywords = [
        "cancel",
        "stop",
        "abort",
        "no",
        "halt",
        "quit",
        "end",
        "don't",
        "do not",
        "never mind",
        "nevermind",
    ]

    for keyword in cancel_keywords:
        if keyword in normalized:
            return "cancel"

    # If no clear intent, return unknown
    return "unknown"


def requires_bulk_continuation(user_message: str) -> bool:
    """Check if user message is a bulk continuation command.

    This is a convenience wrapper around classify_bulk_intent for
    use in agent logic that needs a simple boolean check.

    Args:
        user_message: The raw user text.

    Returns:
        True if intent is "continue", False otherwise.

    Example:
        >>> requires_bulk_continuation("yes, continue")
        True
        >>> requires_bulk_continuation("cancel")
        False
        >>> requires_bulk_continuation("show me my emails")
        False
    """

    return classify_bulk_intent(user_message) == "continue"


def requires_bulk_cancellation(user_message: str) -> bool:
    """Check if user message is a bulk cancellation command.

    This is a convenience wrapper around classify_bulk_intent for
    use in agent logic that needs a simple boolean check.

    Args:
        user_message: The raw user text.

    Returns:
        True if intent is "cancel", False otherwise.

    Example:
        >>> requires_bulk_cancellation("stop")
        True
        >>> requires_bulk_cancellation("continue")
        False
        >>> requires_bulk_cancellation("what time is it?")
        False
    """

    return classify_bulk_intent(user_message) == "cancel"
