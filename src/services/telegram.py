"""Telegram service integration for the Jarvis AI Agent.

This module provides helpers for receiving updates via webhooks and sending
messages back to Telegram users.
TODO: Implement Telegram bot client, webhook validation, and message sending.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

import logging
import os
from pathlib import Path
import uuid

import httpx

from src.core.agent import agent
from src.utils.format import detect_type
from src.utils.format import safe_get
from src.utils.logger import get_logger
from src.utils.logger import log_error
from src.utils.logger import log_info
from src.utils.logger import log_warn
from src.utils.ratelimiter import check_rate_limit


_PROCESS_START_UTC = datetime.now(timezone.utc)
_LAST_SEEN_UPDATE_ID: Optional[int] = None


def extract_basic_info(update: Dict[str, Any]) -> Dict[str, Any]:
    """Extract basic user and message information from a Telegram update.

    Returns a dictionary containing user_id, username, message_id, and
    message_type (e.g. text, voice, photo, callback_query).
    """

    message = update.get("message")
    callback_query = update.get("callback_query")

    # Prefer the message object; fall back to the message inside a callback.
    container = message or (callback_query.get("message") if callback_query else None)

    user = None
    if container and "from" in container:
        user = container["from"]
    elif callback_query and "from" in callback_query:
        user = callback_query["from"]

    user_id = (user or {}).get("id")
    username = (user or {}).get("username")
    message_id = (container or {}).get("message_id")

    message_type = "unknown"
    if message:
        if "text" in message:
            message_type = "text"
        elif "voice" in message:
            message_type = "voice"
        elif "photo" in message:
            message_type = "photo"
        elif "video" in message:
            message_type = "video"
        elif "audio" in message:
            message_type = "audio"
        elif "document" in message:
            message_type = "document"
    elif callback_query:
        message_type = "callback_query"

    return {
        "user_id": user_id,
        "username": username,
        "message_id": message_id,
        "message_type": message_type,
    }


async def process_raw_update(update: Dict[str, Any]) -> None:
    """Placeholder for further raw update processing.

    TODO: Implement message normalization and routing to the core agent.
    """
    # Phase 2: no-op implementation.
    _ = update

def normalize_message(update: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a Telegram update into a unified message structure.

    The returned dict follows the contract defined in the system directive
    for the universal message normalizer.
    """

    message = safe_get(update, ["message"]) or safe_get(update, ["callback_query", "message"])

    # User and chat extraction.
    user = safe_get(message or {}, ["from"], {}) or safe_get(update, ["callback_query", "from"], {})
    user_id = user.get("id")
    username = user.get("username")

    chat_id = safe_get(message or {}, ["chat", "id"])

    # Determine message type.
    msg_type = detect_type(message or {})

    text = safe_get(message or {}, ["text"]) or ""
    caption = safe_get(message or {}, ["caption"]) or ""

    # Voice-specific metadata (Phase 4).
    file_id = None
    if msg_type == "voice":
        voice_payload = safe_get(message or {}, ["voice"], {})
        if isinstance(voice_payload, dict):
            file_id = voice_payload.get("file_id")

    if msg_type == "voice":
        content = "VOICE_MESSAGE_RECEIVED"
    elif msg_type == "audio":
        content = "AUDIO_MESSAGE_RECEIVED"
    elif msg_type == "caption":
        content = caption or "MEDIA_NO_CAPTION"
    elif msg_type == "command":
        content = text or "EMPTY_MESSAGE"
    else:  # text or unknown
        content = text or caption or "EMPTY_MESSAGE"

    # Telegram `date` is a Unix timestamp in seconds.
    unix_ts = safe_get(message or {}, ["date"]) or 0
    timestamp = datetime.fromtimestamp(int(unix_ts), tz=timezone.utc)

    normalized = {
        "user_id": int(user_id) if user_id is not None else 0,
        "username": username,
        "message": content,
        "type": msg_type,
        "timestamp": timestamp,
        "raw": update,
        "file_id": file_id,  # Voice file identifier when present.
        "chat_id": chat_id,
    }

    return normalized


def download_telegram_file(file_id: str) -> bytes:
    """Download a file from Telegram given its file_id.

    1. Call getFile to resolve file_path.
    2. Download the actual file content.
    """

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        log_error("TELEGRAM_BOT_TOKEN is not set in environment")
        return b""


