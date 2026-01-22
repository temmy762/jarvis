# Jarvis Time Awareness System - Complete Documentation

## Overview

This is a comprehensive real-time awareness subsystem for Saara's Jarvis AI assistant. Jarvis **NEVER guesses** the current date or time. It always requests actual system time through function calls and parses human language time expressions into precise ISO 8601 timestamps.

---

## Core Principle

**Jarvis must NEVER hallucinate or assume dates/times.**

When the user says "in 2 hours" or "tomorrow morning", Jarvis:
1. Calls `get_current_time()` to get the REAL current time
2. Calls `parse_human_time_expression()` to convert natural language to ISO timestamps
3. Uses precise timestamps for scheduling, task creation, and availability checking

---

## File Structure

```
src/
├── services/
│   └── time_service.py              # Time awareness module (NEW)
└── core/
    ├── tools.py                     # Tool registry (UPDATED)
    └── context.py                   # System prompt (UPDATED)
```

---

## Module: `src/services/time_service.py`

### **Function 1: `get_current_time(timezone)`**

**Purpose**: Get the REAL current system time in ISO 8601 format with timezone.

**Parameters**:
- `timezone` (optional): Timezone string (e.g., "Europe/Berlin", "America/New_York")
  - Defaults to "Europe/Berlin" for Saara

**Returns**:
```python
{
    "success": True,
    "currentTime": "2025-12-10T15:22:11+01:00",
    "timezone": "Europe/Berlin",
    "timestamp": 1733844131,
    "readable": "Tuesday, December 10, 2025 at 03:22 PM"
}
```

**When Jarvis Must Call This**:
- User asks "What time is it now?"
- User asks "What's today's date?"
- User uses ANY relative time expression
- Scheduling calendar events
- Creating Trello tasks with due dates
- Checking availability
- Calculating durations

**Example Usage**:
```python
from src.services.time_service import get_current_time

result = await get_current_time()
current_time = result["currentTime"]  # "2025-12-10T15:22:11+01:00"
```

---

### **Function 2: `parse_human_time_expression(expression, current_time, timezone, default_duration_minutes)`**

**Purpose**: Parse natural language time expressions into precise ISO 8601 timestamps.

**Parameters**:
- `expression` (required): Natural language time expression
- `current_time` (required): ISO 8601 current time from `get_current_time()`
- `timezone` (optional): Timezone for parsing
- `default_duration_minutes` (optional): Default meeting duration (default: 60)

**Supported Expressions**:

1. **Relative Hours/Minutes/Days**:
   - "in 2 hours"
   - "in 30 minutes"
   - "in 3 days"

2. **Tomorrow**:
   - "tomorrow"
   - "tomorrow morning" (9 AM)
   - "tomorrow afternoon" (2 PM)
   - "tomorrow evening" (6 PM)
   - "tomorrow at 3pm"

3. **Today**:
   - "today at 5pm"
   - "later today" (+2 hours)
   - "this afternoon" (2 PM)
   - "this evening" (6 PM)

4. **Weekdays**:
   - "Monday"
   - "next Friday"
   - "Tuesday at 10am"
   - "Friday at 3:30pm"

5. **Relative Weeks**:
   - "next week" (next Monday 9 AM)
   - "2 weeks from now"

6. **Special Expressions**:
   - "end of day" (5 PM today)
   - "by end of day" (5 PM today)
   - "X days from now"

**Returns**:
```python
{
    "success": True,
    "startTime": "2025-12-10T17:22:11+01:00",
    "endTime": "2025-12-10T18:22:11+01:00",
    "duration": 60,
    "isRelative": True,
    "expression": "in 2 hours"
}
```

**Error Response** (ambiguous time):
```python
{
    "success": False,
    "error": "AMBIGUOUS_TIME",
    "message": "I need a specific time. Can you clarify?",
    "expression": "sometime"
}
```

**Example Usage**:
```python
from src.services.time_service import get_current_time, parse_human_time_expression

# Get current time
time_result = await get_current_time()
current_time = time_result["currentTime"]

# Parse expression
parse_result = await parse_human_time_expression(
    expression="in 2 hours",
    current_time=current_time
)

start_time = parse_result["startTime"]  # "2025-12-10T17:22:11+01:00"
end_time = parse_result["endTime"]      # "2025-12-10T18:22:11+01:00"
```

---

### **Function 3: `format_time_readable(iso_time)`**

**Purpose**: Convert ISO 8601 timestamp to human-readable format.

**Parameters**:
- `iso_time` (required): ISO 8601 timestamp

**Returns**:
```python
{
    "success": True,
    "readable": "Tuesday, December 10, 2025 at 03:22 PM",
    "date": "December 10, 2025",
    "time": "03:22 PM",
    "weekday": "Tuesday"
}
```

**Example Usage**:
```python
from src.services.time_service import format_time_readable

result = await format_time_readable("2025-12-10T15:22:11+01:00")
print(result["readable"])  # "Tuesday, December 10, 2025 at 03:22 PM"
```

---

### **Function 4: `calculate_time_until(target_time, current_time)`**

