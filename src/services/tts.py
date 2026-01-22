"""Text-to-speech (TTS) service for the Jarvis AI Agent.

This module wraps OpenAI TTS models for generating audio responses.
"""

from __future__ import annotations

from typing import Any, Dict

import base64
import logging
import os
from pathlib import Path
import uuid

from openai import OpenAI


logger = logging.getLogger("jarvis.tts")


class TTSService:
    """Wrapper around TTS functionality.

    Kept for compatibility; new code should use synthesize_speech.
    """

    def __init__(self) -> None:
        """Initialize the TTS service."""
        self._logger = logging.getLogger(self.__class__.__name__)

    async def synthesize(self, text: str, **kwargs: Any) -> bytes:  # pragma: no cover - legacy
        """Legacy wrapper that calls synthesize_speech and returns raw audio bytes."""

        result = await synthesize_speech(text, voice=kwargs.get("voice", "alloy"))
        if not result.get("success"):
            return b""
        audio_b64 = result.get("audio_base64", "")
        try:
            return base64.b64decode(audio_b64)
        except Exception:  # noqa: BLE001
            return b""


async def synthesize_speech(text: str, voice: str = "alloy") -> Dict[str, Any]:
    """Tool-friendly TTS helper using OpenAI audio.speech.

    Returns a dict of the form::

        {"success": bool, "audio_base64": str, "file_path": str | None, "error": str | None}
    """

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY is not set; TTS will fail")
        return {"success": False, "audio_base64": "", "file_path": None, "error": "MISSING_OPENAI_API_KEY"}

    client = OpenAI(api_key=api_key)

    try:
        # The new OpenAI TTS API returns bytes when stream=False.
        result = client.audio.speech.create(
            model="tts-1",  # OpenAI TTS model (tts-1 or tts-1-hd)
            voice=voice,
            input=text,
        )

        audio_bytes: bytes = result.read() if hasattr(result, "read") else bytes(result)  # type: ignore[arg-type]
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        # Persist audio to a temporary file so Telegram can send it as voice.
        tmp_dir = Path("tmp")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        file_path = tmp_dir / f"tts_{uuid.uuid4().hex}.mp3"
        file_path.write_bytes(audio_bytes)

        return {"success": True, "audio_base64": audio_b64, "file_path": str(file_path), "error": None}

    except Exception as exc:  # noqa: BLE001
        logger.error("TTS error: %r", exc)
        return {"success": False, "audio_base64": "", "file_path": None, "error": "TTS_ERROR"}
