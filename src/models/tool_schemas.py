"""Tool schema models for the Jarvis AI Agent.

This module defines Pydantic models that describe inputs and outputs for
tools exposed to the LLM.
TODO: Add detailed schemas for Gmail, calendar, web fetch, and memory tools.
"""

from typing import Any, Dict

from pydantic import BaseModel


class BaseToolSchema(BaseModel):
    """Base class for all tool input/output schemas."""

    # TODO: Extend with common metadata fields as needed.
    pass


def get_all_tool_schemas() -> Dict[str, Any]:
    """Return a mapping of tool names to their schema definitions.

    TODO: Populate this mapping as tools are implemented.
    """
    # Placeholder implementation for Phase 1.
    return {}
