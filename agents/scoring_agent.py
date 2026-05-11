"""
RasoSpeak v2 — ScoringAgent
Uses external LLM APIs (no GPU required)
Works on 4GB RAM with streaming support
"""

import json
import logging
import time
import asyncio
from typing import Optional, AsyncIterator

from .base_agent import BaseAgent
from .llm_client import create_llm_client, LLMClient
from config.settings import settings
from config.prompts import SCORING_SYSTEM, scoring_user_prompt

log = logging.getLogger("rasospeak.scoring")


class ScoringAgent(BaseAgent):
    """
    Agent 2: ScoringAgent

    Uses external LLM APIs (Google Gemini, NVIDIA NIM, OpenAI, Anthropic, etc.)
    to evaluate speech. No GPU needed - runs entirely via API calls.

    Supports streaming for real-time feedback.
    """

    name = "ScoringAgent"

    def __init__(self):
        self._llm_client: Optional[LLMClient] = None

    async def initialize(self):
        """Initialize LLM client."""
        log.info(f"Initializing ScoringAgent with provider: {settings.DEFAULT_PROVIDER}")
        self._llm_client = create_llm_client(settings.DEFAULT_PROVIDER)
        log.info(f"✅ ScoringAgent ready (API mode, no GPU)")

    async def cleanup(self):
        """Cleanup resources."""
        if self._llm_client:
            await self._llm_client.close()

    async def score_speech(
        self,
        transcript: str,
        reference: str,
        provider: str = None,
    ) -> dict:
        """
        Score a speech transcript against a reference.

        Args:
            transcript: What the user actually said
            reference: What they should have said
            provider: Override default provider

        Returns:
            {
                "accuracy": 0.85,
                "fluency": 0.78,
                "completeness": 0.92,
                "overall": 0.85,
                "feedback": "Great job! ...",
            }
        """
        t_start = time.perf_counter()

        if not self._llm_client:
            return {"error": "LLM client not initialized"}

        # Create client for specific provider if provided
        client = create_llm_client(provider) if provider else self._llm_client

        messages = [
            {"role": "system", "content": SCORING_SYSTEM},
            {"role": "user", "content": scoring_user_prompt.format(
                reference=reference,
                transcript=transcript
            )}
        ]

        try:
            result = await client.chat(messages, temperature=0.15, max_tokens=512)
            elapsed_ms = int((time.perf_counter() - t_start) * 1000)

            # Parse the JSON response
            try:
                scores = json.loads(result["content"])
                return {
                    "accuracy": scores.get("accuracy", 0.5),
                    "fluency": scores.get("fluency", 0.5),
                    "completeness": scores.get("completeness", 0.5),
                    "overall": scores.get("overall", 0.5),
                    "feedback": scores.get("feedback", ""),
                    "provider": provider or settings.DEFAULT_PROVIDER,
                    "processing_ms": elapsed_ms,
                }
            except json.JSONDecodeError:
                # If not JSON, return as feedback
                return {
                    "accuracy": 0.5,
                    "fluency": 0.5,
                    "completeness": 0.5,
                    "overall": 0.5,
                    "feedback": result["content"],
                    "provider": provider or settings.DEFAULT_PROVIDER,
                    "processing_ms": elapsed_ms,
                }
        except Exception as e:
            log.error(f"Scoring failed: {e}")
            return {"error": str(e)}

    async def score_speech_streaming(
        self,
        transcript: str,
        reference: str,
        provider: str = None,
    ) -> AsyncIterator[dict]:
        """
        Score speech with streaming feedback.
        Yields partial results as they come in.
        """
        if not self._llm_client:
            yield {"error": "LLM client not initialized"}
            return

        client = create_llm_client(provider) if provider else self._llm_client

        messages = [
            {"role": "system", "content": SCORING_SYSTEM},
            {"role": "user", "content": scoring_user_prompt.format(
                reference=reference,
                transcript=transcript
            )}
        ]

        try:
            # Stream the response
            async for chunk in client.chat(messages, temperature=0.15, max_tokens=512, stream=True):
                yield {"partial": chunk, "type": "stream"}
        except Exception as e:
            yield {"error": str(e)}


class StreamingScoringAgent(ScoringAgent):
    """ScoringAgent with built-in streaming support."""

    async def score_with_streaming(self, transcript: str, reference: str) -> dict:
        """Score and stream feedback simultaneously."""
        result = await self.score_speech(transcript, reference)
        return result