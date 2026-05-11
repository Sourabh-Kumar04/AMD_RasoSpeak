"""
RasoSpeak v2 — CoachingAgent
Uses external LLM APIs for personalized coaching (no GPU)
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

log = logging.getLogger("rasospeak.coaching")

COACHING_SYSTEM = """You are Raso, a friendly and encouraging speech coach.
Your goal is to help users improve their speaking skills through practice.
Provide positive, actionable feedback that helps them improve.
Keep responses concise and encouraging."""


class CoachingAgent(BaseAgent):
    """
    Agent 3: CoachingAgent

    Uses external LLM APIs to generate personalized coaching.
    No GPU required - runs on 4GB RAM via API calls.

    Provides:
    - Real-time feedback during speech practice
    - Encouragement based on progress
    - Session summaries with improvement tips
    """

    name = "CoachingAgent"

    def __init__(self):
        self._llm_client: Optional[LLMClient] = None

    async def initialize(self):
        """Initialize LLM client."""
        log.info(f"Initializing CoachingAgent with provider: {settings.default_provider}")
        self._llm_client = create_llm_client(settings.default_provider)
        log.info(f"✅ CoachingAgent ready (API mode, no GPU)")

    async def cleanup(self):
        """Cleanup resources."""
        if self._llm_client:
            await self._llm_client.close()

    async def generate_feedback(
        self,
        transcript: str,
        reference: str,
        scores: dict = None,
        provider: str = None,
    ) -> dict:
        """
        Generate coaching feedback based on transcript and scores.

        Args:
            transcript: What user said
            reference: Target script
            scores: Optional scores from ScoringAgent
            provider: Override default provider

        Returns:
            {"feedback": "...", "strategy": "encourage|correct|advance"}
        """
        if not self._llm_client:
            return {"error": "LLM client not initialized"}

        client = create_llm_client(provider) if provider else self._llm_client

        # Build context
        context = f"Reference: {reference}\nTranscript: {transcript}\n"
        if scores:
            context += f"Scores: Accuracy={scores.get('accuracy', 0):.0%}, "
            context += f"Fluency={scores.get('fluency', 0):.0%}, "
            context += f"Overall={scores.get('overall', 0):.0%}\n"

        messages = [
            {"role": "system", "content": COACHING_SYSTEM},
            {"role": "user", "content": f"Provide coaching feedback for this speech practice:\n\n{context}"}
        ]

        try:
            result = await client.chat(messages, temperature=0.15, max_tokens=768)

            # Try to parse as JSON
            try:
                feedback_data = json.loads(result["content"])
                return {
                    "feedback": feedback_data.get("feedback", result["content"]),
                    "strategy": feedback_data.get("strategy", "encourage"),
                    "tts_text": feedback_data.get("tts_text", feedback_data.get("feedback", "")),
                    "display_text": feedback_data.get("display_text", feedback_data.get("feedback", "")),
                    "provider": provider or settings.default_provider,
                }
            except json.JSONDecodeError:
                return {
                    "feedback": result["content"],
                    "strategy": "encourage",
                    "tts_text": result["content"],
                    "display_text": result["content"],
                    "provider": provider or settings.default_provider,
                }
        except Exception as e:
            log.error(f"Feedback generation failed: {e}")
            return {"error": str(e)}

    async def generate_feedback_streaming(
        self,
        transcript: str,
        reference: str,
        scores: dict = None,
        provider: str = None,
    ) -> AsyncIterator[dict]:
        """
        Generate coaching feedback with streaming.
        Useful for real-time speech coaching.
        """
        if not self._llm_client:
            yield {"error": "LLM client not initialized"}
            return

        client = create_llm_client(provider) if provider else self._llm_client

        context = f"Reference: {reference}\nTranscript: {transcript}\n"
        if scores:
            context += f"Scores: Accuracy={scores.get('accuracy', 0):.0%}, "
            context += f"Fluency={scores.get('fluency', 0):.0%}, "
            context += f"Overall={scores.get('overall', 0):.0%}\n"

        messages = [
            {"role": "system", "content": COACHING_SYSTEM},
            {"role": "user", "content": f"Provide coaching feedback:\n\n{context}"}
        ]

        try:
            full_text = ""
            async for chunk in client.chat(messages, temperature=0.15, max_tokens=768, stream=True):
                full_text += chunk
                yield {"partial": chunk, "type": "stream", "accumulated": full_text}
        except Exception as e:
            yield {"error": str(e)}

    async def generate_encouragement(
        self,
        progress: dict,
        provider: str = None,
    ) -> dict:
        """Generate encouragement based on user progress."""
        if not self._llm_client:
            return {"error": "LLM client not initialized"}

        client = create_llm_client(provider) if provider else self._llm_client

        messages = [
            {"role": "system", "content": COACHING_SYSTEM},
            {"role": "user", "content": f"Generate an encouraging message for a user who has done {progress.get('chunks_done', 0)} out of {progress.get('total_chunks', 0)} chunks with {progress.get('avg_accuracy', 0):.0%} average accuracy and {progress.get('avg_wpm', 0)} WPM."}
        ]

        try:
            result = await client.chat(messages, temperature=0.3, max_tokens=256)
            return {
                "encouragement": result["content"],
                "provider": provider or settings.default_provider,
            }
        except Exception as e:
            return {"error": str(e)}

    async def generate_session_insights(
        self,
        session_data: dict,
        provider: str = None,
    ) -> dict:
        """Generate AI-powered insights from a session."""
        if not self._llm_client:
            return {"error": "LLM client not initialized"}

        client = create_llm_client(provider) if provider else self._llm_client

        # Summarize session
        total_chunks = session_data.get("stats", {}).get("total_chunks", 0)
        avg_accuracy = session_data.get("stats", {}).get("avg_accuracy", 0)
        avg_wpm = session_data.get("stats", {}).get("avg_wpm", 0)
        weak_words = session_data.get("weak_words", [])

        messages = [
            {"role": "system", "content": "You are a speech coaching expert."},
            {"role": "user", "content": f"Provide insights from a speech practice session with {total_chunks} chunks, {avg_accuracy:.0%} average accuracy, {avg_wpm} WPM. Problem words: {', '.join(weak_words[:10]) if weak_words else 'none'}."}
        ]

        try:
            result = await client.chat(messages, temperature=0.15, max_tokens=512)
            return {
                "insights": result["content"],
                "provider": provider or settings.default_provider,
            }
        except Exception as e:
            return {"error": str(e)}