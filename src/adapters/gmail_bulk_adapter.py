"""Gmail bulk operations adapter for the Jarvis AI Agent.

This adapter implements the BulkToolAdapter interface for Gmail operations.

Supported actions:
- label: Apply labels to emails
- archive: Archive emails (remove INBOX label)
- move_to_label: Apply label and remove INBOX (combined operation)
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.adapters.bulk_tool_adapter import (
    BulkToolAdapter,
    PreparedBulkContext,
    BulkItem,
    BulkResult,
)
from src.services.gmail_advanced import gmail_resolve_label_id
from src.services.gmail_bulk import gmail_batch_modify_labels, gmail_list_message_ids_page


class GmailBulkAdapter(BulkToolAdapter):
    """Gmail bulk operations adapter.

    Supports:
    - label: Add labels to emails
    - archive: Remove INBOX label from emails
    - move_to_label: Add label and remove INBOX
    """

    @property
    def tool_name(self) -> str:
        return "gmail"

    async def prepare(self, params: Dict[str, Any]) -> PreparedBulkContext:
        """Prepare Gmail bulk operation context.

        Expected params:
        - action: "label", "archive", or "move_to_label"
        - query_type: "sender", "keyword", "subject", "label", or "date_range"
        - query_value: The value for the query (e.g., sender email, keyword, etc.)
        - label_name: (for label/move_to_label actions) Human-readable label name
        - after: (optional, for date_range) Start date
        - before: (optional, for date_range) End date

        Returns:
            PreparedBulkContext with validated query and action parameters.

        Raises:
            ValueError: If required parameters are missing or invalid.
        """

        action = params.get("action")
        if not action or action not in ["label", "archive", "move_to_label"]:
            raise ValueError(
                f"Invalid or missing action. Must be one of: label, archive, move_to_label"
            )

        query_type = params.get("query_type")
        if not query_type or query_type not in [
            "sender",
            "keyword",
            "subject",
            "label",
            "date_range",
        ]:
            raise ValueError(
                f"Invalid or missing query_type. Must be one of: sender, keyword, subject, label, date_range"
            )

        query_value = params.get("query_value")
        if not query_value and query_type != "date_range":
            raise ValueError("query_value is required for this query_type")

        # Build a Gmail query string (Gmail search syntax)
        # This MUST remain deterministic and MUST NOT trigger any network calls.
        query_params: Dict[str, Any] = {"query_type": query_type}

        if query_type == "sender":
            query_params["sender"] = query_value
            query_params["gmail_query"] = f"from:{query_value}"
        elif query_type == "keyword":
            query_params["keyword"] = query_value
            query_params["gmail_query"] = str(query_value)
        elif query_type == "subject":
            query_params["subject"] = query_value
            query_params["gmail_query"] = f"subject:{query_value}"
        elif query_type == "label":
            query_params["label"] = query_value
            # Label query can be either name or ID; Gmail query syntax uses label:
            query_params["gmail_query"] = f"label:{query_value}"
        elif query_type == "date_range":
            after = params.get("after")
            before = params.get("before")
            if not after and not before:
                raise ValueError("date_range requires at least 'after' or 'before'")
            query_params["after"] = after
            query_params["before"] = before
            parts = []
            if after:
                parts.append(f"after:{after}")
            if before:
                parts.append(f"before:{before}")
            query_params["gmail_query"] = " ".join(parts)

        # Build action_params based on action
        action_params = {}

        if action in ["label", "move_to_label"]:
            label_name = params.get("label_name")
            if not label_name:
                raise ValueError(f"label_name is required for action '{action}'")

            # Resolve label name to ID
            resolve_result = await gmail_resolve_label_id(label_name)
            if not resolve_result.get("success"):
                raise ValueError(
                    f"Label '{label_name}' not found. Available labels can be listed with gmail_list_labels."
                )

            label_id = resolve_result["data"]["id"]
            action_params["label_id"] = label_id
            action_params["label_name"] = label_name

        # The adapter owns pagination state; it must be stored in JSON-safe metadata.
        # The bulk gate will persist this via BulkOperationState.metadata.
        return PreparedBulkContext(
            tool_name="gmail",
            action=action,
            query_params=query_params,
            action_params=action_params,
            metadata={
                "page_token": None,
            },
        )

    async def get_total_count(self, context: PreparedBulkContext) -> int:
        """Get total count of emails matching the query.

        Args:
            context: Prepared bulk context from prepare().

        Returns:
            Total number of emails matching the query.

        Raises:
            Exception: If the count query fails.
        """

        query = context.query_params.get("gmail_query")
        if not query:
            raise ValueError("Missing gmail_query in prepared context")

        # Exactly ONE list call to get an estimated count.
        page = await gmail_list_message_ids_page(query=query, max_results=1, page_token=None)
        if not page.get("success"):
            raise Exception(f"Failed to count emails: {page.get('error', 'Unknown error')}")

        estimate = page.get("data", {}).get("result_size_estimate")
        if estimate is None:
            # Gmail may omit estimate; fall back to at-least-1 if any messages returned.
            return len(page.get("data", {}).get("message_ids", []) or [])

        return int(estimate)

    async def get_next_batch(
        self, context: PreparedBulkContext, batch_size: int, offset: int = 0
    ) -> List[BulkItem]:
        """Fetch next batch of emails.

        Args:
            context: Prepared bulk context.
            batch_size: Maximum number of items to fetch.
            offset: Number of items to skip (for pagination).

        Returns:
            List of BulkItem objects representing emails.

        Raises:
            Exception: If the fetch fails.
        """

        # NOTE: The offset parameter is intentionally ignored for Gmail.
        # We MUST NOT refetch from page 1 and slice, as that causes request storms.
        query = context.query_params.get("gmail_query")
        if not query:
            raise ValueError("Missing gmail_query in prepared context")

        page_token = None
        if context.metadata:
            page_token = context.metadata.get("page_token")

        page = await gmail_list_message_ids_page(
            query=query,
            max_results=batch_size,
            page_token=page_token,
        )

        if not page.get("success"):
            raise Exception(f"Failed to fetch message IDs: {page.get('error', 'Unknown error')}")

        data = page.get("data", {})
        next_token = data.get("next_page_token")
        estimate = data.get("result_size_estimate")

        if context.metadata is None:
            context.metadata = {}
        context.metadata["page_token"] = next_token
        if estimate is not None:
            context.metadata["total_estimated_count"] = int(estimate)

        message_ids = data.get("message_ids", []) or []
        return [BulkItem(id=mid, display_name=mid, raw_data=None) for mid in message_ids]

    async def execute_batch(
        self, items: List[BulkItem], context: PreparedBulkContext
    ) -> List[BulkResult]:
        """Execute the action on a batch of emails.

        Args:
            items: List of emails to process.
            context: Prepared bulk context with action parameters.

        Returns:
            List of BulkResult objects, one per email.
        """

        # Execute exactly ONE Gmail batchModify call.
        action = context.action
        message_ids = [i.id for i in items]

        add_label_ids: List[str] = []
        remove_label_ids: List[str] = []

        if action == "label":
            add_label_ids = [context.action_params["label_id"]]
        elif action == "archive":
            remove_label_ids = ["INBOX"]
        elif action == "move_to_label":
            add_label_ids = [context.action_params["label_id"]]
            remove_label_ids = ["INBOX"]
        else:
            return [
                BulkResult(
                    item_id=mid,
                    success=False,
                    error=f"Unsupported Gmail bulk action: {action}",
                )
                for mid in message_ids
            ]

        result = await gmail_batch_modify_labels(
            message_ids=message_ids,
            add_label_ids=add_label_ids,
            remove_label_ids=remove_label_ids,
        )

        if result.get("success"):
            return [BulkResult(item_id=mid, success=True) for mid in message_ids]

        # Auth/permission errors should terminate the bulk operation immediately.
        status_code = result.get("status_code")
        if status_code in (401, 403):
            raise PermissionError(result.get("error") or "GMAIL_AUTH_ERROR")

        err = result.get("error", "Unknown error")
        return [BulkResult(item_id=mid, success=False, error=str(err)) for mid in message_ids]
