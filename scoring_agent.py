"""
RasoSpeak v2 — ScoringAgent
Qwen2.5-7B-Instruct on vLLM (ROCm backend) for intelligent speech scoring.

Why LLM scoring over rule-based NLP:
- Understands semantic equivalence ("gonna" = "going to")
- Handles paraphrasing intelligently
- Ignores filler words without hardcoding
- Returns structured multi-dimensional scores
- Gives natural language feedback
"""

import json
import logging
import time

import httpx

from .base_agent import BaseAgent
from config.settings import settings
from config.prompts import SCORING_SYSTEM, scoring_user_prompt

log = logging.getLogger("rasospeak.scoring")


class ScoringAgent(BaseAgent):
    """
    Agent 2: ScoringAgent

    Uses Qwen2.5-7B-Instruct (via vLLM on AMD ROCm) to evaluate
    how well a presenter delivered a script chunk.

    Returns structured scores: accuracy, fluency, completeness, overall.
    Much smarter than Levenshtein — understands meaning, not just characters.
    """

    name = "ScoringAgent"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def initialize(self):
        self._client = httpx.AsyncClient(
            base_url=settings.VLLM_BASE_URL,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
        # Verify vLLM is reachable
        try:
            resp = await self._client.get("/models")
            if resp.status_code == 200:
                log.info(f"✅ vLLM connected at {settings.VLLM_BASE_URL}")
            else:
                log.warning(f"vLLM returned {resp.status_code} — using mock mode")
        except Exception as e:
            log.warning(f"vLLM not reachable ({e}) — using mock scoring")

    async def score(
        self,
        expected:        str,
        spoken:          str,
        strict_level:    int  = 3,
        user_weak_words: list = None,
    ) -> dict:
        """
        Score a presenter's delivery against the expected chunk.

        Args:
            expected:        The exact chunk text the presenter should say
            spoken:          What Whisper transcribed from the presenter
            strict_level:    2=lenient, 3=normal, 4=strict
            user_weak_words: Historical weak spots for this user

        Returns:
            ScoreResult dict with dimensions + pass/fail + feedback
        """
        t_start = time.perf_counter()
        weak_words = user_weak_words or []

        user_prompt = scoring_user_prompt(expected, spoken, strict_level, weak_words)

        try:
            result = await self._call_vllm(
                system=SCORING_SYSTEM,
                user=user_prompt,
                max_tokens=settings.SCORING_MAX_TOKENS,
            )
            parsed = json.loads(result)

            # Ensure "passed" is set correctly based on threshold
            threshold = settings.PASS_THRESHOLDS.get(strict_level, 55)
            parsed["passed"] = parsed.get("overall", 0) >= threshold

            elapsed_ms = int((time.perf_counter() - t_start) * 1000)
            log.debug(f"Scored: overall={parsed.get('overall')} passed={parsed.get('passed')} in {elapsed_ms}ms")

            return {**parsed, "processing_ms": elapsed_ms}

        except (json.JSONDecodeError, KeyError) as e:
            log.warning(f"Scoring parse error: {e} — falling back to rule-based")
            return self._fallback_score(expected, spoken, strict_level, t_start)

        except Exception as e:
            log.error(f"Scoring error: {e}")
            return self._fallback_score(expected, spoken, strict_level, t_start)

    async def _call_vllm(self, system: str, user: str, max_tokens: int) -> str:
        """Call vLLM OpenAI-compatible API."""
        if self._client is None:
            raise RuntimeError("ScoringAgent not initialized")

        payload = {
            "model":       settings.SCORING_MODEL,
            "messages":    [
                {"role": "system",  "content": system},
                {"role": "user",    "content": user},
            ],
            "max_tokens":  max_tokens,
            "temperature": settings.LLM_TEMPERATURE,
            "stream":      False,
        }

        resp = await self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def _fallback_score(
        self,
        expected: str,
        spoken: str,
        strict_level: int,
        t_start: float,
    ) -> dict:
        """
        Rule-based fallback if vLLM is unavailable.
        Uses Levenshtein + keyword matching (same as v1, but only as backup).
        """
        from difflib import SequenceMatcher

        if not spoken or len(spoken.strip()) < 2:
            elapsed = int((time.perf_counter() - t_start) * 1000)
            return {
                "accuracy": 0, "fluency": 0, "completeness": 0, "overall": 0,
                "passed": False, "missing_concepts": [], "extra_concepts": [],
                "feedback_brief": "No speech detected.",
                "processing_ms": elapsed,
            }

        ratio    = SequenceMatcher(None, expected.lower(), spoken.lower()).ratio()
        score    = int(ratio * 100)
        threshold = settings.PASS_THRESHOLDS.get(strict_level, 55)
        elapsed  = int((time.perf_counter() - t_start) * 1000)

        return {
            "accuracy":         score,
            "fluency":          min(score + 8, 100),
            "completeness":     score,
            "overall":          score,
            "passed":           score >= threshold,
            "missing_concepts": [],
            "extra_concepts":   [],
            "feedback_brief":   f"{'Good delivery.' if score >= threshold else 'Needs improvement.'}",
            "processing_ms":    elapsed,
        }

    async def shutdown(self):
        if self._client:
            await self._client.aclose()
        log.info("ScoringAgent shut down")
