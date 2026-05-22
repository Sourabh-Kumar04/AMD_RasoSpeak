"""
RasoSpeak OS — Server-Side Voice Pipeline
Streaming STT, TTS, wake word detection, and voice cognition
"""

import asyncio
import base64
import json
import logging
import os
import time
from typing import AsyncIterator, Optional, Callable
from dataclasses import dataclass
from enum import Enum

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import numpy as np

log = logging.getLogger("rasospeak.voice")

# Voice pipeline modes
class VoiceMode(Enum):
    STREAMING = "streaming"  # Continuous streaming
    COMMAND = "command"       # Single command mode
    INTERACTIVE = "interactive"  # Back-and-forth dialogue


@dataclass
class VoiceConfig:
    """Configuration for voice pipeline."""
    sample_rate: int = 16000
    channels: int = 1
    bit_depth: int = 16
    buffer_size: int = 4096
    silence_threshold: float = 0.01
    min_speech_duration: float = 0.3
    max_speech_duration: float = 30.0
    wake_word: str = "hey raso"
    tts_voice: str = "en-US-Neural2-F"


class VoicePipeline:
    """
    Server-side voice processing pipeline.

    Flow:
    1. Client streams audio via WebSocket
    2. Server processes with streaming STT
    3. Transcript triggers cognitive pipeline
    4. Response generates TTS
    5. Server streams audio back to client
    """

    def __init__(self, config: VoiceConfig = None):
        self.config = config or VoiceConfig()
        self._running = False
        self._stt_model = None
        self._tts_model = None
        self._cognition_callback: Optional[Callable] = None

    async def initialize(self) -> None:
        """Initialize STT/TTS models."""
        log.info("Initializing voice pipeline...")

        # Initialize streaming STT
        try:
            # Use faster-whisper for server-side STT (or whispercpp)
            # For now, use deepgram/other API as fallback
            self._stt_model = os.getenv("STT_MODEL", "base")
            log.info(f"STT model: {self._stt_model}")
        except Exception as e:
            log.warning(f"STT initialization failed: {e}, using API fallback")

        # Initialize TTS
        try:
            self._tts_model = os.getenv("TTS_MODEL", "en-US-Neural2-F")
            log.info(f"TTS voice: {self._tts_model}")
        except Exception as e:
            log.warning(f"TTS initialization failed: {e}")

        self._running = True
        log.info("✅ Voice pipeline initialized")

    def set_cognition_callback(self, callback: Callable) -> None:
        """Set callback for cognitive processing."""
        self._cognition_callback = callback

    async def process_audio_stream(
        self,
        websocket: WebSocket,
        user_id: str = "default",
    ) -> AsyncIterator[dict]:
        """
        Main audio processing loop.
        Yields transcription chunks and TTS audio.
        """
        audio_buffer = []
        silence_count = 0
        speech_active = False

        try:
            await websocket.accept()

            # Send ready signal
            yield {"type": "ready", "mode": "streaming"}

            while self._running:
                try:
                    # Receive audio data
                    data = await websocket.receive()

                    # Handle binary audio
                    if "bytes" in data:
                        audio_chunk = data["bytes"]
                        audio_buffer.append(audio_chunk)

                        # Check for speech
                        if self._is_speech(audio_chunk):
                            speech_active = True
                            silence_count = 0
                        else:
                            silence_count += 1

                        # End of speech detection
                        if speech_active and silence_count > 10:
                            # Process complete utterance
                            transcript = await self._transcribe(b"".join(audio_buffer))

                            if transcript:
                                # Get cognitive response
                                response = await self._cognize(transcript, user_id)

                                yield {
                                    "type": "transcript",
                                    "text": transcript,
                                    "response": response.get("text", ""),
                                    "audio": await self._synthesize(response.get("text", "")),
                                }

                            # Reset buffer
                            audio_buffer = []
                            speech_active = False
                            silence_count = 0

                    # Handle text commands
                    elif "text" in data:
                        msg = json.loads(data["text"])
                        await self._handle_message(websocket, msg)

                except asyncio.TimeoutError:
                    continue
                except WebSocketDisconnect:
                    break

        except Exception as e:
            log.error(f"Voice stream error: {e}")
            yield {"type": "error", "message": str(e)}

    def _is_speech(self, audio_data: bytes) -> bool:
        """Simple voice activity detection."""
        try:
            # Convert to numpy array
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            # Check if above silence threshold
            return np.abs(audio_np).mean() > self.config.silence_threshold
        except:
            return True  # Assume speech if can't determine

    async def _transcribe(self, audio_data: bytes) -> str:
        """Convert audio to text using STT."""
        if not audio_data:
            return ""

        # Option 1: Use faster-whisper locally
        try:
            # Import would be: from faster_whisper import WhisperModel
            # For now, use API fallback
            pass
        except ImportError:
            pass

        # Option 2: Use external API (Deepgram, AssemblyAI, etc.)
        api_key = os.getenv("DEEPGRAM_API_KEY")
        if api_key:
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://api.deepgram.com/v1/listen",
                        headers={"Authorization": f"Token {api_key}"},
                        content=audio_data,
                        params={"model": "nova-2", "smart_format": "true"},
                    )
                    result = response.json()
                    return result.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
            except Exception as e:
                log.error(f"Deepgram STT failed: {e}")

        return ""

    async def _cognize(self, transcript: str, user_id: str) -> dict:
        """Process transcript through cognitive pipeline."""
        if self._cognition_callback:
            return await self._cognition_callback(transcript, user_id)

        # Default: return echo
        return {"text": f"You said: {transcript}"}

    async def _synthesize(self, text: str) -> str:
        """Convert text to speech audio (base64)."""
        if not text:
            return ""

        # Use OpenAI TTS or similar
        tts_api_key = os.getenv("OPENAI_API_KEY") or os.getenv("TTS_API_KEY")
        if tts_api_key:
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://api.openai.com/v1/audio/speech",
                        headers={
                            "Authorization": f"Bearer {tts_api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "tts-1",
                            "voice": self.config.tts_voice,
                            "input": text,
                        },
                    )
                    audio_bytes = response.content
                    return base64.b64encode(audio_bytes).decode()
            except Exception as e:
                log.error(f"TTS failed: {e}")

        return ""

    async def _handle_message(self, websocket: WebSocket, msg: dict) -> None:
        """Handle control messages."""
        msg_type = msg.get("type")

        if msg_type == "switch_provider":
            # Handle provider switch during voice
            pass

        elif msg_type == "interrupt":
            # Handle barge-in (user interrupted)
            log.info(f"Voice interrupted by user")

        elif msg_type == "stop":
            self._running = False

    async def shutdown(self) -> None:
        """Clean up resources."""
        self._running = False
        log.info("Voice pipeline shutdown")


