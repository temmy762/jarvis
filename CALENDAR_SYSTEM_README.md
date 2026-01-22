# Jarvis Calendar Scheduling System - Complete Documentation

## Overview

This is a comprehensive Google Calendar scheduling system built for Saara's Jarvis AI assistant. The system provides full calendar management with Google Meet integration, conflict detection, availability checking, and clean response formatting.

---

## File Structure

```
src/
├── services/
│   ├── calendar.py                  # Basic calendar operations (existing)
│   ├── calendar_advanced.py         # Advanced scheduling operations (NEW)
│   └── calendar_intent.py           # Intent router for natural language (NEW)
└── core/
    └── tools.py                     # Tool registry (UPDATED)
```

---

## Module Descriptions

### 1. `src/services/calendar_advanced.py`

**Purpose**: Comprehensive calendar scheduling with Google Meet integration

**Key Functions**:

#### **Availability Checking**

- `calendar_get_availability(start_date, end_date)`
  - Fetches all events in date range
  - Returns busy blocks with start/end times
  - Returns boolean `is_available`

- `calendar_check_slot_available(start_time, end_time)`
  - Checks if specific slot is free
  - Detects conflicts
  - Returns formatted conflict message if busy
  - Format: "This time is unavailable. Saara is busy between [time]."

- `calendar_find_next_available_slots(start_search, duration_minutes=30, num_slots=3)`
  - Finds next N available time slots
  - Respects business hours (9 AM - 5 PM)
  - Skips weekends
  - Returns readable time formats

#### **Google Meet Event Creation**

- `calendar_create_meet_event(title, start_time, end_time, attendees=None, description=None)`
  - Creates calendar event with Google Meet link
  - Uses `conferenceData` with `createRequest`
  - Automatically sends invitations to attendees
  - Sets `sendUpdates: "all"`
  - Returns:
    ```python
    {
        "event_id": "...",
        "meet_link": "https://meet.google.com/...",
        "start_time": "...",
        "end_time": "...",
        "start_readable": "03:00 PM on Tuesday, December 10",
        "end_readable": "03:30 PM on Tuesday, December 10",
        "attendees": ["john@example.com"],
        "title": "Team Sync"
    }
    ```

#### **Meeting Management**

- `calendar_reschedule_meeting(event_id, new_start_time, new_end_time)`
  - Updates existing event to new time
  - Notifies all attendees automatically
  - Returns updated event details

- `calendar_cancel_meeting(event_id)`
  - Deletes event
  - Sends cancellation notices to attendees
  - Returns success confirmation

- `calendar_update_attendees(event_id, attendees)`
  - Updates attendee list
  - Sends new invitations
  - Returns updated attendee list

---

### 2. `src/services/calendar_intent.py`

**Purpose**: Route natural language scheduling commands to appropriate functions

**Main Function**:
```python
handle_scheduling_intent(
    action="create_meeting",
    title="Team Sync",
    start_time="2025-12-10T15:00:00+00:00",
    end_time="2025-12-10T15:30:00+00:00",
    attendees=["john@example.com"]
)
```

**Supported Actions**:

1. **check_availability**
   - Params: `start_date`, `end_date`
   - Returns: Busy/free status with event count

2. **check_slot**
   - Params: `start_time`, `end_time`
   - Returns: Available/unavailable with conflict details

3. **find_slots**
   - Params: `start_time`, `duration_minutes`, (optional)
   - Returns: Next 3 available time slots

4. **create_meeting**
   - Params: `title`, `start_time`, `end_time`, `attendees`, `description`
   - Checks conflicts first
   - Suggests alternatives if busy
   - Returns: Google Meet link + confirmation

5. **reschedule_meeting**
   - Params: `event_id`, `start_time`, `end_time`
   - Returns: Confirmation with new time

6. **cancel_meeting**
   - Params: `event_id`
   - Returns: Cancellation confirmation

7. **update_attendees**
   - Params: `event_id`, `attendees`
   - Returns: Updated attendee list

**Response Formatting**:

All responses are clean, plain-text messages:

