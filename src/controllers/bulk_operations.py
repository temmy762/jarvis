"""Bulk Operations Controller for the Jarvis AI Agent.

This module provides a reusable, domain-agnostic controller for safely handling
large or multi-item user requests. It processes operations in small batches,
pauses after each batch, and requires explicit user confirmation before continuing.

Usage Pattern
-------------
1. **Start a bulk operation:**
   Call `start_bulk_operation(...)` with the domain, action name, list of items,
   and optional batch size. This returns an initial state and metadata but does
   NOT process any items yet.

2. **Process one batch:**
   Call `continue_bulk_operation(state, action_callable)` where `action_callable`
   is an async function that processes exactly ONE item. This processes up to
   `batch_size` items and returns updated state.

3. **Store the returned state:**
   Jarvis should store the returned `state` dict (e.g., in conversation context
   or memory) so it can be passed back when the user confirms continuation.

4. **Resume on user confirmation:**
   When the user says "continue" or "yes", Jarvis reconstructs the state from
   the stored dict and calls `continue_bulk_operation(...)` again.

5. **Cancel if requested:**
   If the user says "stop" or "cancel", call `cancel_bulk_operation(state)`.

Example Domains
---------------
- **Gmail:** Bulk label, archive, delete, or move emails.
- **Calendar:** Bulk delete or update events.
- **Trello:** Bulk move cards, add labels, or archive items.

The controller is stateless internally; all state is passed in and returned
as a serializable dict, making it safe for async and multi-turn conversations.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Awaitable, Callable, Dict, List, Optional


@dataclass
class BulkOperationState:
    """Represents the current state of a bulk operation.

    Attributes:
        op_id: Unique identifier for this bulk operation.
        domain: The domain this operation applies to (e.g., "gmail", "calendar", "trello").
        action: The action being performed (e.g., "label", "archive", "delete").
        batch_size: Number of items to process per batch.
        total: Total number of items in the original request.
        processed: Number of items processed so far.
        remaining_items: List of items still to be processed.
        metadata: Optional domain-specific metadata (e.g., label ID, target list).
    """

    op_id: str
    domain: str
    action: str
    batch_size: int
    total: int
    processed: int
    remaining_items: List[Any]
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state to a JSON-safe dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BulkOperationState":
        """Reconstruct state from a dictionary."""
        return cls(
            op_id=data["op_id"],
            domain=data["domain"],
            action=data["action"],
            batch_size=data["batch_size"],
            total=data["total"],
            processed=data["processed"],
            remaining_items=data["remaining_items"],
            metadata=data.get("metadata") or {},
        )


async def start_bulk_operation(
    domain: str,
    action: str,
    items: List[Any],
    batch_size: int = 10,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Initialize a new bulk operation without processing any items.

    This function sets up the operation state and returns it to Jarvis.
    No items are processed until `continue_bulk_operation` is called.

    Args:
        domain: The domain (e.g., "gmail", "calendar", "trello").
        action: The action to perform (e.g., "label", "archive", "delete").
        items: The full list of items to process.
        batch_size: How many items to process per batch (default 10).
        metadata: Optional domain-specific data (e.g., {"label_id": "Label_123"}).

    Returns:
        A dict with:
        - success: True
        - processed_this_batch: 0
        - processed_total: 0
        - remaining: len(items)
        - total: len(items)
        - needs_confirmation: True (always, since no work done yet)
        - state: Serialized BulkOperationState
        - errors: None

    Example:
        result = await start_bulk_operation(
            domain="gmail",
            action="label",
            items=["msg_1", "msg_2", ..., "msg_50"],
            batch_size=10,
            metadata={"label_id": "Label_Work"}
        )
        # Jarvis stores result["state"] and asks user to confirm.
    """

    state = BulkOperationState(
        op_id=str(uuid.uuid4()),
        domain=domain,
        action=action,
        batch_size=batch_size,
        total=len(items),
        processed=0,
        remaining_items=list(items),
        metadata=metadata or {},
    )

    return {
        "success": True,
        "processed_this_batch": 0,
        "processed_total": 0,
        "remaining": len(items),
        "total": len(items),
        "needs_confirmation": True,
        "state": state.to_dict(),
        "errors": None,
    }


