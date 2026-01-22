"""Main entrypoint for the Jarvis AI Agent FastAPI application.

This module initializes the FastAPI app and exposes basic health and webhook endpoints.
TODO: Wire up Telegram webhook handling and core agent loop in later phases.
"""

import os
import secrets
from urllib.parse import urlencode

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse

import httpx

from src.services.telegram import handle_telegram_update
from src.utils.logger import generate_request_id
from src.utils.logger import log_error
from src.utils.logger import log_info


load_dotenv()

app = FastAPI(title="Jarvis AI Agent", version="0.1.0")

_OAUTH_STATE_CACHE: set[str] = set()


def _require_setup_token(request: Request) -> bool:
    required = os.getenv("OAUTH_SETUP_TOKEN")
    if not required:
        return True
    provided = request.query_params.get("setup_token")
    return bool(provided) and secrets.compare_digest(provided, required)


def _get_redirect_uri(request: Request) -> str:
    explicit = os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
    if explicit:
        return explicit
    base = str(request.base_url).rstrip("/")
    return f"{base}/oauth2/callback"


@app.get("/oauth/start", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
async def google_oauth_start(request: Request) -> RedirectResponse:
    if not _require_setup_token(request):
        return RedirectResponse(url="/health", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        return RedirectResponse(url="/health", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    redirect_uri = _get_redirect_uri(request)

    state = secrets.token_urlsafe(24)
    _OAUTH_STATE_CACHE.add(state)

    scope = " ".join(
        [
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/calendar",
        ]
    )

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }

    if request.query_params.get("setup_token"):
        params["state"] = f"{state}:{request.query_params.get('setup_token')}"

    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/oauth2/callback")
async def google_oauth_callback(request: Request) -> HTMLResponse:
    error = request.query_params.get("error")
    if error:
        return HTMLResponse(f"OAuth error: {error}", status_code=status.HTTP_400_BAD_REQUEST)

    code = request.query_params.get("code")
    if not code:
        return HTMLResponse("Missing authorization code", status_code=status.HTTP_400_BAD_REQUEST)

    raw_state = request.query_params.get("state") or ""
    state = raw_state.split(":", 1)[0] if raw_state else ""
    setup_token = raw_state.split(":", 1)[1] if ":" in raw_state else request.query_params.get("setup_token")

    required = os.getenv("OAUTH_SETUP_TOKEN")
    if required:
        if not setup_token or not secrets.compare_digest(setup_token, required):
            return HTMLResponse("Forbidden", status_code=status.HTTP_403_FORBIDDEN)

    if not state or state not in _OAUTH_STATE_CACHE:
        return HTMLResponse("Invalid state", status_code=status.HTTP_400_BAD_REQUEST)
    _OAUTH_STATE_CACHE.discard(state)

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        return HTMLResponse(
            "Missing GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET on server",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    redirect_uri = _get_redirect_uri(request)
    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post("https://oauth2.googleapis.com/token", data=data)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return HTMLResponse(
            f"Token exchange failed: {exc!r}",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    payload = resp.json() or {}
    refresh_token = payload.get("refresh_token")
    access_token = payload.get("access_token")
    scope = payload.get("scope")

    if not refresh_token:
        return HTMLResponse(
            "No refresh_token returned. Try revoking access and re-running /oauth/start (prompt=consent is enabled).",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    html = "<h2>Google OAuth success</h2>"
    html += "<p>Copy this into your VPS .env as <b>GOOGLE_REFRESH_TOKEN</b>:</p>"
    html += f"<pre>{refresh_token}</pre>"
    if isinstance(scope, str) and scope.strip():
        html += f"<p><b>Granted scopes:</b> {scope}</p>"
    if isinstance(access_token, str) and access_token.strip():
        html += "<p>Access token received (short-lived).</p>"
    return HTMLResponse(html)


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> dict:
    """Health check endpoint to verify that the service is running.

    TODO: Extend with checks for dependencies (Supabase, Redis, OpenAI, etc.).
    """

    return {"status": "ok"}


@app.post("/webhook/telegram", status_code=status.HTTP_200_OK)
async def telegram_webhook(request: Request) -> dict:
    """Telegram webhook endpoint for receiving updates from Telegram.

    This endpoint performs minimal parsing and logging of the raw Telegram
    update before delegating to the Telegram service layer.
    TODO: Extend with security checks, error handling, and agent integration.
    """

    payload = await request.json()

    # Generate a correlation id so all logs for this request can be tied
    # together across services.
    request_id = generate_request_id()
    request.state.request_id = request_id

    # Log the raw incoming update for observability.
    log_info("Received raw Telegram update", request_id=request_id, payload=payload)

    try:
        await handle_telegram_update(payload, request_id=request_id)
    except Exception as exc:  # noqa: BLE001
        # Log and continue to respond with 200 OK so Telegram does not
        # repeatedly retry the webhook.
        log_error(
            "Error while handling Telegram update",
            request_id=request_id,
            error=repr(exc),
        )

    return {"status": "ok"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler for uncaught exceptions.

    Ensures the service returns a 500 JSON error rather than crashing, and
    logs the error together with any request_id associated with the request.
    """

    request_id = getattr(request.state, "request_id", None)
    log_error("Unhandled exception", request_id=request_id, error=str(exc))

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )
