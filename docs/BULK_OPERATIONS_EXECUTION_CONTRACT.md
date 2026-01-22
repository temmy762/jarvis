# Bulk Operations Execution Contract

## Purpose

This document defines the **canonical execution lifecycle** for bulk operations in Jarvis.

It is a binding contract for all engineers working on agent logic, tool integrations, and conversation flows.

Violating this contract will result in:
- Uncontrolled execution
- Resource exhaustion
- Poor user experience
- Difficult-to-debug failures

---

## Core Principles

1. **Human-in-the-loop**: Every batch requires explicit user confirmation.
2. **Stateless execution**: No background loops, schedulers, or persistent workers.
3. **Deterministic behavior**: Same input → same output, always.
4. **Crash-resistant**: Individual item failures do not stop the batch.
5. **Transparent progress**: User always knows what was done and what remains.

---

## Execution Lifecycle (Step-by-Step)

### Phase 1: Initialization

**Trigger**: User requests a bulk operation (e.g., "label all emails from X").

**Agent behavior**:
1. Detect that the request involves multiple items (e.g., 50 emails).
2. Call `start_bulk_operation(domain, action, items, batch_size, metadata)`.
3. Store the returned `state` dict in conversation context or memory.
4. Present the initial status to the user using `present_bulk_status(result)`.
5. **STOP and WAIT** for user confirmation.

**Critical rules**:
- Do NOT process any items in this phase.
- Do NOT call `continue_bulk_operation` automatically.
- Do NOT loop or schedule future work.

**Example user-facing message**:
> "Ready to label 50 emails in batches of 10. Say 'continue' to start, or 'cancel' to abort."

---

### Phase 2: User Confirmation

**Trigger**: User responds with a message.

**Agent behavior**:
1. Classify user intent using `classify_bulk_intent(user_message)`.
2. If intent is `"continue"`:
   - Proceed to Phase 3 (Batch Execution).
3. If intent is `"cancel"`:
   - Proceed to Phase 5 (Cancellation).
4. If intent is `"unknown"`:
   - Treat as a new, unrelated request.
   - Do NOT auto-continue the bulk operation.

**Critical rules**:
- Do NOT guess user intent.
- Do NOT auto-continue if the message is ambiguous.
- If unsure, ask the user explicitly: "Did you mean to continue the bulk operation?"

---

### Phase 3: Batch Execution

**Trigger**: User confirmed continuation (intent = `"continue"`).

**Agent behavior**:
1. Reconstruct `BulkOperationState` from the stored state dict:
   ```python
   state = BulkOperationState.from_dict(stored_state_dict)
   ```
2. Define the `action_callable` for the specific domain/action:
   ```python
   async def action_callable(item, metadata):
       # Call existing single-item function
       return await some_existing_function(item, metadata)
   ```
3. Call `continue_bulk_operation(state, action_callable)`.
4. Store the returned updated `state` dict.
5. Present the result to the user using `present_bulk_status(result)`.
6. **STOP and WAIT** for user confirmation again.

**Critical rules**:
- Process **exactly one batch** per user turn.
- Do NOT loop to process multiple batches.
- Do NOT call `continue_bulk_operation` recursively.
- Individual item errors are collected but do NOT stop the batch.

**Example user-facing message**:
> "Processed 10 items (10/50 total). 40 items remaining. Say 'continue' to process the next batch, or 'cancel' to stop."

---

### Phase 4: Completion

**Trigger**: `result["needs_confirmation"]` is `False` (all items processed).

**Agent behavior**:
1. Present the final status to the user using `present_bulk_status(result)`.
2. Clear the stored bulk operation state from conversation context.
3. Return to normal agent behavior.

**Critical rules**:
- Do NOT keep the state in memory after completion.
- If there were errors, present them using `present_bulk_errors(result["errors"])`.

**Example user-facing message**:
> "✅ Completed! Processed 50/50 items. 2 item(s) had errors."

---

### Phase 5: Cancellation

**Trigger**: User says "cancel" or similar (intent = `"cancel"`).

