"""
Audio Runtime - Voice-First OS Core
====================================
Continuous voice processing, wake word detection, and audio pipeline.
"""

from __future__ import annotations
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable, AsyncGenerator
import structlog

logger = structlog.get_logger("rasospeak.audio")


class VoiceState(Enum):
    """Voice assistant state machine."""
    IDLE = "idle"                    # Not listening
    LISTENING = "listening"          # Wake word detected, waiting for speech
    PROCESSING = "processing"         # Transcribing/processing
    SPEAKING = "speaking"            # Generating audio response
    INTERRUPTED = "interrupted"      # User interrupted mid-response
    ERROR = "error"                  # Error state


class WakeWordResult(Enum):
    """Wake word detection result."""
    DETECTED = "detected"
    NOT_DETECTED = "not_detected"
    CONFUSED = "confused"            # Multiple possibilities
    ERROR = "error"


@dataclass
class AudioSegment:
    """Audio segment with metadata."""
    audio_id: str
    session_id: str
    user_id: str

    # Audio data
    audio_data: bytes
    sample_rate: int = 16000
    channels: int = 1
    format: str = "pcm"

    # Timing
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: int = 0

    # Transcription
    transcript: Optional[str] = None
    confidence: float = 0.0
    language: str = "en"

    # Speaker
    speaker_id: Optional[str] = None
    is_user: bool = True

    # Metadata
    metadata: dict = field(default_factory=dict)


@dataclass
class TranscriptionResult:
    """Transcription result."""
    transcript: str
    confidence: float
    language: str
    words: list[dict] = field(default_factory=list)  # word, start, end, confidence
    is_final: bool = True
    audio_duration_ms: int = 0


@dataclass
class WakeWordDetection:
    """Wake word detection result."""
    result: WakeWordResult
    wake_word: str
    confidence: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    audio_start_ms: int = 0
    audio_end_ms: int = 0
    alternatives: list[str] = field(default_factory=list)