```python
# Meeting created
"Your meeting has been scheduled. Here is your Google Meet link: https://meet.google.com/abc-defg-hij

Invitations have been sent to: john@example.com, sarah@company.com"

# Conflict detected
"This time is unavailable. Saara is busy between 03:00 PM and 04:00 PM on Tuesday, December 10.

Here are the next available time slots:

1. 04:00 PM on Tuesday, December 10
2. 09:00 AM on Wednesday, December 11
3. 10:00 AM on Wednesday, December 11"

# Rescheduled
"Your meeting 'Team Sync' has been rescheduled to 04:00 PM on Tuesday, December 10."

# Cancelled
"The meeting has been cancelled and attendees have been notified."
```

---

### 3. Tool Registry Updates (`src/core/tools.py`)

**New Tools Registered**:

1. `calendar_check_slot_available` - Check if time slot is free
2. `calendar_find_next_available_slots` - Find next N available slots
3. `calendar_create_meet_event` - Create event with Google Meet
4. `calendar_reschedule_meeting` - Reschedule existing meeting
5. `calendar_cancel_meeting` - Cancel meeting
6. `calendar_update_attendees` - Update attendee list

---

## Key Features

### **Google Meet Integration**

Every meeting created with `calendar_create_meet_event` automatically includes:
- Google Meet video conferencing link
- Proper `conferenceData` structure
- Unique `requestId` for conference creation
- Entry point with video URI

**API Structure**:
```python
"conferenceData": {
    "createRequest": {
        "requestId": "unique-uuid",
        "conferenceSolutionKey": {"type": "hangoutsMeet"}
    }
}
```

### **Conflict Detection**

Before creating any meeting:
1. Check if slot is available
2. If conflict exists:
   - Return clear message: "Saara is busy between X and Y"
   - Find next 3 available slots
   - Suggest alternatives

### **Automatic Invitations**

All attendees receive:
- Email invitation from Google Calendar
- Google Meet link
- Event details
- Updates for reschedules/cancellations

Controlled by: `"sendUpdates": "all"`

### **Business Hours Logic**

Available slot finder respects:
- **Hours**: 9 AM - 5 PM
- **Days**: Monday - Friday
- **Default duration**: 30 minutes (configurable)

### **Clean Formatting**

All responses:
- Plain text only
- No Markdown symbols
- No asterisks or decorative characters
- Human-readable time formats
- No system commentary

---

## Usage Examples

### Example 1: Create Meeting with Google Meet

```python
from src.services.calendar_advanced import calendar_create_meet_event

result = await calendar_create_meet_event(
    title="Q4 Planning Session",
    start_time="2025-12-15T14:00:00+00:00",
    end_time="2025-12-15T15:00:00+00:00",
    attendees=["john@example.com", "sarah@company.com"],
    description="Discuss Q4 goals and budget"
)

if result["success"]:
    data = result["data"]
    print(f"Meet link: {data['meet_link']}")
    print(f"Event ID: {data['event_id']}")
```

**Response**:
```
Your meeting has been scheduled. Here is your Google Meet link: https://meet.google.com/abc-defg-hij

Invitations have been sent to: john@example.com, sarah@company.com
```

### Example 2: Check Availability

```python
from src.services.calendar_advanced import calendar_check_slot_available

result = await calendar_check_slot_available(
    start_time="2025-12-10T15:00:00+00:00",
    end_time="2025-12-10T15:30:00+00:00"
)

if result["success"]:
    if result["data"]["available"]:
        print("Slot is free!")
    else:
        print(result["data"]["message"])
```

### Example 3: Find Next Available Slots

```python
from src.services.calendar_advanced import calendar_find_next_available_slots

result = await calendar_find_next_available_slots(
    start_search="2025-12-10T09:00:00+00:00",
    duration_minutes=60,
    num_slots=5
)

if result["success"]:
    for slot in result["data"]["slots"]:
        print(slot["readable"])
```

**Output**:
```
09:00 AM on Tuesday, December 10
10:30 AM on Tuesday, December 10
02:00 PM on Tuesday, December 10
09:00 AM on Wednesday, December 11
11:00 AM on Wednesday, December 11
```

### Example 4: Reschedule Meeting

```python
from src.services.calendar_advanced import calendar_reschedule_meeting

result = await calendar_reschedule_meeting(
    event_id="abc123xyz",
    new_start_time="2025-12-10T16:00:00+00:00",
    new_end_time="2025-12-10T16:30:00+00:00"
)

if result["success"]:
    print(result["data"]["start_readable"])
```

