"""
RasoSpeak v2 — CoachingAgent
Qwen2.5-7B-Instruct on vLLM/ROCm for personalized coaching interventions.

Activates only when ScoringAgent returns passed=False.
Generates earpiece-ready corrections tailored to mode + attempt count.
"""

import json
import logging
import time

import httpx

from .base_agent import BaseAgent
from config.settings import settings
from config.prompts import (
    COACHING_SYSTEM, coaching_user_prompt,
    INSIGHTS_SYSTEM, insights_user_prompt,
)

log = logging.getLogger("rasospeak.coaching")


class CoachingAgent(BaseAgent):
    """
    Agent 3: CoachingAgent

    Generates personalized corrections when a presenter misses a chunk.
    Three modes:
      - silent: just replay (no verbal coaching)
      - hint:   short keyword prompt ("remember: 'real-time'")
      - full:   full sentence replay with gentle prefix

    Also generates end-of-session AI insights for the stats dashboard.
    """

    name = "CoachingAgent"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def initialize(self):
        self._client = httpx.AsyncClient(
            base_url=settings.VLLM_BASE_URL,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
        log.info(f"CoachingAgent using {settings.COACHING_MODEL}")

    async def coach(
        self,
        expected:        str,
        spoken:          str,
        score:           dict,
        mode:            str  = "hint",
        attempt_number:  int  = 1,
        user_weak_words: list = None,
    ) -> dict:
        """
        Generate a coaching intervention for a failed chunk.

        Args:
            expected:       What the presenter should have said
            spoken:         What they actually said (from Whisper)
            score:          ScoreResult from ScoringAgent
            mode:           Correction mode (silent/hint/full)
            attempt_number: How many tries on this chunk so far
            user_weak_words:Historical weak words for this user

        Returns:
            CoachResult dict with tts_text, display_text, strategy
        """
        t_start    = time.perf_counter()
        weak_words = user_weak_words or []

        # Silent mode: just replay, no LLM needed
        if mode == "silent":
            elapsed = int((time.perf_counter() - t_start) * 1000)
            return {
                "strategy":        "replay",
                "tts_text":        expected,
                "display_text":    "Replaying chunk...",
                "missed_concepts": score.get("missing_concepts", []),
                "encouragement":   "",
                "auto_skip":       attempt_number >= settings.MAX_ATTEMPTS_BEFORE_SKIP,
                "processing_ms":   elapsed,
            }

        # Auto-skip after too many attempts
        if attempt_number >= settings.MAX_ATTEMPTS_BEFORE_SKIP:
            elapsed = int((time.perf_counter() - t_start) * 1000)
            return {
                "strategy":        "skip",
                "tts_text":        "Moving on. You've got this.",
                "display_text":    f"Auto-advancing after {attempt_number} attempts. Keep going!",
                "missed_concepts": score.get("missing_concepts", []),
                "encouragement":   "Every session you improve.",
                "auto_skip":       True,
                "processing_ms":   elapsed,
            }

        user_prompt = coaching_user_prompt(
            expected, spoken, score, mode, attempt_number, weak_words
        )

        try:
            result = await self._call_vllm(
                system=COACHING_SYSTEM,
                user=user_prompt,
                max_tokens=settings.COACHING_MAX_TOKENS,
            )
            parsed = json.loads(result)
            elapsed = int((time.perf_counter() - t_start) * 1000)
            log.debug(f"Coaching: strategy={parsed.get('strategy')} in {elapsed}ms")
            return {**parsed, "auto_skip": False, "processing_ms": elapsed}

        except Exception as e:
            log.warning(f"CoachingAgent fallback: {e}")
            return self._fallback_coach(expected, score, mode, attempt_number, t_start)

    async def generate_session_insights(self, session: dict) -> dict:
        """
        Generate AI insights for the end-of-session stats dashboard.
        Uses Qwen to produce personalized, actionable feedback.
        """
        t_start = time.perf_counter()
        user_prompt = insights_user_prompt(session)

        try:
            result = await self._call_vllm(
                system=INSIGHTS_SYSTEM,
                user=user_prompt,
                max_tokens=768,
            )
            parsed = json.loads(result)
            elapsed = int((time.perf_counter() - t_start) * 1000)
            log.info(f"Session insights generated in {elapsed}ms")
            return parsed

        except Exception as e:
            log.warning(f"Insights generation failed: {e}")
            stats = session.get("stats", {})
            avg   = stats.get("avg_accuracy", 0)
            return {
                "overall_assessment": f"You completed {stats.get('chunks_done', 0)} chunks with {avg:.0f}% average accuracy.",
                "strengths":          ["Completed the session", "Maintained consistent delivery"],
                "improvements":       ["Focus on key technical terms", "Practice problematic chunks"],
                "focus_words":        session.get("weak_words", [])[:5],
                "recommended_mode":   "hint" if avg < 70 else "silent",
                "encouragement":      "Every session makes you more confident on stage.",
            }

    async def _call_vllm(self, system: str, user: str, max_tokens: int) -> str:
        if self._client is None:
            raise RuntimeError("CoachingAgent not initialized")

        payload = {
            "model":       settings.COACHING_MODEL,
            "messages":    [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "max_tokens":  max_tokens,
            "temperature": settings.LLM_TEMPERATURE,
            "stream":      False,
        }
        resp = await self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    def _fallback_coach(
        self,
        expected: str,
        score: dict,
        mode: str,
        attempt: int,
        t_start: float,
    ) -> dict:
        """Rule-based fallback when vLLM is unavailable."""
        elapsed  = int((time.perf_counter() - t_start) * 1000)
        missing  = score.get("missing_concepts", [])
        prefixes = ["Try again: ", "Once more: ", "Last chance: ", "Let's do this: "]
        prefix   = prefixes[min(attempt - 1, len(prefixes) - 1)]

        if mode == "hint" and missing:
            return {
                "strategy":        "hint",
                "tts_text":        f"Remember: {', '.join(missing[:3])}",
                "display_text":    f"Missed: {', '.join(missing[:3])}",
                "missed_concepts": missing,
                "encouragement":   "You're getting there!",
                "auto_skip":       False,
                "processing_ms":   elapsed,
            }
        return {
            "strategy":        "full",
            "tts_text":        prefix + expected,
            "display_text":    f"Attempt {attempt}: {prefix.lower()}{expected}",
            "missed_concepts": missing,
            "encouragement":   "Almost there!",
            "auto_skip":       False,
            "processing_ms":   elapsed,
        }

    async def shutdown(self):
        if self._client:
            await self._client.aclose()
        log.info("CoachingAgent shut down")
