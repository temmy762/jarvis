# Jarvis Trello Task Management System - Complete Documentation

## Overview

This is a comprehensive Trello task management system built for Saara's Jarvis AI assistant. The system provides intelligent task management with context awareness, smart board/list detection, and clean plain-text formatting.

---

## File Structure

```
src/
├── services/
│   ├── trello.py                    # Basic Trello operations (existing)
│   ├── trello_advanced.py           # Advanced task management (NEW)
│   └── trello_intent.py             # Intent router for natural language (NEW)
└── core/
    └── tools.py                     # Tool registry (UPDATED)
```

---

## Module Descriptions

### 1. `src/services/trello_advanced.py`

**Purpose**: Comprehensive Trello task management with smart detection

**Key Functions**:

#### **Board & List Management**

- `trello_list_boards()` - List all boards
- `trello_list_lists(board_id)` - List all lists on a board
- `trello_find_board_by_name(name)` - Find board by name (case-insensitive)
- `trello_find_list_by_name(board_id, name)` - Find list by name
- `trello_create_board(name, description)` - Create new board
- `trello_create_list(board_id, name)` - Create new list

#### **Card (Task) Management**

- `trello_list_cards(list_id)` - Get all cards in a list
- `trello_get_board_cards(board_id)` - Get all cards on a board
- `trello_get_card(card_id)` - Get single card details
- `trello_create_card(list_id, name, description, due, labels, members)` - Create card with full details
- `trello_update_card(card_id, fields)` - Update card fields
- `trello_move_card(card_id, list_id, board_id)` - Move card to different list/board
- `trello_delete_card(card_id)` - Delete card permanently
- `trello_find_card_by_name(board_id, name)` - Find card by name

#### **Search & Filter**

- `trello_search_cards(query, board_ids)` - Search cards by keyword
- `trello_filter_cards_by_due_date(cards, filter_type)` - Filter by due date
  - Types: `overdue`, `today`, `tomorrow`, `this_week`

#### **Organization**

- `trello_sort_cards_by_due_date(cards)` - Sort by due date
- `trello_group_cards_by_status(cards)` - Group into active/completed
- `trello_group_cards_by_label(cards)` - Group by label

#### **Formatting**

- `_format_card_readable(card)` - Format card in clean plain text:
  ```
  Title: Task Name
  Description: Task details
  Due: December 10, 2025 at 03:00 PM
  Status: Active
  Labels: Urgent, Work
  ```

---

### 2. `src/services/trello_intent.py`

**Purpose**: Route natural language task commands to appropriate functions

**Main Function**:
```python
handle_trello_intent(
    action="create_task",
    board_name="Marketing",
    list_name="To Do",
    title="Create social media posts",
    description="Design posts for Q1 campaign",
    due="2025-12-15T17:00:00Z"
)
```

**Supported Actions**:

1. **list_boards** - List all Trello boards
2. **list_lists** - List all lists on a board
3. **get_board_tasks** - Get all tasks on a board
4. **get_list_tasks** - Get all tasks in a list
5. **create_task** - Create new task (smart board/list detection)
6. **update_task** - Update task fields
7. **move_task** - Move task to different list/board
8. **delete_task** - Delete task (requires confirmation)
9. **search_tasks** - Search tasks by keyword
10. **filter_by_due** - Filter tasks by due date
11. **group_by_status** - Group tasks by active/completed
12. **create_board** - Create new board
13. **create_list** - Create new list

**Smart Context Awareness**:

- **Missing Board**: Asks "Which board should I create this task on?"
- **Missing List**: Defaults to first list on board
- **Missing Card**: Asks "Which task should I update?"
- **Delete Confirmation**: Asks "Are you sure you want to delete 'Task Name'?"

**Response Formatting**:

All responses are clean plain-text:

```
# Task created
Task 'Create social media posts' has been created.

# Board tasks
Your Trello boards:

1. Marketing
2. Development
3. Personal

# Task list
1. Title: Create social media posts
Description: Design posts for Q1 campaign
Due: December 15, 2025 at 05:00 PM
Status: Active
Labels: Urgent, Marketing

2. Title: Review analytics
Description: Check Q4 performance
Due: December 12, 2025 at 10:00 AM
Status: Active
Labels: Analytics

# Missing board
Which board should I create this task on?

# Confirmation required
Are you sure you want to delete 'Old Task'?
```

