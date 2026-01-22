"""Real-time awareness service for Jarvis AI Agent.

This module provides accurate current time retrieval and human language
time expression parsing. Jarvis must NEVER guess the time - it must always
call getCurrentTime() to get the real system time.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import re
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


logger = logging.getLogger("jarvis.time_service")

DEFAULT_TIMEZONE = "Europe/Berlin"


def _get_timezone(tz_name: str):
    """Get timezone object using available library."""
    if ZONEINFO_AVAILABLE:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            # Fallback to UTC offset for common timezones
            pass
    
    if PYTZ_AVAILABLE:
        try:
            return pytz.timezone(tz_name)
        except Exception:
            pass
    
    # Fallback: use UTC offset for common European timezones
    offset_map = {
        "Europe/Berlin": timezone(timedelta(hours=1)),
        "Europe/London": timezone(timedelta(hours=0)),
        "Europe/Paris": timezone(timedelta(hours=1)),
        "America/New_York": timezone(timedelta(hours=-5)),
        "America/Los_Angeles": timezone(timedelta(hours=-8)),
        "Asia/Tokyo": timezone(timedelta(hours=9)),
        "UTC": timezone.utc,
    }
    
    return offset_map.get(tz_name, timezone.utc)


async def get_current_time(timezone_name: Optional[str] = None) -> Dict[str, Any]:
    """Get the real current system time in ISO 8601 format with timezone.
    
    This function returns the actual current time. Jarvis must call this
    whenever it needs to know the current date/time for scheduling, parsing
    relative expressions, or answering time-related questions.
    
    Args:
        timezone_name: Optional timezone string (e.g., "Europe/Berlin", "America/New_York")
                      Defaults to Europe/Berlin for Saara.
    
    Returns:
        {
            "success": True,
            "currentTime": "2025-01-21T15:22:11+01:00",
            "timezone": "Europe/Berlin",
            "timestamp": 1737467531
        }
    """
    try:
        tz_name = timezone_name or DEFAULT_TIMEZONE
        tz = _get_timezone(tz_name)
        now = datetime.now(tz)
        
        return {
            "success": True,
            "currentTime": now.isoformat(),
            "timezone": tz_name,
            "timestamp": int(now.timestamp()),
            "readable": now.strftime("%A, %B %d, %Y at %I:%M %p")
        }
    except Exception as exc:
        logger.error(f"Error getting current time: {exc!r}")
        return {
            "success": False,
            "error": f"TIME_ERROR: {exc!r}"
        }


async def parse_human_time_expression(
    expression: str,
    current_time: str,
    timezone_name: Optional[str] = None,
    default_duration_minutes: int = 60,
    **kwargs,  # Accept extra args for backward compatibility
) -> Dict[str, Any]:
    """Parse natural language time expressions into precise ISO timestamps.
    
    This function converts human language like "in 2 hours", "tomorrow morning",
    "next Friday at 3pm" into exact ISO 8601 timestamps.
    
    Args:
        expression: Natural language time expression
        current_time: ISO 8601 current time from getCurrentTime()
        timezone_name: Timezone for parsing (defaults to Europe/Berlin)
        default_duration_minutes: Default meeting duration if not specified
    
    Returns:
        {
            "success": True,
            "startTime": "2025-01-21T17:00:00+01:00",
            "endTime": "2025-01-21T18:00:00+01:00",
            "duration": 60,
            "isRelative": True,
            "expression": "in 2 hours"
        }
    """
    # Handle alternative parameter name from tool schema
    if timezone_name is None:
        timezone_name = kwargs.get("timezone")
    
    try:
        tz = _get_timezone(timezone_name or DEFAULT_TIMEZONE)
        now = datetime.fromisoformat(current_time.replace('Z', '+00:00'))
        if now.tzinfo is None:
            now = now.replace(tzinfo=tz)
        
        expr_lower = expression.lower().strip()
        
        # Parse "in X minutes/hours/days"
        in_pattern = r'in\s+(\d+)\s+(minute|minutes|min|hour|hours|hr|day|days)'
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
            
            start_time = now + delta
            end_time = start_time + timedelta(minutes=default_duration_minutes)
            
            return {
                "success": True,
                "startTime": start_time.isoformat(),
                "endTime": end_time.isoformat(),
                "duration": default_duration_minutes,
                "isRelative": True,
                "expression": expression
            }
        
        # Parse "tomorrow"
        if 'tomorrow' in expr_lower:
            tomorrow = now + timedelta(days=1)
            
            # Check for time specification
            time_match = re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', expr_lower)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2)) if time_match.group(2) else 0
                ampm = time_match.group(3)
                
                if ampm == 'pm' and hour < 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0
                
                start_time = tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
            elif 'morning' in expr_lower:
                start_time = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
            elif 'afternoon' in expr_lower:
                start_time = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
            elif 'evening' in expr_lower:
                start_time = tomorrow.replace(hour=18, minute=0, second=0, microsecond=0)
            else:
                start_time = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
            
            end_time = start_time + timedelta(minutes=default_duration_minutes)
            
            return {
                "success": True,
                "startTime": start_time.isoformat(),
                "endTime": end_time.isoformat(),
                "duration": default_duration_minutes,
                "isRelative": True,
                "expression": expression
            }
        
        # Parse "today" or "later today"
        if 'today' in expr_lower or 'later' in expr_lower:
            time_match = re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', expr_lower)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2)) if time_match.group(2) else 0
                ampm = time_match.group(3)
                
                if ampm == 'pm' and hour < 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0
                
                start_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            elif 'afternoon' in expr_lower:
                start_time = now.replace(hour=14, minute=0, second=0, microsecond=0)
            elif 'evening' in expr_lower:
                start_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
            else:
                start_time = now + timedelta(hours=2)
            
            end_time = start_time + timedelta(minutes=default_duration_minutes)
            
            return {
                "success": True,
                "startTime": start_time.isoformat(),
                "endTime": end_time.isoformat(),
                "duration": default_duration_minutes,
                "isRelative": True,
                "expression": expression
            }
        
        # Parse "next week"
        if 'next week' in expr_lower:
            next_week = now + timedelta(weeks=1)
            start_time = next_week.replace(hour=9, minute=0, second=0, microsecond=0)
            
            # Adjust to Monday if not already
            days_ahead = 0 - start_time.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            start_time = start_time + timedelta(days=days_ahead)
            
            end_time = start_time + timedelta(minutes=default_duration_minutes)
            
            return {
                "success": True,
                "startTime": start_time.isoformat(),
                "endTime": end_time.isoformat(),
                "duration": default_duration_minutes,
                "isRelative": True,
                "expression": expression
            }
        
        # Parse weekday names (Monday, Tuesday, etc.)
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
                
                # Check for time specification
                time_match = re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', expr_lower)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2)) if time_match.group(2) else 0
                    ampm = time_match.group(3)
                    
                    if ampm == 'pm' and hour < 12:
                        hour += 12
                    elif ampm == 'am' and hour == 12:
                        hour = 0
                    
                    start_time = target_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
                else:
                    start_time = target_day.replace(hour=9, minute=0, second=0, microsecond=0)
                
                end_time = start_time + timedelta(minutes=default_duration_minutes)
                
                return {
                    "success": True,
                    "startTime": start_time.isoformat(),
                    "endTime": end_time.isoformat(),
                    "duration": default_duration_minutes,
                    "isRelative": True,
                    "expression": expression
                }
        
        # Parse "X days from now"
        days_pattern = r'(\d+)\s+days?\s+from\s+now'
        match = re.search(days_pattern, expr_lower)
        if match:
            days = int(match.group(1))
            target_day = now + timedelta(days=days)
            start_time = target_day.replace(hour=9, minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(minutes=default_duration_minutes)
            
            return {
                "success": True,
                "startTime": start_time.isoformat(),
                "endTime": end_time.isoformat(),
                "duration": default_duration_minutes,
                "isRelative": True,
                "expression": expression
            }
        
        # Parse "X weeks from now"
        weeks_pattern = r'(\d+)\s+weeks?\s+from\s+now'
        match = re.search(weeks_pattern, expr_lower)
        if match:
            weeks = int(match.group(1))
            target_day = now + timedelta(weeks=weeks)
            start_time = target_day.replace(hour=9, minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(minutes=default_duration_minutes)
            
            return {
                "success": True,
                "startTime": start_time.isoformat(),
                "endTime": end_time.isoformat(),
                "duration": default_duration_minutes,
                "isRelative": True,
                "expression": expression
            }
        
        # Parse "end of day" or "by end of day"
        if 'end of day' in expr_lower or 'eod' in expr_lower:
            start_time = now.replace(hour=17, minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(minutes=default_duration_minutes)
            
            return {
                "success": True,
                "startTime": start_time.isoformat(),
                "endTime": end_time.isoformat(),
                "duration": default_duration_minutes,
                "isRelative": True,
                "expression": expression
            }
        
        # If no pattern matched, return error
        return {
            "success": False,
            "error": "AMBIGUOUS_TIME",
            "message": "I need a specific time. Can you clarify?",
            "expression": expression
        }
        
    except Exception as exc:
        logger.error(f"Error parsing time expression '{expression}': {exc!r}")
        return {
            "success": False,
            "error": f"PARSE_ERROR: {exc!r}",
            "expression": expression
        }


async def format_time_readable(iso_time: str) -> Dict[str, Any]:
    """Convert ISO 8601 timestamp to human-readable format.
    
    Args:
        iso_time: ISO 8601 timestamp
    
    Returns:
        {
            "success": True,
            "readable": "Monday, January 21, 2025 at 03:00 PM"
        }
    """
    try:
        dt = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
        readable = dt.strftime("%A, %B %d, %Y at %I:%M %p")
        
        return {
            "success": True,
            "readable": readable,
            "date": dt.strftime("%B %d, %Y"),
            "time": dt.strftime("%I:%M %p"),
            "weekday": dt.strftime("%A")
        }
    except Exception as exc:
        logger.error(f"Error formatting time '{iso_time}': {exc!r}")
        return {
            "success": False,
            "error": f"FORMAT_ERROR: {exc!r}"
        }


async def calculate_time_until(target_time: str, current_time: str) -> Dict[str, Any]:
    """Calculate the duration between current time and a target time.
    
    Args:
        target_time: ISO 8601 target timestamp
        current_time: ISO 8601 current timestamp
    
    Returns:
        {
            "success": True,
            "duration_seconds": 7200,
            "duration_minutes": 120,
            "duration_hours": 2,
            "readable": "2 hours"
        }
    """
    try:
        target = datetime.fromisoformat(target_time.replace('Z', '+00:00'))
        current = datetime.fromisoformat(current_time.replace('Z', '+00:00'))
        
        delta = target - current
        total_seconds = int(delta.total_seconds())
        
        if total_seconds < 0:
            return {
                "success": False,
                "error": "TARGET_IN_PAST",
                "message": "That time is in the past."
            }
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        if hours > 0:
            readable = f"{hours} hour{'s' if hours != 1 else ''}"
            if minutes > 0:
                readable += f" and {minutes} minute{'s' if minutes != 1 else ''}"
        elif minutes > 0:
            readable = f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            readable = "less than a minute"
        
        return {
            "success": True,
            "duration_seconds": total_seconds,
            "duration_minutes": total_seconds // 60,
            "duration_hours": hours,
            "readable": readable
        }
    except Exception as exc:
        logger.error(f"Error calculating time until: {exc!r}")
        return {
            "success": False,
            "error": f"CALCULATION_ERROR: {exc!r}"
        }


async def validate_time_range(start_time: str, end_time: str) -> Dict[str, Any]:
    """Validate that a time range is logical (end after start).
    
    Args:
        start_time: ISO 8601 start timestamp
        end_time: ISO 8601 end timestamp
    
    Returns:
        {
            "success": True,
            "valid": True,
            "duration_minutes": 60
        }
    """
    try:
        start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        
        if end <= start:
            return {
                "success": True,
                "valid": False,
                "error": "END_BEFORE_START",
                "message": "The end time must be after the start time."
            }
        
        delta = end - start
        duration_minutes = int(delta.total_seconds() // 60)
        
        return {
            "success": True,
            "valid": True,
            "duration_minutes": duration_minutes
        }
    except Exception as exc:
        logger.error(f"Error validating time range: {exc!r}")
        return {
            "success": False,
            "error": f"VALIDATION_ERROR: {exc!r}"
        }
