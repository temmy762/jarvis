"""Advanced Google Calendar scheduling for Jarvis AI Agent.

This module provides comprehensive calendar management including availability
checking, conflict detection, Google Meet integration, rescheduling, and
cancellation with clean formatting for Saara.
"""

from __future__ import annotations

import os
import re
import uuid
import asyncio
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from zoneinfo import ZoneInfo

import httpx
import logging

from src.services.calendar import _calendar_auth_headers, _calendar_id, DEFAULT_TIMEZONE
from src.core.decision_authority import (
    RiskLevel,
    choose_best_match,
    decide_requires_confirmation,
)


logger = logging.getLogger("jarvis.calendar_advanced")

SAARA_EMAIL = "saar@alaw.co.il"

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_MEET_URI_RE = re.compile(r"^https://meet\.google\.com/([a-z0-9-]+)$", re.IGNORECASE)
_MEET_CODE_RE = re.compile(r"^[a-z0-9]{3,10}(?:-[a-z0-9]{3,10}){0,2}$", re.IGNORECASE)


def _parse_iso_datetime(iso_string: str) -> datetime:
    try:
        if iso_string.endswith('Z'):
            iso_string = iso_string[:-1] + '+00:00'
        return datetime.fromisoformat(iso_string)
    except Exception:
        return datetime.now(tz=timezone.utc)


def _format_time_readable(dt: datetime) -> str:
    return dt.strftime("%I:%M %p on %A, %B %d")


def _get_timezone_obj(timezone_name: str) -> timezone:
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return timezone.utc


