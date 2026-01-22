# Jarvis Gmail Management System - Complete Documentation

## Overview

This is a comprehensive Gmail management system built for Saara's Jarvis AI assistant. The system provides full email management capabilities with clean, production-ready code that enforces strict formatting rules and identity management.

---

## File Structure

```
src/
├── services/
│   ├── gmail.py                 # Basic Gmail operations (existing)
│   ├── gmail_advanced.py        # Advanced Gmail operations (NEW)
│   └── gmail_intent.py          # Intent router for natural language (NEW)
├── utils/
│   └── formatter.py             # Response formatting middleware (NEW)
└── core/
    ├── tools.py                 # Tool registry (UPDATED)
    └── agent.py                 # Agent loop (UPDATED)
```

---

## Module Descriptions

### 1. `src/services/gmail_advanced.py`

**Purpose**: Comprehensive Gmail operations with clean formatting

**Key Functions**:

- **Email Fetching**:
  - `gmail_fetch_by_keyword(keyword, limit=20)` - Full-body search
  - `gmail_fetch_by_sender(sender, limit=20)` - Filter by sender
  - `gmail_fetch_by_subject(subject, limit=20)` - Filter by subject
  - `gmail_fetch_by_label(label, limit=20)` - Filter by label
  - `gmail_fetch_by_date_range(after, before, limit=20)` - Date range filter

- **Email Sorting**:
  - `gmail_sort_emails(emails)` - Categorizes into Work, Personal, Urgent, Follow Up, Receipts, Important

- **Label Management**:
  - `gmail_list_labels()` - List all labels
  - `gmail_create_label(label_name)` - Create new label
  - `gmail_delete_label(label_id)` - Delete label
  - `gmail_rename_label(label_id, new_name)` - Rename label
  - `gmail_move_to_label(message_id, add_labels, remove_labels)` - Move email between labels
  - `gmail_remove_label(message_id, label_ids)` - Remove labels from email

- **Email Actions**:
  - `gmail_forward_email(message_id, recipient)` - Forward with clean formatting and Saara's signature
  - `gmail_compose_email(to, subject, body)` - Compose with automatic signature and Markdown stripping

**Return Format**:
All functions return:
```python
{
    "success": bool,
    "data": {...} | "error": "ERROR_CODE"
}
```

Email objects returned:
```python
{
    "id": "message_id",
    "subject": "Email subject",
    "from": "sender@example.com",
    "to": "recipient@example.com",
    "date": "Mon, 10 Dec 2025 10:00:00 +0000",
    "snippet": "Preview text...",
    "body": "Full email body",
    "labels": ["INBOX", "IMPORTANT"]
}
```

---

### 2. `src/utils/formatter.py`

**Purpose**: Clean all outputs to remove Markdown, emojis, and system commentary

**Key Functions**:

- `strip_markdown(text)` - Remove **, *, __, _, ~~, `, #, [links]
- `strip_emojis(text)` - Remove all emoji characters
- `normalize_whitespace(text)` - Clean up spacing
- `strip_urls_for_voice(text)` - Replace URLs with [link] for TTS
- `strip_metadata_for_voice(text)` - Remove attachment references
- `clean_response_for_text(response)` - Full text cleaning
- `clean_response_for_voice(response)` - Full voice cleaning
- `format_agent_response(response, is_voice=False)` - Main formatter
- `strip_system_commentary(text)` - Remove phrases like "I have sent your email"

**Usage**:
```python
from src.utils.formatter import format_agent_response, strip_system_commentary

raw_response = await agent(user_id, message)
clean_response = format_agent_response(raw_response, is_voice=False)
clean_response = strip_system_commentary(clean_response)
```

---

### 3. `src/services/gmail_intent.py`

**Purpose**: Route natural language commands to appropriate Gmail functions

**Main Function**:
```python
execute_gmail_intent(
    action="fetch_by_keyword",
    keyword="meeting notes",
    limit=20
)
```

**Supported Actions**:
- `fetch_by_keyword`
- `fetch_by_sender`
- `fetch_by_subject`
- `fetch_by_label`
- `fetch_by_date_range`
- `list_labels`
- `create_label`
- `delete_label`
- `rename_label`
- `move_to_label`
- `remove_label`
- `forward_email`
- `compose_email`

---

### 4. `src/core/tools.py` (UPDATED)

**New Tools Registered**:

All Gmail advanced operations are now available as LLM tools:

1. `gmail_fetch_by_keyword` - Search emails by keyword
2. `gmail_fetch_by_sender` - Get emails from specific sender
3. `gmail_fetch_by_subject` - Get emails by subject
4. `gmail_fetch_by_label` - Get emails with specific label
5. `gmail_fetch_by_date_range` - Get emails in date range
6. `gmail_list_labels` - List all labels
7. `gmail_delete_label` - Delete a label
8. `gmail_rename_label` - Rename a label
9. `gmail_move_to_label` - Move email to label
10. `gmail_remove_label` - Remove label from email
11. `gmail_forward_email` - Forward email with signature
12. `gmail_compose_email` - Compose clean email with signature

---

### 5. Integration Points

**Agent (`src/core/agent.py`)**:
- Imports formatter utilities
- All responses are automatically cleaned before returning

**Telegram Handler (`src/services/telegram.py`)**:
- Applies `format_agent_response()` to all replies
- Detects voice input and applies voice-specific cleaning
- Strips system commentary before sending

---

## Identity and Formatting Rules

### Owner Identity
- **Name**: Saara
- **Email**: saar@alaw.co.il
- All emails are signed as Saara
- All actions are performed on behalf of Saara

### Email Signature
Every composed or forwarded email automatically includes:
```
Warm regards,
Saara
```

### Formatting Rules

**Text Mode**:
- No Markdown symbols (*, **, _, __, etc.)
- No emojis
- No decorative characters
- Clean plain-text only
- URLs provided as-is

**Voice Mode**:
- All text mode rules apply
- URLs replaced with "[link]"
- No attachment/file metadata
- No brackets or symbols
- Natural spoken language only

**System Commentary**:
Automatically removed:
- "I have sent your email"
- "I've sent the email"
- "Email sent successfully"
- "Here is your email"
- "I've composed the email"

---

## Usage Examples

### Example 1: Fetch Emails by Keyword
```python
from src.services.gmail_advanced import gmail_fetch_by_keyword