# Singleton
voice_pipeline = VoicePipeline()


# ── WAKE WORD DETECTION ─────────────────────────────────

class WakeWordDetector:
    """Server-side wake word detection."""

    def __init__(self, wake_word: str = "hey raso"):
        self.wake_word = wake_word.lower()
        self._enabled = False

    async def enable(self) -> None:
        """Enable wake word listening."""
        self._enabled = True
        log.info(f"Wake word detection enabled: '{self.wake_word}'")

    async def disable(self) -> None:
        """Disable wake word listening."""
        self._enabled = False
        log.info("Wake word detection disabled")

    async def process_audio(self, audio_data: bytes) -> dict:
        """Process audio chunk for wake word."""
        if not self._enabled:
            return {"detected": False}

        # Convert audio and check for wake word
        # For production, use: https://github.com/kitt-ai/porcupine
        # or a fine-tuned model

        transcript = await voice_pipeline._transcribe(audio_data)

        if self.wake_word in transcript.lower():
            # Extract command after wake word
            parts = transcript.lower().split(self.wake_word, 1)
            command = parts[1].strip() if len(parts) > 1 else ""

            return {
                "detected": True,
                "wake_word": self.wake_word,
                "command": command,
                "full_transcript": transcript,
            }

        return {"detected": False}


# Singleton
wake_word_detector = WakeWordDetector()


# ── TTS STREAMING RESPONSE ──────────────────────────────

async def generate_speech_stream(text: str) -> AsyncIterator[bytes]:
    """Generate streaming TTS response."""
    # This would stream audio chunks as they're generated
    # For now, yield complete audio
    tts_api_key = os.getenv("OPENAI_API_KEY") or os.getenv("TTS_API_KEY")
    if tts_api_key:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                async with client.stream_post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={"Authorization": f"Bearer {tts_api_key}"},
                    json={"model": "tts-1", "voice": "alloy", "input": text},
                ) as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk
        except Exception as e:
            log.error(f"Streaming TTS failed: {e}")