def _date_to_time_window(date_str: str, timezone_name: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    try:
        d = date.fromisoformat(date_str)
    except Exception:
        return None, None, "Invalid date. Please provide date as YYYY-MM-DD."

    tz = _get_timezone_obj(timezone_name)
    start_dt = datetime.combine(d, dt_time.min).replace(tzinfo=tz)
    end_dt = start_dt + timedelta(days=1)
    return start_dt.isoformat(), end_dt.isoformat(), None


def _normalize_meet_link(raw: Optional[str]) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    cleaned = cleaned.rstrip(").,;")
    if not cleaned:
        return None
    if cleaned.lower().startswith("https://meet.google.com/"):
        base = cleaned.split("?")[0].strip("/")
        match = _MEET_URI_RE.match(base.lower())
        if match and _MEET_CODE_RE.match(match.group(1)):
            meet_code = match.group(1).lower()
            return f"https://meet.google.com/{meet_code}"
    elif _MEET_CODE_RE.match(cleaned.replace(" ", "").lower()):
        meet_code = cleaned.replace(" ", "").lower()
        return f"https://meet.google.com/{meet_code}"
    return None


def _extract_meet_link(event: Dict[str, Any]) -> Optional[str]:
    conference_data = event.get("conferenceData") or {}
    entry_points = conference_data.get("entryPoints") or []
    for entry in entry_points:
        if entry.get("entryPointType") == "video":
            link = _normalize_meet_link(entry.get("uri"))
            if link:
                return link
    hangout_link = _normalize_meet_link(event.get("hangoutLink"))
    if hangout_link:
        return hangout_link
    conf_id = _normalize_meet_link(conference_data.get("conferenceId"))
    if conf_id:
        return conf_id
    return None


async def _fetch_event_with_conference(event_id: str, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
    cal_id = _calendar_id()
    url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events/{event_id}"
    params = {"conferenceDataVersion": 1}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


async def _calendar_find_events(
    title: str,
    time_min: str,
    time_max: str,
    timezone_name: str,
    max_results: int = 5,
) -> Dict[str, Any]:
    headers = await _calendar_auth_headers()
    if not headers:
        return {
            "success": False,
            "error": "AUTH_ERROR",
            "message": "Unable to authenticate with Google Calendar. Please reauthorize.",
        }

    cal_id = _calendar_id()
    url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events"
    params: Dict[str, Any] = {
        "q": title,
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": True,
        "orderBy": "startTime",
        "maxResults": max_results,
        "timeZone": timezone_name,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"FIND_EVENTS_ERROR: {exc!r}"}

    data = resp.json()
    items = data.get("items", []) or []
    matches: List[Dict[str, Any]] = []
    for ev in items:
        status = ev.get("status")
        if status == "cancelled":
            continue
        start = (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date")
        end = (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date")
        matches.append(
            {
                "id": ev.get("id", ""),
                "title": ev.get("summary", ""),
                "start": start,
                "end": end,
                "recurring_event_id": ev.get("recurringEventId"),
                "original_start_time": (ev.get("originalStartTime") or {}).get("dateTime")
                or (ev.get("originalStartTime") or {}).get("date"),
                "recurrence": ev.get("recurrence"),
                "status": status,
            }
        )

    return {"success": True, "data": matches}


async def _resolve_event_id(
    *,
    event_id: str,
    event_title: str,
    date_str: Optional[str],
    time_min: Optional[str],
    time_max: Optional[str],
    timezone_name: str,
) -> Dict[str, Any]:
    if event_id:
        return {"success": True, "data": {"event_id": event_id}}

    if not event_title:
        return {
            "success": False,
            "error": "CLARIFICATION_NEEDED",
            "clarification_needed": True,
            "message": "Which event do you want to modify? Provide the event title and date (YYYY-MM-DD), or provide the event_id.",
        }

    resolved_time_min: Optional[str] = None
    resolved_time_max: Optional[str] = None
    if date_str:
        resolved_time_min, resolved_time_max, err = _date_to_time_window(date_str, timezone_name)
        if err:
            return {
                "success": False,
                "error": "CLARIFICATION_NEEDED",
                "clarification_needed": True,
                "message": err,
            }
    elif time_min and time_max:
        resolved_time_min, resolved_time_max = time_min, time_max
    else:
        return {
            "success": False,
            "error": "CLARIFICATION_NEEDED",
            "clarification_needed": True,
            "message": "Please provide the event date (YYYY-MM-DD) so I can find the correct event, or provide time_min and time_max in ISO format.",
        }

    found = await _calendar_find_events(
        title=event_title,
        time_min=resolved_time_min,
        time_max=resolved_time_max,
        timezone_name=timezone_name,
    )
    if not found.get("success"):
        return found

    matches = found.get("data", []) or []
    if len(matches) == 0:
        return {
            "success": False,
            "error": "NOT_FOUND",
            "message": f"No calendar event found matching '{event_title}' in the specified time window.",
        }

    if len(matches) > 1:
        picked = choose_best_match(
            query_title=event_title,
            date_str=date_str,
            time_min=resolved_time_min,
            time_max=resolved_time_max,
            matches=matches,
        )
        chosen = picked.get("chosen")
        if isinstance(chosen, dict) and chosen.get("id"):
            return {
                "success": True,
                "data": {
                    "event_id": str(chosen.get("id")),
                    "confidence": float(picked.get("confidence") or 0.0),
                },
            }
        options = "\n".join(
            [
                f"- {m.get('title','')} ({m.get('start','')} to {m.get('end','')}) [id: {m.get('id','')}]"
                for m in matches
            ]
        )
        return {
            "success": False,
            "error": "CLARIFICATION_NEEDED",
            "clarification_needed": True,
            "message": f"I found multiple events named '{event_title}'. Which one should I modify?\n{options}",
            "matches": matches,
        }

    return {"success": True, "data": {"event_id": matches[0].get("id", "")}}


async def calendar_get_availability(start_date: str = "", end_date: str = "", **kwargs) -> Dict[str, Any]:
    # Handle alternative parameter names
    if not start_date:
        start_date = kwargs.get("start_time") or kwargs.get("start") or ""
    if not end_date:
        end_date = kwargs.get("end_time") or kwargs.get("end") or ""
    headers = await _calendar_auth_headers()
    if not headers:
        return {"success": False, "error": "AUTH_ERROR", "message": "Unable to authenticate with Google Calendar. Please reauthorize."}
    
    cal_id = _calendar_id()
    url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events"
    
    params = {
        "timeMin": start_date,
        "timeMax": end_date,
        "singleEvents": True,
        "orderBy": "startTime",
    }
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"AVAILABILITY_CHECK_ERROR: {exc!r}"}
    
    data = resp.json()
    events = data.get("items", [])
    
    busy_blocks = []
    for event in events:
        start = event.get("start", {}).get("dateTime")
        end = event.get("end", {}).get("dateTime")
        if start and end:
            busy_blocks.append({
                "start": start,
                "end": end,
                "summary": event.get("summary", "Busy")
            })
    
    return {
        "success": True,
        "data": {
            "busy_blocks": busy_blocks,
            "is_available": len(busy_blocks) == 0
        }
    }


async def calendar_check_slot_available(start_time: str = "", end_time: str = "", **kwargs) -> Dict[str, Any]:
    # Handle alternative parameter names
    if not start_time:
        start_time = kwargs.get("start") or kwargs.get("start_date") or ""
    if not end_time:
        end_time = kwargs.get("end") or kwargs.get("end_date") or ""
    result = await calendar_get_availability(start_time, end_time)
    
    if not result.get("success"):
        return result
    
    busy_blocks = result["data"]["busy_blocks"]
    
    if len(busy_blocks) == 0:
        return {
            "success": True,
            "data": {
                "available": True,
                "message": "This time slot is available."
            }
        }
    
    start_dt = _parse_iso_datetime(start_time)
    end_dt = _parse_iso_datetime(end_time)
    
    conflicts = []
    for block in busy_blocks:
        block_start = _parse_iso_datetime(block["start"])
        block_end = _parse_iso_datetime(block["end"])
        
        if not (end_dt <= block_start or start_dt >= block_end):
            conflicts.append({
                "summary": block["summary"],
                "start": _format_time_readable(block_start),
                "end": _format_time_readable(block_end)
            })
    
    if conflicts:
        conflict_msg = f"This time is unavailable. Saara is busy between {conflicts[0]['start']} and {conflicts[0]['end']}."
        return {
            "success": True,
            "data": {
                "available": False,
                "message": conflict_msg,
                "conflicts": conflicts
            }
        }
    
    return {
        "success": True,
        "data": {
            "available": True,
            "message": "This time slot is available."
        }
    }


async def calendar_find_next_available_slots(
    start_search: str = "",
    duration_minutes: int = 30,
    num_slots: int = 3,
    **kwargs
) -> Dict[str, Any]:
    # Handle alternative parameter names
    if not start_search:
        start_search = kwargs.get("start_time") or kwargs.get("start") or ""
    
    search_start = _parse_iso_datetime(start_search)
    search_end = search_start + timedelta(days=7)
    
    result = await calendar_get_availability(
        search_start.isoformat(),
        search_end.isoformat()
    )
    
    if not result.get("success"):
        return result
    
    busy_blocks = result["data"]["busy_blocks"]
    busy_intervals = []
    for block in busy_blocks:
        busy_intervals.append((
            _parse_iso_datetime(block["start"]),
            _parse_iso_datetime(block["end"])
        ))
    
    busy_intervals.sort(key=lambda x: x[0])
    
    available_slots = []
    current_time = search_start
    
    while len(available_slots) < num_slots and current_time < search_end:
        if current_time.hour < 9:
            current_time = current_time.replace(hour=9, minute=0, second=0, microsecond=0)
        
        if current_time.hour >= 17:
            current_time = (current_time + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
            continue
        
        if current_time.weekday() >= 5:
            current_time = (current_time + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
            continue
        
        slot_end = current_time + timedelta(minutes=duration_minutes)
        
        is_free = True
        for busy_start, busy_end in busy_intervals:
            if not (slot_end <= busy_start or current_time >= busy_end):
                is_free = False
                current_time = busy_end
                break
        
        if is_free:
            available_slots.append({
                "start": current_time.isoformat(),
                "end": slot_end.isoformat(),
                "readable": _format_time_readable(current_time)
            })
            current_time = slot_end
        else:
            current_time += timedelta(minutes=15)
    
    return {
        "success": True,
        "data": {
            "slots": available_slots
        }
    }


async def calendar_create_meet_event(
    title: str = "",
    start_time: str = "",
    end_time: str = "",
    attendees: Optional[List[str]] = None,
    description: Optional[str] = None,
    timezone_name: Optional[str] = None,
    **kwargs,  # Accept extra args for backward compatibility
) -> Dict[str, Any]:
    
    # Handle backward compatibility with different parameter names
    if not title:
        title = kwargs.get("summary", "")
    if not start_time:
        start_time = kwargs.get("start_iso") or kwargs.get("start") or ""
    if not end_time:
        end_time = kwargs.get("end_iso") or kwargs.get("end") or ""
    
    # Auto-generate end_time if not provided (1 hour default)
    if not end_time and start_time:
        from src.services.calendar import _parse_natural_time, _get_timezone_obj, DEFAULT_TIMEZONE as CAL_TZ
        from datetime import timedelta
        tz = _get_timezone_obj(timezone_name or CAL_TZ)
        from datetime import datetime
        now = datetime.now(tz)
        start_dt, _ = _parse_natural_time(start_time, now, timezone_name or CAL_TZ)
        if start_dt:
            end_dt = start_dt + timedelta(hours=1)
            start_time = start_dt.isoformat()
            end_time = end_dt.isoformat()
    
    tz_name = timezone_name or DEFAULT_TIMEZONE
    
    # Validate required fields
    if not title:
        return {"success": False, "error": "VALIDATION_ERROR", "message": "Event title is required."}
    if not start_time:
        return {"success": False, "error": "VALIDATION_ERROR", "message": "Start time is required."}
    if not end_time:
        return {"success": False, "error": "VALIDATION_ERROR", "message": "End time is required."}
    
    headers = await _calendar_auth_headers()
    if not headers:
        return {"success": False, "error": "AUTH_ERROR", "message": "Unable to authenticate with Google Calendar. Please reauthorize."}
    
    cal_id = _calendar_id()
    url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events"
    
    request_id = str(uuid.uuid4())
    
    attendee_list = []
    if attendees:
        for email in attendees:
            attendee_list.append({"email": email})
    
    body: Dict[str, Any] = {
        "summary": title,
        "start": {"dateTime": start_time, "timeZone": tz_name},
        "end": {"dateTime": end_time, "timeZone": tz_name},
        "conferenceData": {
            "createRequest": {
                "requestId": request_id,
                "conferenceSolutionKey": {"type": "hangoutsMeet"}
            }
        },
        "attendees": attendee_list,
        "sendUpdates": "all"
    }
    
    if description:
        body["description"] = description
    
    params = {"conferenceDataVersion": 1}
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=body, params=params)
        resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"CREATE_MEET_ERROR: {exc!r}"}
    
    event_data = resp.json()
    
    event_id = event_data.get("id", "")
    meet_link = _extract_meet_link(event_data)

    if not meet_link and event_id:
        # Google sometimes needs a moment to finalize conference data.
        await asyncio.sleep(0.5)
        refreshed = await _fetch_event_with_conference(event_id, headers)
        if isinstance(refreshed, dict):
            meet_link = _extract_meet_link(refreshed)
    
    start_dt = _parse_iso_datetime(start_time)
    end_dt = _parse_iso_datetime(end_time)

    start_readable = _format_time_readable(start_dt)
    end_readable = _format_time_readable(end_dt)

    if meet_link:
        user_message = f"Scheduled '{title}' from {start_readable} to {end_readable}. Google Meet link: {meet_link}"
    else:
        user_message = (
            f"Scheduled '{title}' from {start_readable} to {end_readable}. "
            "Google Meet did not return a link yet. You can open the event in Google Calendar to generate one manually."
        )
    
    return {
        "success": True,
        "message": user_message,
        "data": {
            "event_id": event_id,
            "meet_link": meet_link,
            "start_time": start_time,
            "end_time": end_time,
            "start_readable": start_readable,
            "end_readable": end_readable,
            "attendees": attendees or [],
            "title": title
        }
    }


async def calendar_reschedule_meeting(
    event_id: str = "",
    new_start_time: str = "",
    new_end_time: str = "",
    event_title: str = "",
    date_str: Optional[str] = None,
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    timezone_name: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    # Handle alternative parameter names
    if not event_id:
        event_id = kwargs.get("id") or ""
    if not new_start_time:
        new_start_time = kwargs.get("start_time") or kwargs.get("start") or ""
    if not new_end_time:
        new_end_time = kwargs.get("end_time") or kwargs.get("end") or ""

    if not event_title:
        event_title = (
            kwargs.get("title")
            or kwargs.get("summary")
            or kwargs.get("event_name")
            or ""
        )
    if date_str is None:
        date_str = kwargs.get("date")
    if time_min is None:
        time_min = kwargs.get("timeMin") or kwargs.get("time_min")
    if time_max is None:
        time_max = kwargs.get("timeMax") or kwargs.get("time_max")

    tz_name = timezone_name or DEFAULT_TIMEZONE

    if event_id and not event_title and (date_str or (time_min and time_max)):
        event_title = event_id
        event_id = ""

    resolved = await _resolve_event_id(
        event_id=event_id,
        event_title=event_title,
        date_str=date_str,
        time_min=time_min,
        time_max=time_max,
        timezone_name=tz_name,
    )
    if not resolved.get("success"):
        return resolved

    event_id = (resolved.get("data") or {}).get("event_id", "")
    
    
    headers = await _calendar_auth_headers()
    if not headers:
        return {"success": False, "error": "AUTH_ERROR", "message": "Unable to authenticate with Google Calendar. Please reauthorize."}
    
    cal_id = _calendar_id()
    url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events/{event_id}"
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            get_resp = await client.get(url, headers=headers)
        get_resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"FETCH_EVENT_ERROR: {exc!r}"}
    
    event_data = get_resp.json()
    
    event_data["start"] = {"dateTime": new_start_time, "timeZone": tz_name}
    event_data["end"] = {"dateTime": new_end_time, "timeZone": tz_name}
    
    params = {"sendUpdates": "all"}
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            update_resp = await client.put(url, headers=headers, json=event_data, params=params)
        update_resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"RESCHEDULE_ERROR: {exc!r}"}
    
    updated_event = update_resp.json()
    
    start_dt = _parse_iso_datetime(new_start_time)
    end_dt = _parse_iso_datetime(new_end_time)
    
    return {
        "success": True,
        "data": {
            "event_id": event_id,
            "new_start": new_start_time,
            "new_end": new_end_time,
            "start_readable": _format_time_readable(start_dt),
            "end_readable": _format_time_readable(end_dt),
            "title": updated_event.get("summary", "")
        }
    }


async def calendar_cancel_meeting(
    event_id: str = "",
    event_title: str = "",
    date_str: Optional[str] = None,
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    timezone_name: Optional[str] = None,
    confirm: bool = False,
    cancel_scope: Optional[str] = None,  # "single" | "series"
    delete: bool = False,
    **kwargs,
) -> Dict[str, Any]:
    tz_name = timezone_name or kwargs.get("timezone") or DEFAULT_TIMEZONE

    # Backward compatibility
    if not event_id:
        event_id = kwargs.get("id") or ""
    if not event_title:
        event_title = (
            kwargs.get("title")
            or kwargs.get("summary")
            or kwargs.get("event_name")
            or kwargs.get("event_title")
            or ""
        )
    if date_str is None:
        date_str = kwargs.get("date")
    if time_min is None:
        time_min = kwargs.get("timeMin") or kwargs.get("time_min")
    if time_max is None:
        time_max = kwargs.get("timeMax") or kwargs.get("time_max")
    if cancel_scope is None:
        cancel_scope = kwargs.get("scope") or kwargs.get("cancel_scope")
    if "confirm" in kwargs and confirm is False:
        try:
            confirm = bool(kwargs.get("confirm"))
        except Exception:
            confirm = False
    if "delete" in kwargs and delete is False:
        try:
            delete = bool(kwargs.get("delete"))
        except Exception:
            delete = False

    # If callers mistakenly put title into event_id, treat it as a title only when a time window is provided.
    if event_id and not event_title and (date_str or (time_min and time_max)):
        event_title = event_id
        event_id = ""

    headers = await _calendar_auth_headers()
    if not headers:
        return {
            "success": True,
            "cancelled": False,
            "message": "I can't access your Google Calendar right now. Please reauthorize and try again.",
        }

    cal_id = _calendar_id()

    # Resolve target event
    chosen: Optional[Dict[str, Any]] = None
    confidence: float = 0.0

    if event_id:
        url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events/{event_id}"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(url, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = (exc.response.text or "").strip()
            detail = body[:800] if body else ""
            logger.warning(
                "Calendar cancel GET failed: status=%s event_id=%s body=%s",
                exc.response.status_code,
                event_id,
                detail,
            )
            if exc.response.status_code in (404, 410):
                return {
                    "success": True,
                    "cancelled": True,
                    "message": "That event appears to have already been cancelled or deleted.",
                    "data": {"event_id": event_id},
                }
            return {
                "success": False,
                "error": f"GOOGLE_CALENDAR_HTTP_{exc.response.status_code}",
                "detail": detail,
                "cancelled": False,
                "message": "I couldn't fetch that event to cancel (Google Calendar rejected the request).",
            }
        except Exception as exc:
            logger.warning("Calendar cancel GET failed: event_id=%s err=%r", event_id, exc)
            return {
                "success": False,
                "error": "GOOGLE_CALENDAR_REQUEST_FAILED",
                "detail": repr(exc),
                "cancelled": False,
                "message": "I couldn't fetch that event to cancel (request failed).",
            }

        ev = resp.json()
        chosen = {
            "id": ev.get("id", ""),
            "title": ev.get("summary", ""),
            "start": (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date"),
            "end": (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date"),
            "recurring_event_id": ev.get("recurringEventId"),
            "original_start_time": (ev.get("originalStartTime") or {}).get("dateTime")
            or (ev.get("originalStartTime") or {}).get("date"),
            "recurrence": ev.get("recurrence"),
            "status": ev.get("status"),
        }
        confidence = 1.0
    else:
        if not event_title:
            return {
                "success": True,
                "cancelled": False,
                "message": "Which event should I cancel? Tell me the event title and the date (YYYY-MM-DD).",
            }

        resolved_time_min: Optional[str] = None
        resolved_time_max: Optional[str] = None
        if date_str:
            resolved_time_min, resolved_time_max, err = _date_to_time_window(date_str, tz_name)
            if err:
                return {"success": True, "cancelled": False, "message": err}
        elif time_min and time_max:
            resolved_time_min, resolved_time_max = time_min, time_max
        else:
            return {
                "success": True,
                "cancelled": False,
                "message": "Please provide the event date (YYYY-MM-DD) so I can find the correct event to cancel.",
            }

        found = await _calendar_find_events(
            title=event_title,
            time_min=resolved_time_min,
            time_max=resolved_time_max,
            timezone_name=tz_name,
        )
        if not found.get("success"):
            return {
                "success": True,
                "cancelled": False,
                "message": "I couldn't search your calendar right now. Please try again.",
            }

        matches = found.get("data", []) or []
        if len(matches) == 0:
            return {
                "success": True,
                "cancelled": False,
                "message": f"I couldn't find any event titled '{event_title}' in that time window.",
            }

        if len(matches) > 1:
            picked = choose_best_match(
                query_title=event_title,
                date_str=date_str,
                time_min=resolved_time_min,
                time_max=resolved_time_max,
                matches=matches,
            )
            auto = picked.get("chosen")
            if isinstance(auto, dict) and auto.get("id"):
                chosen = auto
                confidence = float(picked.get("confidence") or 0.0)
            else:
                lines: List[str] = []
                for idx, m in enumerate(matches, start=1):
                    start_dt = _parse_iso_datetime(m.get("start") or "")
                    start_readable = _format_time_readable(start_dt)
                    lines.append(f"{idx}) {m.get('title','(no title)')} at {start_readable}")
                return {
                    "success": True,
                    "cancelled": False,
                    "selection_required": True,
                    "options": matches,
                    "message": "I found multiple matching events. Reply with the number of the one you want to cancel:\n" + "\n".join(lines),
                }

        if chosen is None:
            chosen = matches[0]
        if confidence <= 0.0:
            confidence = 0.9

    if not chosen:
        return {"success": True, "cancelled": False, "message": "I couldn't find an event to cancel."}

    # Idempotency: if the event is already cancelled, treat as success.
    # (Avoid refusing due to 'past event' checks and avoid making a redundant PATCH.)
    if chosen.get("status") == "cancelled" and cancel_scope != "series":
        return {
            "success": True,
            "cancelled": True,
            "message": f"'{chosen.get('title','(no title)')}' is already cancelled.",
            "data": {"event_id": chosen.get("id", "")},
        }

    # Refuse cancelling past events
    now_dt = datetime.now(tz=_get_timezone_obj(tz_name))
    chosen_start = _parse_iso_datetime(chosen.get("start") or "")
    if chosen_start <= now_dt:
        start_readable = _format_time_readable(chosen_start)
        return {
            "success": True,
            "cancelled": False,
            "message": f"I can't cancel past events. '{chosen.get('title','(no title)')}' started at {start_readable}.",
        }

    # Recurring events: default to single occurrence unless explicitly requested.
    is_recurring = bool(chosen.get("recurring_event_id") or chosen.get("recurrence"))
    if is_recurring and cancel_scope not in ("single", "series"):
        cancel_scope = "single"

    # Confirmation required (only when high-risk or low-confidence).
    start_readable = _format_time_readable(chosen_start)
    risk = RiskLevel.MEDIUM
    if delete:
        risk = RiskLevel.HIGH
    if cancel_scope == "series":
        risk = RiskLevel.HIGH

    if not confirm:
        needs_confirm = decide_requires_confirmation(
            domain="calendar",
            action="calendar_cancel",
            risk=risk,
            confidence=confidence,
        )
        if not needs_confirm:
            confirm = True
        else:
            return {
                "success": True,
                "cancelled": False,
                "confirmation_required": True,
                "data": {
                    "event_id": chosen.get("id"),
                    "event_title": chosen.get("title"),
                    "start": chosen.get("start"),
                    "recurring_event_id": chosen.get("recurring_event_id"),
                    "cancel_scope": cancel_scope or ("single" if not is_recurring else None),
                    "delete": delete,
                    "confidence": confidence,
                },
                "message": f"Do you want me to cancel '{chosen.get('title','(no title)')}' scheduled for {start_readable}?",
            }

    # Execute cancel
    target_id = chosen.get("id", "")
    if cancel_scope == "series" and chosen.get("recurring_event_id"):
        target_id = chosen.get("recurring_event_id")

    if delete:
        url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events/{target_id}"
        params = {"sendUpdates": "all"}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.delete(url, headers=headers, params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = (exc.response.text or "").strip()
            detail = body[:800] if body else ""
            logger.warning(
                "Calendar delete failed: status=%s event_id=%s body=%s",
                exc.response.status_code,
                target_id,
                detail,
            )
            if exc.response.status_code in (404, 410):
                return {
                    "success": True,
                    "cancelled": True,
                    "message": "That event appears to have already been deleted.",
                    "data": {"event_id": target_id},
                }
            return {
                "success": False,
                "error": f"GOOGLE_CALENDAR_HTTP_{exc.response.status_code}",
                "detail": detail,
                "cancelled": False,
                "message": "I couldn't delete that event (Google Calendar rejected the request).",
            }
        except Exception as exc:
            return {
                "success": False,
                "error": "GOOGLE_CALENDAR_REQUEST_FAILED",
                "detail": repr(exc),
                "cancelled": False,
                "message": "I couldn't delete that event (request failed).",
            }
    else:
        url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events/{target_id}"
        params = {"sendUpdates": "all"}
        payload = {"status": "cancelled"}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.patch(url, headers=headers, json=payload, params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = (exc.response.text or "").strip()
            detail = body[:800] if body else ""
            logger.warning(
                "Calendar cancel PATCH failed: status=%s event_id=%s body=%s",
                exc.response.status_code,
                target_id,
                detail,
            )
            if exc.response.status_code in (404, 410):
                return {
                    "success": True,
                    "cancelled": True,
                    "message": "That event appears to have already been cancelled or deleted.",
                    "data": {"event_id": target_id},
                }
            return {
                "success": False,
                "error": f"GOOGLE_CALENDAR_HTTP_{exc.response.status_code}",
                "detail": detail,
                "cancelled": False,
                "message": "I couldn't cancel that event (Google Calendar rejected the request).",
            }
        except Exception as exc:
            return {
                "success": False,
                "error": "GOOGLE_CALENDAR_REQUEST_FAILED",
                "detail": repr(exc),
                "cancelled": False,
                "message": "I couldn't cancel that event (request failed).",
            }

    return {
        "success": True,
        "cancelled": True,
        "message": f"Cancelled '{chosen.get('title','(no title)')}' scheduled for {start_readable}.",
        "data": {"event_id": target_id},
    }


async def calendar_update_attendees(
    event_id: str = "",
    attendees: List[str] = None,
    event_title: str = "",
    date_str: Optional[str] = None,
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    timezone_name: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    # Handle alternative parameter names
    if not event_id:
        event_id = kwargs.get("id") or ""
    if attendees is None:
        attendees = kwargs.get("emails") or []

    attendees = [a.strip() for a in (attendees or []) if isinstance(a, str) and a.strip()]
    if not attendees:
        return {
            "success": False,
            "error": "MISSING_ATTENDEES",
            "message": "Please provide at least one attendee email address.",
        }

    invalid = [a for a in attendees if not _EMAIL_RE.match(a)]
    if invalid:
        return {
            "success": False,
            "error": "INVALID_ATTENDEE_EMAIL",
            "clarification_needed": True,
            "message": "Attendees must be valid email addresses (e.g. name@example.com).",
            "invalid": invalid,
        }

    if not event_title:
        event_title = (
            kwargs.get("title")
            or kwargs.get("summary")
            or kwargs.get("event_name")
            or ""
        )
    if date_str is None:
        date_str = kwargs.get("date")
    if time_min is None:
        time_min = kwargs.get("timeMin") or kwargs.get("time_min")
    if time_max is None:
        time_max = kwargs.get("timeMax") or kwargs.get("time_max")

    tz_name = timezone_name or DEFAULT_TIMEZONE

    if event_id and not event_title and (date_str or (time_min and time_max)):
        event_title = event_id
        event_id = ""

    resolved = await _resolve_event_id(
        event_id=event_id,
        event_title=event_title,
        date_str=date_str,
        time_min=time_min,
        time_max=time_max,
        timezone_name=tz_name,
    )
    if not resolved.get("success"):
        return resolved

    event_id = (resolved.get("data") or {}).get("event_id", "")
    
    headers = await _calendar_auth_headers()
    if not headers:
        return {"success": False, "error": "AUTH_ERROR", "message": "Unable to authenticate with Google Calendar. Please reauthorize."}
    
    cal_id = _calendar_id()
    url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events/{event_id}"
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            get_resp = await client.get(url, headers=headers)
        get_resp.raise_for_status()
    except Exception as exc:
        return {"success": False, "error": f"FETCH_EVENT_ERROR: {exc!r}"}
    
    event_data = get_resp.json()
    
    attendee_list = []
    for email in attendees:
        attendee_list.append({"email": email})

    params = {"sendUpdates": "all"}
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            update_resp = await client.patch(url, headers=headers, json={"attendees": attendee_list}, params=params)
        update_resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = (exc.response.text or "").strip()
        detail = body[:800] if body else ""
        return {
            "success": False,
            "error": "UPDATE_ATTENDEES_ERROR",
            "detail": detail,
            "message": "Google Calendar rejected the attendee update.",
        }
    except Exception as exc:
        return {
            "success": False,
            "error": "UPDATE_ATTENDEES_ERROR",
            "detail": repr(exc),
            "message": "I couldn't update attendees (request failed).",
        }
    
    return {"success": True, "message": "Attendees updated successfully.", "data": {"event_id": event_id, "attendees": attendees}}


async def calendar_add_note_to_meeting(
    note: str = "",
    event_id: str = "",
    event_title: str = "",
    date_str: Optional[str] = None,
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    timezone_name: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    if not note:
        note = kwargs.get("text") or kwargs.get("content") or ""
    note = (note or "").strip()

    tz_name = timezone_name or DEFAULT_TIMEZONE

    if not event_id:
        event_id = kwargs.get("id") or ""
    if not event_title:
        event_title = (
            kwargs.get("title")
            or kwargs.get("summary")
            or kwargs.get("event_name")
            or ""
        )
    if date_str is None:
        date_str = kwargs.get("date")
    if time_min is None:
        time_min = kwargs.get("timeMin") or kwargs.get("time_min")
    if time_max is None:
        time_max = kwargs.get("timeMax") or kwargs.get("time_max")

    if event_id and not event_title and (date_str or (time_min and time_max)):
        event_title = event_id
        event_id = ""

    resolved = await _resolve_event_id(
        event_id=event_id,
        event_title=event_title,
        date_str=date_str,
        time_min=time_min,
        time_max=time_max,
        timezone_name=tz_name,
    )

    if not resolved.get("success"):
        if resolved.get("clarification_needed") and isinstance(resolved.get("matches"), list) and resolved.get("matches"):
            matches = resolved.get("matches") or []
            safe_opts: List[Dict[str, Any]] = []
            lines: List[str] = []
            for idx, m in enumerate(matches, start=1):
                if isinstance(m, dict) and m.get("id"):
                    safe_opts.append({
                        "id": str(m.get("id")),
                        "title": m.get("title") or m.get("summary") or "",
                        "start": m.get("start"),
                        "end": m.get("end"),
                    })
                    start_dt = _parse_iso_datetime(m.get("start") or "")
                    start_readable = _format_time_readable(start_dt)
                    lines.append(f"{idx}) {m.get('title','(no title)')} at {start_readable}")

            if safe_opts:
                msg = "I found multiple matching events. Reply with the number of the one you want to add a note to:\n" + "\n".join(lines)
                data: Dict[str, Any] = {"note": note} if note else {}
                return {
                    "success": True,
                    "selection_required": True,
                    "options": safe_opts,
                    "data": data,
                    "message": msg,
                }

        msg = resolved.get("message") or "Which meeting should I add a note to? Provide the event title and date (YYYY-MM-DD), or provide the event_id."
        if note:
            msg = f"{msg}\n\nPlease resend the note after choosing the meeting."
        return {"success": True, "note_required": False, "message": msg}

    event_id = (resolved.get("data") or {}).get("event_id", "")
    if not event_id:
        return {"success": True, "note_required": False, "message": "Which meeting should I add a note to?"}

    if not note:
        return {
            "success": True,
            "note_required": True,
            "data": {"event_id": event_id},
            "message": "What note should I add to the meeting?",
        }
    headers = await _calendar_auth_headers()
    if not headers:
        return {"success": False, "error": "AUTH_ERROR", "message": "Unable to authenticate with Google Calendar. Please reauthorize."}

    cal_id = _calendar_id()
    url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events/{event_id}"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            get_resp = await client.get(url, headers=headers)
        get_resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (404, 410):
            return {"success": False, "error": "NOT_FOUND", "message": "I couldn't find that meeting to add a note."}
        return {"success": False, "error": f"GOOGLE_CALENDAR_HTTP_{exc.response.status_code}", "message": "I couldn't fetch that meeting to add a note."}
    except Exception as exc:
        return {"success": False, "error": "GOOGLE_CALENDAR_REQUEST_FAILED", "detail": repr(exc), "message": "I couldn't fetch that meeting to add a note."}

    event_data = get_resp.json()
    existing_desc = (event_data.get("description") or "").strip()
    new_desc = f"{existing_desc}\n\n{note}".strip() if existing_desc else note

    params = {"sendUpdates": "all"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            patch_resp = await client.patch(url, headers=headers, json={"description": new_desc}, params=params)
        patch_resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = (exc.response.text or "").strip()
        detail = body[:800] if body else ""
        return {
            "success": False,
            "error": "ADD_NOTE_ERROR",
            "detail": detail,
            "message": "Google Calendar rejected the note update.",
        }
    except Exception as exc:
        return {
            "success": False,
            "error": "ADD_NOTE_ERROR",
            "detail": repr(exc),
            "message": "I couldn't add the note (request failed).",
        }

    return {"success": True, "message": "Note added to the meeting.", "data": {"event_id": event_id}}