**Response**:
```
Your meeting 'Team Sync' has been rescheduled to 04:00 PM on Tuesday, December 10.
```

### Example 5: Cancel Meeting

```python
from src.services.calendar_advanced import calendar_cancel_meeting

result = await calendar_cancel_meeting(event_id="abc123xyz")

if result["success"]:
    print("Meeting cancelled")
```

**Response**:
```
The meeting has been cancelled and attendees have been notified.
```

---

## Natural Language Commands

The LLM can now understand and execute commands like:

- "Schedule a meeting with John tomorrow at 3pm"
- "Create a Google Meet link for Friday at 2pm with the team"
- "Am I free on Tuesday afternoon?"
- "Find me available times next week"
- "Reschedule my 4pm meeting to 5pm"
- "Cancel the 2pm call"
- "Add Sarah to the team meeting"

---

## Testing

### 1. Test Google Meet Creation

```bash
# Start server
python -m uvicorn main:app --host 0.0.0.0 --port 5000

# Via Telegram:
"Schedule a meeting with john@example.com tomorrow at 3pm"

# Expected: Clean response with Google Meet link
```

### 2. Test Conflict Detection

```bash
# Via Telegram:
"Schedule a meeting at 3pm today"
# (If 3pm is busy)

# Expected: "This time is unavailable. Saara is busy between..."
# Plus 3 alternative time suggestions
```

### 3. Test Availability Check

```bash
# Via Telegram:
"Am I free tomorrow afternoon?"

# Expected: "You are completely free during this time."
# OR "You have 2 event(s) during this time."
```

### 4. Test Rescheduling

```bash
# Via Telegram:
"Move my 4pm meeting to 5pm"

# Expected: "Your meeting 'X' has been rescheduled to 05:00 PM..."
```

---

## Error Handling

All functions return structured responses:

```python
{
    "success": False,
    "error": "ERROR_CODE",
    "message": "User-friendly error message"
}
```

**Common Error Codes**:
- `MISSING_CALENDAR_TOKEN` - Authentication failed
- `AVAILABILITY_CHECK_ERROR` - Failed to fetch events
- `CREATE_MEET_ERROR` - Failed to create event
- `RESCHEDULE_ERROR` - Failed to update event
- `CANCEL_ERROR` - Failed to delete event
- `TIME_CONFLICT` - Requested time is busy

---

## Configuration

**Required Environment Variables**:
```bash
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REFRESH_TOKEN=your-refresh-token
GOOGLE_CALENDAR_ID=primary  # or specific calendar ID
```

**Owner Information** (hardcoded):
- Name: Saara
- Email: saar@alaw.co.il

---

## API Integration Details

### Google Calendar API Endpoints Used

1. **List Events**: `GET /calendars/{calendarId}/events`
2. **Create Event**: `POST /calendars/{calendarId}/events?conferenceDataVersion=1`
3. **Update Event**: `PUT /calendars/{calendarId}/events/{eventId}?sendUpdates=all`
4. **Delete Event**: `DELETE /calendars/{calendarId}/events/{eventId}?sendUpdates=all`

### Conference Data Structure

```json
{
  "conferenceData": {
    "createRequest": {
      "requestId": "unique-uuid-here",
      "conferenceSolutionKey": {
        "type": "hangoutsMeet"
      }
    }
  }
}
```

**Critical**: Must include `?conferenceDataVersion=1` in query params when creating events with conference data.

---

## Summary

This system provides:

✅ **Google Meet Integration** - Automatic link generation  
✅ **Conflict Detection** - Smart availability checking  
✅ **Alternative Suggestions** - Next 3 available slots  
✅ **Automatic Invitations** - Email notifications to attendees  
✅ **Rescheduling** - Update meetings with attendee notification  
✅ **Cancellation** - Delete with automatic notifications  
✅ **Clean Formatting** - Plain-text responses only  
✅ **Business Hours** - Respects 9-5 Mon-Fri schedule  
✅ **Natural Language** - Understands scheduling commands  
✅ **Production Ready** - Full error handling and logging  

All code is modular, typed, and ready for immediate production use.
