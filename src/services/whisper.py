"""Whisper transcription service for the Jarvis AI Agent.

This module provides an abstraction for speech-to-text using OpenAI models.
TODO: Implement audio download, conversion, and transcription calls.
"""

from typing import Any, Dict

import logging
import os
import tempfile

from openai import OpenAI


class WhisperService:
    """Wrapper around Whisper transcription functionality."""

    def __init__(self) -> None:
        """Initialize the Whisper service."""
        self._logger = logging.getLogger(self.__class__.__name__)

    async def transcribe(self, audio_bytes: bytes, **kwargs: Any) -> Dict[str, Any]:
        """Transcribe audio into text using the low-level bytes helper."""

        text = _transcribe_audio_bytes(audio_bytes)
        return {"text": text}


def _transcribe_audio_bytes(audio_bytes: bytes) -> str:
    """Transcribe audio bytes into text using OpenAI Whisper.

    Uses the gpt-4o-mini-transcribe model as specified in the directive.
    """

    logger = logging.getLogger("jarvis.whisper")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("[JARVIS-WHISPER] OPENAI_API_KEY is not set")
        return "TRANSCRIPTION_ERROR"

    client = OpenAI(api_key=api_key)

    try:
        # The OpenAI Python SDK expects the `file` argument to be either bytes,
        # an IOBase, a PathLike, or a (filename, bytes, content_type) tuple.
        # We send the in-memory bytes with an .ogg filename and appropriate
        # MIME type.

        file_tuple = ("audio.ogg", audio_bytes, "audio/ogg")

        result = client.audio.transcriptions.create(
            model="gpt-4o-transcribe",
            file=file_tuple,
        )

        text: str | None = None
        if isinstance(result, dict):
            text = result.get("text")  # type: ignore[assignment]
        else:
            text = getattr(result, "text", None)

        if not text:
            logger.warning("[JARVIS-WHISPER] Empty transcription result")
            return "TRANSCRIPTION_EMPTY"

        return text

    except Exception as exc:  # noqa: BLE001
        logger.error(f"[JARVIS-WHISPER] Transcription error: {exc!r}")
        return "TRANSCRIPTION_ERROR"


async def transcribe_audio(file_path: str) -> Dict[str, Any]:
    """Transcribe an audio file from disk and return a normalized result.

    Returns a dict of the form::

        {"success": bool, "text": str | None, "error": str | None}
    """

    logger = logging.getLogger("jarvis.whisper")

    try:
        with open(file_path, "rb") as f:
            audio_bytes = f.read()
    except OSError as exc:  # noqa: BLE001
        logger.error("[JARVIS-WHISPER] Failed to read audio file %s: %r", file_path, exc)
        return {"success": False, "text": None, "error": f"FILE_READ_ERROR: {exc!r}"}

    text = _transcribe_audio_bytes(audio_bytes)
    if text in {"TRANSCRIPTION_ERROR", "TRANSCRIPTION_EMPTY"}:
        return {"success": False, "text": None, "error": text}

    return {"success": True, "text": text, "error": None}


async def transcribe_audio_tool(file_path: str) -> Dict[str, Any]:
    """Tool wrapper that transcribes an audio file from disk.

    Returns a normalized dict with success flag and text.
    """

    result = await transcribe_audio(file_path)
    if not result.get("success"):
        # Preserve the older shape for callers expecting "error" only.
        return {"success": False, "error": result.get("error", "TRANSCRIPTION_ERROR")}

    return {"success": True, "text": result.get("text", "")}
