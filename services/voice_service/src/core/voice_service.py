"""
RasoSpeak AI OS — Voice Service
================================
Audio-first voice processing with:
- Streaming STT (Speech-to-Text)
- Streaming TTS (Text-to-Speech)
- Voice Activity Detection (VAD)
- Wake Word Detection
- Speaker Diarization
- Full-duplex conversation handling
- Prosodic analysis (emotion detection)
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, AsyncIterator, Callable

import structlog

logger = structlog.get_logger("rasospeak.voice")


# ──────────────────────────────────────────────────────────────────────────────
# Voice Types
# ──────────────────────────────────────────────────────────────────────────────

class VoiceState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    ERROR = "error"


class Emotion(Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    EXCITED = "excited"
    CONFUSED = "confused"
    CURIOUS = "curious"
    TIRED = "tired"


@dataclass
class Transcript:
    """Speech-to-text result."""
    text: str
    confidence: float
    is_final: bool
    timestamp: datetime
    language: str = "en"
    duration_ms: int = 0


@dataclass
class SpeakerSegment:
    """Speaker diarization result."""
    speaker_id: str
    text: str
    start_ms: int
    end_ms: int
    confidence: float


@dataclass
class TTSChunk:
    """Text-to-speech audio chunk."""
    audio_data: bytes
    is_final: bool
    chunk_index: int
    timestamp: datetime


@dataclass
class VoiceActivity:
    """Voice activity detection result."""
    is_speech: bool
    confidence: float
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None


@dataclass
class WakeWordResult:
    """Wake word detection result."""
    detected: bool
    wake_word: str
    confidence: float
    timestamp: datetime


@dataclass
class ProsodicAnalysis:
    """Emotional/prosodic analysis."""
    emotion: Emotion
    energy: float  # 0-1
    valence: float  # 0-1 (positive/negative)
    speaking_rate: float  # words per minute
    pauses: list[tuple[int, int]]  # (start_ms, duration_ms)


@dataclass
class VoiceSession:
    """Active voice session."""
    session_id: str
    user_id: str
    state: VoiceState
    started_at: datetime
    current_transcript: str = ""
    conversation_history: list[dict] = field(default_factory=list)
    interrupted: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# STT Service (Speech-to-Text)
# ──────────────────────────────────────────────────────────────────────────────

class STTService(ABC):
    """Abstract STT service interface."""

    @abstractmethod
    async def stream_transcribe(self, audio_chunk: bytes) -> AsyncIterator[Transcript]:
        """Stream audio and yield partial/final transcripts."""
        pass

    @abstractmethod
    async def transcribe(self, audio_data: bytes) -> Transcript:
        """Transcribe complete audio."""
        pass


class WhisperSTTService(STTService):
    """OpenAI Whisper-based STT service."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "whisper-1",
        language: str = "en",
    ):
        self._api_key = api_key
        self._model = model
        self._language = language
        self._buffer: list[bytes] = []
        self._sample_rate = 16000
        logger.info("whisper_stt_initialized", model=model, language=language)

    async def stream_transcribe(self, audio_chunk: bytes) -> AsyncIterator[Transcript]:
        """Stream audio chunks for real-time transcription."""
        self._buffer.append(audio_chunk)

        # Process buffer every ~1 second
        if len(self._buffer) * 0.03 >= 1.0:  # ~1 second of audio
            combined_audio = b''.join(self._buffer)
            self._buffer = []

            try:
                # Simulated streaming - in production use real API
                yield Transcript(
                    text="[Streaming transcription...]",
                    confidence=0.85,
                    is_final=False,
                    timestamp=datetime.utcnow(),
                    language=self._language,
                )
            except Exception as e:
                logger.error("stt_stream_error", error=str(e))
                yield Transcript(
                    text="",
                    confidence=0.0,
                    is_final=True,
                    timestamp=datetime.utcnow(),
                    language=self._language,
                )

    async def transcribe(self, audio_data: bytes) -> Transcript:
        """Transcribe complete audio file."""
        # In production, call OpenAI Whisper API
        # For now, return placeholder
        logger.info("transcribe_called", audio_size=len(audio_data))

        return Transcript(
            text="Transcribed speech text",
            confidence=0.9,
            is_final=True,
            timestamp=datetime.utcnow(),
            language=self._language,
            duration_ms=len(audio_data) // 2 if audio_data else 0,
        )


