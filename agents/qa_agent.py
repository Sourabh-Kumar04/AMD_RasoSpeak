"""
RasoSpeak v2 — Q&A Agent
Multi-provider AI question answering with streaming support.

No GPU required - uses external APIs:
Google Gemini, NVIDIA NIM, OpenAI, Anthropic, HuggingFace, OpenRouter, OpenCode, xAI, DeepSeek
"""

import asyncio
import json
import logging
import time
from typing import AsyncIterator, Optional

from .base_agent import BaseAgent
from .llm_client import create_llm_client, LLMClient, LLMProvider
from config.settings import settings

log = logging.getLogger("rasospeak.qa")


class QAAgent(BaseAgent):
    """
    Agent for real-time question answering via external AI APIs.

    Uses unified LLM client supporting multiple providers with streaming.
    No GPU required - works on 4GB RAM.

    Uses SharedMemoryAgent to:
    - Remember conversation history
    - Get user context for personalized responses
    - Store important facts
    - Track weak words for coaching
    """

    name = "QAAgent"

    def __init__(self):
        self._llm_client: Optional[LLMClient] = None
        self._default_provider = settings.default_provider
        self._shared_memory = None
        self._second_brain = None  # Second Brain for enhanced memory context

    async def initialize(self):
        """Initialize LLM client."""
        log.info(f"Initializing QAAgent with provider: {self._default_provider}")
        self._llm_client = create_llm_client(self._default_provider)

        # Log available providers
        available = []
        for provider in ["google", "nvidia", "openai", "anthropic", "huggingface", "openrouter", "opencode", "xai", "deepseek"]:
            config = settings.get_provider_config(provider)
            if config.get("api_key"):
                available.append(provider)

        log.info(f"✅ QAAgent ready (API mode, no GPU)")
        log.info(f"   Available providers: {available}")

    async def cleanup(self):
        """Cleanup resources."""
        if self._llm_client:
            await self._llm_client.close()

    def set_second_brain(self, second_brain):
        """Connect to Second Brain for enhanced memory context."""
        self._second_brain = second_brain
        log.info("QAAgent connected to SecondBrainAgent")

    def set_shared_memory(self, shared_memory):
        """Connect to shared memory for context."""
        self._shared_memory = shared_memory

    async def ask(
        self,
        question: str,
        provider: str = None,
        context: str = None,
        stream_to_earpiece: bool = True,
        session_id: str = None,
    ) -> dict:
        """
        Ask a question to AI.

        Args:
            question: The question to ask
            provider: Override default provider (google, nvidia, openai, anthropic, etc.)
            context: Additional context to include
            stream_to_earpiece: For future streaming support
            session_id: For memory context

        Returns:
            {"answer": "...", "provider": "...", "processing_ms": ...}
        """
        t_start = time.perf_counter()

        if not self._llm_client:
            return {"error": "LLM client not initialized"}

        # Use specified provider or default
        client = create_llm_client(provider) if provider else self._llm_client

        # Build messages with context
        messages = [{"role": "system", "content": "You are RasoSpeak, a helpful AI assistant with perfect memory. Be concise and friendly."}]

        # Add memory context from Second Brain
        if self._second_brain and session_id:
            try:
                brain_context = await self._second_brain.get_context_for_ai("qa", max_tokens=3000)
                if brain_context:
                    messages.append({"role": "system", "content": f"User context: {brain_context}"})
            except Exception as e:
                log.warning(f"Failed to get Second Brain context: {e}")

        # Add provided context
        if context:
            messages.append({"role": "system", "content": f"Additional context: {context}"})

        messages.append({"role": "user", "content": question})

        try:
            result = await client.chat(messages, temperature=0.15, max_tokens=4096)
            elapsed_ms = int((time.perf_counter() - t_start) * 1000)

            return {
                "answer": result["content"],
                "provider": provider or self._default_provider,
                "finish_reason": result.get("finish_reason", "stop"),
                "processing_ms": elapsed_ms,
            }
        except Exception as e:
            log.error(f"QA request failed: {e}")
            return {"error": str(e)}

    async def ask_streaming(
        self,
        question: str,
        provider: str = None,
        context: str = None,
    ) -> AsyncIterator[str]:
        """
        Ask a question and stream the response.

        Yields response chunks in real-time for TTS output.
        """
        if not self._llm_client:
            yield "Error: LLM client not initialized"
            return

        client = create_llm_client(provider) if provider else self._llm_client

        messages = [{"role": "system", "content": "You are RasoSpeak, a helpful AI assistant."}]
        if context:
            messages.append({"role": "system", "content": f"Context: {context}"})
        messages.append({"role": "user", "content": question})

        try:
            async for chunk in client.chat(messages, temperature=0.15, max_tokens=4096, stream=True):
                yield chunk
        except Exception as e:
            yield f"Error: {str(e)}"

    async def get_available_providers(self) -> dict:
        """Get list of available providers based on configured API keys."""
        available = []
        for provider in ["google", "nvidia", "openai", "anthropic", "huggingface", "openrouter", "opencode", "xai", "deepseek"]:
            config = settings.get_provider_config(provider)
            if config.get("api_key"):
                available.append(provider)

        return {
            "available": available,
            "default": self._default_provider,
        }

    async def switch_provider(self, provider: str) -> dict:
        """Switch to a different provider."""
        if provider not in ["google", "nvidia", "openai", "anthropic", "huggingface", "openrouter", "opencode", "xai", "deepseek"]:
            return {"error": f"Unknown provider: {provider}"}

        self._default_provider = provider
        self._llm_client = create_llm_client(provider)
        log.info(f"Switched to provider: {provider}")

        return {
            "provider": provider,
            "message": f"Switched to {provider}"
        }