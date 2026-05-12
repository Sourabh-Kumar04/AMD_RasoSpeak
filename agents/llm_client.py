"""
RasoSpeak v2 — Unified LLM Client

No GPU required - works on 4GB RAM using external APIs.
Supports streaming for all providers.

Example:
    client = LLMClient("google")
    result = await client.chat(messages)
    async for chunk in client.chat(messages, stream=True):
        print(chunk)
"""

import json
import logging
from typing import AsyncIterator, Optional

import httpx
from config.settings import settings

log = logging.getLogger("rasospeak.llm")


class LLMProvider(str):
    """Supported LLM provider names."""
    GOOGLE = "google"
    NVIDIA = "nvidia"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    HUGGINGFACE = "huggingface"
    OPENROUTER = "openrouter"
    OPENCODE = "opencode"
    XAI = "xai"
    DEEPSEEK = "deepseek"


class LLMClient:
    """
    Unified LLM client with streaming support.

    Works without GPU - uses external APIs only.
    Automatically routes to the correct provider based on config.

    Attributes:
        provider: The current provider name (e.g., "google", "nvidia")
    """

    def __init__(self, provider: Optional[str] = None) -> None:
        """Initialize LLM client.

        Args:
            provider: Override default provider from settings.
        """
        self.provider = provider or settings.default_provider
        self._client = httpx.AsyncClient(timeout=120.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.15,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> dict[str, str] | AsyncIterator[str]:
        """Send chat request with optional streaming.

        Args:
            messages: List of message dicts [{"role": "...", "content": "..."}].
            model: Override default model for this provider.
            temperature: Creativity level (0.0 to 1.0).
            max_tokens: Maximum tokens in response.
            stream: Enable streaming response.

        Returns:
            If stream=False: Dict with "content" and "finish_reason".
            If stream=True: AsyncIterator yielding text chunks.
        """
        provider = self.provider

        if stream:
            return self._stream_chat(provider, messages, model, temperature, max_tokens)
        else:
            return await self._sync_chat(provider, messages, model, temperature, max_tokens)

    async def _sync_chat(
        self,
        provider: str,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, str]:
        """Synchronous (non-streaming) chat request."""
        if provider == "google":
            return await self._google_chat(messages, model, temperature, max_tokens)
        elif provider == "nvidia":
            return await self._nvidia_chat(messages, model, temperature, max_tokens)
        elif provider == "openai":
            return await self._openai_chat(messages, model, temperature, max_tokens)
        elif provider == "anthropic":
            return await self._anthropic_chat(messages, model, temperature, max_tokens)
        elif provider == "huggingface":
            return await self._hf_chat(messages, model, temperature, max_tokens)
        elif provider == "openrouter":
            return await self._openrouter_chat(messages, model, temperature, max_tokens)
        elif provider == "opencode":
            return await self._opencode_chat(messages, model, temperature, max_tokens)
        elif provider == "xai":
            return await self._xai_chat(messages, model, temperature, max_tokens)
        elif provider == "deepseek":
            return await self._deepseek_chat(messages, model, temperature, max_tokens)
        else:
            return await self._google_chat(messages, model, temperature, max_tokens)

    async def _stream_chat(
        self,
        provider: str,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Streaming chat request."""
        if provider == "google":
            async for chunk in self._google_stream(messages, model, temperature, max_tokens):
                yield chunk
        elif provider == "nvidia":
            async for chunk in self._nvidia_stream(messages, model, temperature, max_tokens):
                yield chunk
        elif provider == "openai":
            async for chunk in self._openai_stream(messages, model, temperature, max_tokens):
                yield chunk
        elif provider == "anthropic":
            async for chunk in self._anthropic_stream(messages, model, temperature, max_tokens):
                yield chunk
        elif provider == "openrouter":
            async for chunk in self._openrouter_stream(messages, model, temperature, max_tokens):
                yield chunk
        elif provider == "deepseek":
            async for chunk in self._deepseek_stream(messages, model, temperature, max_tokens):
                yield chunk
        else:
            async for chunk in self._google_stream(messages, model, temperature, max_tokens):
                yield chunk

    # ── SHARED OPENAI-COMPATIBLE HELPERS ──────────────────

    async def _openai_compatible_chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
        url: str,
        api_key: str,
        headers_extra: Optional[dict] = None,
    ) -> dict[str, str]:
        """OpenAI-compatible non-streaming chat (used by nvidia, openai, openrouter, opencode, deepseek, xai, huggingface)."""
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        if headers_extra:
            headers.update(headers_extra)
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = await self._client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        return {
            "content": data["choices"][0]["message"]["content"],
            "finish_reason": data["choices"][0].get("finish_reason", "stop"),
        }

    async def _openai_compatible_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
        url: str,
        api_key: str,
        headers_extra: Optional[dict] = None,
    ) -> AsyncIterator[str]:
        """OpenAI-compatible streaming (used by nvidia, openai, openrouter, deepseek)."""
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        if headers_extra:
            headers.update(headers_extra)
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        async with self._client.stream("POST", url, headers=headers, json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    if line.strip() == "data: [DONE]":
                        break
                    data = json.loads(line[6:])
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    if delta.get("content"):
                        yield delta["content"]

    # ── GOOGLE GEMINI ───────────────────────────────────
    async def _google_chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, str]:
        """Chat with Google Gemini API."""
        config = settings.get_provider_config("google")
        if not config.get("api_key"):
            raise ValueError("Google API key not configured")

        gemini_messages = []
        for msg in messages:
            role = "model" if msg["role"] == "assistant" else msg["role"]
            if role == "system":
                gemini_messages.append({"role": "user", "parts": [{"text": msg["content"]}]})
            else:
                gemini_messages.append({"role": role, "parts": [{"text": msg["content"]}]})

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model or config['model']}:generateContent"
        )
        params = {"key": config["api_key"]}
        body = {
            "contents": gemini_messages,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": 0.95,
                "topK": 40,
            }
        }

        resp = await self._client.post(url, params=params, json=body)
        resp.raise_for_status()
        data = resp.json()

        return {
            "content": data["candidates"][0]["content"]["parts"][0]["text"],
            "finish_reason": data.get("candidates", [{}])[0].get("finishReason", "STOP"),
        }

    async def _google_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Stream from Google Gemini API."""
        config = settings.get_provider_config("google")
        if not config.get("api_key"):
            raise ValueError("Google API key not configured")

        gemini_messages = []
        for msg in messages:
            role = "model" if msg["role"] == "assistant" else msg["role"]
            if role == "system":
                gemini_messages.append({"role": "user", "parts": [{"text": msg["content"]}]})
            else:
                gemini_messages.append({"role": role, "parts": [{"text": msg["content"]}]})

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model or config['model']}:streamGenerateContent?alt=sse"
        )
        params = {"key": config["api_key"]}
        body = {
            "contents": gemini_messages,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            }
        }

        async with self._client.stream("POST", url, params=params, json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            yield parts[0].get("text", "")

    # ── NVIDIA NIM ─────────────────────────────────────
    async def _nvidia_chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, str]:
        """Chat with NVIDIA NIM API."""
        config = settings.get_provider_config("nvidia")
        if not config.get("api_key"):
            raise ValueError("NVIDIA API key not configured")
        return await self._openai_compatible_chat(
            messages, model or config["model"], temperature, max_tokens,
            f"{config['base_url']}/chat/completions", config["api_key"]
        )

    async def _nvidia_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Stream from NVIDIA NIM API."""
        config = settings.get_provider_config("nvidia")
        if not config.get("api_key"):
            raise ValueError("NVIDIA API key not configured")
        async for chunk in self._openai_compatible_stream(
            messages, model or config["model"], temperature, max_tokens,
            f"{config['base_url']}/chat/completions", config["api_key"]
        ):
            yield chunk

    # ── OPENAI ──────────────────────────────────────────
    async def _openai_chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, str]:
        """Chat with OpenAI API."""
        config = settings.get_provider_config("openai")
        if not config.get("api_key"):
            raise ValueError("OpenAI API key not configured")
        return await self._openai_compatible_chat(
            messages, model or config["model"], temperature, max_tokens,
            f"{config['base_url']}/chat/completions", config["api_key"]
        )

    async def _openai_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Stream from OpenAI API."""
        config = settings.get_provider_config("openai")
        if not config.get("api_key"):
            raise ValueError("OpenAI API key not configured")
        async for chunk in self._openai_compatible_stream(
            messages, model or config["model"], temperature, max_tokens,
            f"{config['base_url']}/chat/completions", config["api_key"]
        ):
            yield chunk

    # ── ANTHROPIC ───────────────────────────────────────
    async def _anthropic_chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, str]:
        """Chat with Anthropic Claude API."""
        config = settings.get_provider_config("anthropic")
        if not config.get("api_key"):
            raise ValueError("Anthropic API key not configured")

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": config["api_key"],
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        anthropic_messages = []
        system_content = ""
        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            elif msg["role"] != "developer":
                anthropic_messages.append({"role": msg["role"], "content": msg["content"]})

        body = {
            "model": model or config["model"],
            "messages": anthropic_messages,
            "system": system_content,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        resp = await self._client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

        return {
            "content": data["content"][0]["text"],
            "finish_reason": data.get("stop_reason", "stop"),
        }

    async def _anthropic_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Stream from Anthropic Claude API."""
        config = settings.get_provider_config("anthropic")
        if not config.get("api_key"):
            raise ValueError("Anthropic API key not configured")

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": config["api_key"],
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        anthropic_messages = []
        system_content = ""
        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            elif msg["role"] != "developer":
                anthropic_messages.append({"role": msg["role"], "content": msg["content"]})

        body = {
            "model": model or config["model"],
            "messages": anthropic_messages,
            "system": system_content,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        async with self._client.stream("POST", url, headers=headers, json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    if line.strip() == "data: [DONE]":
                        break
                    data = json.loads(line[6:])
                    if data.get("type") == "content_block_delta":
                        yield data.get("delta", {}).get("text", "")

    # ── HUGGINGFACE ─────────────────────────────────────
    async def _hf_chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, str]:
        """Chat with HuggingFace Inference API."""
        config = settings.get_provider_config("huggingface")
        if not config.get("api_key"):
            raise ValueError("HuggingFace API key not configured")
        model_name = model or config["model"]
        return await self._openai_compatible_chat(
            messages, model_name, temperature, max_tokens,
            f"https://api-inference.huggingface.co/models/{model_name}/v1/chat/completions",
            config["api_key"]
        )

    # ── OPENROUTER ──────────────────────────────────────
    async def _openrouter_chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, str]:
        """Chat with OpenRouter API (80+ models)."""
        config = settings.get_provider_config("openrouter")
        if not config.get("api_key"):
            raise ValueError("OpenRouter API key not configured")
        return await self._openai_compatible_chat(
            messages, model or config["model"], temperature, max_tokens,
            "https://openrouter.ai/api/v1/chat/completions", config["api_key"],
            headers_extra={
                "HTTP-Referer": "https://rasospeak.ai",
                "X-Title": "RasoSpeak",
            }
        )

    async def _openrouter_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Stream from OpenRouter API."""
        config = settings.get_provider_config("openrouter")
        if not config.get("api_key"):
            raise ValueError("OpenRouter API key not configured")
        async for chunk in self._openai_compatible_stream(
            messages, model or config["model"], temperature, max_tokens,
            "https://openrouter.ai/api/v1/chat/completions", config["api_key"],
            headers_extra={
                "HTTP-Referer": "https://rasospeak.ai",
                "X-Title": "RasoSpeak",
            }
        ):
            yield chunk

    # ── OPENCODE ────────────────────────────────────────
    async def _opencode_chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, str]:
        """Chat with OpenCode API."""
        config = settings.get_provider_config("opencode")
        if not config.get("api_key"):
            raise ValueError("OpenCode API key not configured")
        return await self._openai_compatible_chat(
            messages, model or config["model"], temperature, max_tokens,
            f"{config['base_url']}/chat/completions", config["api_key"]
        )

    # ── XAI (GROK) ─────────────────────────────────────
    async def _xai_chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, str]:
        """Chat with xAI Grok API."""
        config = settings.get_provider_config("xai")
        if not config.get("api_key"):
            raise ValueError("xAI API key not configured")
        return await self._openai_compatible_chat(
            messages, model or config["model"], temperature, max_tokens,
            "https://api.x.ai/v1/chat/completions", config["api_key"]
        )

    # ── DEEPSEEK ────────────────────────────────────────
    async def _deepseek_chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, str]:
        """Chat with DeepSeek API."""
        config = settings.get_provider_config("deepseek")
        if not config.get("api_key"):
            raise ValueError("DeepSeek API key not configured")
        return await self._openai_compatible_chat(
            messages, model or config["model"], temperature, max_tokens,
            f"{config['base_url']}/chat/completions", config["api_key"]
        )

    async def _deepseek_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Stream from DeepSeek API."""
        config = settings.get_provider_config("deepseek")
        if not config.get("api_key"):
            raise ValueError("DeepSeek API key not configured")
        async for chunk in self._openai_compatible_stream(
            messages, model or config["model"], temperature, max_tokens,
            f"{config['base_url']}/chat/completions", config["api_key"]
        ):
            yield chunk


def create_llm_client(provider: Optional[str] = None) -> LLMClient:
    """Create an LLM client for the specified provider.

    Args:
        provider: Provider name (google, nvidia, openai, anthropic, etc.).

    Returns:
        Configured LLMClient instance.
    """
    return LLMClient(provider=provider)