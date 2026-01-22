"""Shared Google OAuth helpers for Gmail and Calendar tools.

This module centralizes the logic for refreshing Google access tokens using a
long-lived refresh token, and validates that tokens have required scopes.
"""

from __future__ import annotations

from typing import Optional

import logging
import os
import time

import httpx


logger = logging.getLogger("jarvis.google_oauth")

_cached_access_token: Optional[str] = None
_cached_access_token_expires_at: float = 0.0
_scope_validation_token: Optional[str] = None


async def get_google_access_token(force_refresh: bool = False) -> Optional[str]:
    """Return a fresh Google OAuth access token.

    This is the SINGLE token manager for ALL Google services (Gmail, Calendar, Meet).
    All services share the same OAuth token.

    Prefers an explicit GOOGLE_ACCESS_TOKEN env var if present; otherwise it
    uses the standard refresh-token flow against https://oauth2.googleapis.com/token
    with GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN.
    
    Args:
        force_refresh: If True, ignores cached token and fetches a new one.
    """

    # If the user has manually provided an access token, just use it.
    explicit = os.getenv("GOOGLE_ACCESS_TOKEN")
    if explicit:
        return explicit

    global _cached_access_token, _cached_access_token_expires_at
    
    # Return cached token if valid and not forcing refresh
    if not force_refresh and _cached_access_token and time.time() < _cached_access_token_expires_at:
        return _cached_access_token
    
    # If forcing refresh, clear cache first
    if force_refresh:
        _cached_access_token = None
        _cached_access_token_expires_at = 0.0
        logger.info("Forcing token refresh...")

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")

    if not client_id or not client_secret or not refresh_token:
        logger.error(
            "Missing GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN; "
            "cannot refresh Google access token.",
        )
        return None

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    # Use a slightly longer timeout and a simple retry loop to be more
    # resilient to transient network issues.
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            last_exc: Exception | None = None
            for _attempt in range(2):
                try:
                    resp = await client.post(
                        "https://oauth2.googleapis.com/token",
                        data=data,
                    )
                    resp.raise_for_status()
                    break
                except httpx.RequestError as exc:  # network / protocol error
                    last_exc = exc
                    logger.warning(
                        "Transient error refreshing Google access token: %r",
                        exc,
                    )
                except httpx.HTTPStatusError as exc:
                    logger.error(
                        "Google token endpoint returned %s: %s",
                        exc.response.status_code,
                        exc.response.text,
                    )
                    return None
            else:
                # All attempts failed with RequestError.
                logger.error(
                    "Error refreshing Google access token after retries: %r",
                    last_exc,
                )
                return None
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error refreshing Google access token: %r", exc)
        return None

    payload = resp.json()
    token = payload.get("access_token")
    if not token:
        logger.error("Token endpoint response missing access_token: %r", payload)
        return None

    expires_in = payload.get("expires_in")
    try:
        expires_in_int = int(expires_in) if expires_in is not None else 3600
    except Exception:
        expires_in_int = 3600

    _cached_access_token = token
    _cached_access_token_expires_at = time.time() + max(0, expires_in_int - 60)

    await _validate_gmail_scopes_once(token)

    return token


async def _validate_gmail_scopes_once(access_token: str) -> None:
    """Validate Gmail scopes once per session and log warnings if missing.
    
    This runs asynchronously in the background to avoid blocking token refresh.
    """
    global _scope_validation_token

    if _scope_validation_token == access_token:
        return

    _scope_validation_token = access_token
    
    try:
        from src.services.gmail_oauth_scopes import validate_gmail_scopes, get_reauth_instructions
        
        validation = await validate_gmail_scopes(access_token)
        
        if validation["valid"]:
            logger.info("✓ Gmail OAuth token has all required scopes")
            return
        
        # Log warnings based on what's missing
        if not validation["has_core"]:
            logger.error(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "CRITICAL: Gmail core scopes missing!\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{validation['message']}\n"
                f"Missing: {', '.join(validation['missing_scopes'])}\n"
                "Gmail operations will FAIL until re-authorization.\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
        elif not validation["has_settings"]:
            logger.warning(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Gmail filter management requires re-authorization\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{validation['message']}\n\n"
                "Current capabilities:\n"
                "  ✓ Read emails\n"
                "  ✓ Send emails\n"
                "  ✓ Modify labels\n"
                "  ✗ Create/manage filters (requires gmail.settings.basic)\n\n"
                f"{get_reauth_instructions()}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
        
    except Exception as exc:
        logger.error(f"Error validating Gmail scopes: {exc!r}")