class LocalSTTService(STTService):
    """Local Faster Whisper STT service."""

    def __init__(
        self,
        model_name: str = "base",
        device: str = "cpu",
    ):
        self._model_name = model_name
        self._device = device
        self._model = None
        logger.info("local_stt_initialized", model=model_name, device=device)

    async def _load_model(self):
        """Lazy load the model."""
        if self._model is None:
            # In production: from faster_whisper import WhisperModel
            # self._model = WhisperModel(self._model_name, device=self._device)
            logger.info("loading_faster_whisper", model=self._model_name)
            self._model = "loaded"  # Placeholder

    async def stream_transcribe(self, audio_chunk: bytes) -> AsyncIterator[Transcript]:
        await self._load_model()
        yield Transcript(
            text="[Local streaming]",
            confidence=0.8,
            is_final=False,
            timestamp=datetime.utcnow(),
        )

    async def transcribe(self, audio_data: bytes) -> Transcript:
        await self._load_model()
        return Transcript(
            text="Local transcription",
            confidence=0.85,
            is_final=True,
            timestamp=datetime.utcnow(),
        )


# ──────────────────────────────────────────────────────────────────────────────
# TTS Service (Text-to-Speech)
# ──────────────────────────────────────────────────────────────────────────────

class TTSService(ABC):
    """Abstract TTS service interface."""

    @abstractmethod
    async def stream_speak(self, text: str, voice: str = "alloy") -> AsyncIterator[TTSChunk]:
        """Stream audio chunks as they're generated."""
        pass

    @abstractmethod
    async def speak(self, text: str, voice: str = "alloy") -> bytes:
        """Generate complete audio."""
        pass


class OpenAITTSService(TTSService):
    """OpenAI TTS service."""

    VOICES = ["alloy", "echo", "fable", "onyx", "shimmer", "nova"]

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "tts-1",
        default_voice: str = "alloy",
    ):
        self._api_key = api_key
        self._model = model
        self._default_voice = default_voice
        logger.info("openai_tts_initialized", model=model, voice=default_voice)

    async def stream_speak(self, text: str, voice: str = "alloy") -> AsyncIterator[TTSChunk]:
        """Stream TTS audio chunks."""
        if voice not in self.VOICES:
            voice = self._default_voice

        # In production, call OpenAI TTS API
        # Simulate streaming chunks
        words = text.split()
        chunk_size = max(1, len(words) // 5)

        for i in range(0, len(words), chunk_size):
            chunk_text = ' '.join(words[i:i + chunk_size])

            # Simulate audio data (in production real audio)
            audio_chunk = f"AUDIO_CHUNK_{i}".encode()

            yield TTSChunk(
                audio_data=audio_chunk,
                is_final=i + chunk_size >= len(words),
                chunk_index=i // chunk_size,
                timestamp=datetime.utcnow(),
            )

            await asyncio.sleep(0.05)  # Simulate streaming delay

    async def speak(self, text: str, voice: str = "alloy") -> bytes:
        """Generate complete audio."""
        if voice not in self.VOICES:
            voice = self._default_voice

        # In production, call OpenAI TTS API
        return b"COMPLETE_AUDIO_DATA"


class CoquiTTSService(TTSService):
    """Local Coqui TTS service."""

    def __init__(self, model_path: str = "coqui/vits"):
        self._model_path = model_path
        self._model = None
        logger.info("coqui_tts_initialized", model=model_path)

    async def _load_model(self):
        """Lazy load TTS model."""
        if self._model is None:
            # In production: from TTS import TTS
            # self._model = TTS(model_path=self._model_path)
            self._model = "loaded"

    async def stream_speak(self, text: str, voice: str = "alloy") -> AsyncIterator[TTSChunk]:
        await self._load_model()
        yield TTSChunk(audio_data=b"LOCAL_TTS_AUDIO", is_final=True, chunk_index=0, timestamp=datetime.utcnow())

    async def speak(self, text: str, voice: str = "alloy") -> bytes:
        await self._load_model()
        return b"LOCAL_TTS_AUDIO"


# ──────────────────────────────────────────────────────────────────────────────
# VAD Service (Voice Activity Detection)
# ──────────────────────────────────────────────────────────────────────────────

class VADService:
    """Voice Activity Detection service."""

    def __init__(
        self,
        threshold: float = 0.5,
        min_speech_ms: int = 250,
        min_silence_ms: int = 500,
    ):
        self._threshold = threshold
        self._min_speech_ms = min_speech_ms
        self._min_silence_ms = min_silence_ms
        self._is_speaking = False
        self._speech_start: Optional[int] = None
        logger.info("vad_initialized", threshold=threshold)

    async def detect(self, audio_chunk: bytes) -> VoiceActivity:
        """Detect voice activity in audio chunk."""
        # In production, use silero-vad or webRTC VAD
        # Simple energy-based detection for demo

        if len(audio_chunk) < 100:
            return VoiceActivity(is_speech=False, confidence=0.0)

        # Calculate simple energy (simplified)
        energy = min(1.0, len(audio_chunk) / 10000)

        is_speech = energy > self._threshold
        confidence = energy if is_speech else (1.0 - energy)

        return VoiceActivity(
            is_speech=is_speech,
            confidence=confidence,
        )

    async def segment(self, audio_data: bytes) -> list[VoiceActivity]:
        """Segment audio into speech/non-speech regions."""
        segments = []
        chunk_size = 1600  # 100ms at 16kHz

        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i + chunk_size]
            activity = await self.detect(chunk)
            activity.start_ms = i // 16
            activity.end_ms = (i + len(chunk)) // 16
            segments.append(activity)

        return segments


