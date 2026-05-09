"""
RasoSpeak v2 — Q&A Agent
Multi-provider AI question answering with streaming TTS output.

Supports: OpenAI GPT, Anthropic Claude, Google Gemini, xAI Grok
Streams answers to user's earpiece in real-time.
"""

import asyncio
import json
import logging
import time
from typing import AsyncIterator, Optional

import httpx

from .base_agent import BaseAgent
from config.settings import settings

log = logging.getLogger("rasospeak.qa")


class QAProvider(str):
    """Supported AI providers for Q&A."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    XAI = "xai"
    QWEN_LOCAL = "qwen_local"


class QAAgent(BaseAgent):
    """
    Agent for real-time question answering via external AI APIs.

    Connects to multiple AI providers and streams responses
    directly to the user's earpiece via TTS.

    Uses SharedMemoryAgent to:
    - Remember conversation history
    - Get user context for personalized responses
    - Store important facts
    - Track weak words for coaching
    """

    name = "QAAgent"

    def __init__(self):
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._default_provider = settings.QA_DEFAULT_PROVIDER
        self._shared_memory = None

    async def initialize(self):
        """Initialize HTTP clients for each provider."""
        log.info(f"Initializing QAAgent with provider: {self._default_provider}")

        # Initialize clients based on available API keys
        if settings.OPENAI_API_KEY:
            self._clients[QAProvider.OPENAI] = httpx.AsyncClient(
                base_url="https://api.openai.com/v1",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                timeout=60.0,
            )
            log.info("✅ OpenAI client initialized")

        if settings.ANTHROPIC_API_KEY:
            self._clients[QAProvider.ANTHROPIC] = httpx.AsyncClient(
                base_url="https://api.anthropic.com/v1",
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                timeout=60.0,
            )
            log.info("✅ Anthropic client initialized")

        if settings.GOOGLE_API_KEY:
            self._clients[QAProvider.GOOGLE] = httpx.AsyncClient(
                base_url="https://generativelanguage.googleapis.com/v1beta",
                headers={"Authorization": f"Bearer {settings.GOOGLE_API_KEY}"},
                timeout=60.0,
            )
            log.info("✅ Google Gemini client initialized")

        if settings.XAI_API_KEY:
            self._clients[QAProvider.XAI] = httpx.AsyncClient(
                base_url="https://api.x.ai/v1",
                headers={"Authorization": f"Bearer {settings.XAI_API_KEY}"},
                timeout=60.0,
            )
            log.info("✅ xAI Grok client initialized")

        # Always available: local Qwen via vLLM
        if settings.VLLM_BASE_URL:
            self._clients[QAProvider.QWEN_LOCAL] = httpx.AsyncClient(
                base_url=settings.VLLM_BASE_URL,
                timeout=60.0,
            )
            log.info("✅ Local Qwen via vLLM initialized")

    async def ask(
        self,
        question: str,
        provider: str = None,
        context: str = None,
        stream_to_earpiece: bool = True,
        session_id: str = None,
    ) -> dict:
        """
        Answer a question using the specified AI provider.

        Args:
            question: The user's question
            provider: Which AI to use (openai/anthropic/google/xai/qwen_local)
            context: Optional context (script content, previous conversation)
            stream_to_earpiece: Whether to stream TTS to earpiece
            session_id: Session ID for conversation history

        Returns:
            QAResult with answer, sources, metadata
        """
        provider = provider or self._default_provider
        t_start = time.perf_counter()

        log.info(f"QAAgent processing: provider={provider}, question={question[:50]}...")

        # Get context from shared memory for personalized responses
        shared_context = ""
        if self._shared_memory:
            try:
                shared_context = await self._shared_memory.get_context_for_ai(
                    ai_name=provider,
                    include_recent=3
                )
            except Exception as e:
                log.warning(f"Failed to get shared context: {e}")

        # Combine all context
        full_context = shared_context
        if context:
            full_context += f"\n\nScript context: {context}" if full_context else context

        try:
            if provider == QAProvider.OPENAI:
                result = await self._call_openai(question, full_context)
            elif provider == QAProvider.ANTHROPIC:
                result = await self._call_anthropic(question, full_context)
            elif provider == QAProvider.GOOGLE:
                result = await self._call_google(question, full_context)
            elif provider == QAProvider.XAI:
                result = await self._call_xai(question, full_context)
            elif provider == QAProvider.QWEN_LOCAL:
                result = await self._call_qwen_local(question, full_context)
            else:
                result = await self._call_qwen_local(question, full_context)

            elapsed_ms = int((time.perf_counter() - t_start) * 1000)

            # Save conversation to shared memory for future reference
            if self._shared_memory:
                try:
                    await self._shared_memory.add_conversation(
                        user_input=question,
                        ai_response=result["answer"],
                        ai_provider=provider,
                        context=context,
                    )
                except Exception as e:
                    log.warning(f"Failed to save conversation to shared memory: {e}")

            return {
                **result,
                "provider": provider,
                "stream_enabled": stream_to_earpiece,
                "processing_ms": elapsed_ms,
            }

        except Exception as e:
            log.error(f"QAAgent error: {e}")
            elapsed_ms = int((time.perf_counter() - t_start) * 1000)
            return {
                "answer": f"I encountered an error: {str(e)}",
                "provider": provider,
                "error": str(e),
                "processing_ms": elapsed_ms,
            }

    async def _call_openai(self, question: str, context: str = None) -> dict:
        """Call OpenAI GPT API."""
        client = self._clients.get(QAProvider.OPENAI)
        if not client:
            raise RuntimeError("OpenAI not configured")

        messages = []
        if context:
            messages.append({"role": "system", "content": f"Context: {context}"})
        messages.append({"role": "user", "content": question})

        resp = await client.post(
            "/chat/completions",
            json={
                "model": settings.OPENAI_MODEL or "gpt-4o",
                "messages": messages,
                "temperature": 0.7,
                "stream": False,
            }
        )
        resp.raise_for_status()
        data = resp.json()

        return {
            "answer": data["choices"][0]["message"]["content"],
            "model": data["model"],
            "input_tokens": data.get("usage", {}).get("prompt_tokens"),
            "output_tokens": data.get("usage", {}).get("completion_tokens"),
        }

    async def _call_anthropic(self, question: str, context: str = None) -> dict:
        """Call Anthropic Claude API."""
        client = self._clients.get(QAProvider.ANTHROPIC)
        if not client:
            raise RuntimeError("Anthropic not configured")

        system = f"You are a helpful voice assistant. Keep responses concise for text-to-speech." if not context else f"Context: {context}\n\nYou are a helpful voice assistant."

        resp = await client.post(
            "/messages",
            json={
                "model": settings.ANTHROPIC_MODEL or "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "system": system,
                "messages": [{"role": "user", "content": question}],
            }
        )
        resp.raise_for_status()
        data = resp.json()

        return {
            "answer": data["content"][0]["text"],
            "model": data["model"],
            "input_tokens": data.get("usage", {}).get("input_tokens"),
            "output_tokens": data.get("usage", {}).get("output_tokens"),
        }

    async def _call_google(self, question: str, context: str = None) -> dict:
        """Call Google Gemini API."""
        client = self._clients.get(QAProvider.GOOGLE)
        if not client:
            raise RuntimeError("Google not configured")

        contents = [{"role": "user", "parts": [{"text": question}]}]
        if context:
            contents.insert(0, {"role": "system", "parts": [{"text": f"Context: {context}"}]})

        model_name = settings.GOOGLE_MODEL or "gemini-2.0-flash"
        resp = await client.post(
            f"/models/{model_name}:generateContent",
            json={"contents": contents},
        )
        resp.raise_for_status()
        data = resp.json()

        answer = data["candidates"][0]["content"]["parts"][0]["text"]
        return {"answer": answer, "model": model_name}

    async def _call_xai(self, question: str, context: str = None) -> dict:
        """Call xAI Grok API."""
        client = self._clients.get(QAProvider.XAI)
        if not client:
            raise RuntimeError("xAI not configured")

        messages = []
        if context:
            messages.append({"role": "system", "content": f"Context: {context}"})
        messages.append({"role": "user", "content": question})

        resp = await client.post(
            "/chat/completions",
            json={
                "model": settings.XAI_MODEL or "grok-2-1212",
                "messages": messages,
                "temperature": 0.7,
            }
        )
        resp.raise_for_status()
        data = resp.json()

        return {
            "answer": data["choices"][0]["message"]["content"],
            "model": data["model"],
        }

    async def _call_qwen_local(self, question: str, context: str = None) -> dict:
        """Call local Qwen via vLLM."""
        client = self._clients.get(QAProvider.QWEN_LOCAL)
        if not client:
            raise RuntimeError("Local Qwen not configured")

        system_prompt = "You are a helpful voice assistant. Keep responses concise for text-to-speech output."
        if context:
            system_prompt += f"\n\nContext from document: {context}"

        resp = await client.post(
            "/chat/completions",
            json={
                "model": settings.QA_MODEL or "Qwen/Qwen2.5-7B-Instruct",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                "temperature": 0.7,
                "max_tokens": 1024,
            }
        )
        resp.raise_for_status()
        data = resp.json()

        return {
            "answer": data["choices"][0]["message"]["content"],
            "model": "qwen-local",
        }

    def set_shared_memory(self, shared_memory):
        """Connect to shared memory for context-aware responses."""
        self._shared_memory = shared_memory
        log.info("QAAgent connected to SharedMemoryAgent")

    def set_memory_agent(self, memory_agent):
        """Legacy method - now uses shared_memory instead."""
        pass  # Deprecated, use set_shared_memory

    async def shutdown(self):
        for client in self._clients.values():
            await client.aclose()
        log.info("QAAgent shut down")