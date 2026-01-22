# Jarvis Long-Term Memory System - Complete Documentation

## Overview

This is a comprehensive persistent memory subsystem for Saara's Jarvis AI assistant. The memory system stores user preferences, habits, personal details, and configuration in a JSON file that survives system restarts. The LLM can save and retrieve memory reliably through function-calling.

---

## Core Principle

**Jarvis remembers what matters.**

When the user says "I prefer short emails" or "my assistant is David", Jarvis:
1. Classifies the information as storable
2. Saves it to persistent storage with a descriptive key
3. Loads it automatically in future conversations
4. Uses it to personalize responses

---

## File Structure

```
src/
├── services/
│   └── memory_engine.py             # Memory engine (NEW)
└── core/
    ├── tools.py                     # Tool registry (UPDATED)
    └── context.py                   # Context builder (UPDATED)

data/
└── memory.json                      # Persistent storage (AUTO-CREATED)
```

---

## Module: `src/services/memory_engine.py`

### **Function 1: `save_memory(key, value)`**

**Purpose**: Save a key-value pair to persistent storage.

**Parameters**:
- `key` (required): Memory key (e.g., "email_preference", "assistant_name")
- `value` (required): Memory value (e.g., "short emails", "David")

**Behavior**:
- If key exists → updates value
- Prevents storing empty or invalid data
- Prevents storing duplicates
- Adds timestamps (created_at, updated_at)

**Returns**:
```python
{
    "success": True,
    "message": "Memory saved successfully",
    "key": "email_preference",
    "value": "short emails",
    "is_update": False
}
```

**Error Response**:
```python
{
    "success": False,
    "error": "INVALID_KEY",
    "message": "Memory key must be a non-empty string"
}
```

**Example Usage**:
```python
from src.services.memory_engine import save_memory

result = await save_memory("email_preference", "short emails")
# Returns: {"success": True, "message": "Memory saved successfully", ...}
```

---

### **Function 2: `load_memory()`**

**Purpose**: Load all memory entries from persistent storage.

**Parameters**: None

**Returns**:
```python
{
    "success": True,
    "memory": [
        {
            "key": "email_preference",
            "value": "short emails",
            "created_at": "2025-12-10T13:00:00",
            "updated_at": "2025-12-10T13:00:00"
        },
        {
            "key": "assistant_name",
            "value": "David"
        }
    ],
    "count": 2
}
```

**Error Response**:
```python
{
    "success": False,
    "error": "LOAD_ERROR: ...",
    "message": "An error occurred while loading memory",
    "memory": [],
    "count": 0
}
```

**Example Usage**:
```python
from src.services.memory_engine import load_memory

result = await load_memory()
memory_list = result["memory"]
```

---

### **Function 3: `delete_memory(key)`**

**Purpose**: Delete a memory entry by key.

**Parameters**:
- `key` (required): Memory key to delete

**Returns**:
```python
{
    "success": True,
    "message": "Memory deleted successfully",
    "key": "email_preference",
    "deleted_value": "short emails"
}
```

**Error Response** (key not found):
```python
{
    "success": False,
    "error": "KEY_NOT_FOUND",
    "message": "Memory key 'email_preference' does not exist"
}
```

**Example Usage**:
```python
from src.services.memory_engine import delete_memory

result = await delete_memory("email_preference")
```

---

### **Function 4: `list_memory()`**

**Purpose**: List all memory keys without their values.

**Parameters**: None

**Returns**:
```python
{
    "success": True,
    "keys": ["email_preference", "assistant_name", "meeting_time_preference"],
    "count": 3
}
```

**Example Usage**:
```python
from src.services.memory_engine import list_memory

result = await list_memory()
keys = result["keys"]
```

---

### **Function 5: `search_memory(query)`**

**Purpose**: Search memory by keyword in keys or values.

**Parameters**:
- `query` (required): Search query string

**Returns**:
```python
{
    "success": True,
    "results": [
        {"key": "email_preference", "value": "short emails"},
        {"key": "email_signature", "value": "Warm regards, Saara"}
    ],
    "count": 2,
    "query": "email"
}
```

**Example Usage**:
```python
from src.services.memory_engine import search_memory

result = await search_memory("email")
results = result["results"]
```

---

### **Function 6: `classify_memory(user_message)`**

**Purpose**: Analyze a user message to determine if it contains storable information.

**Parameters**:
- `user_message` (required): The user's message to analyze

**STORE when user shares**:
- Preferences: "I prefer short emails"
- Stable habits: "remind me every morning"
- Personal details: "my assistant is David"
- Long-term goals
- Configuration: "use formal tone"

**DO NOT STORE**:
- Temporary tasks
- One-time instructions
- Emotional statements
- Unclear information

