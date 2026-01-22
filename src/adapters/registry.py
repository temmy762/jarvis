"""Bulk adapter registry for the Jarvis AI Agent.

This module provides a central registry for all bulk-capable tool adapters.
"""

from typing import Dict

from src.adapters.bulk_tool_adapter import BulkToolAdapter
from src.adapters.gmail_bulk_adapter import GmailBulkAdapter


# Central registry of all bulk adapters
BULK_ADAPTERS: Dict[str, BulkToolAdapter] = {
    "gmail": GmailBulkAdapter(),
    # Wave 2 adapters (to be added):
    # "calendar": CalendarBulkAdapter(),
    # Wave 3 adapters (to be added):
    # "trello": TrelloBulkAdapter(),
}


def get_adapter(tool_name: str) -> BulkToolAdapter:
    """Get a bulk adapter by tool name.

    Args:
        tool_name: The name of the tool (e.g., "gmail", "calendar", "trello").

    Returns:
        The registered BulkToolAdapter for that tool.

    Raises:
        ValueError: If no adapter is registered for the given tool name.

    Example:
        >>> adapter = get_adapter("gmail")
        >>> isinstance(adapter, GmailBulkAdapter)
        True
    """

    adapter = BULK_ADAPTERS.get(tool_name)
    if not adapter:
        available = ", ".join(BULK_ADAPTERS.keys())
        raise ValueError(
            f"No bulk adapter registered for tool: {tool_name}. "
            f"Available adapters: {available}"
        )
    return adapter


def list_available_adapters() -> list[str]:
    """List all registered bulk adapter names.

    Returns:
        List of tool names that have bulk adapters.

    Example:
        >>> list_available_adapters()
        ['gmail']
    """

    return list(BULK_ADAPTERS.keys())
