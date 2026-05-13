"""
OpenAI Provider Adapter
========================
"""

import asyncio
import json
from typing import AsyncGenerator, Optional
from ..core.provider_base import (
    ProviderBase, ProviderCapability, ProviderHealth, ProviderStatus,
    ModelInfo, StreamChunk, ProviderResponse, ProviderError
)
import structlog

logger = structlog.get_logger("rasospeak.providers.openai")


class OpenAIProvider(ProviderBase):
    """OpenAI provider implementation."""

    DEFAULT_MODELS = {
        "chat": "gpt-4o",
        "fast": "gpt-4o-mini",
        "reasoning": "o1-preview",
        "vision": "gpt-4o",
        "cheap": "gpt-4o-mini",
    }

    CAPABILITIES = [
        ProviderCapability.STREAMING,
        ProviderCapability.FUNCTION_CALLING,
        ProviderCapability.VISION,
        ProviderCapability.JSON_MODE,
        ProviderCapability.TOOL_USE,
    ]

    def __init__(self, api_key: str, **kwargs):
        super().__init__(
            provider_name="openai",
            api_key=api_key,
            base_url="https://api.openai.com/v1",
            default_model=self.DEFAULT_MODELS["chat"],
            **kwargs
        )
        self._client = None

    async def chat_complete(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        tools: Optional[list[dict]] = None,
        **kwargs
    ) -> ProviderResponse | AsyncGenerator[StreamChunk, None]:
        model = model or self.default_model

        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        # Handle reasoning models (o1 family)
        if model.startswith("o1"):
            body.pop("temperature", None)
            body["reasoning_effort"] = kwargs.get("reasoning_effort", "medium")

        try:
            if stream:
                return self._stream_response(body, model)
            else:
                return await self._non_stream_response(body, model)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"OpenAI request failed: {str(e)}", provider="openai")

    async def _non_stream_response(self, body: dict, model: str) -> ProviderResponse:
        import httpx
        start = datetime.utcnow()

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=body,
                headers=self._build_headers()
            )

            latency_ms = (datetime.utcnow() - start).total_seconds() * 1000
            self._record_request(latency_ms, error=response.status_code >= 400)

            if response.status_code == 429:
                raise ProviderError(
                    "OpenAI rate limit exceeded",
                    status_code=429,
                    provider="openai",
                    rate_limited=True
                )
            if response.status_code == 403:
                raise ProviderError(
                    "OpenAI quota exceeded",
                    status_code=403,
                    provider="openai",
                    quota_exceeded=True
                )
            if response.status_code >= 400:
                raise ProviderError(
                    f"OpenAI error: {response.text}",
                    status_code=response.status_code,
                    provider="openai"
                )

            data = response.json()
            choice = data["choices"][0]
            message = choice["message"]

            return ProviderResponse(
                response_id=data["id"],
                content=message.get("content", ""),
                model=model,
                provider="openai",
                usage=data.get("usage", {}),
                finish_reason=choice.get("finish_reason", "stop"),
                metadata={"service_tier": data.get("service_tier")},
                latency_ms=latency_ms
            )

    async def _stream_response(self, body: dict, model: str) -> AsyncGenerator[StreamChunk, None]:
        import httpx

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=body,
                headers=self._build_headers()
            ) as response:
                if response.status_code >= 400:
                    raise ProviderError(
                        f"OpenAI stream error: {response.status_code}",
                        status_code=response.status_code,
                        provider="openai"
                    )

                async for line in response.aiter_lines():
                    if not line.strip() or not line.startswith("data:"):
                        continue

                    if line.strip() == "data: [DONE]":
                        break

                    try:
                        data = json.loads(line[6:])
                        delta = data["choices"][0].get("delta", {})
                        chunk = StreamChunk(
                            chunk_id=data.get("id", str(uuid.uuid4())),
                            content=delta.get("content", ""),
                            delta=delta.get("content", ""),
                            finish_reason=data["choices"][0].get("finish_reason"),
                            model=model,
                            usage=data.get("usage")
                        )
                        yield chunk
                    except json.JSONDecodeError:
                        continue

    async def health_check(self) -> ProviderHealth:
        """Check OpenAI API health."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                start = datetime.utcnow()
                response = await client.get(
                    f"{self.base_url}/models",
                    headers=self._build_headers()
                )
                latency_ms = (datetime.utcnow() - start).total_seconds() * 1000

                if response.status_code == 200:
                    return ProviderHealth(
                        status=ProviderStatus.AVAILABLE,
                        latency_ms=latency_ms,
                        error_rate=0.0
                    )
                elif response.status_code == 401:
                    return ProviderHealth(
                        status=ProviderStatus.UNAVAILABLE,
                        latency_ms=latency_ms,
                        error_rate=1.0,
                        failure_reason="Invalid API key"
                    )
                else:
                    return ProviderHealth(
                        status=ProviderStatus.DEGRADED,
                        latency_ms=latency_ms,
                        error_rate=1.0
                    )
        except Exception as e:
            return ProviderHealth(
                status=ProviderStatus.UNAVAILABLE,
                latency_ms=0,
                error_rate=1.0,
                failure_reason=str(e)
            )

    async def list_models(self) -> list[ModelInfo]:
        """List available OpenAI models."""
        models = [
            ModelInfo(
                model_id="gpt-4o",
                name="GPT-4o",
                provider="openai",
                context_window=128000,
                max_output_tokens=16384,
                capabilities=self.CAPABILITIES + [ProviderCapability.REASONING],
                pricing={"input": 5.0, "output": 15.0},
                latency_p50_ms=800,
                latency_p99_ms=2500,
                reliability=0.98
            ),
            ModelInfo(
                model_id="gpt-4o-mini",
                name="GPT-4o Mini",
                provider="openai",
                context_window=128000,
                max_output_tokens=16384,
                capabilities=self.CAPABILITIES,
                pricing={"input": 0.15, "output": 0.6},
                latency_p50_ms=300,
                latency_p99_ms=800,
                reliability=0.99
            ),
            ModelInfo(
                model_id="o1-preview",
                name="o1 Preview",
                provider="openai",
                context_window=128000,
                max_output_tokens=32768,
                capabilities=[ProviderCapability.REASONING, ProviderCapability.STREAMING],
                pricing={"input": 15.0, "output": 60.0},
                latency_p50_ms=15000,
                latency_p99_ms=60000,
                reliability=0.95
            ),
            ModelInfo(
                model_id="gpt-4-turbo",
                name="GPT-4 Turbo",
                provider="openai",
                context_window=128000,
                max_output_tokens=4096,
                capabilities=self.CAPABILITIES,
                pricing={"input": 10.0, "output": 30.0},
                latency_p50_ms=1000,
                latency_p99_ms=3000,
                reliability=0.97
            ),
        ]
        return models

    async def embeddings(
        self,
        texts: list[str],
        model: str = "text-embedding-3-large",
        **kwargs
    ) -> list[list[float]]:
        """Generate embeddings using OpenAI."""
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                json={"input": texts, "model": model},
                headers=self._build_headers()
            )

            if response.status_code >= 400:
                raise ProviderError(
                    f"OpenAI embeddings error: {response.status_code}",
                    status_code=response.status_code,
                    provider="openai"
                )

            data = response.json()
            return [item["embedding"] for item in data["data"]]

    async def close(self):
        """Close provider."""
        pass


from datetime import datetime
from typing import Optional
import uuid