**Returns** (should store):
```python
{
    "should_store": True,
    "key": "email_preference",
    "value": "short emails",
    "reason": "User preference detected"
}
```

**Returns** (should not store):
```python
{
    "should_store": False,
    "reason": "Temporary instruction detected"
}
```

**Example Usage**:
```python
from src.services.memory_engine import classify_memory

result = await classify_memory("I prefer short emails")
if result["should_store"]:
    await save_memory(result["key"], result["value"])
```

---

### **Function 7: `inject_memory_context(memory_list, max_entries)`**

**Purpose**: Format memory entries into a clean string for LLM context injection.

**Parameters**:
- `memory_list` (required): List of memory entries from `load_memory()`
- `max_entries` (optional): Maximum entries to include (default: 10)

**Returns**:
```
LONG-TERM MEMORY:
- email_preference: short emails
- assistant_name: David
- meeting_time_preference: mornings
```

**Example Usage**:
```python
from src.services.memory_engine import load_memory, inject_memory_context

memory_result = await load_memory()
memory_context = inject_memory_context(memory_result["memory"])
# Inject into LLM prompt
```

---

## Storage Format

Memory is stored in `data/memory.json`:

```json
{
  "email_preference": {
    "value": "short emails",
    "created_at": "2025-12-10T13:00:00",
    "updated_at": "2025-12-10T13:00:00"
  },
  "assistant_name": {
    "value": "David",
    "created_at": "2025-12-10T13:05:00",
    "updated_at": "2025-12-10T13:05:00"
  }
}
```

**Features**:
- ✅ Persistent (survives restarts)
- ✅ JSON safe
- ✅ Thread-safe (uses Lock)
- ✅ Timestamped entries
- ✅ Human-readable

---

## LLM Tool Registration

All memory functions are registered as LLM-callable tools in `src/core/tools.py`:

1. **`save_memory`** - Save key-value pair
2. **`load_memory`** - Load all memory
3. **`delete_memory`** - Delete entry by key
4. **`list_memory`** - List all keys
5. **`search_memory`** - Search by keyword
6. **`classify_memory`** - Analyze if message is storable

---

## System Prompt Integration

The system prompt in `src/core/context.py` now includes:

### **LONG-TERM MEMORY RULES**

**WHEN TO SAVE MEMORY**:
Use `save_memory()` when the user shares:
- Preferences (e.g., "I prefer short emails")
- Stable habits (e.g., "remind me every morning")
- Personal details (e.g., "my assistant is David")
- Long-term goals
- Configuration preferences (e.g., "use formal tone")

**DO NOT SAVE**:
- Temporary tasks
- One-time instructions
- Emotional statements
- Unclear or ambiguous information

**MEMORY WORKFLOW**:
1. When user shares storable information, call `save_memory(key, value)`
2. Use descriptive keys: "email_preference", "assistant_name", "meeting_time_preference"
3. Store clean, concise values
4. Confirm to user: "I'll remember that"

**LOADING MEMORY**:
- Call `load_memory()` at the start of conversations to retrieve context
- Use stored preferences to personalize responses
- Reference memory naturally: "As you prefer short emails..."

---

## Context Builder Integration

The `build_context()` function in `src/core/context.py` now:

1. **Loads memory automatically**:
```python
memory_result = await load_memory()
memory_context = inject_memory_context(memory_result["memory"])
```

2. **Injects memory into LLM context**:
```python
if memory_context:
    messages.append({"role": "system", "content": memory_context})
```

3. **Memory is loaded BEFORE every conversation**

---

## Usage Examples

### **Example 1: User Shares Preference**

**User**: "I prefer short emails"

**Jarvis Workflow**:
1. Classify message: `classify_memory("I prefer short emails")`
   - Returns: `{"should_store": True, "key": "preference", "value": "short emails"}`
2. Save to memory: `save_memory("email_preference", "short emails")`
3. Confirm: "I'll remember that"

**Code**:
```python
# Jarvis calls this automatically
result = await classify_memory("I prefer short emails")
if result["should_store"]:
    await save_memory("email_preference", "short emails")
```

---

### **Example 2: User Shares Personal Detail**

**User**: "My assistant is David"

**Jarvis Workflow**:
1. Classify: `classify_memory("My assistant is David")`
   - Returns: `{"should_store": True, "key": "assistant", "value": "David"}`
2. Save: `save_memory("assistant_name", "David")`
3. Confirm: "I'll remember that David is your assistant"

---

### **Example 3: Load Memory in Conversation**

**User**: "Send an email to my assistant"

**Jarvis Workflow**:
1. Load memory: `load_memory()`
   - Returns: `{"memory": [{"key": "assistant_name", "value": "David"}]}`
