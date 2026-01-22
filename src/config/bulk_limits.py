"""Bulk operation capacity constraints for the Jarvis AI Agent.

This module defines hard safety limits for bulk operations to prevent
resource exhaustion, API rate limiting, and uncontrolled execution.

These limits are enforced by higher-level logic (intent routers, agent handlers)
and are NOT enforced by the bulk_operations controller itself, which remains
domain-agnostic and stateless.
"""

# Maximum number of items that may be processed in a single batch.
# This limit applies to all domains (Gmail, Calendar, Trello, etc.).
#
# Rationale:
# - Prevents overwhelming external APIs (Gmail, Google Calendar, Trello)
# - Keeps LLM context size manageable when reporting results
# - Ensures reasonable response times per user turn
# - Allows graceful error recovery without losing too much progress
#
# This value should be tuned based on:
# - Average API latency per item
# - Acceptable user wait time (typically 10-30 seconds)
# - LLM context window constraints
MAX_BATCH_SIZE = 20

# Maximum total items allowed in a single bulk operation request.
# If a user requests more than this, Jarvis should reject or ask to narrow scope.
#
# Rationale:
# - Prevents accidentally triggering operations on thousands of items
# - Forces users to be explicit about very large operations
# - Reduces risk of partial failures affecting too many items
MAX_TOTAL_ITEMS = 200

# Minimum batch size (for validation).
# Batch sizes below this are inefficient and should default to this value.
MIN_BATCH_SIZE = 5
