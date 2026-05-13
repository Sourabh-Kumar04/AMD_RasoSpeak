"""
Google Gemini Provider Adapter
==============================
"""

import asyncio
import json
from typing import AsyncGenerator, Optional
from ..core.provider_base import (
    ProviderBase, ProviderCapability, ProviderHealth, ProviderStatus,
    ModelInfo, StreamChunk, ProviderResponse, ProviderError
)
from datetime import datetime
import uuid
import structlog

logger = structlog.get_logger("rasospeak.providers.google")


class GoogleProvider(ProviderBase):
    """Google Gemini provider implementation."""

    DEFAULT_MODELS = {
        "chat": "gemini-2.0-flash-exp",
        "fast": "gemini-1.5-flash-8b",
        "vision": "gemini-1.5-pro",
        "reasoning": "gemini-2.0-flash-exp",
        "voice": "gemini-2.0-flash-exp",
    }

    CAPABILITIES = [
        ProviderCapability.STREAMING,
        ProviderCapability.VISION,
        ProviderCapability.VOICE,
        ProviderCapability.FAST_MODE,
        ProviderCapability.LARGE_CONTEXT,
    ]

    def __init__(self, api_key: str, **kwargs):
        super().__init__(
            provider_name="google",
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta",
            default_model=self.DEFAULT_MODELS["chat"],
            **kwargs
        )

    async def chat_complete(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> ProviderResponse | AsyncGenerator[StreamChunk, None]:
        model = model or self.default_model

        # Convert messages to Gemini format
        contents = self._convert_messages(messages)

        body = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens or 8192,
                "topP": 0.95,
                "topK": 40,
            }
        }

        # Handle system instruction
        for msg in messages:
            if msg.get("role") == "system":
                body["systemInstruction"] = {"parts": [{"text": msg["content"]}]}
                break

        try:
            if stream:
                return self._stream_response(body, model)
            else:
                return await self._non_stream_response(body, model)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Google request failed: {str(e)}", provider="google")

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        """Convert messages to Gemini format."""
        contents = []
        for msg in messages:
            role = "model" if msg.get("role") == "assistant" else "user"
            content = msg.get("content", "")

            if isinstance(content, list):
                parts = []
                for part in content:
                    if part.get("type") == "text":
                        parts.append({"text": part["text"]})
                    elif part.get("type") == "image_url":
                        parts.append({"fileData": {"mimeType": "image/jpeg", "fileUri": part["image_url"]["url"]}})
                contents.append({"role": role, "parts": parts})
            else:
                contents.append({"role": role, "parts": [{"text": str(content)}]})

        return contents

    async def _non_stream_response(self, body: dict, model: str) -> ProviderResponse:
        import httpx
        start = datetime.utcnow()

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/models/{model}:generateContent",
                json=body,
                params={"key": self.api_key}
            )

            latency_ms = (datetime.utcnow() - start).total_seconds() * 1000
            self._record_request(latency_ms, error=response.status_code >= 400)

            if response.status_code == 429:
                raise ProviderError(
                    "Google rate limit exceeded",
                    status_code=429,
                    provider="google",
                    rate_limited=True
                )
            if response.status_code == 403:
                raise ProviderError(
                    "Google quota exceeded",
                    status_code=403,
                    provider="google",
                    quota_exceeded=True
                )
            if response.status_code >= 400:
                raise ProviderError(
                    f"Google error: {response.text}",
                    status_code=response.status_code,
                    provider="google"
                )

            data = response.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]

            return ProviderResponse(
                response_id=data.get("promptFeedback", {}).get("safetyRatings", [{}])[0].get("category", "unknown"),
                content=content,
                model=model,
                provider="google",
                usage={
                    "prompt_tokens": data.get("usageMetadata", {}).get("promptTokenCount", 0),
                    "completion_tokens": data.get("usageMetadata", {}).get("candidatesTokenCount", 0)
                },
                finish_reason="stop",
                latency_ms=latency_ms
            )

    async def _stream_response(self, body: dict, model: str) -> AsyncGenerator[StreamChunk, None]:
        import httpx

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/models/{model}:streamGenerateContent",
                params={"key": self.api_key},
                json=body
            ) as response:
                if response.status_code >= 400:
                    raise ProviderError(
                        f"Google stream error: {response.status_code}",
                        status_code=response.status_code,
                        provider="google"
                    )

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        if "candidates" in data and data["candidates"]:
                            content = data["candidates"][0]["content"]["parts"][0]["text"]
                            chunk = StreamChunk(
                                chunk_id=str(uuid.uuid4()),
                                content=content,
                                delta=content,
                                finish_reason=None,
                                model=model
                            )
                            yield chunk
                    except json.JSONDecodeError:
                        continue

    async def health_check(self) -> ProviderHealth:
        """Check Google API health."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                start = datetime.utcnow()
                response = await client.post(
                    f"{self.base_url}/models/{self.default_model}:generateContent",
                    params={"key": self.api_key},
                    json={"contents": [{"parts": [{"text": "ping"}]}]}
                )
                latency_ms = (datetime.utcnow() - start).total_seconds() * 1000

                if response.status_code == 200:
                    return ProviderHealth(
                        status=ProviderStatus.AVAILABLE,
                        latency_ms=latency_ms,
                        error_rate=0.0
                    )
                else:
                    return ProviderHealth(
                        status=ProviderStatus.DEGRADED if response.status_code < 500 else ProviderStatus.UNAVAILABLE,
                        latency_ms=latency_ms,
                        error_rate=1.0
                    )
        except Exception as e:
            return ProviderHealth(
                status=ProviderStatus.UNAVABLE,
                latency_ms=0,
                error_rate=1.0,
                failure_reason=str(e)
            )

    async def list_models(self) -> list[ModelInfo]:
        """List available Google models."""
        return [
            ModelInfo(
                model_id="gemini-2.0-flash-exp",
                name="Gemini 2.0 Flash Experimental",
                provider="google",
                context_window=1000000,
                max_output_tokens=8192,
                capabilities=self.CAPABILITIES + [ProviderCapability.REASONING],
                pricing={"input": 0.0, "output": 0.0},  # Free tier
                latency_p50_ms=500,
                latency_p99_ms=1500,
                reliability=0.95
            ),
            ModelInfo(
                model_id="gemini-1.5-pro",
                name="Gemini 1.5 Pro",
                provider="google",
                context_window=2000000,
                max_output_tokens=8192,
                capabilities=self.CAPABILITIES,
                pricing={"input": 1.25, "output": 5.0},
                latency_p50_ms=1000,
                latency_p99_ms=3000,
                reliability=0.96
            ),
            ModelInfo(
                model_id="gemini-1.5-flash-8b",
                name="Gemini 1.5 Flash 8B",
                provider="google",
                context_window=1000000,
                max_output_tokens=8192,
                capabilities=self.CAPABILITIES,
                pricing={"input": 0.075, "output": 0.3},
                latency_p50_ms=300,
                latency_p99_ms=800,
                reliability=0.98
            ),
        ]

    async def embeddings(self, texts: list[str], model: str = "embedding-001", **kwargs) -> list[list[float]]:
        """Generate embeddings using Google."""
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            responses = []
            for text in texts:
                response = await client.post(
                    f"{self.base_url}/models/{model}:predict",
                    params={"key": self.api_key},
                    json={"content": {"role": "user", "parts": [{"text": text}]}}
                )
                data = response.json()
                responses.append(data["embedding"]["values"])

            return responses

    async def close(self):
        """Close provider."""
        pass