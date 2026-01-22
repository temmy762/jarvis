# Bulk Tool Adapter Contract

## Purpose

This document defines the **universal interface** that ALL bulk-capable tools must implement in Jarvis.

It enforces strict separation of concerns:
- **Tools** provide primitives (prepare, count, fetch, execute)
- **Controllers** orchestrate batching and state management
- **Agents** handle conversation flow and user confirmation

No tool should ever:
- Talk directly to the agent
- Manage continuation logic
- Know about conversation state
- Handle user confirmations

---

## The Interface

Every bulk-capable tool MUST implement `BulkToolAdapter`:

```python
class BulkToolAdapter(ABC):
    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Return the name of this tool (e.g., 'gmail', 'calendar')."""
        pass

    @abstractmethod
    async def prepare(self, params: Dict[str, Any]) -> PreparedBulkContext:
        """Prepare a bulk operation context from user-provided parameters."""
        pass

    @abstractmethod
    async def get_total_count(self, context: PreparedBulkContext) -> int:
        """Get the total number of items matching the query."""
        pass

    @abstractmethod
    async def get_next_batch(
        self, context: PreparedBulkContext, batch_size: int, offset: int = 0
    ) -> List[BulkItem]:
        """Fetch the next batch of items to process."""
        pass

    @abstractmethod
    async def execute_batch(
        self, items: List[BulkItem], context: PreparedBulkContext
    ) -> List[BulkResult]:
        """Execute the action on a batch of items."""
        pass
```

---

## Data Structures

### PreparedBulkContext

Returned by `prepare()`. Contains all information needed to fetch and process items.

```python
@dataclass
class PreparedBulkContext:
    tool_name: str              # e.g., "gmail"
    action: str                 # e.g., "label"
    query_params: Dict[str, Any]  # e.g., {"sender": "hostinger"}
    action_params: Dict[str, Any] # e.g., {"label_id": "Label_123"}
    metadata: Optional[Dict[str, Any]] = None
```

### BulkItem

Represents a single item in a bulk operation.

```python
@dataclass
class BulkItem:
    id: str                     # Unique identifier
    display_name: str           # Human-readable name
    raw_data: Optional[Dict[str, Any]] = None  # Full item data if needed
```

### BulkResult

Represents the result of executing an action on one item.

```python
@dataclass
class BulkResult:
    item_id: str
    success: bool
    error: Optional[str] = None
```

---

## Method Contracts

### 1. `prepare(params) -> PreparedBulkContext`

**Purpose**: Validate and normalize user-provided parameters.

**Responsibilities**:
- Validate required parameters
- Resolve human-readable names to IDs (e.g., label names → label IDs)
- Split parameters into query_params (for fetching) and action_params (for execution)
- Raise `ValueError` if parameters are invalid

**Example (Gmail)**:
```python
async def prepare(self, params):
    action = params.get("action")
    sender = params.get("sender")
    label_name = params.get("label_name")

    if not action or not sender or not label_name:
        raise ValueError("Missing required parameters")

    # Resolve label name to ID
    label_result = await gmail_resolve_label_id(label_name)
    if not label_result.get("success"):
        raise ValueError(f"Label '{label_name}' not found")

    label_id = label_result["data"]["id"]

    return PreparedBulkContext(
        tool_name="gmail",
        action=action,
        query_params={"sender": sender},
        action_params={"label_id": label_id},
    )
```

**Critical rules**:
- Do NOT fetch items in this method
- Do NOT execute any actions
- Only validate and prepare

---

### 2. `get_total_count(context) -> int`

**Purpose**: Return the total number of items matching the query.

**Responsibilities**:
- Execute a count query using `context.query_params`
- Return an integer count
- Raise exception if the count query fails

**Example (Gmail)**:
```python
async def get_total_count(self, context):
    # Use existing Gmail search with limit=1 to get count
    result = await gmail_search(
        query=f"from:{context.query_params['sender']}",
        limit=1
    )
    if not result.get("success"):
        raise Exception("Failed to count emails")

    return result.get("total_count", 0)
```

**Critical rules**:
- Do NOT fetch full item data
- Do NOT execute any actions
- Keep this fast (use count-only queries if available)

---

### 3. `get_next_batch(context, batch_size, offset) -> List[BulkItem]`

**Purpose**: Fetch the next batch of items to process.

**Responsibilities**:
- Use `context.query_params` to build the query
- Fetch up to `batch_size` items, skipping `offset` items
- Convert raw items to `BulkItem` objects
- Return an empty list if no more items

