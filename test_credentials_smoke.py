import asyncio
import os
import sys
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv


def _present(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def _mask(value: Optional[str]) -> str:
    if not value or not value.strip():
        return "<missing>"
    return "<set>"


async def _test_openai() -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"ok": False, "reason": "OPENAI_API_KEY missing"}

    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=api_key)
        models = client.models.list()
        _ = getattr(models, "data", None)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "reason": f"OpenAI call failed: {type(exc).__name__}"}


async def _test_telegram() -> Dict[str, Any]:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return {"ok": False, "reason": "TELEGRAM_BOT_TOKEN missing"}

    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            return {"ok": False, "reason": "Telegram returned ok=false"}
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "reason": f"Telegram call failed: {type(exc).__name__}"}


async def _test_trello() -> Dict[str, Any]:
    key = os.getenv("TRELLO_API_KEY")
    token = os.getenv("TRELLO_API_TOKEN")
    if not key or not token:
        return {"ok": False, "reason": "TRELLO_API_KEY/TRELLO_API_TOKEN missing"}

    url = "https://api.trello.com/1/members/me"
    params = {"key": key, "token": token}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or not data.get("id"):
            return {"ok": False, "reason": "Unexpected Trello response"}
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "reason": f"Trello call failed: {type(exc).__name__}"}


async def _test_supabase() -> Dict[str, Any]:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        return {"ok": False, "reason": "SUPABASE_URL + (SERVICE_ROLE_KEY or ANON_KEY) missing"}

    try:
        from supabase import create_client  # type: ignore

        client = create_client(url, key)
        result = client.table("conversation_messages").select("id").limit(1).execute()
        _ = getattr(result, "data", None)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "reason": f"Supabase call failed: {type(exc).__name__}"}


async def _test_google_oauth() -> Dict[str, Any]:
    explicit = os.getenv("GOOGLE_ACCESS_TOKEN")
    cid = os.getenv("GOOGLE_CLIENT_ID")
    csec = os.getenv("GOOGLE_CLIENT_SECRET")
    rtoken = os.getenv("GOOGLE_REFRESH_TOKEN")

    if not explicit and not (cid and csec and rtoken):
        return {"ok": False, "reason": "Google OAuth not configured"}

    try:
        from src.services.google_oauth import get_google_access_token

        token = await get_google_access_token(force_refresh=True)
        if not token:
            return {"ok": False, "reason": "Failed to obtain Google access token"}
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "reason": f"Google OAuth failed: {type(exc).__name__}"}


async def _test_gmail() -> Dict[str, Any]:
    token = os.getenv("GMAIL_API_TOKEN")
    if not token:
        token = None
        try:
            from src.services.google_oauth import get_google_access_token

            token = await get_google_access_token()
        except Exception:
            token = None

    if not token:
        return {"ok": False, "reason": "No Gmail token available"}

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        url = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or not data.get("emailAddress"):
            return {"ok": False, "reason": "Unexpected Gmail response"}
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "reason": f"Gmail call failed: {type(exc).__name__}"}


async def _test_calendar() -> Dict[str, Any]:
    token = None
    try:
        from src.services.google_oauth import get_google_access_token

        token = await get_google_access_token()
    except Exception:
        token = None

    if not token:
        return {"ok": False, "reason": "No Google token available for Calendar"}

    cal_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or not data.get("id"):
            return {"ok": False, "reason": "Unexpected Calendar response"}
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "reason": f"Calendar call failed: {type(exc).__name__}"}


async def main() -> int:
    load_dotenv()

    sys.path.insert(0, "src")

    checks = [
        ("OpenAI", _test_openai),
        ("Telegram", _test_telegram),
        ("Trello", _test_trello),
        ("Supabase", _test_supabase),
        ("Google OAuth", _test_google_oauth),
        ("Gmail", _test_gmail),
        ("Google Calendar", _test_calendar),
    ]

    print("=" * 60)
    print("CREDENTIAL SMOKE TEST (no secrets printed)")
    print("=" * 60)

    presence = {
        "OPENAI_API_KEY": _mask(os.getenv("OPENAI_API_KEY")),
        "TELEGRAM_BOT_TOKEN": _mask(os.getenv("TELEGRAM_BOT_TOKEN")),
        "TRELLO_API_KEY": _mask(os.getenv("TRELLO_API_KEY")),
        "TRELLO_API_TOKEN": _mask(os.getenv("TRELLO_API_TOKEN")),
        "SUPABASE_URL": _mask(os.getenv("SUPABASE_URL")),
        "SUPABASE_SERVICE_ROLE_KEY": _mask(os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
        "SUPABASE_ANON_KEY": _mask(os.getenv("SUPABASE_ANON_KEY")),
        "GOOGLE_CLIENT_ID": _mask(os.getenv("GOOGLE_CLIENT_ID")),
        "GOOGLE_CLIENT_SECRET": _mask(os.getenv("GOOGLE_CLIENT_SECRET")),
        "GOOGLE_REFRESH_TOKEN": _mask(os.getenv("GOOGLE_REFRESH_TOKEN")),
        "GOOGLE_ACCESS_TOKEN": _mask(os.getenv("GOOGLE_ACCESS_TOKEN")),
        "GMAIL_API_TOKEN": _mask(os.getenv("GMAIL_API_TOKEN")),
        "GOOGLE_CALENDAR_ID": os.getenv("GOOGLE_CALENDAR_ID", "primary"),
    }

    print("\nENV presence (masked):")
    for k in sorted(presence.keys()):
        print(f"- {k} = {presence[k]}")

    print("\nAPI checks:")
    ok_all = True
    for label, fn in checks:
        result = await fn()
        ok = bool(result.get("ok"))
        ok_all = ok_all and ok
        if ok:
            print(f"- {label}: OK")
        else:
            print(f"- {label}: FAIL ({result.get('reason', 'unknown')})")

    print("\n" + ("OK" if ok_all else "FAILED") + ": credential smoke test")
    return 0 if ok_all else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
