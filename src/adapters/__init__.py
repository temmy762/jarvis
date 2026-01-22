"""Adapters package for the Jarvis AI Agent.

This package contains tool adapters that implement the BulkToolAdapter interface,
providing a standardized way for tools to expose bulk operation capabilities.
"""

from src.adapters.bulk_tool_adapter import (
    BulkToolAdapter,
    PreparedBulkContext,
    BulkItem,
    BulkResult,
)

__all__ = [
    "BulkToolAdapter",
    "PreparedBulkContext",
    "BulkItem",
    "BulkResult",
]