---

### 3. Tool Registry Updates (`src/core/tools.py`)

**New Tools Registered**:

1. `trello_get_board_cards` - Get all cards on a board
2. `trello_list_cards` - Get cards in a list
3. `trello_get_card` - Get card details
4. `trello_update_card` - Update card fields
5. `trello_move_card` - Move card
6. `trello_delete_card` - Delete card
7. `trello_search_cards` - Search by keyword
8. `trello_find_board_by_name` - Find board by name
9. `trello_find_card_by_name` - Find card by name
10. `trello_create_board` - Create board
11. `trello_create_list` - Create list

---

## Key Features

### **Smart Board/List Detection**

When creating a task:
1. If board name provided → finds board automatically
2. If board missing → asks user
3. If list name provided → finds list on board
4. If list missing → uses first list on board
5. If board/list not found → returns helpful error

### **Intelligent Task Finding**

- Case-insensitive search
- Partial name matching
- Searches across all boards or specific board
- Returns clear "not found" messages

### **Deletion Safety**

Before deleting:
```python
{
    "success": False,
    "error": "CONFIRMATION_REQUIRED",
    "message": "Are you sure you want to delete 'Task Name'?"
}
```

User must explicitly confirm with `confirm_delete=True`

### **Clean Plain-Text Formatting**

All outputs:
- No Markdown symbols
- No asterisks or bullets
- No decorative characters
- Human-readable dates
- Clear section headers

### **Task Organization**

**Group by Status**:
```
Active:
  - Task 1
  - Task 2

Completed:
  - Task 3
  - Task 4
```

**Group by Label**:
```
Urgent:
  - Critical bug fix
  - Client meeting prep

Marketing:
  - Social media posts
  - Email campaign

No Label:
  - Miscellaneous task
```

**Filter by Due Date**:
- Overdue tasks
- Due today
- Due tomorrow
- Due this week

---

## Usage Examples

### Example 1: Create Task with Smart Detection

```python
from src.services.trello_intent import handle_trello_intent

result = await handle_trello_intent(
    action="create_task",
    board_name="Marketing",
    title="Create Q1 social posts",
    description="Design and schedule posts",
    due="2025-12-20T17:00:00Z"
)

# If board exists, task is created
# If board missing, returns: "Which board should I create this task on?"
```

**Response**:
```
Task 'Create Q1 social posts' has been created.
```

### Example 2: Get Board Tasks

```python
result = await handle_trello_intent(
    action="get_board_tasks",
    board_name="Development"
)
```

**Response**:
```
1. Title: Fix login bug
Description: Users can't login with special characters
Due: December 11, 2025 at 02:00 PM
Status: Active
Labels: Bug, High Priority

2. Title: Update documentation
Description: Add API examples
Due: December 15, 2025 at 05:00 PM
Status: Active
Labels: Documentation
```

### Example 3: Move Task

```python
result = await handle_trello_intent(
    action="move_task",
    board_name="Marketing",
    card_name="Create social posts",
    list_name="In Progress"
)
```

**Response**:
```
Task 'Create social posts' has been moved.
```

### Example 4: Search Tasks

```python
result = await handle_trello_intent(
    action="search_tasks",
    keyword="budget",
    board_name="Finance"
)
```

**Response**:
```
1. Title: Q4 Budget Review
Description: Analyze spending
Due: December 12, 2025 at 10:00 AM
Status: Active

2. Title: 2026 Budget Planning
Description: Draft next year's budget
Due: December 20, 2025 at 03:00 PM
Status: Active
```

### Example 5: Filter Overdue Tasks

```python
result = await handle_trello_intent(
    action="filter_by_due",
    board_name="Personal",
    filter_type="overdue"
)
```

**Response**:
```
1. Title: Pay electricity bill
Due: December 05, 2025 at 05:00 PM
Status: Active

2. Title: Submit tax documents
Due: December 08, 2025 at 12:00 PM
Status: Active
```

### Example 6: Delete Task with Confirmation

```python
# First attempt without confirmation
result = await handle_trello_intent(
    action="delete_task",
    board_name="Marketing",
    card_name="Old Campaign",
    confirm_delete=False
)
# Returns: "Are you sure you want to delete 'Old Campaign'?"

# Confirmed deletion
result = await handle_trello_intent(
    action="delete_task",
    card_id="abc123",
    confirm_delete=True
)
# Returns: "Task 'Old Campaign' has been deleted."
```