**Example (Gmail)**:
```python
async def get_next_batch(self, context, batch_size, offset):
    result = await gmail_fetch_by_sender(
        sender=context.query_params["sender"],
        limit=batch_size,
        # Note: offset may require custom implementation
    )

    if not result.get("success"):
        raise Exception("Failed to fetch emails")

    items = []
    for msg in result.get("data", []):
        items.append(
            BulkItem(
                id=msg["id"],
                display_name=msg.get("subject", "(no subject)"),
                raw_data=msg,
            )
        )

    return items
```

**Critical rules**:
- Do NOT execute any actions
- Do NOT fetch more than `batch_size` items
- Handle pagination correctly

---

### 4. `execute_batch(items, context) -> List[BulkResult]`

**Purpose**: Execute the action on a batch of items.

**Responsibilities**:
- Use `context.action_params` to perform the action
- Process each item independently
- Capture per-item errors without stopping the batch
- Return a `BulkResult` for each item

**Example (Gmail)**:
```python
async def execute_batch(self, items, context):
    results = []
    label_id = context.action_params["label_id"]

    for item in items:
        try:
            result = await gmail_label(item.id, [label_id])
            if result.get("success"):
                results.append(BulkResult(item_id=item.id, success=True))
            else:
                results.append(
                    BulkResult(
                        item_id=item.id,
                        success=False,
                        error=result.get("error", "Unknown error"),
                    )
                )
        except Exception as exc:
            results.append(
                BulkResult(item_id=item.id, success=False, error=str(exc))
            )

    return results
```

**Critical rules**:
- Individual item failures do NOT raise exceptions
- Always return a `BulkResult` for each item
- Do NOT retry failed items (let the user decide)

---

## Adapter Registry

All adapters should be registered in a central registry for easy lookup:

```python
# src/adapters/registry.py
from src.adapters.gmail_bulk_adapter import GmailBulkAdapter
from src.adapters.calendar_bulk_adapter import CalendarBulkAdapter
from src.adapters.trello_bulk_adapter import TrelloBulkAdapter

BULK_ADAPTERS = {
    "gmail": GmailBulkAdapter(),
    "calendar": CalendarBulkAdapter(),
    "trello": TrelloBulkAdapter(),
}

def get_adapter(tool_name: str) -> BulkToolAdapter:
    adapter = BULK_ADAPTERS.get(tool_name)
    if not adapter:
        raise ValueError(f"No bulk adapter registered for tool: {tool_name}")
    return adapter
```

---

## Integration with Bulk Operations Controller

The controller uses adapters like this:

```python
# 1. Prepare
adapter = get_adapter("gmail")
context = await adapter.prepare(params)

# 2. Count
total = await adapter.get_total_count(context)

# 3. Fetch batch
items = await adapter.get_next_batch(context, batch_size=10, offset=0)

# 4. Execute
results = await adapter.execute_batch(items, context)
```

The controller handles:
- State management
- User confirmation
- Progress tracking
- Error aggregation

The adapter only provides primitives.

---

## Testing Checklist

Before deploying a new adapter, verify:

- [ ] `prepare()` validates all required parameters
- [ ] `prepare()` resolves human-readable names to IDs
- [ ] `prepare()` raises `ValueError` for invalid input
- [ ] `get_total_count()` returns accurate count
- [ ] `get_next_batch()` respects `batch_size` and `offset`
- [ ] `get_next_batch()` returns empty list when no more items
- [ ] `execute_batch()` processes all items even if some fail
- [ ] `execute_batch()` returns a `BulkResult` for each item
- [ ] Individual item errors are captured, not raised

---

## Anti-Patterns (DO NOT DO THIS)

### ❌ Managing conversation state in adapter
```python
# WRONG: Adapter should not store state
class GmailBulkAdapter:
    def __init__(self):
        self.current_batch = []  # NO
```

### ❌ Calling agent methods from adapter
```python
# WRONG: Adapter should not talk to agent
async def execute_batch(self, items, context):
    await agent.send_message("Processing...")  # NO
```

### ❌ Auto-retrying failed items
```python
# WRONG: Let the user decide whether to retry
async def execute_batch(self, items, context):
    for item in items:
        for attempt in range(3):  # NO
            try:
                await process(item)
                break
            except:
                continue
```

### ❌ Fetching all items at once
```python
# WRONG: Respect batch_size
async def get_next_batch(self, context, batch_size, offset):
    return await fetch_all_items()  # NO
```

---

## Summary

This contract ensures that:
- Tools are reusable and composable
- Agent logic stays clean
- Bulk operations are safe and predictable
- New tools can be added easily

**When implementing a new adapter, follow this contract exactly.**
