"""Calendar service integration for the Jarvis AI Agent.

This module provides tool-facing helpers for Google Calendar operations.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone as tz_module
from typing import Any, Dict, Optional, Tuple

import httpx
import logging

try:
    from zoneinfo import ZoneInfo
    ZONEINFO_AVAILABLE = True
except ImportError:
    ZONEINFO_AVAILABLE = False

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False

from src.services.google_oauth import get_google_access_token


logger = logging.getLogger("jarvis.calendar")

# Default timezone for calendar operations (IANA format)
DEFAULT_TIMEZONE = "Africa/Lagos"


def _get_timezone_obj(tz_name: str):
    """Get timezone object using available library."""
    if ZONEINFO_AVAILABLE:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    
    if PYTZ_AVAILABLE:
        try:
            return pytz.timezone(tz_name)
        except Exception:
            pass
    
    # Fallback: use UTC offset for common timezones
    offset_map = {
        "Africa/Lagos": tz_module(timedelta(hours=1)),
        "Europe/Berlin": tz_module(timedelta(hours=1)),
        "Europe/London": tz_module(timedelta(hours=0)),
        "America/New_York": tz_module(timedelta(hours=-5)),
        "America/Los_Angeles": tz_module(timedelta(hours=-8)),
        "UTC": tz_module.utc,
    }
    
    return offset_map.get(tz_name, tz_module.utc)


def _parse_natural_time(
    expression: str,
    reference_time: datetime,
    timezone_name: str = DEFAULT_TIMEZONE
) -> Tuple[Optional[datetime], Optional[str]]:
    """Parse natural language time into datetime.
    
    Returns:
        (datetime, None) on success
        (None, error_message) on failure
    """
    expr_lower = expression.lower().strip()
    tz = _get_timezone_obj(timezone_name)
    now = reference_time
    
    # Already ISO format? Parse directly
    if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', expression):
        try:
            dt = datetime.fromisoformat(expression.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            return (dt, None)
        except Exception:
            pass
    
    # Parse "in X minutes/hours/days"
    in_pattern = r'in\s+(\d+)\s+(minute|minutes|min|mins|hour|hours|hr|hrs|day|days)'
    match = re.search(in_pattern, expr_lower)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        
        if 'min' in unit:
            delta = timedelta(minutes=amount)
        elif 'hour' in unit or 'hr' in unit:
            delta = timedelta(hours=amount)
        elif 'day' in unit:
            delta = timedelta(days=amount)
        else:
            delta = timedelta(hours=1)
        
        return (now + delta, None)
    
    # Parse "tomorrow"
    if 'tomorrow' in expr_lower:
        tomorrow = now + timedelta(days=1)
        hour, minute = _extract_time_from_expr(expr_lower)
        if hour is not None:
            result = tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
        elif 'morning' in expr_lower:
            result = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
        elif 'afternoon' in expr_lower:
            result = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
        elif 'evening' in expr_lower or 'night' in expr_lower:
            result = tomorrow.replace(hour=18, minute=0, second=0, microsecond=0)
        else:
            result = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
        return (result, None)
    
    # Parse "today"
    if 'today' in expr_lower:
        hour, minute = _extract_time_from_expr(expr_lower)
        if hour is not None:
            result = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        elif 'afternoon' in expr_lower:
            result = now.replace(hour=14, minute=0, second=0, microsecond=0)
        elif 'evening' in expr_lower or 'night' in expr_lower:
            result = now.replace(hour=18, minute=0, second=0, microsecond=0)
        else:
            result = now + timedelta(hours=1)
        return (result, None)
    
    # Parse weekday names
    weekdays = {
        'monday': 0, 'mon': 0,
        'tuesday': 1, 'tue': 1, 'tues': 1,
        'wednesday': 2, 'wed': 2,
        'thursday': 3, 'thu': 3, 'thur': 3, 'thurs': 3,
        'friday': 4, 'fri': 4,
        'saturday': 5, 'sat': 5,
        'sunday': 6, 'sun': 6
    }
    
    for day_name, day_num in weekdays.items():
        if day_name in expr_lower:
            days_ahead = day_num - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            
            target_day = now + timedelta(days=days_ahead)
            hour, minute = _extract_time_from_expr(expr_lower)
            if hour is not None:
                result = target_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
            else:
                result = target_day.replace(hour=9, minute=0, second=0, microsecond=0)
            return (result, None)
    
    # Parse standalone time like "6am", "3:30pm", "14:00"
    hour, minute = _extract_time_from_expr(expr_lower)
    if hour is not None:
        result = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # If the time is in the past today, schedule for tomorrow
        if result <= now:
            result = result + timedelta(days=1)
        return (result, None)
    
    # Could not parse
    return (None, f"Could not understand time '{expression}'. Please specify like 'tomorrow at 3pm' or '2025-01-21T15:00:00'.")


def _extract_time_from_expr(expr: str) -> Tuple[Optional[int], int]:
    """Extract hour and minute from expression. Returns (hour, minute) or (None, 0)."""
    # Match patterns like "6am", "6:30pm", "14:00", "3 pm"
    patterns = [
        r'(\d{1,2}):(\d{2})\s*(am|pm)?',  # 6:30pm, 14:00
        r'(\d{1,2})\s*(am|pm)',              # 6am, 3 pm
    ]
    
    for pattern in patterns:
        match = re.search(pattern, expr.lower())
        if match:
            groups = match.groups()
            hour = int(groups[0])
            
            if len(groups) == 3 and groups[1]:  # Has minutes
                minute = int(groups[1])
                ampm = groups[2]
            elif len(groups) == 2:  # No minutes
                minute = 0
                ampm = groups[1]
            else:
                minute = 0
                ampm = None
            
            if ampm == 'pm' and hour < 12:
                hour += 12
            elif ampm == 'am' and hour == 12:
                hour = 0
            
            return (hour, minute)
    
    return (None, 0)


async def _calendar_auth_headers(force_refresh: bool = False) -> Dict[str, str]:
    """Return auth headers for Google Calendar using the SHARED Google OAuth token.
    
    This uses the SAME token as Gmail - there is no separate calendar token.
    All Google services (Gmail, Calendar, Meet) share one OAuth token.
    
    Args:
        force_refresh: If True, forces a token refresh even if cached token exists.
    """
    # Use the shared Google OAuth token manager (same as Gmail)
    # There is NO separate calendar token - it's all one OAuth token
    token = await get_google_access_token(force_refresh=force_refresh)

    if not token:
        logger.error(
            "Unable to authenticate with Google Calendar. "
            "The OAuth token could not be refreshed. Please reauthorize."
        )
        return {}

    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _calendar_id() -> str:
    return os.getenv("GOOGLE_CALENDAR_ID", "primary")


async def calendar_list_events(max_results: int = 10) -> Dict[str, Any]:
    """List upcoming events from the configured calendar."""

    headers = await _calendar_auth_headers()
    if not headers:
        return {
            "success": False, 
            "error": "AUTH_ERROR",
            "message": "Unable to authenticate with Google Calendar. Please reauthorize."
        }

    cal_id = _calendar_id()
    url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events"
    params: Dict[str, Any] = {
        "maxResults": max_results,
        "singleEvents": True,
        "orderBy": "startTime",
        "timeMin": datetime.now(tz_module.utc).isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            
            # If 401 Unauthorized, token may have just expired - retry once with fresh token
            if resp.status_code == 401:
                logger.warning("Calendar API returned 401, retrying with fresh token...")
                headers = await _calendar_auth_headers(force_refresh=True)
                if headers:
                    resp = await client.get(url, headers=headers, params=params)
            
            resp.raise_for_status()
    except httpx.RequestError as exc:
        return {"success": False, "error": f"HTTP_ERROR: {exc!r}"}
    except httpx.HTTPStatusError as exc:
        error_body = exc.response.text
        if exc.response.status_code == 401:
            return {
                "success": False, 
                "error": "AUTH_ERROR",
                "message": "Unable to authenticate with Google Calendar. Please reauthorize."
            }
        return {"success": False, "error": f"API_ERROR: {exc.response.status_code}", "body": error_body}

    data = resp.json()
    events = data.get("items", []) or []
    return {"success": True, "data": events}


async def calendar_create_event(
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str | None = None,
    location: str | None = None,
    timezone_name: str | None = None,
) -> Dict[str, Any]:
    """Create a new event in the configured Google Calendar.
    
    IMPORTANT: Both start_iso and end_iso must be valid ISO 8601 datetimes.
    The timezone_name should be an IANA timezone (e.g., 'Africa/Lagos').
    """
    tz_name = timezone_name or DEFAULT_TIMEZONE
    
    headers = await _calendar_auth_headers()
    if not headers:
        return {
            "success": False, 
            "error": "AUTH_ERROR",
            "message": "Unable to authenticate with Google Calendar. Please reauthorize."
        }

    cal_id = _calendar_id()
    url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events"

    body: Dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start_iso, "timeZone": tz_name},
        "end": {"dateTime": end_iso, "timeZone": tz_name},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            
            # If 401 Unauthorized, token may have just expired - retry once with fresh token
            if resp.status_code == 401:
                logger.warning("Calendar API returned 401, retrying with fresh token...")
                headers = await _calendar_auth_headers(force_refresh=True)
                if headers:
                    resp = await client.post(url, headers=headers, json=body)
            
            resp.raise_for_status()
    except httpx.RequestError as exc:
        return {"success": False, "error": f"HTTP_ERROR: {exc!r}"}
    except httpx.HTTPStatusError as exc:
        error_body = exc.response.text
        if exc.response.status_code == 401:
            return {
                "success": False, 
                "error": "AUTH_ERROR",
                "message": "Unable to authenticate with Google Calendar. Please reauthorize."
            }
        return {"success": False, "error": f"API_ERROR: {exc.response.status_code}", "body": error_body}

    return {"success": True, "data": resp.json()}


async def calendar_create_event_safe(
    summary: str = "",
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    timezone_name: Optional[str] = None,
    duration_minutes: int = 60,
    **kwargs,  # Accept any extra args for backward compatibility
) -> Dict[str, Any]:
    """Safe calendar event creation with validation and natural language parsing.
    
    This function:
    1. Parses natural language time ("tomorrow at 6am") into ISO 8601
    2. Auto-generates end_time = start_time + duration if not provided
    3. Validates that end > start before calling API
    4. Returns clarification request if parsing fails (never calls API with bad data)
    
    Args:
        summary: Event title (required)
        start_time: Start time - can be ISO 8601 or natural language
        end_time: End time - can be ISO 8601 or natural language (optional, defaults to start + duration)
        description: Event description
        location: Event location
        timezone_name: IANA timezone (defaults to Africa/Lagos)
        duration_minutes: Default duration if end_time not specified (default: 60)
    
    Returns:
        On success: {"success": True, "data": {...event data...}}
        On validation failure: {"success": False, "error": "VALIDATION_ERROR", "message": "..."}
        On parse failure: {"success": False, "error": "PARSE_ERROR", "clarification_needed": True, "message": "..."}
    
    Note: Also accepts old parameter names (start_iso, end_iso) for backward compatibility.
    """
    # Handle backward compatibility with old parameter names
    if start_time is None:
        start_time = kwargs.get("start_iso") or kwargs.get("start") or ""
    if end_time is None:
        end_time = kwargs.get("end_iso") or kwargs.get("end")
    if not summary:
        summary = kwargs.get("title", "")
    
    tz_name = timezone_name or DEFAULT_TIMEZONE
    tz = _get_timezone_obj(tz_name)
    now = datetime.now(tz)
    
    # Validate summary
    if not summary or not summary.strip():
        return {
            "success": False,
            "error": "VALIDATION_ERROR",
            "message": "Event title (summary) is required."
        }
    
    # Parse start_time
    if not start_time or not start_time.strip():
        return {
            "success": False,
            "error": "PARSE_ERROR",
            "clarification_needed": True,
            "message": "When would you like to schedule this event? Please provide a time like 'tomorrow at 3pm' or 'Friday at 10am'."
        }
    
    start_dt, start_error = _parse_natural_time(start_time, now, tz_name)
    if start_dt is None:
        return {
            "success": False,
            "error": "PARSE_ERROR",
            "clarification_needed": True,
            "message": start_error
        }
    
    # Parse or auto-generate end_time
    if end_time and end_time.strip():
        end_dt, end_error = _parse_natural_time(end_time, now, tz_name)
        if end_dt is None:
            return {
                "success": False,
                "error": "PARSE_ERROR",
                "clarification_needed": True,
                "message": end_error
            }
    else:
        # Auto-generate: end = start + duration
        end_dt = start_dt + timedelta(minutes=duration_minutes)
    
    # Validate: end must be after start
    if end_dt <= start_dt:
        return {
            "success": False,
            "error": "VALIDATION_ERROR",
            "message": f"End time must be after start time. You specified start: {start_dt.strftime('%I:%M %p')}, end: {end_dt.strftime('%I:%M %p')}."
        }
    
    # Validate: start should not be in the past
    if start_dt < now - timedelta(minutes=5):  # 5 min grace period
        return {
            "success": False,
            "error": "VALIDATION_ERROR",
            "message": f"Cannot schedule an event in the past. The time '{start_time}' has already passed."
        }
    
    # Convert to ISO format with timezone
    start_iso = start_dt.isoformat()
    end_iso = end_dt.isoformat()
    
    logger.info(
        f"Creating calendar event: '{summary}' from {start_iso} to {end_iso} ({tz_name})"
    )
    
    # Call the base function with validated data
    return await calendar_create_event(
        summary=summary,
        start_iso=start_iso,
        end_iso=end_iso,
        description=description,
        location=location,
        timezone_name=tz_name,
    )
