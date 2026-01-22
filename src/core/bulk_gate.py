"""Bulk operation gate for the Jarvis AI Agent.

This module implements the SINGLE decision point for bulk operation handling
in the agent loop. It enforces strict control flow:

1. Check if there's an active bulk session
2. If yes → only accept continue/cancel
3. If no → proceed with normal intent routing

This is the ONLY place where bulk operation state is checked and routed.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.adapters.bulk_tool_adapter import BulkToolAdapter
from src.agents.bulk_intent_router import classify_bulk_intent
from src.config.bulk_limits import MAX_TOTAL_ITEMS, MAX_BATCH_SIZE, MIN_BATCH_SIZE
from src.controllers.bulk_operations import (
    BulkOperationState,
    start_bulk_operation,
    continue_bulk_operation,
    cancel_bulk_operation,
)
from src.presenters.bulk_status_presenter import present_bulk_status
from src.adapters.bulk_tool_adapter import PreparedBulkContext, BulkItem


async def check_bulk_gate(
    user_message: str,
    active_bulk_state: Optional[Dict[str, Any]],
    adapter: Optional[BulkToolAdapter] = None,
) -> Dict[str, Any]:
    """The single bulk operation gate in the agent loop.

    This function implements the canonical decision flow:

    1. Is there an active bulk session?
       - Yes → only accept continue/cancel
       - No → return None (proceed with normal intent routing)

    2. On "continue":
       - Reconstruct state
       - Get next batch from adapter
       - Execute batch via adapter
       - Update state via continue_bulk_operation
       - Present status
       - Return response

    3. On "cancel":
       - Reconstruct state
       - Cancel via cancel_bulk_operation
       - Present status
       - Return response

    4. On anything else (when bulk is active):
       - Return reminder to continue or cancel

    Args:
        user_message: The raw user text.
        active_bulk_state: The stored bulk state dict, or None if no active session.
        adapter: The BulkToolAdapter for the active session (required if active_bulk_state is set).

    Returns:
        A dict with:
        - handled (bool): True if bulk gate handled this message, False if agent should proceed normally
        - response (str, optional): The response to send to user (if handled=True)
        - new_state (dict, optional): Updated bulk state to store (if handled=True)
        - clear_state (bool, optional): True if bulk state should be cleared (if handled=True)

    Example:
        result = await check_bulk_gate(user_message, active_bulk_state, adapter)
        if result["handled"]:
            # Bulk gate handled it
            return result["response"]
        else:
            # Proceed with normal agent logic
            ...
    """

    # Case 1: No active bulk session → proceed with normal intent routing
    if not active_bulk_state:
        return {"handled": False}

    # Case 2: Active bulk session exists → only accept continue/cancel
    intent = classify_bulk_intent(user_message)

    # Reconstruct state
    state = BulkOperationState.from_dict(active_bulk_state)

    # Sub-case 2a: User wants to continue
    if intent == "continue":
        if not adapter:
            return {
                "handled": True,
                "response": "Internal error: No adapter available for bulk operation.",
                "clear_state": True,
            }

        try:
            # Gmail bulk must obey strict limits per turn:
            # - <= 1 list-page call
            # - <= 1 batchModify call
            if state.domain == "gmail":
                prepared_context_dict = (state.metadata or {}).get("prepared_context")
                if not isinstance(prepared_context_dict, dict):
                    raise ValueError("Missing prepared_context for gmail bulk operation")

                # Reconstruct PreparedBulkContext (JSON-safe)
                ctx = PreparedBulkContext(
                    tool_name=prepared_context_dict["tool_name"],
                    action=prepared_context_dict["action"],
                    query_params=prepared_context_dict["query_params"],
                    action_params=prepared_context_dict["action_params"],
                    metadata=prepared_context_dict.get("metadata") or {},
                )

                # Load persisted pagination state
                message_buffer = list((state.metadata or {}).get("message_buffer") or [])
                page_token = (state.metadata or {}).get("page_token")
                ctx.metadata["page_token"] = page_token

                # If we don't have enough buffered IDs for this batch, fetch exactly ONE page.
                if len(message_buffer) < state.batch_size and page_token is not None:
                    page_items = await adapter.get_next_batch(
                        context=ctx,
                        batch_size=state.batch_size,
                        offset=0,
                    )
                    message_buffer.extend([i.id for i in page_items])
                    page_token = (ctx.metadata or {}).get("page_token")

                # Pop <= batch_size IDs from buffer
                batch_ids = message_buffer[: state.batch_size]
                message_buffer = message_buffer[len(batch_ids) :]

                # If no IDs are available, we are done (estimate may have been high).
                if not batch_ids:
                    state.remaining_items = []
                    bulk_result = {
                        "success": True,
                        "processed_this_batch": 0,
                        "processed_total": state.processed,
                        "remaining": 0,
                        "total": state.total,
                        "needs_confirmation": False,
                        "state": state.to_dict(),
                        "errors": None,
                    }
                    return {
                        "handled": True,
                        "response": present_bulk_status(bulk_result),
                        "new_state": None,
                        "clear_state": True,
                    }

                # Execute exactly ONE batchModify call via adapter
                results = await adapter.execute_batch(
                    items=[BulkItem(id=mid, display_name=mid, raw_data=None) for mid in batch_ids],
                    context=ctx,
                )

                # Convert adapter results to error list
                errors = []
                for result in results:
                    if not result.success:
                        errors.append({"item": result.item_id, "error": result.error})

                # Update progress and remaining placeholders
                state.processed += len(batch_ids)
                state.remaining_items = state.remaining_items[len(batch_ids) :]

                # Persist pagination state
                if state.metadata is None:
                    state.metadata = {}
                state.metadata["message_buffer"] = message_buffer
                state.metadata["page_token"] = page_token
                prepared_context_dict["metadata"] = ctx.metadata
                state.metadata["prepared_context"] = prepared_context_dict

                bulk_result = {
                    "success": True,
                    "processed_this_batch": len(batch_ids),
                    "processed_total": state.processed,
                    "remaining": len(state.remaining_items),
                    "total": state.total,
                    "needs_confirmation": len(state.remaining_items) > 0,
                    "state": state.to_dict(),
                    "errors": errors if errors else None,
                }

                response = present_bulk_status(bulk_result)
                clear_state = not bulk_result["needs_confirmation"]

                return {
                    "handled": True,
                    "response": response,
                    "new_state": bulk_result["state"] if not clear_state else None,
                    "clear_state": clear_state,
                }

            # Non-gmail domains (not yet rolled out): fall back to previous behavior.
            # Get next batch from adapter
            batch = await adapter.get_next_batch(
                context=state.metadata.get("prepared_context"),
                batch_size=state.batch_size,
                offset=state.processed,
            )

            # Execute batch via adapter
            results = await adapter.execute_batch(
                items=batch,
                context=state.metadata.get("prepared_context"),
            )

            # Convert adapter results to simple success/failure for controller
            # The controller expects action_callable to process one item at a time,
            # but we've already processed the batch, so we'll update state manually
            errors = []
            success_count = 0
            for result in results:
                if result.success:
                    success_count += 1
                else:
                    errors.append({"item": result.item_id, "error": result.error})

            # Update state
            state.processed += len(batch)
            state.remaining_items = state.remaining_items[len(batch) :]

            # Build result dict
            bulk_result = {
                "success": True,
                "processed_this_batch": len(batch),
                "processed_total": state.processed,
                "remaining": len(state.remaining_items),
                "total": state.total,
                "needs_confirmation": len(state.remaining_items) > 0,
                "state": state.to_dict(),
                "errors": errors if errors else None,
            }

            # Present status
            response = present_bulk_status(bulk_result)

            # Determine if we should clear state (operation complete)
            clear_state = not bulk_result["needs_confirmation"]

            return {
                "handled": True,
                "response": response,
                "new_state": bulk_result["state"] if not clear_state else None,
                "clear_state": clear_state,
            }

        except Exception as exc:
            return {
                "handled": True,
                "response": (
                    f"An error occurred while processing this batch: {exc}\n\n"
                    f"You can try again by saying 'continue', or say 'cancel' to stop."
                ),
                "new_state": state.to_dict(),
                "clear_state": False,
            }

    # Sub-case 2b: User wants to cancel
    if intent == "cancel":
        result = await cancel_bulk_operation(state)
        response = present_bulk_status(result)
        return {
            "handled": True,
            "response": response,
            "clear_state": True,
        }

    # Sub-case 2c: User said something else (unclear intent)
    return {
        "handled": True,
        "response": (
            f"You have an active bulk operation in progress "
            f"({state.processed}/{state.total} items processed).\n\n"
            f"Please say **'continue'** to process the next batch, "
            f"or **'cancel'** to stop the operation."
        ),
        "new_state": state.to_dict(),
        "clear_state": False,
    }


async def initiate_bulk_operation(
    adapter: BulkToolAdapter,
    params: Dict[str, Any],
    batch_size: int = MAX_BATCH_SIZE,
) -> Dict[str, Any]:
    """Initiate a new bulk operation.

    This function implements the bulk start flow:

    1. Call adapter.prepare() to validate and normalize parameters
    2. Call adapter.get_total_count() to get total items
    3. Enforce MAX_TOTAL_ITEMS limit
    4. Validate batch_size against MIN/MAX limits
    5. Call start_bulk_operation() to initialize state
    6. Present status to user
    7. Return response and state

    Args:
        adapter: The BulkToolAdapter for the target tool.
        params: Raw parameters from the user (e.g., {"action": "label", "sender": "hostinger"}).
        batch_size: Number of items per batch (default: MAX_BATCH_SIZE).

    Returns:
        A dict with:
        - success (bool): True if initialization succeeded
        - response (str): Message to send to user
        - state (dict, optional): Initial bulk state to store
        - error (str, optional): Error message if success=False

    Example:
        result = await initiate_bulk_operation(
            adapter=gmail_adapter,
            params={"action": "label", "sender": "hostinger", "label_name": "Work"},
            batch_size=10
        )
        if result["success"]:
            # Store result["state"] and send result["response"]
        else:
            # Send result["error"]
    """

    try:
        # Step 1: Prepare and validate
        context = await adapter.prepare(params)

        # Step 4: Validate batch_size
        if batch_size < MIN_BATCH_SIZE:
            batch_size = MIN_BATCH_SIZE
        if batch_size > MAX_BATCH_SIZE:
            batch_size = MAX_BATCH_SIZE

        # Step 5 (Gmail only): Fetch EXACTLY ONE list page (IDs only) and STOP.
        # - No eager pagination
        # - No loops
        # - No processing
        if adapter.tool_name == "gmail":
            # Gmail START (no processing):
            # - Fetch exactly ONE search/list page (IDs only)
            # - Store page_token + message_buffer in JSON-safe bulk state
            # - Derive total_estimated_count from the same page (no extra list call)
            first_page = await adapter.get_next_batch(
                context=context,
                batch_size=batch_size,
                offset=0,
            )

            message_buffer = [i.id for i in first_page]
            page_token = (context.metadata or {}).get("page_token")
            total_count = (context.metadata or {}).get("total_estimated_count")
            if total_count is None:
                total_count = len(message_buffer)
            total_count = int(total_count)

            # Enforce MAX_TOTAL_ITEMS based on estimate
            if total_count > MAX_TOTAL_ITEMS:
                return {
                    "success": False,
                    "error": (
                        f"This operation would affect {total_count} items, "
                        f"which exceeds the maximum limit of {MAX_TOTAL_ITEMS}.\n\n"
                        f"Please narrow your query (e.g., add date filters or more specific criteria)."
                    ),
                }

            if total_count == 0:
                return {
                    "success": False,
                    "error": "No items found matching your criteria.",
                }

            # Initialize bulk operation state with placeholders only.
            # This avoids eager fetching IDs while keeping controller totals accurate.
            placeholder_items = [0] * total_count

            result = await start_bulk_operation(
                domain=adapter.tool_name,
                action=context.action,
                items=placeholder_items,
                batch_size=batch_size,
                metadata={
                    "prepared_context": {
                        "tool_name": context.tool_name,
                        "action": context.action,
                        "query_params": context.query_params,
                        "action_params": context.action_params,
                        "metadata": context.metadata or {},
                    },
                    "page_token": page_token,
                    "message_buffer": message_buffer,
                    "total_estimated_count": int(total_count),
                },
            )

            response = present_bulk_status(result)

            return {
                "success": True,
                "response": response,
                "state": result["state"],
            }

        # Step 5 (other domains): not implemented in this rollout.
        return {
            "success": False,
            "error": f"Bulk operations are not enabled for tool: {adapter.tool_name}",
        }

        # Step 7: Present status
        response = present_bulk_status(result)

        return {
            "success": True,
            "response": response,
            "state": result["state"],
        }

    except ValueError as exc:
        return {
            "success": False,
            "error": f"Invalid parameters: {exc}",
        }
    except Exception as exc:
        return {
            "success": False,
            "error": f"Failed to initialize bulk operation: {exc}",
        }