class VoiceRuntime:
    """
    Continuous voice runtime for RasoSpeak OS.

    Responsibilities:
    - Wake word detection ("Hey Raso")
    - Continuous audio capture
    - Real-time transcription
    - Audio streaming to providers
    - Text-to-speech synthesis
    - Duplex conversation handling
    - Interruption handling
    """

    def __init__(
        self,
        wake_words: list[str] = None,
        sample_rate: int = 16000,
        buffer_size_ms: int = 100,
        vad_threshold: float = 0.5
    ):
        # Configuration
        self._wake_words = wake_words or ["hey raso", "raso", "jarvis", "ok computer"]
        self._sample_rate = sample_rate
        self._buffer_size_ms = buffer_size_ms
        self._vad_threshold = vad_threshold  # Voice activity detection

        # State
        self._state = VoiceState.IDLE
        self._current_session: Optional[str] = None
        self._current_user: str = "default"

        # Components
        self._wake_word_model = None
        self._vad_model = None
        self._transcriber = None
        self._tts = None

        # Audio buffer for continuous capture
        self._audio_buffer: asyncio.Queue = asyncio.Queue()
        self._transcript_buffer: list[str] = []

        # Callbacks
        self._on_wake_word: Optional[Callable] = None
        self._on_transcript: Optional[Callable] = None
        self._on_speech_start: Optional[Callable] = None
        self._on_speech_end: Optional[Callable] = None
        self._on_state_change: Optional[Callable] = None
        self._on_error: Optional[Callable] = None

        # Metrics
        self._total_wake_words = 0
        self._total_transcripts = 0
        self._avg_latency_ms = 0

        # Continuous mode
        self._continuous_mode = True  # Keep listening after response

    # ─────────────────────────────────────────────────────────────
    # State Management
    # ─────────────────────────────────────────────────────────────

    def get_state(self) -> VoiceState:
        return self._state

    async def set_state(self, new_state: VoiceState):
        """Set state and notify listeners."""
        old_state = self._state
        self._state = new_state

        logger.info("voice_state_changed", old=old_state.value, new=new_state.value)

        if self._on_state_change:
            try:
                if asyncio.iscoroutinefunction(self._on_state_change):
                    await self._on_state_change(old_state, new_state)
                else:
                    self._on_state_change(old_state, new_state)
            except Exception as e:
                logger.error("state_change_callback_error", error=str(e))

    # ─────────────────────────────────────────────────────────────
    # Callbacks
    # ─────────────────────────────────────────────────────────────

    def on_wake_word(self, callback: Callable):
        """Set callback for wake word detection."""
        self._on_wake_word = callback

    def on_transcript(self, callback: Callable):
        """Set callback for transcription results."""
        self._on_transcript = callback

    def on_speech_start(self, callback: Callable):
        """Set callback for speech start."""
        self._on_speech_start = callback

    def on_speech_end(self, callback: Callable):
        """Set callback for speech end."""
        self._on_speech_end = callback

    def on_state_change(self, callback: Callable):
        """Set callback for state changes."""
        self._on_state_change = callback

    def on_error(self, callback: Callable):
        """Set callback for errors."""
        self._on_error = callback

    # ─────────────────────────────────────────────────────────────
    # Wake Word Detection
    # ─────────────────────────────────────────────────────────────

    async def detect_wake_word(
        self,
        audio_chunk: bytes,
        timestamp_ms: int = 0
    ) -> Optional[WakeWordDetection]:
        """
        Detect wake word in audio chunk.

        This is called continuously during IDLE state.
        """
        # Placeholder for actual wake word detection
        # In production, would use:
        # - Precise RVC (Realtime Voice Conversion) model
        # - Porcupine
        # - Snowboy
        # - Custom trained model

        # For now, simulate detection
        # In real implementation:
        # 1. Run VAD to check if speech present
        # 2. If speech, run wake word model
        # 3. Return detection result

        return None  # Placeholder

    async def start_listening(self, session_id: str, user_id: str = "default"):
        """Start listening for wake word."""
        self._current_session = session_id
        self._current_user = user_id

        await self.set_state(VoiceState.LISTENING)

        logger.info("voice_listening_started", session_id=session_id)

    async def stop_listening(self):
        """Stop listening."""
        await self.set_state(VoiceState.IDLE)
        self._current_session = None
        self._audio_buffer = asyncio.Queue()

        logger.info("voice_listening_stopped")

    # ─────────────────────────────────────────────────────────────
    # Transcription
    # ─────────────────────────────────────────────────────────────

    async def transcribe(
        self,
        audio: bytes,
        language: str = "en",
        interim: bool = False
    ) -> TranscriptionResult:
        """
        Transcribe audio to text.

        Uses Web Speech API in browser or Whisper API server-side.
        """
        # Placeholder - actual implementation would use:
        # - Browser: Web Speech API
        # - Server: Whisper API or local model

        return TranscriptionResult(
            transcript="",
            confidence=0.0,
            language=language,
            is_final=not interim
        )

    async def transcribe_stream(
        self,
        audio_chunks: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[TranscriptionResult, None]:
        """Stream transcription."""
        async for chunk in audio_chunks:
            result = await self.transcribe(chunk, interim=True)
            if result.transcript:
                yield result

    # ─────────────────────────────────────────────────────────────
    # Text-to-Speech
    # ─────────────────────────────────────────────────────────────

    async def speak(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
        pitch: float = 1.0
    ) -> AsyncGenerator[bytes, None]:
        """
        Convert text to speech.

        Yields audio chunks.
        """
        await self.set_state(VoiceState.SPEAKING)

        # Placeholder - actual implementation would use:
        # - Browser: Web Speech API synthesis
        # - Server: TTS API (ElevenLabs, OpenAI, etc.)

        # For now, just yield empty bytes
        yield b""

        # After speaking, return to listening if continuous mode
        if self._continuous_mode and self._current_session:
            await self.set_state(VoiceState.LISTENING)
        else:
            await self.set_state(VoiceState.IDLE)

    async def speak_with_fallback(
        self,
        text: str,
        preferred_provider: str = "google"
    ) -> AsyncGenerator[bytes, None]:
        """Speak with automatic provider fallback."""
        providers = ["google", "openai", "elevenlabs"]

        for provider in providers:
            if provider == preferred_provider or provider in providers:
                try:
                    async for chunk in self.speak(text):
                        yield chunk
                    break
                except Exception as e:
                    logger.warning("tts_provider_failed", provider=provider, error=str(e))
                    continue

    # ─────────────────────────────────────────────────────────────
    # Interruption Handling
    # ─────────────────────────────────────────────────────────────

    async def interrupt(self):
        """Handle user interruption."""
        if self._state in [VoiceState.PROCESSING, VoiceState.SPEAKING]:
            await self.set_state(VoiceState.INTERRUPTED)
            logger.info("voice_interrupted")

            # Return to listening
            if self._current_session:
                await self.set_state(VoiceState.LISTENING)

    async def resume(self):
        """Resume after interruption."""
        if self._state == VoiceState.INTERRUPTED:
            if self._current_session:
                await self.set_state(VoiceState.LISTENING)
            else:
                await self.set_state(VoiceState.IDLE)

    # ─────────────────────────────────────────────────────────────
    # Continuous Audio Capture (Browser-side)
    # ─────────────────────────────────────────────────────────────

    async def process_audio_buffer(self, audio_data: bytes):
        """
        Process incoming audio from browser.

        Runs continuously in LISTENING state.
        """
        if self._state != VoiceState.LISTENING:
            return

        # Detect wake word
        detection = await self.detect_wake_word(audio_data)

        if detection and detection.result == WakeWordResult.DETECTED:
            logger.info("wake_word_detected", word=detection.wake_word, confidence=detection.confidence)
            self._total_wake_words += 1

            # Notify callback
            if self._on_wake_word:
                try:
                    if asyncio.iscoroutinefunction(self._on_wake_word):
                        await self._on_wake_word(detection)
                    else:
                        self._on_wake_word(detection)
                except Exception as e:
                    logger.error("wake_word_callback_error", error=str(e))

            # Transition to processing
            await self.set_state(VoiceState.PROCESSING)

    # ─────────────────────────────────────────────────────────────
    # Session Management
    # ─────────────────────────────────────────────────────────────

    async def start_session(
        self,
        user_id: str = "default",
        session_id: Optional[str] = None
    ) -> str:
        """Start new voice session."""
        import uuid
        session_id = session_id or str(uuid.uuid4())

        self._current_session = session_id
        self._current_user = user_id

        await self.set_state(VoiceState.LISTENING)

        logger.info("voice_session_started", session_id=session_id, user_id=user_id)

        return session_id

    async def end_session(self):
        """End current voice session."""
        if self._current_session:
            session_id = self._current_session

            await self.set_state(VoiceState.IDLE)

            logger.info("voice_session_ended", session_id=session_id)

            self._current_session = None
            self._transcript_buffer = []

    def get_current_session(self) -> Optional[str]:
        return self._current_session

    # ─────────────────────────────────────────────────────────────
    # Voice Commands
    # ─────────────────────────────────────────────────────────────

    async def parse_voice_command(self, transcript: str) -> dict:
        """
        Parse voice command to structured intent.

        Examples:
        - "Switch to NVIDIA" -> {action: "switch_provider", provider: "nvidia"}
        - "Use Claude for reasoning" -> {action: "set_model", model: "claude", purpose: "reasoning"}
        - "Pause proactive mode" -> {action: "toggle_feature", feature: "proactive"}
        """
        transcript = transcript.lower().strip()

        commands = {
            "switch": [
                ("switch to ", "switch_provider"),
                ("use ", "use_provider"),
                ("change to ", "switch_provider"),
            ],
            "model": [
                ("use ", "set_model"),
                ("switch model to ", "set_model"),
                ("use .* for ", "set_model_purpose"),
            ],
            "mode": [
                ("pause ", "disable_feature"),
                ("stop ", "disable_feature"),
                ("resume ", "enable_feature"),
                ("start ", "enable_feature"),
            ]
        }

        # Simple pattern matching
        result = {"action": "chat", "raw": transcript}

        for prefix, action in [
            ("switch to ", "switch_provider"),
            ("use ", "use_provider"),
        ]:
            if transcript.startswith(prefix):
                provider = transcript[len(prefix):].strip()
                result = {"action": action, "provider": provider, "raw": transcript}
                break

        # Model-specific commands
        for model in ["claude", "gpt", "gemini", "deepseek", "nvidia"]:
            if model in transcript:
                if "reasoning" in transcript:
                    result = {"action": "set_model", "model": model, "purpose": "reasoning"}
                elif "coding" in transcript or "code" in transcript:
                    result = {"action": "set_model", "model": model, "purpose": "coding"}
                else:
                    result = {"action": "set_model", "model": model}

        # Feature toggles
        if "pause" in transcript or "stop" in transcript:
            for feature in ["proactive", "listening", "recording", "memory"]:
                if feature in transcript:
                    result = {"action": "disable_feature", "feature": feature}

        if "resume" in transcript or "start" in transcript:
            for feature in ["proactive", "listening", "recording", "memory"]:
                if feature in transcript:
                    result = {"action": "enable_feature", "feature": feature}

        return result

    # ─────────────────────────────────────────────────────────────
    # Metrics
    # ─────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get voice runtime statistics."""
        return {
            "state": self._state.value,
            "session": self._current_session,
            "total_wake_words": self._total_wake_words,
            "total_transcripts": self._total_transcripts,
            "avg_latency_ms": self._avg_latency_ms,
            "continuous_mode": self._continuous_mode,
            "wake_words": self._wake_words
        }


# Global voice runtime
_voice_runtime: Optional[VoiceRuntime] = None


def get_voice_runtime() -> VoiceRuntime:
    """Get global voice runtime instance."""
    global _voice_runtime
    if _voice_runtime is None:
        _voice_runtime = VoiceRuntime()
    return _voice_runtime