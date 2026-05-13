"""
Anthropic Provider Adapter
===========================
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

logger = structlog.get_logger("rasospeak.providers.anthropic")


class AnthropicProvider(ProviderBase):
    """Anthropic provider implementation (Claude)."""

    DEFAULT_MODELS = {
        "chat": "claude-sonnet-4-20250514",
        "fast": "claude-haiku-3-20240307",
        "reasoning": "claude-opus-4-20250514",
        "vision": "claude-sonnet-4-20250514",
        "cheap": "claude-haiku-3-20240307",
    }

    CAPABILITIES = [
        ProviderCapability.STREAMING,
        ProviderCapability.FUNCTION_CALLING,
        ProviderCapability.VISION,
        ProviderCapability.JSON_MODE,
        ProviderCapability.TOOL_USE,
        ProviderCapability.REASONING,
    ]

    def __init__(self, api_key: str, **kwargs):
        super().__init__(
            provider_name="anthropic",
            api_key=api_key,
            base_url="https://api.anthropic.com/v1",
            default_model=self.DEFAULT_MODELS["chat"],
            **kwargs
        )
        self._anthropic_version = "2023-06-01"

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

        # Convert OpenAI message format to Anthropic format
        anthropic_messages = self._convert_messages(messages)

        body = {
            "model": model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
            "stream": stream,
        }
        if tools:
            body["tools"] = tools

        try:
            if stream:
                return self._stream_response(body, model)
            else:
                return await self._non_stream_response(body, model)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Anthropic request failed: {str(e)}", provider="anthropic")

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        """Convert OpenAI message format to Anthropic format."""
        converted = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                # Anthropic uses system as first message
                converted.insert(0, {"role": "system", "content": msg.get("content", "")})
            elif role == "tool":
                converted.append({
                    "role": "user",
                    "content": f"[Tool Result: {msg.get('tool_call_id')}]\n{msg.get('content', '')}"
                })
            else:
                content = msg.get("content", "")
                if isinstance(content, list):
                    # Handle vision/images
                    text_parts = []
                    images = []
                    for part in content:
                        if part.get("type") == "text":
                            text_parts.append(part["text"])
                        elif part.get("type") == "image_url":
                            images.append(part["image_url"]["url"])
                    final_content = "\n".join(text_parts)
                    if images:
                        for img in images:
                            final_content += f"\n[Image: {img}]"
                    converted.append({"role": role, "content": final_content})
                else:
                    converted.append({"role": role, "content": str(content)})
        return converted

    async def _non_stream_response(self, body: dict, model: str) -> ProviderResponse:
        import httpx
        start = datetime.utcnow()

        headers = self._build_headers()
        headers["anthropic-version"] = self._anthropic_version

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/messages",
                json=body,
                headers=headers
            )

            latency_ms = (datetime.utcnow() - start).total_seconds() * 1000
            self._record_request(latency_ms, error=response.status_code >= 400)

            if response.status_code == 429:
                raise ProviderError(
                    "Anthropic rate limit exceeded",
                    status_code=429,
                    provider="anthropic",
                    rate_limited=True
                )
            if response.status_code == 403:
                raise ProviderError(
                    "Anthropic quota exceeded",
                    status_code=403,
                    provider="anthropic",
                    quota_exceeded=True
                )
            if response.status_code >= 400:
                raise ProviderError(
                    f"Anthropic error: {response.text}",
                    status_code=response.status_code,
                    provider="anthropic"
                )

            data = response.json()
            content = data["content"][0]["text"] if data.get("content") else ""

            return ProviderResponse(
                response_id=data["id"],
                content=content,
                model=model,
                provider="anthropic",
                usage={
                    "input_tokens": data.get("usage", {}).get("input_tokens", 0),
                    "output_tokens": data.get("usage", {}).get("output_tokens", 0)
                },
                finish_reason=data.get("stop_reason", "end_turn"),
                latency_ms=latency_ms
            )

    async def _stream_response(self, body: dict, model: str) -> AsyncGenerator[StreamChunk, None]:
        import httpx

        headers = self._build_headers()
        headers["anthropic-version"] = self._anthropic_version

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/messages",
                json=body,
                headers=headers
            ) as response:
                if response.status_code >= 400:
                    raise ProviderError(
                        f"Anthropic stream error: {response.status_code}",
                        status_code=response.status_code,
                        provider="anthropic"
                    )

                async for line in response.aiter_lines():
                    if not line.strip() or not line.startswith("data:"):
                        continue

                    try:
                        # Anthropic sends "data: " prefix
                        data = json.loads(line[6:])

                        if data.get("type") == "content_block_delta":
                            delta = data.get("delta", {})
                            chunk = StreamChunk(
                                chunk_id=data.get("id", str(uuid.uuid4())),
                                content=delta.get("text", ""),
                                delta=delta.get("text", ""),
                                finish_reason=None,
                                model=model
                            )
                            yield chunk
                        elif data.get("type") == "message_delta":
                            if data.get("delta", {}).get("stop_reason"):
                                chunk = StreamChunk(
                                    chunk_id=data.get("id", str(uuid.uuid4())),
                                    content="",
                                    delta="",
                                    finish_reason=data["delta"]["stop_reason"],
                                    model=model
                                )
                                yield chunk
                    except json.JSONDecodeError:
                        continue

    async def health_check(self) -> ProviderHealth:
        """Check Anthropic API health."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                start = datetime.utcnow()
                response = await client.post(
                    f"{self.base_url}/messages",
                    json={"model": self.default_model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1},
                    headers={
                        **self._build_headers(),
                        "anthropic-version": self._anthropic_version
                    }
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
        """List available Anthropic models."""
        models = [
            ModelInfo(
                model_id="claude-opus-4-20250514",
                name="Claude Opus 4",
                provider="anthropic",
                context_window=200000,
                max_output_tokens=4096,
                capabilities=self.CAPABILITIES,
                pricing={"input": 15.0, "output": 75.0},
                latency_p50_ms=1200,
                latency_p99_ms=4000,
                reliability=0.97
            ),
            ModelInfo(
                model_id="claude-sonnet-4-20250514",
                name="Claude Sonnet 4",
                provider="anthropic",
                context_window=200000,
                max_output_tokens=4096,
                capabilities=self.CAPABILITIES,
                pricing={"input": 3.0, "output": 15.0},
                latency_p50_ms=800,
                latency_p99_ms=2500,
                reliability=0.98
            ),
            ModelInfo(
                model_id="claude-haiku-3-20240307",
                name="Claude Haiku 3",
                provider="anthropic",
                context_window=200000,
                max_output_tokens=4096,
                capabilities=self.CAPABILITIES,
                pricing={"input": 0.25, "output": 1.25},
                latency_p50_ms=400,
                latency_p99_ms=1000,
                reliability=0.99
            ),
        ]
        return models

    async def embeddings(self, texts: list[str], **kwargs) -> list[list[float]]:
        """Anthropic doesn't have embeddings API - fallback."""
        raise NotImplementedError("Anthropic does not support embeddings")

    async def close(self):
        """Close provider."""
        pass