"""Calendar intent router for natural language scheduling commands.

This module interprets user scheduling requests and routes to appropriate
calendar functions, returning clean, formatted responses for Saara.
"""

from typing import Any, Dict, Optional, List
import logging
from datetime import datetime, timedelta, timezone

from src.services.calendar_advanced import (
    calendar_get_availability,
    calendar_check_slot_available,
    calendar_find_next_available_slots,
    calendar_create_meet_event,
    calendar_reschedule_meeting,
    calendar_cancel_meeting,
    calendar_update_attendees,
)


logger = logging.getLogger("jarvis.calendar_intent")


def _format_meet_response(data: Dict[str, Any]) -> str:
    meet_link = data.get("meet_link", "")
    start_readable = data.get("start_readable", "")
    title = data.get("title", "Meeting")
    attendees = data.get("attendees", [])
    
    if not meet_link:
        return f"Your meeting '{title}' has been scheduled for {start_readable}."
    
    response = f"Your meeting has been scheduled. Here is your Google Meet link: {meet_link}"
    
    if attendees:
        attendee_names = ", ".join(attendees)
        response += f"\n\nInvitations have been sent to: {attendee_names}"
    
    return response


def _format_availability_response(data: Dict[str, Any]) -> str:
    if data.get("available"):
        return data.get("message", "This time slot is available.")
    
    message = data.get("message", "This time is unavailable.")
    return message


def _format_slots_response(slots: List[Dict[str, Any]]) -> str:
    if not slots:
        return "No available time slots found in the next week."
    
    response = "Here are the next available time slots:\n\n"
    for i, slot in enumerate(slots, 1):
        response += f"{i}. {slot['readable']}\n"
    
    return response.strip()


def _format_reschedule_response(data: Dict[str, Any]) -> str:
    title = data.get("title", "Meeting")
    start_readable = data.get("start_readable", "")
    
    return f"Your meeting '{title}' has been rescheduled to {start_readable}."


def _format_cancel_response(data: Dict[str, Any]) -> str:
    return "The meeting has been cancelled and attendees have been notified."


async def handle_scheduling_intent(
    action: str,
    title: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    description: Optional[str] = None,
    event_id: Optional[str] = None,
    duration_minutes: int = 30,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    
    action = action.lower().strip()
    
    if action == "check_availability":
        if not start_date or not end_date:
            return {
                "success": False,
                "error": "MISSING_DATE_RANGE",
                "message": "Please provide start and end dates."
            }
        
        result = await calendar_get_availability(start_date, end_date)
        if not result.get("success"):
            return result
        
        is_available = result["data"]["is_available"]
        busy_count = len(result["data"]["busy_blocks"])
        
        if is_available:
            message = "You are completely free during this time."
        else:
            message = f"You have {busy_count} event(s) during this time."
        
        return {
            "success": True,
            "message": message,
            "data": result["data"]
        }
    
    if action == "check_slot":
        if not start_time or not end_time:
            return {
                "success": False,
                "error": "MISSING_TIME_SLOT",
                "message": "Please provide start and end times."
            }
        
        result = await calendar_check_slot_available(start_time, end_time)
        if not result.get("success"):
            return result
        
        message = _format_availability_response(result["data"])
        
        return {
            "success": True,
            "message": message,
            "data": result["data"]
        }
    
    if action == "find_slots":
        if not start_time:
            now = datetime.now(tz=timezone.utc)
            start_time = now.isoformat()
        
        result = await calendar_find_next_available_slots(
            start_time,
            duration_minutes=duration_minutes,
            num_slots=3
        )
        
        if not result.get("success"):
            return result
        
        slots = result["data"]["slots"]
        message = _format_slots_response(slots)
        
        return {
            "success": True,
            "message": message,
            "data": result["data"]
        }
    
    if action == "create_meeting":
        if not title or not start_time or not end_time:
            return {
                "success": False,
                "error": "MISSING_MEETING_DETAILS",
                "message": "Please provide meeting title, start time, and end time."
            }
        
        slot_check = await calendar_check_slot_available(start_time, end_time)
        if slot_check.get("success") and not slot_check["data"].get("available"):
            conflict_msg = slot_check["data"].get("message", "This time is unavailable.")
            
            alt_slots_result = await calendar_find_next_available_slots(
                start_time,
                duration_minutes=duration_minutes,
                num_slots=3
            )
            
            if alt_slots_result.get("success"):
                slots = alt_slots_result["data"]["slots"]
                suggestions = _format_slots_response(slots)
                conflict_msg += f"\n\n{suggestions}"
            
            return {
                "success": False,
                "error": "TIME_CONFLICT",
                "message": conflict_msg
            }
        
        result = await calendar_create_meet_event(
            title=title,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees,
            description=description
        )
        
        if not result.get("success"):
            return result
        
        message = _format_meet_response(result["data"])
        
        return {
            "success": True,
            "message": message,
            "data": result["data"]
        }
    
    if action == "reschedule_meeting":
        if not event_id or not start_time or not end_time:
            return {
                "success": False,
                "error": "MISSING_RESCHEDULE_DETAILS",
                "message": "Please provide event ID, new start time, and new end time."
            }
        
        result = await calendar_reschedule_meeting(event_id, start_time, end_time)
        
        if not result.get("success"):
            return result
        
        message = _format_reschedule_response(result["data"])
        
        return {
            "success": True,
            "message": message,
            "data": result["data"]
        }
    
    if action == "cancel_meeting":
        if not event_id:
            return {
                "success": False,
                "error": "MISSING_EVENT_ID",
                "message": "Please provide the event ID to cancel."
            }
        
        result = await calendar_cancel_meeting(event_id)
        
        if not result.get("success"):
            return result
        
        message = _format_cancel_response(result["data"])
        
        return {
            "success": True,
            "message": message,
            "data": result["data"]
        }
    
    if action == "update_attendees":
        if not event_id or not attendees:
            return {
                "success": False,
                "error": "MISSING_ATTENDEE_DETAILS",
                "message": "Please provide event ID and attendee list."
            }
        
        result = await calendar_update_attendees(event_id, attendees)
        
        if not result.get("success"):
            return result
        
        attendee_names = ", ".join(attendees)
        message = f"Attendees updated. Invitations sent to: {attendee_names}"
        
        return {
            "success": True,
            "message": message,
            "data": result["data"]
        }
    
    return {
        "success": False,
        "error": "INVALID_ACTION",
        "message": "Unknown scheduling action."
    }
