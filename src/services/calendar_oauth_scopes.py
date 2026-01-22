"""Calendar OAuth scope validation and management for Jarvis AI Agent.

This module validates that the Google OAuth token has all required scopes
for Google Calendar operations, including Meet-enabled event creation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

import httpx


logger = logging.getLogger("jarvis.calendar_oauth_scopes")


@dataclass
class CalendarScopeRequirements:
    """Required Calendar OAuth scopes."""

    EVENTS_SCOPES: List[str] = None
    ALL_SCOPES: List[str] = None

    def __post_init__(self) -> None:
        self.EVENTS_SCOPES = [
            "https://www.googleapis.com/auth/calendar.events",
        ]
        self.ALL_SCOPES = list(self.EVENTS_SCOPES)


SCOPE_REQUIREMENTS = CalendarScopeRequirements()

_validated_scopes_by_token: Dict[str, Set[str]] = {}
_validation_failed_tokens: Set[str] = set()


async def get_token_scopes(access_token: str) -> Optional[Set[str]]:
    url = f"https://www.googleapis.com/oauth2/v1/tokeninfo?access_token={access_token}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)

        if resp.status_code != 200:
            logger.error("Token validation failed with status %s: %s", resp.status_code, resp.text)
            return None

        data = resp.json()
        scope_string = data.get("scope", "")
        scopes = set(scope_string.split())
        return scopes
    except Exception as exc:  # noqa: BLE001
        logger.error("Error validating token scopes: %r", exc)
        return None


async def validate_calendar_scopes(access_token: str) -> Dict[str, Any]:  # type: ignore[name-defined]
    global _validated_scopes_by_token, _validation_failed_tokens

    if access_token in _validated_scopes_by_token:
        return _build_validation_result(_validated_scopes_by_token[access_token])

    if access_token in _validation_failed_tokens:
        return {
            "valid": False,
            "missing_scopes": SCOPE_REQUIREMENTS.ALL_SCOPES,
            "message": "Scope validation previously failed for this token. Check logs for details.",
        }

    token_scopes = await get_token_scopes(access_token)
    if token_scopes is None:
        _validation_failed_tokens.add(access_token)
        return {
            "valid": False,
            "missing_scopes": SCOPE_REQUIREMENTS.ALL_SCOPES,
            "message": "Failed to validate token scopes with Google OAuth API",
        }

    _validated_scopes_by_token[access_token] = token_scopes
    return _build_validation_result(token_scopes)


def _build_validation_result(token_scopes: Set[str]) -> Dict[str, Any]:  # type: ignore[name-defined]
    required = set(SCOPE_REQUIREMENTS.ALL_SCOPES)
    missing = sorted(list(required - token_scopes))
    valid = len(missing) == 0

    if valid:
        message = "All required Calendar scopes are present"
    else:
        message = "Calendar access requires re-authorization. Missing scope: calendar.events"

    return {
        "valid": valid,
        "missing_scopes": missing,
        "message": message,
    }


def clear_scope_cache() -> None:
    global _validated_scopes_by_token, _validation_failed_tokens
    _validated_scopes_by_token = {}
    _validation_failed_tokens = set()


def get_reauth_instructions() -> str:
    return """
Calendar Re-Authorization Required
=================================

Your Calendar integration needs additional permissions to create events (and generate Google Meet links).

Required OAuth Scope:
  ✗ https://www.googleapis.com/auth/calendar.events (MISSING)

Steps to Re-Authorize:
1. Update your OAuth consent screen / client configuration to include:
   https://www.googleapis.com/auth/calendar.events
2. Re-run your OAuth authorization flow to get a new refresh token
3. Update GOOGLE_REFRESH_TOKEN in your .env file
4. Restart Jarvis

Until re-authorization:
  ✗ Creating Calendar events may fail
  ✗ Generating Meet links will fail

For help: https://developers.google.com/calendar/api/auth
"""
