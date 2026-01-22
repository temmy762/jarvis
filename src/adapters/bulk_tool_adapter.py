"""Universal bulk tool adapter interface for the Jarvis AI Agent.

This module defines the standard contract that ALL bulk-capable tools must implement.
It enforces clean separation between:
- Tool-specific logic (adapters)
- Agent conversation flow (agent.py)
- Bulk operation orchestration (controllers/bulk_operations.py)

NO tool should talk directly to the agent.
NO tool should manage continuation or conversation state.
NO tool should know about user confirmations.

Tools only know how to:
1. Prepare a bulk context
2. Count total items
3. Fetch items in batches
4. Execute operations on items
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class PreparedBulkContext:
    """Represents a prepared bulk operation context.

    This is returned by the adapter's prepare() method and contains
    all the information needed to fetch and process items.

    Attributes:
        tool_name: Name of the tool (e.g., "gmail", "calendar", "trello").
        action: The action to perform (e.g., "label", "delete", "archive").
        query_params: Tool-specific parameters for fetching items
                      (e.g., {"sender": "hostinger"} for Gmail).
        action_params: Tool-specific parameters for executing the action
                       (e.g., {"label_id": "Label_123"} for Gmail labeling).
        metadata: Optional additional context.
    """

    tool_name: str
    action: str
    query_params: Dict[str, Any]
    action_params: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class BulkItem:
    """Represents a single item in a bulk operation.

    Attributes:
        id: Unique identifier for the item (e.g., Gmail message ID).
        display_name: Human-readable name for logging/display.
        raw_data: Optional full item data if needed for execution.
    """

    id: str
    display_name: str
    raw_data: Optional[Dict[str, Any]] = None


@dataclass
class BulkResult:
    """Represents the result of executing an action on one item.

    Attributes:
        item_id: The ID of the item that was processed.
        success: Whether the operation succeeded.
        error: Error message if success is False, None otherwise.
    """

    item_id: str
    success: bool
    error: Optional[str] = None


class BulkToolAdapter(ABC):
    """Abstract base class for all bulk-capable tool adapters.

    Every tool that supports bulk operations (Gmail, Calendar, Trello, etc.)
    must implement this interface.

    The adapter is stateless and does NOT manage conversation flow.
    It only provides the primitives needed by the bulk operations controller.
    """

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Return the name of this tool (e.g., 'gmail', 'calendar')."""
        pass

    @abstractmethod
    async def prepare(self, params: Dict[str, Any]) -> PreparedBulkContext:
        """Prepare a bulk operation context from user-provided parameters.

        This method validates and normalizes the parameters, resolving any
        human-readable names to IDs (e.g., label names to label IDs).

        Args:
            params: Raw parameters from the agent, e.g.:
                    {
                        "action": "label",
                        "sender": "hostinger",
                        "label_name": "Work"
                    }

        Returns:
            A PreparedBulkContext with validated query and action parameters.

        Raises:
            ValueError: If parameters are invalid or incomplete.

        Example (Gmail):
            params = {"action": "label", "sender": "hostinger", "label_name": "Work"}
            context = await adapter.prepare(params)
            # context.query_params = {"sender": "hostinger"}
            # context.action_params = {"label_id": "Label_123"}
        """
        pass

    @abstractmethod
    async def get_total_count(self, context: PreparedBulkContext) -> int:
        """Get the total number of items matching the query.

        This is used to show the user how many items will be affected
        BEFORE starting the bulk operation.

        Args:
            context: The prepared bulk context from prepare().

        Returns:
            Total count of items that match the query.

        Raises:
            Exception: If the count query fails (e.g., API error).

        Example (Gmail):
            count = await adapter.get_total_count(context)
            # Returns 50 if there are 50 emails from "hostinger"
        """
        pass

    @abstractmethod
    async def get_next_batch(
        self, context: PreparedBulkContext, batch_size: int, offset: int = 0
    ) -> List[BulkItem]:
        """Fetch the next batch of items to process.

        This method is called by the bulk operations controller to retrieve
        items in manageable chunks.

        Args:
            context: The prepared bulk context from prepare().
            batch_size: Maximum number of items to fetch.
            offset: Number of items to skip (for pagination).

        Returns:
            A list of BulkItem objects, up to batch_size in length.

        Raises:
            Exception: If the fetch fails (e.g., API error).

        Example (Gmail):
            batch = await adapter.get_next_batch(context, batch_size=10, offset=0)
            # Returns first 10 emails from "hostinger"
        """
        pass

    @abstractmethod
    async def execute_batch(
        self, items: List[BulkItem], context: PreparedBulkContext
    ) -> List[BulkResult]:
        """Execute the action on a batch of items.

        This method processes each item and returns a result for each.
        Individual item failures should NOT raise exceptions; instead,
        they should be captured in the BulkResult.

        Args:
            items: List of items to process.
            context: The prepared bulk context with action parameters.

        Returns:
            A list of BulkResult objects, one per item.

        Example (Gmail):
            results = await adapter.execute_batch(items, context)
            # Applies label_id to each email, returns success/failure per item
        """
        pass


# ============================================================================
# USAGE EXAMPLE (Conceptual — not actual implementation)
# ============================================================================
#
# class GmailBulkAdapter(BulkToolAdapter):
#     @property
#     def tool_name(self) -> str:
#         return "gmail"
#
#     async def prepare(self, params):
#         # Validate params
#         action = params.get("action")
#         sender = params.get("sender")
#         label_name = params.get("label_name")
#
#         # Resolve label name to ID
#         label_id = await gmail_resolve_label_id(label_name)
#
#         return PreparedBulkContext(
#             tool_name="gmail",
#             action=action,
#             query_params={"sender": sender},
#             action_params={"label_id": label_id},
#         )
#
#     async def get_total_count(self, context):
#         result = await gmail_fetch_by_sender(
#             context.query_params["sender"], limit=1
#         )
#         return result.get("total_count", 0)
#
#     async def get_next_batch(self, context, batch_size, offset):
#         result = await gmail_fetch_by_sender(
#             context.query_params["sender"],
#             limit=batch_size,
#             offset=offset,
#         )
#         return [
#             BulkItem(id=msg["id"], display_name=msg["subject"])
#             for msg in result["data"]
#         ]
#
#     async def execute_batch(self, items, context):
#         results = []
#         for item in items:
#             try:
#                 await gmail_label(item.id, [context.action_params["label_id"]])
#                 results.append(BulkResult(item_id=item.id, success=True))
#             except Exception as exc:
#                 results.append(
#                     BulkResult(item_id=item.id, success=False, error=str(exc))
#                 )
#         return results
