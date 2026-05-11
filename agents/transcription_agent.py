"""
RasoSpeak v2 — TranscriptionAgent
No GPU required! Uses browser's Web Speech API or OpenAI Whisper API

Two modes:
1. Web Speech API (default) - uses browser's built-in speech recognition
2. OpenAI Whisper API - uses OpenAI's API for higher accuracy
"""

import asyncio
import base64
import logging
import time
from typing import Optional

from .base_agent import BaseAgent
from config.settings import settings

log = logging.getLogger("rasospeak.transcription")


class TranscriptionAgent(BaseAgent):
    """
    Agent 1: TranscriptionAgent

    No GPU required - runs via:
    1. Browser's Web Speech API (for frontend clients)
    2. OpenAI Whisper API (for backend, requires API key)

    This agent acts as a bridge - the actual transcription happens
    in the browser using Web Speech API, or via OpenAI API.
    """

    name = "TranscriptionAgent"

    def __init__(self):
        self._use_api = bool(settings.OPENAI_WHISPER_API_KEY)
        self._client = None

    async def initialize(self):
        """Initialize based on provider."""
        if self._use_api:
            import httpx
            self._client = httpx.AsyncClient(timeout=30.0)
            log.info("✅ TranscriptionAgent ready (OpenAI Whisper API)")
        else:
            log.info("✅ TranscriptionAgent ready (Web Speech API - browser-based)")

    async def cleanup(self):
        """Cleanup resources."""
        if self._client:
            await self._client.aclose()

    async def transcribe(
        self,
        audio_b64: str,
        sample_rate: int = 16000,
        language: str = "en",
    ) -> dict:
        """
        Transcribe audio to text.

        If OPENAI_WHISPER_API_KEY is set, uses OpenAI API.
        Otherwise, returns instructions for browser-based transcription.

        Args:
            audio_b64: Base64-encoded audio
            sample_rate: Audio sample rate
            language: Language code

        Returns:
            {"transcript": "...", "confidence": 0.9, "words": [...]}
        """
        t_start = time.perf_counter()

        if self._use_api:
            return await self._transcribe_api(audio_b64, language, t_start)
        else:
            return await self._transcribe_browser_fallback(audio_b64, language, t_start)

    async def _transcribe_api(self, audio_b64: str, language: str, t_start: float) -> dict:
        """Transcribe using OpenAI Whisper API."""
        if not self._client:
            return {"error": "API client not initialized"}

        try:
            # Decode audio
            audio_bytes = base64.b64decode(audio_b64)

            # Prepare file for upload
            files = {
                "file": ("audio.wav", audio_bytes, "audio/wav"),
                "model": (None, "whisper-1"),
                "language": (None, language),
            }
            headers = {"Authorization": f"Bearer {settings.OPENAI_WHISPER_API_KEY}"}

            resp = await self._client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                files=files,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

            elapsed_ms = int((time.perf_counter() - t_start) * 1000)
            return {
                "transcript": data.get("text", ""),
                "confidence": 0.9,  # OpenAI doesn't return confidence
                "words": [],
                "provider": "openai_whisper",
                "processing_ms": elapsed_ms,
            }
        except Exception as e:
            log.error(f"OpenAI transcription failed: {e}")
            return {"error": str(e)}

    async def _transcribe_browser_fallback(
        self,
        audio_b64: str,
        language: str,
        t_start: float
    ) -> dict:
        """
        Browser-based fallback.
        Returns instructions for frontend to use Web Speech API.
        """
        elapsed_ms = int((time.perf_counter() - t_start) * 1000)

        # This should be called from the browser using Web Speech API
        # The frontend will send the final transcript to the backend
        return {
            "transcript": "",
            "confidence": 0,
            "words": [],
            "provider": "webspeech",
            "processing_ms": elapsed_ms,
            "use_browser": True,
            "message": "Use browser's Web Speech API for transcription"
        }

    async def transcribe_from_blob(
        self,
        audio_data: bytes,
        language: str = "en",
    ) -> dict:
        """Transcribe audio from blob/bytes using OpenAI API."""
        if not self._use_api:
            return {"error": "Use browser Web Speech API", "use_browser": True}

        t_start = time.perf_counter()
        try:
            files = {
                "file": ("audio.wav", audio_data, "audio/wav"),
                "model": (None, "whisper-1"),
                "language": (None, language),
            }
            headers = {"Authorization": f"Bearer {settings.OPENAI_WHISPER_API_KEY}"}

            resp = await self._client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                files=files,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

            elapsed_ms = int((time.perf_counter() - t_start) * 1000)
            return {
                "transcript": data.get("text", ""),
                "confidence": 0.9,
                "provider": "openai_whisper",
                "processing_ms": elapsed_ms,
            }
        except Exception as e:
            return {"error": str(e)}