result = await gmail_fetch_by_keyword("project proposal", limit=10)
if result["success"]:
    emails = result["data"]
    for email in emails:
        print(f"{email['subject']} from {email['from']}")
```

### Example 2: Compose and Send Email
```python
from src.services.gmail_advanced import gmail_compose_email

result = await gmail_compose_email(
    to="john@example.com",
    subject="Meeting Follow-up",
    body="Thank you for the productive meeting today. I'll send the proposal by Friday."
)
# Automatically adds signature and strips Markdown
```

### Example 3: Forward Email
```python
from src.services.gmail_advanced import gmail_forward_email

result = await gmail_forward_email(
    message_id="18c5d2a3b4f1e890",
    recipient="team@company.com"
)
# Automatically formats with Saara's signature
```

### Example 4: Manage Labels
```python
from src.services.gmail_advanced import (
    gmail_create_label,
    gmail_move_to_label,
    gmail_list_labels
)

# Create label
await gmail_create_label("Important Clients")

# List all labels
labels_result = await gmail_list_labels()
labels = labels_result["data"]

# Move email to label
await gmail_move_to_label(
    message_id="18c5d2a3b4f1e890",
    add_label_ids=["Label_123"],
    remove_label_ids=["INBOX"]
)
```

### Example 5: Sort Emails into Categories
```python
from src.services.gmail_advanced import gmail_fetch_by_keyword, gmail_sort_emails

result = await gmail_fetch_by_keyword("", limit=50)
if result["success"]:
    emails = result["data"]
    categorized = await gmail_sort_emails(emails)
    
    print(f"Work: {len(categorized['Work'])}")
    print(f"Urgent: {len(categorized['Urgent'])}")
    print(f"Receipts: {len(categorized['Receipts'])}")
```

---

## Natural Language Commands

The LLM can now understand and execute commands like:

- "Show me emails from john@example.com from last week"
- "Create a label called Important Clients"
- "Forward that email to my team"
- "Compose an email to sarah@company.com thanking her for the meeting"
- "Move all emails from vendor@supplier.com to the Receipts label"
- "List all my Gmail labels"
- "Search for emails about the Q4 budget"

---

## Testing

### 1. Test Email Fetching
```bash
# Start the server
python -m uvicorn main:app --host 0.0.0.0 --port 5000

# Send via Telegram:
"Show me my latest emails"
"Find emails from john@example.com"
"Search for emails about project proposal"
```

### 2. Test Email Composition
```bash
# Via Telegram:
"Compose an email to john@example.com about tomorrow's meeting"

# Expected output: Clean email body with signature, no commentary
```

### 3. Test Label Management
```bash
# Via Telegram:
"Create a label called VIP Clients"
"Show me all my labels"
"Move the latest email from john to the VIP Clients label"
```

### 4. Test Formatting
```bash
# Via Telegram (text):
"What can you do?"
# Should get clean response without asterisks or Markdown

# Via Telegram (voice note):
"What can you do?"
# Should get clean response without URLs or attachments mentioned
```

---

## Error Handling

All functions return structured error responses:

```python
{
    "success": False,
    "error": "ERROR_CODE",
    "body": "Additional error details (optional)"
}
```

Common error codes:
- `MISSING_GMAIL_API_TOKEN` - Authentication failed
- `HTTP_ERROR` - Network/connection issue
- `API_ERROR` - Gmail API returned error
- `FETCH_ERROR` - Failed to fetch emails
- `COMPOSE_ERROR` - Failed to send email
- `FORWARD_ERROR` - Failed to forward email

---

## Security & Best Practices

1. **Authentication**: Uses OAuth2 refresh token flow via `get_google_access_token()`
2. **Rate Limiting**: Per-user rate limiting already implemented in Telegram handler
3. **Error Logging**: All errors logged with request_id for tracing
4. **Clean Output**: All responses sanitized before sending to user
5. **Identity Enforcement**: All emails automatically signed as Saara

---

## Future Enhancements

Potential additions:
- Batch email operations
- Email templates
- Scheduled sending
- Advanced sorting with ML
- Email threading support
- Attachment handling
- Draft management

---

## Summary

This system provides:
✅ Complete Gmail management (fetch, send, forward, label)
✅ Clean formatting (no Markdown, emojis, or system commentary)
✅ Automatic signature injection (Saara)
✅ Voice-friendly output
✅ Natural language command routing
✅ Production-ready error handling
✅ Full LLM tool integration

All code is modular, typed, and ready for immediate use in production.
