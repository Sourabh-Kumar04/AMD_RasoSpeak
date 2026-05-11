"""
RasoSpeak v2 — SegmentationAgent
Qwen2.5-3B-Instruct on vLLM for intelligent script chunking.
"""

import json
import logging
import time

import httpx

from .base_agent import BaseAgent
from config.settings import settings
from config.prompts import SEGMENTATION_SYSTEM, segmentation_user_prompt

log = logging.getLogger("rasospeak.segmentation")


class SegmentationAgent(BaseAgent):
    """
    Agent 4: SegmentationAgent

    Uses a small LLM (Qwen2.5-3B) to intelligently chunk a script.
    Understands sentence structure, rhetorical pauses, and emphasis.
    Falls back to word-count splitting if vLLM unavailable.
    """

    name = "SegmentationAgent"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def initialize(self):
        self._client = httpx.AsyncClient(
            base_url=settings.vllm_base_url,
            timeout=settings.llm_timeout_seconds,
        )
        log.info(f"SegmentationAgent using {settings.segmentation_model}")

    async def segment(
        self,
        script:            str,
        target_chunk_size: int = 8,
        style:             str = "presentation",
    ) -> dict:
        """
        Segment a script into earpiece-friendly chunks using an LLM.

        Returns SegmentResult dict with enriched chunk metadata.
        """
        t_start = time.perf_counter()
        user_prompt = segmentation_user_prompt(script, target_chunk_size, style)

        try:
            result = await self._call_vllm(
                system=SEGMENTATION_SYSTEM,
                user=user_prompt,
                max_tokens=settings.segmentation_max_tokens,
            )
            parsed  = json.loads(result)
            elapsed = int((time.perf_counter() - t_start) * 1000)
            log.info(f"Segmented {parsed['total_chunks']} chunks in {elapsed}ms")
            return {**parsed, "processing_ms": elapsed}

        except Exception as e:
            log.warning(f"SegmentationAgent fallback: {e}")
            return self._fallback_segment(script, target_chunk_size, t_start)

    async def _call_vllm(self, system: str, user: str, max_tokens: int) -> str:
        if self._client is None:
            raise RuntimeError("SegmentationAgent not initialized")

        payload = {
            "model":       settings.segmentation_model,
            "messages":    [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "max_tokens":  max_tokens,
            "temperature": 0.1,   # very low — we want deterministic chunking
            "stream":      False,
        }
        resp = await self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    def _fallback_segment(self, script: str, target: int, t_start: float) -> dict:
        """Word-count fallback — same logic as v1 but returns enriched format."""
        words  = script.replace("\n", " ").split()
        chunks = []
        i, idx = 0, 1

        while i < len(words):
            end   = min(i + target, len(words))
            # Try to break at sentence boundary
            if end < len(words):
                for j in range(min(end + 3, len(words)), max(i + 2, end - 3), -1):
                    if words[j - 1].endswith((".", "!", "?")):
                        end = j
                        break
            # Absorb tiny orphan
            if len(words) - end < 3 and end < len(words):
                end = len(words)

            text = " ".join(words[i:end])
            chunks.append({
                "id":                   idx,
                "text":                 text,
                "word_count":           end - i,
                "type":                 "statement",
                "emphasis_words":       [],
                "suggested_pace":       "normal",
                "breathing_pause_after":True,
            })
            i   += end - i
            idx += 1

        total_words = len(words)
        elapsed     = int((time.perf_counter() - t_start) * 1000)
        return {
            "chunks":                     chunks,
            "total_chunks":               len(chunks),
            "total_words":                total_words,
            "estimated_duration_minutes": round(total_words / 130, 1),
            "processing_ms":              elapsed,
        }

    async def shutdown(self):
        if self._client:
            await self._client.aclose()
        log.info("SegmentationAgent shut down")
