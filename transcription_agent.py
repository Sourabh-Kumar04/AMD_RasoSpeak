"""
RasoSpeak v2 — TranscriptionAgent
Whisper Large v3 running via faster-whisper on AMD MI300X (ROCm).

Why Whisper over Web Speech API:
- Whisper Large v3: ~3% WER (word error rate) on English
- Web Speech API: ~8–15% WER, varies by browser
- Whisper handles accents, filler words, noisy environments
- AMD MI300X makes inference fast enough for real-time use (~400ms/chunk)
"""

import asyncio
import base64
import io
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .base_agent import BaseAgent
from config.settings import settings

log = logging.getLogger("rasospeak.transcription")


class TranscriptionAgent(BaseAgent):
    """
    Agent 1: TranscriptionAgent
    
    Converts speech audio to text using Whisper Large v3.
    Runs on AMD MI300X GPU via ROCm through CTranslate2 backend.
    
    Pipeline:
        base64 audio → decode → numpy array → Whisper → transcript + timestamps
    """

    name = "TranscriptionAgent"

    def __init__(self):
        self.model    = None
        self._executor = ThreadPoolExecutor(max_workers=2)  # parallel transcription

    async def initialize(self):
        """Load Whisper model onto AMD GPU. Called once at startup."""
        log.info(f"Loading Whisper {settings.WHISPER_MODEL} on {settings.WHISPER_DEVICE} (ROCm)...")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, self._load_model)
        log.info(f"✅ Whisper {settings.WHISPER_MODEL} loaded")

    def _load_model(self):
        """Blocking model load — runs in thread pool."""
        try:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(
                model_size_or_path=settings.WHISPER_MODEL,
                device=settings.WHISPER_DEVICE,          # "cuda" = ROCm on AMD
                compute_type=settings.WHISPER_COMPUTE_TYPE,  # float16 for MI300X
                num_workers=2,
            )
        except ImportError:
            log.warning("faster_whisper not installed — using mock transcription")
            self.model = None

    async def transcribe(
        self,
        audio_b64: str,
        sample_rate: int = 16000,
        language: str = "en",
    ) -> dict:
        """
        Transcribe base64-encoded audio to text.
        
        Args:
            audio_b64:   Base64-encoded raw PCM audio bytes (16-bit, mono)
            sample_rate: Audio sample rate (default 16000 for Whisper)
            language:    Language code ("en" for English)
            
        Returns:
            TranscriptResult dict with transcript, confidence, word timestamps
        """
        t_start = time.perf_counter()

        # Decode audio
        audio_bytes = base64.b64decode(audio_b64)
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        if self.model is None:
            # Development fallback — no GPU available
            return self._mock_transcript(audio_array, t_start)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: self._run_whisper(audio_array, language)
        )

        elapsed_ms = int((time.perf_counter() - t_start) * 1000)
        log.debug(f"Transcription: '{result['transcript'][:50]}...' in {elapsed_ms}ms")

        return {
            **result,
            "is_final":      True,
            "processing_ms": elapsed_ms,
        }

    def _run_whisper(self, audio: np.ndarray, language: str) -> dict:
        """Run Whisper inference on AMD GPU. Blocking — called in executor."""
        segments, info = self.model.transcribe(
            audio,
            language=language,
            beam_size=settings.WHISPER_BEAM_SIZE,
            vad_filter=settings.WHISPER_VAD_FILTER,
            word_timestamps=True,
            condition_on_previous_text=False,  # faster for short chunks
        )

        transcript_parts = []
        words = []
        confidences = []

        for segment in segments:
            transcript_parts.append(segment.text.strip())
            if segment.words:
                for w in segment.words:
                    words.append({
                        "word":       w.word.strip(),
                        "start":      round(w.start, 3),
                        "end":        round(w.end, 3),
                        "confidence": round(w.probability, 3),
                    })
                    confidences.append(w.probability)

        transcript  = " ".join(transcript_parts).strip()
        avg_conf    = float(np.mean(confidences)) if confidences else 0.0
        language_detected = info.language if info else language

        return {
            "transcript":  transcript,
            "confidence":  round(avg_conf, 3),
            "words":       words,
            "language":    language_detected,
        }

    def _mock_transcript(self, audio: np.ndarray, t_start: float) -> dict:
        """Fallback when Whisper is not available (development mode)."""
        elapsed_ms = int((time.perf_counter() - t_start) * 1000)
        # Detect silence
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < 0.01:
            return {
                "transcript":    "",
                "is_final":      True,
                "confidence":    0.0,
                "words":         [],
                "language":      "en",
                "processing_ms": elapsed_ms,
            }
        return {
            "transcript":    "[mock transcript — Whisper not loaded]",
            "is_final":      True,
            "confidence":    0.5,
            "words":         [],
            "language":      "en",
            "processing_ms": elapsed_ms,
        }

    async def shutdown(self):
        self._executor.shutdown(wait=False)
        self.model = None
        log.info("TranscriptionAgent shut down")
