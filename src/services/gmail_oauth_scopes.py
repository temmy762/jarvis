"""Gmail OAuth scope validation and management for Jarvis AI Agent.

This module validates that the Gmail OAuth token has all required scopes
for email operations and filter management.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass

import httpx


logger = logging.getLogger("jarvis.gmail_oauth_scopes")


@dataclass
class GmailScopeRequirements:
    """Required Gmail OAuth scopes for different operation categories."""
    
    # Core email operations (read, send, modify labels)
    CORE_SCOPES: List[str] = None
    
    # Filter and settings management
    SETTINGS_SCOPES: List[str] = None
    
    # All required scopes combined
    ALL_SCOPES: List[str] = None
    
    def __post_init__(self):
        self.CORE_SCOPES = [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.modify",
        ]
        
        self.SETTINGS_SCOPES = [
            "https://www.googleapis.com/auth/gmail.settings.basic",
        ]
        
        self.ALL_SCOPES = self.CORE_SCOPES + self.SETTINGS_SCOPES


# Global singleton
SCOPE_REQUIREMENTS = GmailScopeRequirements()


# Cache for validated scopes (avoid repeated API calls)
# Keyed by access_token so new tokens (e.g., after re-authorization) are re-validated.
_validated_scopes_by_token: Dict[str, Set[str]] = {}
_validation_failed_tokens: Set[str] = set()


async def get_token_scopes(access_token: str) -> Optional[Set[str]]:
    """Query Google OAuth2 API to get the scopes for a given access token.
    
    Args:
        access_token: The Google OAuth access token to validate
        
    Returns:
        Set of scope URLs if successful, None if validation fails
    """
    url = f"https://www.googleapis.com/oauth2/v1/tokeninfo?access_token={access_token}"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
        
        if resp.status_code != 200:
            logger.error(
                f"Token validation failed with status {resp.status_code}: {resp.text}"
            )
            return None
        
        data = resp.json()
        scope_string = data.get("scope", "")
        
        # Google returns scopes as space-separated string
        scopes = set(scope_string.split())
        
        logger.info(f"Token has {len(scopes)} scopes: {', '.join(sorted(scopes))}")
        return scopes
        
    except Exception as exc:
        logger.error(f"Error validating token scopes: {exc!r}")
        return None


async def validate_gmail_scopes(access_token: str) -> Dict[str, any]:
    """Validate that the access token has all required Gmail scopes.
    
    Args:
        access_token: The Google OAuth access token to validate
        
    Returns:
        Dict with validation results:
        {
            "valid": bool,
            "has_core": bool,
            "has_settings": bool,
            "missing_scopes": List[str],
            "message": str
        }
    """
    global _validated_scopes_by_token, _validation_failed_tokens

    if access_token in _validated_scopes_by_token:
        return _build_validation_result(_validated_scopes_by_token[access_token])

    if access_token in _validation_failed_tokens:
        return {
            "valid": False,
            "has_core": False,
            "has_settings": False,
            "missing_scopes": SCOPE_REQUIREMENTS.ALL_SCOPES,
            "message": "Scope validation previously failed for this token. Check logs for details.",
        }
    
    token_scopes = await get_token_scopes(access_token)
    
    if token_scopes is None:
        logger.error("Could not retrieve token scopes from Google OAuth API")
        _validation_failed_tokens.add(access_token)
        return {
            "valid": False,
            "has_core": False,
            "has_settings": False,
            "missing_scopes": SCOPE_REQUIREMENTS.ALL_SCOPES,
            "message": "Failed to validate token scopes with Google OAuth API"
        }

    _validated_scopes_by_token[access_token] = token_scopes
    
    return _build_validation_result(token_scopes)


def _build_validation_result(token_scopes: Set[str]) -> Dict[str, any]:
    """Build validation result from token scopes."""
    
    required_core = set(SCOPE_REQUIREMENTS.CORE_SCOPES)
    required_settings = set(SCOPE_REQUIREMENTS.SETTINGS_SCOPES)
    
    has_core = required_core.issubset(token_scopes)
    has_settings = required_settings.issubset(token_scopes)
    
    missing = []
    if not has_core:
        missing.extend(required_core - token_scopes)
    if not has_settings:
        missing.extend(required_settings - token_scopes)
    
    valid = has_core and has_settings
    
    if valid:
        message = "All required Gmail scopes are present"
    elif has_core and not has_settings:
        message = (
            "Gmail filter management requires re-authorization. "
            "Missing scope: gmail.settings.basic"
        )
    elif not has_core:
        message = (
            "Gmail access requires re-authorization. "
            f"Missing core scopes: {', '.join(missing)}"
        )
    else:
        message = f"Missing required scopes: {', '.join(missing)}"
    
    return {
        "valid": valid,
        "has_core": has_core,
        "has_settings": has_settings,
        "missing_scopes": missing,
        "message": message
    }


def clear_scope_cache() -> None:
    """Clear the cached scope validation result.
    
    Call this after re-authorization to force re-validation.
    """
    global _validated_scopes_by_token, _validation_failed_tokens
    _validated_scopes_by_token = {}
    _validation_failed_tokens = set()
    logger.info("Gmail scope cache cleared")


def get_reauth_instructions() -> str:
    """Return human-readable instructions for re-authorizing Gmail.
    
    Returns:
        Formatted string with re-authorization steps
    """
    return """
Gmail Re-Authorization Required
================================

Your Gmail integration needs additional permissions to manage filters and settings.

Required OAuth Scopes:
  ✓ gmail.readonly       - Read emails
  ✓ gmail.send           - Send emails  
  ✓ gmail.modify         - Modify labels
  ✗ gmail.settings.basic - Manage filters (MISSING)

Steps to Re-Authorize:
1. Go to Google Cloud Console → APIs & Services → OAuth consent screen
2. Add scope: https://www.googleapis.com/auth/gmail.settings.basic
3. Re-run your OAuth authorization flow to get a new refresh token
4. Update GOOGLE_REFRESH_TOKEN in your .env file
5. Restart Jarvis

Until re-authorization:
  ✓ Reading emails will work
  ✓ Sending emails will work
  ✓ Labeling emails will work
  ✗ Creating filters will fail

For help: https://developers.google.com/gmail/api/auth/scopes
"""