# ──────────────────────────────────────────────────────────────────────────────
# Wake Word Service
# ──────────────────────────────────────────────────────────────────────────────

class WakeWordService:
    """Wake word detection service - supports 'Hey Raso' for voice-first OS control."""

    DEFAULT_WAKE_WORDS = ["hey raso", "raso", "hey jarvis", "jarvis"]

    def __init__(
        self,
        wake_words: list[str] = None,
        threshold: float = 0.8,
        sensitivity: float = 0.9,
    ):
        self._wake_words = wake_words or self.DEFAULT_WAKE_WORDS
        self._threshold = threshold
        self._sensitivity = sensitivity
        self._last_detection_time: Optional[datetime] = None
        self._cooldown_seconds = 2.0
        logger.info("wake_word_initialized", wake_words=self._wake_words, sensitivity=sensitivity)

    async def detect(self, audio_chunk: bytes) -> WakeWordResult:
        """Detect wake word in audio chunk (simulated for demo)."""
        # In production, use precise wake word model (Porcupine, Snowboy, or custom)
        # For demo, return false - actual detection happens via text

        return WakeWordResult(
            detected=False,
            wake_word="",
            confidence=0.0,
            timestamp=datetime.utcnow(),
        )

    async def detect_in_text(self, text: str) -> Optional[WakeWordResult]:
        """Detect wake word in transcribed text - primary detection method."""
        text_lower = text.lower().strip()

        # Check cooldown
        if self._last_detection_time:
            elapsed = (datetime.utcnow() - self._last_detection_time).total_seconds()
            if elapsed < self._cooldown_seconds:
                return None

        for wake_word in self._wake_words:
            # Check for exact match or word boundary match
            if text_lower == wake_word or text_lower.startswith(wake_word + " ") or " " + wake_word + " " in text_lower:
                self._last_detection_time = datetime.utcnow()
                logger.info("wake_word_detected", wake_word=wake_word, text=text[:50])
                return WakeWordResult(
                    detected=True,
                    wake_word=wake_word,
                    confidence=self._sensitivity,
                    timestamp=datetime.utcnow(),
                )

        return None

    def is_in_cooldown(self) -> bool:
        """Check if wake word is in cooldown period."""
        if not self._last_detection_time:
            return False
        elapsed = (datetime.utcnow() - self._last_detection_time).total_seconds()
        return elapsed < self._cooldown_seconds


# ──────────────────────────────────────────────────────────────────────────────
# Speaker Diarization Service
# ──────────────────────────────────────────────────────────────────────────────

class DiarizationService:
    """Speaker diarization service."""

    def __init__(self):
        self._speaker_count = 2  # Default
        logger.info("diarization_initialized")

    async def diarize(self, audio_data: bytes) -> list[SpeakerSegment]:
        """Identify different speakers in audio."""
        # In production, use pyannote.audio or resemblyzer

        # Return simulated segments
        return [
            SpeakerSegment(
                speaker_id="speaker_1",
                text="Hello, how can I help you?",
                start_ms=0,
                end_ms=2000,
                confidence=0.9,
            ),
            SpeakerSegment(
                speaker_id="speaker_2",
                text="I want to discuss the project timeline.",
                start_ms=2500,
                end_ms=5000,
                confidence=0.85,
            ),
        ]


# ──────────────────────────────────────────────────────────────────────────────
# Prosodic Analysis Service
# ──────────────────────────────────────────────────────────────────────────────