**Agent behavior**:
1. Reconstruct `BulkOperationState` from the stored state dict.
2. Call `cancel_bulk_operation(state)`.
3. Present the cancellation summary to the user using `present_bulk_status(result)`.
4. Clear the stored bulk operation state from conversation context.
5. Return to normal agent behavior.

**Critical rules**:
- Do NOT process any more items after cancellation.
- Do NOT ask for confirmation again.

**Example user-facing message**:
> "Bulk label on gmail cancelled. 20/50 items were processed before cancellation."

---

## State Management Rules

### Where to store state

**Option 1: Conversation context (recommended for short-term)**
- Store in the agent's `messages` list as a special metadata entry.
- Retrieve on next turn if user intent is `"continue"` or `"cancel"`.

**Option 2: Memory system (for longer sessions)**
- Store in Supabase or similar with a TTL (e.g., 1 hour).
- Retrieve by user ID + operation ID.

### When to clear state

- After completion (Phase 4).
- After cancellation (Phase 5).
- After 1 hour of inactivity (TTL expiration).

### State serialization

Always use:
```python
state_dict = state.to_dict()  # For storage
state = BulkOperationState.from_dict(state_dict)  # For retrieval
```

Never store the `BulkOperationState` object directly (not JSON-safe).

---

## Error Handling Rules

### Individual item errors

- Collect in `result["errors"]` list.
- Do NOT stop the batch.
- Present summary to user after batch completes.

### Batch-level errors (e.g., network failure)

- If `continue_bulk_operation` raises an exception:
  1. Log the error.
  2. Return a user-facing message: "An error occurred while processing this batch. Please try again or cancel."
  3. Do NOT auto-retry.
  4. Keep the state intact so user can retry manually.

### API rate limits

- If a domain-specific function (e.g., `gmail_label`) hits a rate limit:
  1. Treat as an individual item error.
  2. Continue processing remaining items in the batch.
  3. User can retry failed items later if needed.

---

## Capacity Limits

From `src/config/bulk_limits.py`:

- `MAX_BATCH_SIZE = 20`: Maximum items per batch.
- `MAX_TOTAL_ITEMS = 200`: Maximum items in a single bulk operation.
- `MIN_BATCH_SIZE = 5`: Minimum items per batch (for efficiency).

**Enforcement**:
- Agent logic must check `len(items) > MAX_TOTAL_ITEMS` before calling `start_bulk_operation`.
- If exceeded, reject the request or ask user to narrow scope.

---

## Anti-Patterns (DO NOT DO THIS)

### ❌ Auto-continuation
```python
# WRONG: Do not loop until completion
while result["needs_confirmation"]:
    result = await continue_bulk_operation(state, action_callable)
```

### ❌ Background processing
```python
# WRONG: Do not schedule async tasks
asyncio.create_task(process_all_batches())
```

### ❌ Guessing user intent
```python
# WRONG: Do not assume "yes" from ambiguous messages
if "maybe" in user_message:
    await continue_bulk_operation(...)
```

### ❌ Storing state in global variables
```python
# WRONG: Do not use module-level state
CURRENT_BULK_OP = None
```

### ❌ Modifying the controller
```python
# WRONG: Do not add loops inside bulk_operations.py
# The controller is stateless and must remain so
```

---

## Testing Checklist

Before deploying bulk operation logic, verify:

- [ ] User can start a bulk operation and see initial status.
- [ ] User can say "continue" and see progress after one batch.
- [ ] User can say "cancel" and see cancellation summary.
- [ ] Individual item errors are collected and reported.
- [ ] Batch-level errors do not crash the agent.
- [ ] State is cleared after completion or cancellation.
- [ ] Ambiguous user messages do NOT auto-continue.
- [ ] Operations respect `MAX_BATCH_SIZE` and `MAX_TOTAL_ITEMS`.

---

## Summary

This contract ensures that Jarvis handles bulk operations in a **safe, predictable, and user-friendly** manner.

Any deviation from this contract must be reviewed and approved by the team lead.

**When in doubt, ask the user for confirmation.**