**Purpose**: Calculate the duration between current time and a target time.

**Parameters**:
- `target_time` (required): ISO 8601 target timestamp
- `current_time` (required): ISO 8601 current timestamp

**Returns**:
```python
{
    "success": True,
    "duration_seconds": 7200,
    "duration_minutes": 120,
    "duration_hours": 2,
    "readable": "2 hours"
}
```

**Error Response** (target in past):
```python
{
    "success": False,
    "error": "TARGET_IN_PAST",
    "message": "That time is in the past."
}
```

---

### **Function 5: `validate_time_range(start_time, end_time)`**

**Purpose**: Validate that a time range is logical (end after start).

**Parameters**:
- `start_time` (required): ISO 8601 start timestamp
- `end_time` (required): ISO 8601 end timestamp

**Returns**:
```python
{
    "success": True,
    "valid": True,
    "duration_minutes": 60
}
```

**Error Response** (invalid range):
```python
{
    "success": True,
    "valid": False,
    "error": "END_BEFORE_START",
    "message": "The end time must be after the start time."
}
```

---

## LLM Tool Registration

All time functions are registered as LLM-callable tools in `src/core/tools.py`:

1. **`get_current_time`** - Get real current time
2. **`parse_human_time_expression`** - Parse natural language to ISO timestamps
3. **`format_time_readable`** - Convert ISO to readable format
4. **`calculate_time_until`** - Calculate duration
5. **`validate_time_range`** - Validate time ranges

---

## System Prompt Integration

The system prompt in `src/core/context.py` now includes:

### **TIME AWARENESS RULES (CRITICAL)**

Jarvis must NEVER guess the current date or time.

**WHEN TO CALL get_current_time()**:
- User asks "What time is it now?" or "What's today's date?"
- User uses relative time expressions
- Scheduling any calendar event
- Creating Trello tasks with due dates
- Checking availability
- Calculating durations or intervals

**TIME PARSING WORKFLOW**:
1. ALWAYS call `get_current_time()` first
2. Use `parse_human_time_expression()` to convert natural language to ISO timestamps
3. Pass precise ISO timestamps to calendar/Trello functions
4. NEVER assume a default date or time

---

## Usage Examples

### **Example 1: User Asks Current Time**

**User**: "What time is it now?"

**Jarvis Workflow**:
1. Call `get_current_time()`
2. Extract `readable` field
3. Return: "It's 3:22 PM on Tuesday, December 10, 2025."

**Code**:
```python
result = await get_current_time()
# Return: result["readable"]
```

---

### **Example 2: Schedule Meeting in 2 Hours**

**User**: "Schedule a meeting in 2 hours"

**Jarvis Workflow**:
1. Call `get_current_time()` → `"2025-12-10T15:22:11+01:00"`
2. Call `parse_human_time_expression("in 2 hours", current_time)`
   - Returns: `startTime: "2025-12-10T17:22:11+01:00"`, `endTime: "2025-12-10T18:22:11+01:00"`
3. Call `calendar_create_meet_event(start_time, end_time, ...)`
4. Return: "Your meeting is scheduled. Meet link: https://..."

**Code**:
```python
# Step 1: Get current time
time_result = await get_current_time()
current_time = time_result["currentTime"]

# Step 2: Parse expression
parse_result = await parse_human_time_expression("in 2 hours", current_time)
start_time = parse_result["startTime"]
end_time = parse_result["endTime"]

# Step 3: Schedule meeting
meeting_result = await calendar_create_meet_event(
    summary="Meeting",
    start_time=start_time,
    end_time=end_time,
    attendees=["colleague@example.com"]
)
```

---

### **Example 3: Create Task Due Tomorrow**

**User**: "Create a task due tomorrow"

**Jarvis Workflow**:
1. Call `get_current_time()` → `"2025-12-10T15:22:11+01:00"`
2. Call `parse_human_time_expression("tomorrow", current_time)`
   - Returns: `startTime: "2025-12-11T09:00:00+01:00"`
3. Call `trello_create_card(..., due=start_time)`
4. Return: "Task 'Task Name' has been created."

**Code**:
```python
# Step 1: Get current time
time_result = await get_current_time()
current_time = time_result["currentTime"]

# Step 2: Parse expression
parse_result = await parse_human_time_expression("tomorrow", current_time)
due_time = parse_result["startTime"]

# Step 3: Create task
task_result = await trello_create_card(
    list_id="abc123",
    name="Task Name",
    due=due_time
)
```

---

### **Example 4: Ambiguous Time Expression**

**User**: "Schedule a meeting sometime"

**Jarvis Workflow**:
1. Call `get_current_time()`
2. Call `parse_human_time_expression("sometime", current_time)`
   - Returns: `{"success": False, "error": "AMBIGUOUS_TIME", "message": "I need a specific time. Can you clarify?"}`
3. Return: "I need a specific time. Can you clarify?"

---

### **Example 5: Check Time Until Event**

**User**: "How long until my 5pm meeting?"