async def continue_bulk_operation(
    state: BulkOperationState,
    action_callable: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
) -> Dict[str, Any]:
    """Process exactly ONE batch of items and return updated state.

    This function:
    - Takes up to `batch_size` items from `remaining_items`.
    - Calls `action_callable(item, metadata)` for each item.
    - Collects any per-item errors without stopping the batch.
    - Returns updated state for Jarvis to store and use on next confirmation.

    IMPORTANT:
    - This function processes ONE batch only.
    - It does NOT loop until completion.
    - It does NOT call itself or schedule further work.
    - Jarvis must explicitly call this again after user confirmation.

    Args:
        state: The current BulkOperationState (from start or previous continue).
        action_callable: An async function with signature:
            async def action_callable(item: Any, metadata: dict) -> Any
            It should process exactly ONE item and return a result or raise.

    Returns:
        A dict with:
        - success: True if batch completed (even with some item errors)
        - processed_this_batch: Number of items processed in this call
        - processed_total: Cumulative items processed so far
        - remaining: Items still left to process
        - total: Original total
        - needs_confirmation: True if more items remain, False if done
        - state: Updated serialized state
        - errors: List of {"item": ..., "error": ...} for failed items, or None

    Example:
        # Reconstruct state from stored dict
        state = BulkOperationState.from_dict(stored_state_dict)

        # Define the action (wraps existing single-item function)
        async def label_one_email(msg_id, meta):
            return await gmail_label(msg_id, [meta["label_id"]])

        result = await continue_bulk_operation(state, label_one_email)

        if result["needs_confirmation"]:
            # Ask user: "Processed 10/50. Continue?"
            # Store result["state"] for next round.
        else:
            # Done: "All 50 items processed."
    """

    batch = state.remaining_items[: state.batch_size]
    remaining_after = state.remaining_items[state.batch_size :]

    errors: List[Dict[str, Any]] = []
    processed_count = 0

    for item in batch:
        try:
            await action_callable(item, state.metadata or {})
            processed_count += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"item": item, "error": str(exc)})
            processed_count += 1  # Count as processed even if failed

    # Update state
    state.processed += processed_count
    state.remaining_items = remaining_after

    needs_confirmation = len(remaining_after) > 0

    return {
        "success": True,
        "processed_this_batch": processed_count,
        "processed_total": state.processed,
        "remaining": len(remaining_after),
        "total": state.total,
        "needs_confirmation": needs_confirmation,
        "state": state.to_dict(),
        "errors": errors if errors else None,
    }


async def cancel_bulk_operation(state: BulkOperationState) -> Dict[str, Any]:
    """Cancel an in-progress bulk operation.

    This simply acknowledges the cancellation and returns a summary of what
    was processed before cancellation. No further items will be processed.

    Args:
        state: The current BulkOperationState.

    Returns:
        A dict with:
        - success: True
        - cancelled: True
        - processed_total: Items processed before cancellation
        - remaining: Items that were NOT processed
        - total: Original total
        - message: Human-readable cancellation summary

    Example:
        state = BulkOperationState.from_dict(stored_state_dict)
        result = await cancel_bulk_operation(state)
        # Jarvis tells user: "Cancelled. 20/50 items were processed."
    """

    return {
        "success": True,
        "cancelled": True,
        "processed_total": state.processed,
        "remaining": len(state.remaining_items),
        "total": state.total,
        "message": (
            f"Bulk {state.action} on {state.domain} cancelled. "
            f"{state.processed}/{state.total} items were processed before cancellation."
        ),
    }