class ProsodicService:
    """Emotional/prosodic analysis service."""

    def __init__(self):
        logger.info("prosodic_service_initialized")

    async def analyze(self, audio_data: bytes, text: str = "") -> ProsodicAnalysis:
        """Analyze prosodic features."""
        # In production, use emotion detection model

        # Simple heuristic from text
        emotion = Emotion.NEUTRAL
        if text:
            text_lower = text.lower()
            if any(w in text_lower for w in ["great", "awesome", "love", "amazing"]):
                emotion = Emotion.HAPPY
            elif any(w in text_lower for w in ["worry", "concerned", "sad", "unfortunately"]):
                emotion = Emotion.SAD
            elif any(w in text_lower for w in ["!"]):
                emotion = Emotion.EXCITED
            elif any(w in text_lower for w in ["?", "confused", "unclear"]):
                emotion = Emotion.CONFUSED

        return ProsodicAnalysis(
            emotion=emotion,
            energy=0.6,
            valence=0.5,
            speaking_rate=150.0,
            pauses=[],
        )


# ──────────────────────────────────────────────────────────────────────────────
# Conversation Manager
# ──────────────────────────────────────────────────────────────────────────────

class ConversationManager:
    """Manages full-duplex voice conversation."""

    def __init__(
        self,
        stt_service: STTService,
        tts_service: TTSService,
        vad_service: VADService,
        wake_word_service: WakeWordService,
        prosodic_service: ProsodicService,
    ):
        self._stt = stt_service
        self._tts = tts_service
        self._vad = vad_service
        self._wake_word = wake_word_service
        self._prosodic = prosodic_service

        self._sessions: dict[str, VoiceSession] = {}
        self._active_session: Optional[VoiceSession] = None
        self._callback: Optional[Callable] = None

        logger.info("conversation_manager_initialized")

    def set_callback(self, callback: Callable):
        """Set callback for processing transcriptions."""
        self._callback = callback

    async def start_session(self, user_id: str) -> str:
        """Start a new voice session."""
        session_id = str(uuid.uuid4())
        session = VoiceSession(
            session_id=session_id,
            user_id=user_id,
            state=VoiceState.IDLE,
            started_at=datetime.utcnow(),
        )
        self._sessions[session_id] = session
        self._active_session = session

        logger.info("voice_session_started", session_id=session_id, user_id=user_id)
        return session_id

    async def process_audio(self, session_id: str, audio_chunk: bytes) -> Optional[Transcript]:
        """Process incoming audio and return transcription."""
        session = self._sessions.get(session_id)
        if not session:
            return None

        # Check for wake word first
        wake_result = await self._wake_word.detect(audio_chunk)
        if wake_result.detected:
            logger.info("wake_word_detected", session_id=session_id)
            session.state = VoiceState.LISTENING

        # If listening, transcribe
        if session.state == VoiceState.LISTENING:
            # VAD check
            vad_result = await self._vad.detect(audio_chunk)

            if vad_result.is_speech:
                session.state = VoiceState.PROCESSING

                # Stream to STT
                transcripts = []
                async for transcript in self._stt.stream_transcribe(audio_chunk):
                    if transcript.is_final:
                        session.current_transcript = transcript.text
                        session.conversation_history.append({
                            "role": "user",
                            "text": transcript.text,
                            "timestamp": transcript.timestamp.isoformat(),
                        })

                        # Process through callback
                        if self._callback:
                            await self._callback(session, transcript)

                        return transcript

        return None

    async def speak(self, session_id: str, text: str, voice: str = "alloy") -> AsyncIterator[TTSChunk]:
        """Speak text to user."""
        session = self._sessions.get(session_id)
        if not session:
            return

        session.state = VoiceState.SPEAKING

        # Analyze prosody of response
        prosodic = await self._prosodic.analyze(b"", text)
        session.conversation_history.append({
            "role": "assistant",
            "text": text,
            "emotion": prosodic.emotion.value,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Stream TTS
        async for chunk in self._tts.stream_speak(text, voice):
            yield chunk

        session.state = VoiceState.LISTENING

    async def interrupt(self, session_id: str):
        """Handle user interruption."""
        session = self._sessions.get(session_id)
        if session:
            session.state = VoiceState.INTERRUPTED
            session.interrupted = True
            logger.info("conversation_interrupted", session_id=session_id)

    async def end_session(self, session_id: str):
        """End voice session."""
        session = self._sessions.get(session_id)
        if session:
            session.state = VoiceState.IDLE
            logger.info("voice_session_ended", session_id=session_id)

        if self._active_session and self._active_session.session_id == session_id:
            self._active_session = None

    def get_session(self, session_id: str) -> Optional[VoiceSession]:
        """Get session info."""
        return self._sessions.get(session_id)


# ──────────────────────────────────────────────────────────────────────────────
# Continuous Audio Capture
# ──────────────────────────────────────────────────────────────────────────────

class ContinuousAudioCapture:
    """Handles continuous audio recording (with consent)."""

    def __init__(self, consent_required: bool = True):
        self._consent_required = consent_required
        self._consents: dict[str, bool] = {}
        self._recording: dict[str, bool] = {}
        self._audio_buffers: dict[str, list[bytes]] = {}
        logger.info("continuous_capture_initialized", consent_required=consent_required)

    async def check_consent(self, user_id: str) -> bool:
        """Check if user has granted consent for continuous recording."""
        if self._consent_required:
            return self._consents.get(user_id, False)
        return True

    async def grant_consent(self, user_id: str):
        """Grant consent for continuous recording."""
        self._consents[user_id] = True
        logger.info("audio_consent_granted", user_id=user_id)

    async def revoke_consent(self, user_id: str):
        """Revoke consent."""
        self._consents[user_id] = False
        self._recording[user_id] = False
        logger.info("audio_consent_revoked", user_id=user_id)

    async def start_recording(self, user_id: str) -> bool:
        """Start continuous recording."""
        if not await self.check_consent(user_id):
            logger.warning("recording_without_consent", user_id=user_id)
            return False

        self._recording[user_id] = True
        self._audio_buffers[user_id] = []
        logger.info("continuous_recording_started", user_id=user_id)
        return True

    async def stop_recording(self, user_id: str) -> bytes:
        """Stop recording and return combined audio."""
        self._recording[user_id] = False
        combined = b''.join(self._audio_buffers.get(user_id, []))
        logger.info("continuous_recording_stopped", user_id=user_id, size_bytes=len(combined))
        return combined

    async def append_audio(self, user_id: str, audio: bytes):
        """Append audio to buffer."""
        if self._recording.get(user_id):
            if user_id not in self._audio_buffers:
                self._audio_buffers[user_id] = []
            self._audio_buffers[user_id].append(audio)


# ──────────────────────────────────────────────────────────────────────────────
# Voice Service Factory
# ──────────────────────────────────────────────────────────────────────────────

class VoiceService:
    """Unified voice service combining all components."""

    def __init__(
        self,
        stt_provider: str = "openai",
        tts_provider: str = "openai",
        openai_key: Optional[str] = None,
    ):
        # Initialize services based on provider
        if stt_provider == "openai":
            self._stt = WhisperSTTService(api_key=openai_key)
        else:
            self._stt = LocalSTTService()

        if tts_provider == "openai":
            self._tts = OpenAITTSService(api_key=openai_key)
        else:
            self._tts = CoquiTTSService()

        # Initialize supporting services
        self._vad = VADService()
        self._wake_word = WakeWordService()
        self._diarization = DiarizationService()
        self._prosodic = ProsodicService()
        self._continuous = ContinuousAudioCapture()

        # Conversation manager
        self._conversation = ConversationManager(
            stt_service=self._stt,
            tts_service=self._tts,
            vad_service=self._vad,
            wake_word_service=self._wake_word,
            prosodic_service=self._prosodic,
        )

        logger.info("voice_service_initialized", stt=stt_provider, tts=tts_provider)

    @property
    def conversation_manager(self) -> ConversationManager:
        return self._conversation

    @property
    def continuous_capture(self) -> ContinuousAudioCapture:
        return self._continuous

    @property
    def diarization(self) -> DiarizationService:
        return self._diarization

    async def transcribe(self, audio_data: bytes) -> Transcript:
        """Quick transcription helper."""
        return await self._stt.transcribe(audio_data)

    async def speak(self, text: str, voice: str = "alloy") -> AsyncIterator[TTSChunk]:
        """Quick speak helper."""
        async for chunk in self._tts.stream_speak(text, voice):
            yield chunk


def create_voice_service(
    stt_provider: str = "openai",
    tts_provider: str = "openai",
    openai_key: Optional[str] = None,
) -> VoiceService:
    """Factory function to create voice service."""
    return VoiceService(
        stt_provider=stt_provider,
        tts_provider=tts_provider,
        openai_key=openai_key,
    )