**Jarvis Workflow**:
1. Call `get_current_time()` → `"2025-12-10T15:22:11+01:00"`
2. Call `calculate_time_until("2025-12-10T17:00:00+01:00", current_time)`
   - Returns: `{"readable": "1 hour and 37 minutes"}`
3. Return: "Your meeting is in 1 hour and 37 minutes."

---

## Time Expression Parsing Details

### **Pattern Matching**

The parser uses regex patterns to detect:

1. **"in X minutes/hours/days"**:
   - Pattern: `r'in\s+(\d+)\s+(minute|minutes|min|hour|hours|hr|day|days)'`
   - Example: "in 2 hours" → +2 hours from now

2. **"tomorrow"**:
   - Detects "tomorrow" keyword
   - Checks for time specification: "tomorrow at 3pm"
   - Defaults to 9 AM if no time specified

3. **Weekday names**:
   - Detects: Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday
   - Calculates days ahead to next occurrence
   - Parses time if specified: "Friday at 3pm"

4. **"X days/weeks from now"**:
   - Pattern: `r'(\d+)\s+days?\s+from\s+now'`
   - Example: "3 days from now" → +3 days

5. **Time of day**:
   - Pattern: `r'(\d{1,2}):?(\d{2})?\s*(am|pm)?'`
   - Handles: "3pm", "3:30pm", "15:30"

---

## Integration with Calendar & Trello

### **Calendar Integration**

All calendar functions should:
1. Call `get_current_time()` first
2. Resolve relative time expressions with `parse_human_time_expression()`
3. Pass precise ISO timestamps to Google Calendar API
4. Never assume default dates

**Example**:
```python
# User: "Schedule a meeting tomorrow at 2pm"
time_result = await get_current_time()
parse_result = await parse_human_time_expression("tomorrow at 2pm", time_result["currentTime"])

await calendar_create_meet_event(
    summary="Meeting",
    start_time=parse_result["startTime"],
    end_time=parse_result["endTime"],
    attendees=["colleague@example.com"]
)
```

### **Trello Integration**

All Trello task creation with due dates should:
1. Call `get_current_time()` first
2. Parse relative expressions with `parse_human_time_expression()`
3. Use ISO timestamp as `due` parameter

**Example**:
```python
# User: "Create a task due end of day"
time_result = await get_current_time()
parse_result = await parse_human_time_expression("end of day", time_result["currentTime"])

await trello_create_card(
    list_id="abc123",
    name="Task Name",
    due=parse_result["startTime"]
)
```

---

## Error Handling

### **Ambiguous Time**
```python
{
    "success": False,
    "error": "AMBIGUOUS_TIME",
    "message": "I need a specific time. Can you clarify?"
}
```

**Jarvis Response**: "I need a specific time. Can you clarify?"

### **Target in Past**
```python
{
    "success": False,
    "error": "TARGET_IN_PAST",
    "message": "That time is in the past."
}
```

**Jarvis Response**: "That time is in the past."

### **Invalid Time Range**
```python
{
    "success": True,
    "valid": False,
    "error": "END_BEFORE_START",
    "message": "The end time must be after the start time."
}
```

**Jarvis Response**: "The end time must be after the start time."

---

## Testing

### **Test 1: Current Time**
```bash
# Via Telegram:
"What time is it?"

# Expected: "It's 3:22 PM on Tuesday, December 10, 2025."
```

### **Test 2: Schedule in 2 Hours**
```bash
# Via Telegram:
"Schedule a meeting in 2 hours"

# Expected:
# 1. Calls get_current_time()
# 2. Parses "in 2 hours"
# 3. Schedules meeting
# 4. Returns: "Your meeting is scheduled. Meet link: https://..."
```

### **Test 3: Create Task Tomorrow**
```bash
# Via Telegram:
"Create a task called Review Report due tomorrow"

# Expected:
# 1. Calls get_current_time()
# 2. Parses "tomorrow"
# 3. Creates task with due date
# 4. Returns: "Task 'Review Report' has been created."
```

### **Test 4: Ambiguous Time**
```bash
# Via Telegram:
"Schedule a meeting sometime"

# Expected: "I need a specific time. Can you clarify?"
```

---

## Configuration

**Default Timezone**: `Europe/Berlin` (for Saara)

Can be overridden by passing `timezone` parameter:
```python
await get_current_time(timezone="America/New_York")
```

---

## Summary

This time-awareness system ensures:

✅ **No Time Hallucination** - Jarvis NEVER guesses dates/times  
✅ **Real System Time** - Always calls `get_current_time()` for actual time  
✅ **Natural Language Parsing** - Converts "in 2 hours", "tomorrow", etc. to ISO timestamps  
✅ **Calendar Integration** - Precise scheduling with no assumptions  
✅ **Trello Integration** - Accurate due date parsing  
✅ **Error Handling** - Clear messages for ambiguous expressions  
✅ **Timezone Support** - Defaults to Europe/Berlin for Saara  
✅ **Production Ready** - Full error handling and logging  

All code is modular, typed, and immediately usable for Saara's Jarvis assistant.