async def download_file(file_id: str) -> str:
    """Download a Telegram file given its file_id and return a local file path.

    This is used primarily for voice messages in the Phase 8 voice pipeline.
    """

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        log_error("TELEGRAM_BOT_TOKEN is not set in environment")
        return ""

    base_url = f"https://api.telegram.org/bot{bot_token}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{base_url}/getFile", params={"file_id": file_id})
        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok"):
            log_error(f"Telegram getFile returned not ok: {data!r}")
            return ""

        result = data.get("result") or {}
        file_path = result.get("file_path")
        if not file_path:
            log_error(f"Telegram getFile missing file_path for file_id={file_id}")
            return ""

        log_info(f"Downloading voice file {file_id}")
        log_info(f"File path: {file_path}")

        file_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            file_resp = await client.get(file_url)
        file_resp.raise_for_status()

        # Persist to a temporary local file.
        tmp_dir = Path("tmp")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        local_path = tmp_dir / f"tg_voice_{uuid.uuid4().hex}.ogg"
        local_path.write_bytes(file_resp.content)

        return str(local_path)

    except httpx.RequestError as exc:
        log_error(f"HTTP error while downloading Telegram file {file_id}: {exc!r}")
    except Exception as exc:  # noqa: BLE001
        log_error(f"Unexpected error while downloading Telegram file {file_id}: {exc!r}")

    return ""

    base_url = f"https://api.telegram.org/bot{bot_token}"

    try:
        # Step 1: resolve file_path via getFile
        resp = httpx.get(
            f"{base_url}/getFile",
            params={"file_id": file_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok"):
            log_error(f"Telegram getFile returned not ok: {data!r}")
            return b""

        result = data.get("result") or {}
        file_path = result.get("file_path")
        if not file_path:
            log_error(f"Telegram getFile missing file_path for file_id={file_id}")
            return b""

        log_info(f"Downloading voice file {file_id}")
        log_info(f"File path: {file_path}")

        # Step 2: download the actual file
        file_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        file_resp = httpx.get(file_url, timeout=30.0)
        file_resp.raise_for_status()
        return file_resp.content

    except httpx.RequestError as exc:
        log_error(f"HTTP error while downloading Telegram file {file_id}: {exc!r}")
    except Exception as exc:  # noqa: BLE001
        log_error(f"Unexpected error while downloading Telegram file {file_id}: {exc!r}")

    return b""


async def handle_telegram_update(update: Dict[str, Any], request_id: Optional[str] = None) -> None:
    """Handle a raw Telegram update with minimal validation and logging.

    This entrypoint is invoked from the FastAPI webhook route.
    """

    if not isinstance(update, dict):
        log_warn("Received Telegram update that is not a dict", request_id=request_id)
        return

    if "message" not in update and "callback_query" not in update:
        log_warn("Received Telegram update without message or callback_query", request_id=request_id)
        return

    # ---------------------------------------------------------------------
    # Dedupe & backlog-drop gate (prevents replay on server restart)
    # ---------------------------------------------------------------------
    # Telegram may retry webhook deliveries, and on restarts you can receive
    # queued older updates. We must ensure Jarvis does NOT re-execute already
    # completed tasks.
    #
    # Rules:
    # - Drop any update older than this server process start time.
    # - Deduplicate updates by monotonically increasing update_id.
    #
    # This is intentionally in-memory and stateless across restarts.
    # It prevents the "previously completed tasks loop again" failure mode.
    global _LAST_SEEN_UPDATE_ID  # noqa: PLW0603

    update_id = update.get("update_id")
    if isinstance(update_id, int):
        if _LAST_SEEN_UPDATE_ID is not None and update_id <= _LAST_SEEN_UPDATE_ID:
            log_info(
                "Dropping duplicate/out-of-order Telegram update",
                request_id=request_id,
                update_id=update_id,
                last_seen=_LAST_SEEN_UPDATE_ID,
            )
            return

    # Drop queued/backlog updates based on Telegram message timestamp.
    # Telegram `date` is a Unix timestamp in seconds.
    container = update.get("message") or (update.get("callback_query") or {}).get("message")
    msg_date = (container or {}).get("date")
    if isinstance(msg_date, int):
        msg_ts = datetime.fromtimestamp(int(msg_date), tz=timezone.utc)
        if msg_ts < _PROCESS_START_UTC:
            log_info(
                "Dropping stale Telegram update from before process start",
                request_id=request_id,
                update_id=update_id,
                message_ts=msg_ts.isoformat(),
                process_start=_PROCESS_START_UTC.isoformat(),
            )
            # Even if we drop due to staleness, we still advance last-seen to
            # prevent repeated delivery of the same stale update.
            if isinstance(update_id, int):
                _LAST_SEEN_UPDATE_ID = update_id
            return

    if isinstance(update_id, int):
        _LAST_SEEN_UPDATE_ID = update_id

    info = extract_basic_info(update)

    user_id = info.get("user_id")
    message_id = info.get("message_id")
    message_type = info.get("message_type")

    if user_id is not None:
        log_info(
            f"Incoming update from user {user_id}",
            user_id=str(user_id),
            request_id=request_id,
            message_id=message_id,
            message_type=message_type,
        )
    else:
        log_warn("Incoming update with missing user_id", request_id=request_id)

    if message_type is not None:
        log_info(
            f"Type: {message_type}",
            user_id=str(user_id) if user_id is not None else None,
            request_id=request_id,
            message_type=message_type,
        )
    else:
        log_warn("Message type could not be determined", request_id=request_id)

    if message_id is not None:
        log_info(
            f"Message ID: {message_id}",
            user_id=str(user_id) if user_id is not None else None,
            request_id=request_id,
            message_id=message_id,
        )
    else:
        log_warn("Message ID missing from update", request_id=request_id)

    normalizer_logger = get_logger("jarvis.normalizer")

    try:
        await process_raw_update(update)
    except Exception as exc:  # noqa: BLE001
        log_error("Error in process_raw_update", request_id=request_id, error=repr(exc))

    # Normalize the message into the universal format.
    normalized = normalize_message(update)

    normalizer_logger.info(f"[JARVIS-NORMALIZER] User: {normalized['user_id']}")
    normalizer_logger.info(f"[JARVIS-NORMALIZER] Type: {normalized['type']}")
    normalizer_logger.info(f"[JARVIS-NORMALIZER] Message: {normalized['message']}")

    # Phase 8: perform voice transcription if needed. This mutates
    # ``normalized`` in-place, turning voice into text.
    is_voice_origin = normalized.get("type") == "voice"
    if is_voice_origin:
        file_id = normalized.get("file_id")
        if not file_id:
            log_warn("Voice message missing file_id; skipping transcription", request_id=request_id)
        else:
            try:
                from src.services.whisper import transcribe_audio

                local_path = await download_file(str(file_id))
                if not local_path:
                    log_error("Failed to download voice file for transcription", request_id=request_id)
                else:
                    result = await transcribe_audio(local_path)
                    if result.get("success"):
                        text = result.get("text") or ""
                        # Mark that this originated from a voice note for the LLM.
                        normalized["message"] = f"(Voice note) {text}"
                        normalized["type"] = "text"
                    else:
                        log_error(
                            "Whisper transcription failed",
                            request_id=request_id,
                            error=result.get("error"),
                        )
            except Exception as exc:  # noqa: BLE001
                log_error(
                    "Error during voice transcription pipeline",
                    request_id=request_id,
                    error=repr(exc),
                )

    # Hand the (possibly transcribed) text off to the core agent and
    # send the reply back to the user via Telegram.
    user_id_norm = normalized.get("user_id", 0)
    chat_id_norm = normalized.get("chat_id")
    text_norm = normalized.get("message", "")

    if chat_id_norm is None:
        log_warn("Normalized message missing chat_id; cannot send reply", request_id=request_id)
        return

    if not text_norm:
        log_warn("Normalized message has empty content; nothing to send to agent", request_id=request_id)
        return

    # Apply per-user rate limiting before invoking the agent.
    if user_id_norm:
        allowed = await check_rate_limit(str(user_id_norm))
        if not allowed:
            log_warn(
                "User is rate-limited",
                user_id=str(user_id_norm),
                request_id=request_id,
            )
            await send_message(
                str(chat_id_norm),
                "You're sending messages too quickly. Please wait a bit and try again.",
            )
            return
    from src.utils.formatter import format_agent_response, strip_system_commentary

    raw_reply = ""
    try:
        raw_reply = await agent(int(user_id_norm), str(text_norm), request_id=request_id)

    except Exception as exc:  # noqa: BLE001
        log_error(
            "Error while running agent",
            user_id=str(user_id_norm),
            request_id=request_id,
            error=repr(exc),
        )
        raw_reply = "Sorry, I had an internal error while processing your message."

    raw_cleaned = str(raw_reply).strip()

    # Check for voice response tag (with or without underscores/spaces)
    wants_voice = (
        raw_cleaned.endswith("[VOICE_RESPONSE_REQUESTED]")
        or raw_cleaned.endswith("[VOICERESPONSEREQUESTED]")
        or raw_cleaned.endswith("[VOICE RESPONSE REQUESTED]")
    )

    # Remove all possible tag variants
    raw_cleaned = (
        raw_cleaned.replace("[VOICE_RESPONSE_REQUESTED]", "")
        .replace("[VOICERESPONSEREQUESTED]", "")
        .replace("[VOICE RESPONSE REQUESTED]", "")
        .strip()
    )

    # Format based on the OUTGOING response type.
    if wants_voice:
        reply_text = format_agent_response(raw_cleaned, is_voice=True)
    else:
        reply_text = format_agent_response(raw_cleaned, is_voice=False)
    reply_text = strip_system_commentary(reply_text)

    if not reply_text:
        log_warn("Agent returned empty reply; nothing will be sent to Telegram", request_id=request_id)
        return

    cleaned_reply = reply_text.strip()

    if wants_voice:
        try:
            from src.services.tts import synthesize_speech
            import re

            urls = re.findall(r"https?://\S+", raw_cleaned)
            urls = [u.strip().rstrip(")].,;\"") for u in urls if isinstance(u, str) and u.strip()]

            tts_result = await synthesize_speech(cleaned_reply)
            if tts_result.get("success") and tts_result.get("file_path"):
                await send_voice(str(chat_id_norm), str(tts_result["file_path"]))
                if urls:
                    await send_message(str(chat_id_norm), "\n".join(urls))
            else:
                log_error(
                    "TTS synthesis failed",
                    user_id=str(user_id_norm),
                    request_id=request_id,
                    result=tts_result,
                )
                await send_message(str(chat_id_norm), cleaned_reply)
        except Exception as exc:  # noqa: BLE001
            log_error(
                "Error while generating TTS reply",
                user_id=str(user_id_norm),
                request_id=request_id,
                error=repr(exc),
            )
            await send_message(str(chat_id_norm), cleaned_reply)
    else:
        await send_message(str(chat_id_norm), cleaned_reply)


class TelegramService:
    """Wrapper around Telegram Bot API interactions.

    TODO: Inject HTTP client and configuration in later phases.
    """

    def __init__(self) -> None:
        """Initialize the Telegram service."""
        self._logger = logging.getLogger(self.__class__.__name__)

    async def handle_update(self, payload: Dict[str, Any]) -> None:
        """Handle an incoming Telegram update payload.

        TODO: Normalize message and forward to the core agent.
        """
        # Placeholder implementation for Phase 1.
        pass

    async def send_message(self, chat_id: str, text: str) -> None:
        """Send a text message to a Telegram chat.

        TODO: Call Telegram sendMessage API via HTTP client.
        """
        await send_message(chat_id, text)


async def send_message(chat_id: str, text: str) -> None:
    """Low-level helper to send a text message via Telegram Bot API."""

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        log_error("TELEGRAM_BOT_TOKEN is not set in environment; cannot send message")
        return

    base_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    try:
        resp = httpx.post(
            base_url,
            json={"chat_id": chat_id, "text": text},
            timeout=10.0,
        )
        resp.raise_for_status()
    except httpx.RequestError as exc:
        log_error(f"HTTP error while sending Telegram message: {exc!r}")
    except Exception as exc:  # noqa: BLE001
        log_error(f"Unexpected error while sending Telegram message: {exc!r}")


async def send_voice(chat_id: str, file_path: str) -> None:
    """Send a voice message to a Telegram chat using a local audio file path."""

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        log_error("TELEGRAM_BOT_TOKEN is not set in environment; cannot send voice")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendVoice"

    try:
        with open(file_path, "rb") as f:
            files = {"voice": f}
            data = {"chat_id": chat_id}
            resp = httpx.post(url, data=data, files=files, timeout=30.0)
            resp.raise_for_status()
    except httpx.RequestError as exc:  # noqa: BLE001
        log_error(f"HTTP error while sending Telegram voice message: {exc!r}")
    except Exception as exc:  # noqa: BLE001
        log_error(f"Unexpected error while sending Telegram voice message: {exc!r}")
