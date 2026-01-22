# Bulk Gate Integration Guide

## Purpose

This document explains how to integrate the bulk gate into the existing Jarvis agent loop.

The bulk gate is the **single decision point** for all bulk operation handling.

---

## The Law: Decision Flow

```
┌─────────────────────────────────────┐
│  User sends message                 │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Is there an active bulk session?   │
└──────────────┬──────────────────────┘
               │
       ┌───────┴───────┐
       │               │
      YES              NO
       │               │
       ▼               ▼
┌──────────────┐  ┌──────────────────┐
│ Bulk Gate    │  │ Normal Intent    │
│ (continue/   │  │ Routing          │
│  cancel only)│  │                  │
└──────────────┘  └──────────────────┘
```

---

## Integration Steps

### Step 1: Add Bulk State Storage

The agent must store the active bulk operation state somewhere accessible across turns.

**Option A: In-memory (simple, for single-instance deployments)**

```python
# In agent.py or a shared context module
ACTIVE_BULK_SESSIONS: Dict[int, Dict[str, Any]] = {}

def get_bulk_state(user_id: int) -> Optional[Dict[str, Any]]:
    return ACTIVE_BULK_SESSIONS.get(user_id)

def set_bulk_state(user_id: int, state: Dict[str, Any]) -> None:
    ACTIVE_BULK_SESSIONS[user_id] = state

def clear_bulk_state(user_id: int) -> None:
    ACTIVE_BULK_SESSIONS.pop(user_id, None)
```

**Option B: Conversation context (recommended for multi-turn conversations)**

Store in the `messages` list as a special metadata entry:

```python
messages.append({
    "role": "system",
    "content": json.dumps({
        "type": "bulk_operation_state",
        "state": state_dict
    })
})
```

**Option C: Supabase (for persistent, multi-instance deployments)**

Store in a `bulk_operation_sessions` table with TTL.

---

### Step 2: Modify Agent Loop Entry Point

In `src/core/agent.py`, add the bulk gate check **before** normal intent routing:

```python
async def agent(user_id: int, message: str, request_id: str | None = None) -> str:
    """Main agent entrypoint for a single user turn."""

    log_info("Agent started", user_id=str(user_id), request_id=request_id)

    # NEW: Check bulk gate FIRST
    active_bulk_state = get_bulk_state(user_id)
    active_adapter = None

    if active_bulk_state:
        # Reconstruct adapter from state
        tool_name = active_bulk_state.get("domain")
        active_adapter = get_adapter(tool_name)  # From adapter registry

    bulk_result = await check_bulk_gate(
        user_message=message,
        active_bulk_state=active_bulk_state,
        adapter=active_adapter,
    )

    if bulk_result["handled"]:
        # Bulk gate handled this message
        if bulk_result.get("clear_state"):
            clear_bulk_state(user_id)
        elif bulk_result.get("new_state"):
            set_bulk_state(user_id, bulk_result["new_state"])

        return bulk_result["response"]

    # If not handled by bulk gate, proceed with normal agent logic
    try:
        ctx = await build_context(user_id, message)
    except Exception as exc:
        logger.error("Failed to build context: %r", exc)
        return "Sorry, I had trouble preparing your conversation context."

    # ... rest of existing agent logic
```

---

### Step 3: Add Bulk Start Detection

In the normal intent routing (after bulk gate returns `handled=False`), detect when the user wants to start a bulk operation:

```python
# After LLM determines intent and tool to use
if tool_name in ["gmail_bulk_label", "gmail_bulk_archive", "calendar_bulk_delete", etc.]:
    # This is a bulk operation request
    adapter = get_adapter(extract_domain_from_tool(tool_name))

    result = await initiate_bulk_operation(
        adapter=adapter,
        params=tool_args,
        batch_size=10,  # Or extract from tool_args
    )

    if result["success"]:
        set_bulk_state(user_id, result["state"])
        return result["response"]
    else:
        return result["error"]
```

**Alternative: Detect bulk intent from existing tools**

If the LLM calls a normal tool (e.g., `gmail_fetch_by_sender`) and the result contains many items, the agent can offer to convert it to a bulk operation:

```python
if tool_name == "gmail_fetch_by_sender":
    result = await run_tool(tool_name, tool_args)
    item_count = len(result.get("data", []))

    if item_count > 20:
        # Offer bulk operation
        return (
            f"Found {item_count} emails. This is a large operation.\n\n"
            f"Would you like me to process them in batches? Say 'yes' to start."
        )
```

---

### Step 4: Add Adapter Registry

Create `src/adapters/registry.py`:

```python
from typing import Dict
from src.adapters.bulk_tool_adapter import BulkToolAdapter
from src.adapters.gmail_bulk_adapter import GmailBulkAdapter
# Import other adapters as they're implemented

BULK_ADAPTERS: Dict[str, BulkToolAdapter] = {
    "gmail": GmailBulkAdapter(),
    # "calendar": CalendarBulkAdapter(),
    # "trello": TrelloBulkAdapter(),
}

def get_adapter(tool_name: str) -> BulkToolAdapter:
    adapter = BULK_ADAPTERS.get(tool_name)
    if not adapter:
        raise ValueError(f"No bulk adapter registered for tool: {tool_name}")
    return adapter
```

---

## Complete Flow Example

### Scenario: User wants to label 50 emails

**Turn 1: User request**
```
User: "Label all emails from Hostinger with 'Work'"
```

**Agent logic:**
1. `check_bulk_gate()` → `handled=False` (no active session)
2. Normal intent routing detects bulk operation
3. `initiate_bulk_operation()` called:
   - `adapter.prepare()` validates params, resolves "Work" → `Label_123`
   - `adapter.get_total_count()` → 50 emails
   - Check 50 ≤ MAX_TOTAL_ITEMS (200) ✓
   - `start_bulk_operation()` creates state
   - `present_bulk_status()` formats response
4. Store state, return response

**Agent response:**
```
Ready to label 50 emails in batches of 10.
Say 'continue' to start, or 'cancel' to abort.
```

---

**Turn 2: User confirms**
```
User: "continue"
```

**Agent logic:**
1. `check_bulk_gate()` → `handled=True` (active session exists)
2. Intent = "continue"
3. `adapter.get_next_batch()` → first 10 emails
4. `adapter.execute_batch()` → label each email
5. Update state (10/50 processed)
6. `present_bulk_status()` formats response
7. Store updated state, return response

**Agent response:**
```
Processed 10 items (10/50 total). 40 items remaining.
Say 'continue' to process the next batch, or 'cancel' to stop.
```

---

**Turn 3: User continues**
```
User: "yes"
```

**Agent logic:**
1. `check_bulk_gate()` → `handled=True`
2. Intent = "continue"
3. Process next batch (20/50 processed)
4. Return response

**Agent response:**
```
Processed 10 items (20/50 total). 30 items remaining.
Say 'continue' to process the next batch, or 'cancel' to stop.
```

---

**Turn 6: Final batch**
```
User: "continue"
```

**Agent logic:**
1. `check_bulk_gate()` → `handled=True`
2. Intent = "continue"
3. Process final batch (50/50 processed)
4. `needs_confirmation=False` → operation complete
5. Clear state, return response

**Agent response:**
```
✅ Completed! Processed 50/50 items.
```

---

## Critical Rules

1. **Always check bulk gate first** before normal intent routing.
2. **Never auto-continue** bulk operations.
3. **Always store state** after initiation or continuation.
4. **Always clear state** after completion or cancellation.
5. **Never bypass the gate** with custom logic.

---

## Error Handling

### Adapter errors during initiation
```python
result = await initiate_bulk_operation(...)
if not result["success"]:
    return result["error"]  # Show error to user, don't store state
```

### Adapter errors during continuation
```python
# check_bulk_gate handles this internally
# Returns error message but keeps state intact so user can retry
```

### State corruption
```python
try:
    state = BulkOperationState.from_dict(active_bulk_state)
except Exception:
    clear_bulk_state(user_id)
    return "Your bulk operation state was corrupted. Please start over."
```

---

## Testing Checklist

- [ ] Bulk gate returns `handled=False` when no active session
- [ ] Bulk gate returns `handled=True` when session is active
- [ ] "continue" intent processes exactly one batch
- [ ] "cancel" intent clears state and returns summary
- [ ] Unclear intent returns reminder message
- [ ] State is stored after initiation
- [ ] State is updated after each batch
- [ ] State is cleared after completion
- [ ] State is cleared after cancellation
- [ ] MAX_TOTAL_ITEMS is enforced during initiation
- [ ] Batch size is clamped to MIN/MAX limits

---

## Summary

The bulk gate is a **single, deterministic decision point** that:
- Checks for active bulk sessions
- Routes to continue/cancel only when active
- Delegates to normal intent routing when inactive
- Enforces all capacity limits
- Manages state lifecycle

**Integration is simple: Add one check at the top of the agent loop.**
