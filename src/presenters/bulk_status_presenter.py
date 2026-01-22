"""Bulk operation status presenter for the Jarvis AI Agent.

This module provides a pure presentation layer that converts bulk operation
state dictionaries into human-readable natural language responses.

The presenter has NO business logic and NO side effects. It only formats
data for display to the user.
"""

from typing import Any, Dict, Optional


def present_bulk_status(result: Dict[str, Any]) -> str:
    """Convert a bulk operation result dict into a natural language response.

    This function handles three scenarios:
    1. Operation in progress (needs user confirmation to continue)
    2. Operation completed (all items processed)
    3. Operation cancelled (user stopped early)

    Args:
        result: The dict returned by start_bulk_operation, continue_bulk_operation,
                or cancel_bulk_operation. Expected keys:
                - success (bool)
                - processed_this_batch (int, optional)
                - processed_total (int)
                - remaining (int)
                - total (int)
                - needs_confirmation (bool, optional)
                - cancelled (bool, optional)
                - errors (list, optional)
                - message (str, optional for cancellation)

    Returns:
        A concise, user-facing string describing the operation status.

    Examples:
        >>> result = {
        ...     "success": True,
        ...     "processed_this_batch": 10,
        ...     "processed_total": 10,
        ...     "remaining": 40,
        ...     "total": 50,
        ...     "needs_confirmation": True,
        ...     "errors": None
        ... }
        >>> present_bulk_status(result)
        "Processed 10 items (10/50 total). 40 items remaining. Say 'continue' to process the next batch, or 'cancel' to stop."

        >>> result = {
        ...     "success": True,
        ...     "processed_total": 50,
        ...     "remaining": 0,
        ...     "total": 50,
        ...     "needs_confirmation": False,
        ...     "errors": [{"item": "msg_5", "error": "API timeout"}]
        ... }
        >>> present_bulk_status(result)
        "Completed! Processed 50/50 items. 1 item(s) had errors."
    """

    # Handle cancellation
    if result.get("cancelled"):
        processed = result.get("processed_total", 0)
        total = result.get("total", 0)
        remaining = result.get("remaining", 0)
        msg = result.get("message", "Operation cancelled.")
        return (
            f"{msg}\n\n"
            f"Summary: {processed}/{total} items were processed. "
            f"{remaining} items were not processed."
        )

    # Extract common fields
    processed_total = result.get("processed_total", 0)
    remaining = result.get("remaining", 0)
    total = result.get("total", 0)
    errors = result.get("errors") or []
    needs_confirmation = result.get("needs_confirmation", False)
    processed_this_batch = result.get("processed_this_batch", 0)

    # Build error summary
    error_summary = ""
    if errors:
        error_count = len(errors)
        error_summary = f" {error_count} item(s) had errors."

    # Case 1: Operation in progress (needs continuation)
    if needs_confirmation and remaining > 0:
        return (
            f"Processed {processed_this_batch} item(s) this batch "
            f"({processed_total}/{total} total).{error_summary}\n\n"
            f"{remaining} item(s) remaining.\n\n"
            f"Say **'continue'** to process the next batch, or **'cancel'** to stop."
        )

    # Case 2: Operation completed (no items remaining)
    if remaining == 0:
        return (
            f"✅ Completed! Processed {processed_total}/{total} items.{error_summary}"
        )

    # Case 3: Initial state (no processing yet, just setup)
    if processed_total == 0 and needs_confirmation:
        return (
            f"Ready to process {total} item(s) in batches.\n\n"
            f"Say **'continue'** to start, or **'cancel'** to abort."
        )

    # Fallback (should not reach here in normal flow)
    return (
        f"Status: {processed_total}/{total} items processed. "
        f"{remaining} remaining.{error_summary}"
    )


def present_bulk_errors(errors: Optional[list]) -> str:
    """Format a list of per-item errors into a readable summary.

    Args:
        errors: List of dicts with "item" and "error" keys, or None.

    Returns:
        A formatted error report, or empty string if no errors.

    Example:
        >>> errors = [
        ...     {"item": "msg_1", "error": "API timeout"},
        ...     {"item": "msg_2", "error": "Invalid label ID"}
        ... ]
        >>> present_bulk_errors(errors)
        "Errors encountered:\\n- msg_1: API timeout\\n- msg_2: Invalid label ID"
    """

    if not errors:
        return ""

    lines = ["Errors encountered:"]
    for err in errors[:10]:  # Limit to first 10 to avoid overwhelming output
        item = err.get("item", "unknown")
        error = err.get("error", "unknown error")
        lines.append(f"- {item}: {error}")

    if len(errors) > 10:
        lines.append(f"... and {len(errors) - 10} more error(s).")

    return "\n".join(lines)