---

## Natural Language Commands

The LLM can now understand and execute commands like:

- "Create a task called Pay Invoices on my Finance board"
- "Move the Logo Design card to the Review list"
- "Show me all tasks due tomorrow"
- "Delete the Branding task"
- "What tasks do I have on the Marketing board?"
- "Update the due date on the Website Launch task to Friday"
- "Search for tasks about budget"
- "Show me overdue tasks"
- "List all my Trello boards"
- "Create a new board called Q1 Planning"

---

## Testing

### 1. Test Task Creation

```bash
# Start server
python -m uvicorn main:app --host 0.0.0.0 --port 5000

# Via Telegram:
"Create a task called Review Analytics on my Marketing board"

# Expected: "Task 'Review Analytics' has been created."
```

### 2. Test Smart Board Detection

```bash
# Via Telegram (without specifying board):
"Create a task called New Feature"

# Expected: "Which board should I create this task on?"
```

### 3. Test Task Retrieval

```bash
# Via Telegram:
"Show me all tasks on my Development board"

# Expected: Clean list of all tasks with details
```

### 4. Test Task Search

```bash
# Via Telegram:
"Search for tasks about budget"

# Expected: All matching tasks across boards
```

### 5. Test Deletion Confirmation

```bash
# Via Telegram:
"Delete the Old Campaign task"

# Expected: "Are you sure you want to delete 'Old Campaign'?"

# User confirms:
"Yes, delete it"

# Expected: "Task 'Old Campaign' has been deleted."
```

---

## Error Handling

All functions return structured responses:

```python
{
    "success": False,
    "error": "ERROR_CODE",
    "message": "User-friendly message"
}
```

**Common Error Codes**:
- `MISSING_BOARD` - Board not specified
- `MISSING_LIST` - List not specified
- `MISSING_CARD` - Card not specified
- `MISSING_TITLE` - Task title not provided
- `BOARD_NOT_FOUND` - Board doesn't exist
- `LIST_NOT_FOUND` - List doesn't exist
- `CARD_NOT_FOUND` - Card doesn't exist
- `CONFIRMATION_REQUIRED` - Delete confirmation needed
- `NO_LISTS` - Board has no lists

---

## Configuration

**Required Environment Variables**:
```bash
TRELLO_API_KEY=your-api-key
TRELLO_API_TOKEN=your-api-token
```

**Owner Information** (hardcoded):
- Name: Saara
- Email: saar@alaw.co.il

---

## API Integration Details

### Trello API Endpoints Used

1. **List Boards**: `GET /members/me/boards`
2. **List Lists**: `GET /boards/{boardId}/lists`
3. **List Cards**: `GET /lists/{listId}/cards`
4. **Get Board Cards**: `GET /boards/{boardId}/cards`
5. **Get Card**: `GET /cards/{cardId}`
6. **Create Card**: `POST /cards`
7. **Update Card**: `PUT /cards/{cardId}`
8. **Delete Card**: `DELETE /cards/{cardId}`
9. **Search**: `GET /search`
10. **Create Board**: `POST /boards`
11. **Create List**: `POST /lists`

### Authentication

All requests include:
```python
params = {
    "key": TRELLO_API_KEY,
    "token": TRELLO_API_TOKEN
}
```

---

## Card Field Mapping

When updating cards, fields are mapped:

```python
{
    "title" → "name",
    "name" → "name",
    "description" → "desc",
    "desc" → "desc",
    "due_date" → "due",
    "due" → "due",
    "labels" → "idLabels",
    "members" → "idMembers",
    "closed" → "closed"
}
```

---

## Summary

This system provides:

✅ **Smart Task Creation** - Auto-detects boards and lists  
✅ **Context Awareness** - Asks for missing information  
✅ **Intelligent Search** - Case-insensitive, partial matching  
✅ **Task Organization** - Group by status, label, due date  
✅ **Deletion Safety** - Requires explicit confirmation  
✅ **Clean Formatting** - Plain-text responses only  
✅ **Board/List Management** - Create and manage structure  
✅ **Natural Language** - Understands task commands  
✅ **Production Ready** - Full error handling and logging  

All code is modular, typed, and ready for immediate production use with Saara's identity enforcement.
