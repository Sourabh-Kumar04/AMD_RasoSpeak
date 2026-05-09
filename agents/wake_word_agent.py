"""
RasoSpeak v2 — Wake Word Agent
Detects "Hey Raso" wake word and activates the AI partner.

Uses Web Speech API or Whisper to continuously listen for wake word.
"""

import asyncio
import base64
import json
import logging
import time
from typing import Optional, Callable

import numpy as np

from .base_agent import BaseAgent
from config.settings import settings

log = logging.getLogger("rasospeak.wakeword")


class WakeWordAgent(BaseAgent):
    """
    Agent that listens for "Hey Raso" wake word.

    Uses streaming audio analysis to detect the wake phrase.
    When detected, activates the PartnerAgent for voice interaction.

    The system can run in two modes:
    1. Browser-side (Web Speech API) - simpler, less accurate
    2. Server-side (Whisper) - more accurate, runs on AMD GPU
    """

    name = "WakeWordAgent"

    def __init__(self):
        self._is_listening = False
        self._wake_word = "raso"  # Detect "Hey Raso"
        self._activation_callback: Optional[Callable] = None
        self._model = None
        self._threshold = 0.5  # Confidence threshold for wake word

    async def initialize(self):
        """Initialize wake word detection."""
        log.info(f"✅ WakeWordAgent initialized (listening for 'Hey Raso')")

    def set_activation_callback(self, callback: Callable):
        """Set callback to call when wake word is detected."""
        self._activation_callback = callback

    async def start_listening(self) -> dict:
        """Start listening for wake word."""
        self._is_listening = True
        log.info("👂 Wake word listening STARTED")
        return {"status": "listening", "wake_word": "Hey Raso"}

    async def stop_listening(self) -> dict:
        """Stop listening for wake word."""
        self._is_listening = False
        log.info("🔇 Wake word listening STOPPED")
        return {"status": "stopped"}

    async def process_audio(
        self,
        audio_b64: str,
        sample_rate: int = 16000,
    ) -> dict:
        """
        Process incoming audio for wake word detection.

        This is called continuously from the frontend when in wake mode.
        """
        if not self._is_listening:
            return {"wake_detected": False}

        try:
            # Decode audio
            audio_bytes = base64.b64decode(audio_b64)
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

            # Simple energy-based wake detection (fallback)
            # In production, would use a proper wake word model
            rms = float(np.sqrt(np.mean(audio_array ** 2)))

            # Check for speech activity (rough detection)
            if rms > 0.02:  # Sound detected
                # In full implementation, would pass to Whisper or wake model
                # For now, we'll handle detection on client side
                return {
                    "wake_detected": False,
                    "audio_level": rms,
                    "status": "detecting"
                }

            return {"wake_detected": False, "audio_level": rms}

        except Exception as e:
            log.error(f"Wake word detection error: {e}")
            return {"wake_detected": False, "error": str(e)}

    def activate_partner(self):
        """Called when wake word is detected - activates the partner."""
        log.info("🎯 WAKE WORD DETECTED! Activating Partner...")

        if self._activation_callback:
            asyncio.create_task(self._activation_callback())

        return {
            "activated": True,
            "message": "I'm here! What would you like to talk about?"
        }

    def is_listening(self) -> bool:
        """Check if currently listening for wake word."""
        return self._is_listening

    async def shutdown(self):
        self._is_listening = False
        log.info("WakeWordAgent shut down")


# WebSocket message type for wake word
def check_for_wake_word(transcript: str) -> bool:
    """Check if transcript contains wake word 'Hey Raso'."""
    wake_phrases = ["hey raso", "hey raso,", "raso", "hey raso "]
    transcript_lower = transcript.lower().strip()

    for phrase in wake_phrases:
        if phrase in transcript_lower:
            return True
    return False


def extract_command_after_wake(transcript: str) -> str:
    """Extract the actual command after wake word."""
    transcript_lower = transcript.lower()

    # Remove wake word from command
    for phrase in ["hey raso", "hey raso,", "hey raso "]:
        if phrase in transcript_lower:
            command = transcript_lower.replace(phrase, "").strip()
            return command

    return transcript_lower.strip()