2. Use memory: "I'll send an email to David"

**Context Injection**:
```
LONG-TERM MEMORY:
- assistant_name: David
- email_preference: short emails
```

---

### **Example 4: Search Memory**

**User**: "What do you remember about emails?"

**Jarvis Workflow**:
1. Search: `search_memory("email")`
   - Returns: `{"results": [{"key": "email_preference", "value": "short emails"}]}`
2. Respond: "I remember you prefer short emails"

---

### **Example 5: Delete Memory**

**User**: "Forget my email preference"

**Jarvis Workflow**:
1. Delete: `delete_memory("email_preference")`
2. Confirm: "I've forgotten your email preference"

---

### **Example 6: List All Memory**

**User**: "What do you remember about me?"

**Jarvis Workflow**:
1. Load: `load_memory()`
2. Format and respond:
```
I remember:
- You prefer short emails
- Your assistant is David
- You prefer morning meetings
```

---

## Classification Logic

The `classify_memory()` function uses keyword detection:

### **Preference Keywords** (STORE):
- "i prefer"
- "i like"
- "i want"
- "i need"
- "i always"
- "my preference"
- "please remember"
- "remember that"
- "from now on"
- "always"
- "never"
- "every time"
- "my assistant"
- "my manager"

### **Temporary Keywords** (DO NOT STORE):
- "right now"
- "today"
- "tomorrow"
- "this week"
- "can you"
- "please"
- "could you"
- "schedule"
- "create a task"
- "send an email"

### **Pattern Extraction**:

1. **"I prefer X"**:
   - Key: "preference"
   - Value: X

2. **"My X is Y"**:
   - Key: X (normalized)
   - Value: Y

3. **"Remember that X"**:
   - Key: "note"
   - Value: X

---

## Error Handling

### **Invalid Key**:
```python
{
    "success": False,
    "error": "INVALID_KEY",
    "message": "Memory key must be a non-empty string"
}
```

### **Empty Data**:
```python
{
    "success": False,
    "error": "EMPTY_DATA",
    "message": "Key and value cannot be empty"
}
```

### **Key Not Found**:
```python
{
    "success": False,
    "error": "KEY_NOT_FOUND",
    "message": "Memory key 'email_preference' does not exist"
}
```

### **Save Failed**:
```python
{
    "success": False,
    "error": "SAVE_FAILED",
    "message": "Failed to save memory to disk"
}
```

---

## Testing

### **Test 1: Save Preference**
```bash
# Via Telegram:
"I prefer short emails"

# Expected:
# 1. Jarvis classifies as storable
# 2. Saves to memory
# 3. Responds: "I'll remember that"
```

### **Test 2: Load Memory**
```bash
# Via Telegram:
"What do you remember about me?"

# Expected:
# 1. Loads all memory
# 2. Formats and returns:
#    "I remember:
#     - You prefer short emails
#     - Your assistant is David"
```

### **Test 3: Use Memory**
```bash
# Via Telegram:
"Send an email to my assistant"

# Expected:
# 1. Loads memory (assistant_name: David)
# 2. Uses it: "I'll send an email to David"
```

### **Test 4: Delete Memory**
```bash
# Via Telegram:
"Forget my email preference"

# Expected:
# 1. Deletes memory entry
# 2. Confirms: "I've forgotten your email preference"
```

### **Test 5: Search Memory**
```bash
# Via Telegram:
"What do you remember about emails?"

# Expected:
# 1. Searches memory for "email"
# 2. Returns matching entries
```

---

## Thread Safety

The memory engine uses a `threading.Lock` to ensure thread-safe operations:

```python
MEMORY_LOCK = Lock()

with MEMORY_LOCK:
    memory = _load_memory_from_disk()
    # ... modify memory ...
    _save_memory_to_disk(memory)
```

This prevents race conditions when multiple requests access memory simultaneously.

---

## Configuration

**Memory File Path**: `data/memory.json`

Can be changed by modifying:
```python
MEMORY_FILE_PATH = "data/memory.json"
```

**Max Context Entries**: 10 (default)

Can be changed when calling:
```python
inject_memory_context(memory_list, max_entries=20)
```

---

## Summary

This memory system provides:

✅ **Persistent Storage** - JSON file survives restarts  
✅ **Intelligent Classification** - Knows what to store  
✅ **Thread-Safe** - Handles concurrent access  
✅ **LLM-Callable** - Function-calling integration  
✅ **Context Injection** - Automatic loading in conversations  
✅ **Search & Filter** - Find specific memories  
✅ **Error Handling** - Never fails silently  
✅ **Timestamped** - Tracks creation and updates  
✅ **Production Ready** - Full validation and logging  

All code is modular, typed, and immediately usable for Saara's Jarvis assistant.
