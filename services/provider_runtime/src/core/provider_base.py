"""
Provider Runtime - Base Provider Interface
============================================
Defines the contract all AI providers must implement for RasoSpeak OS.
"""

from __future__ import annotations
import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Callable, AsyncGenerator
import uuid
import structlog

logger = structlog.get_logger("rasospeak.provider")


class ProviderCapability(Enum):
    """Provider capability flags."""
    STREAMING = "streaming"
    FUNCTION_CALLING = "function_calling"
    VISION = "vision"
    EMBEDDINGS = "embeddings"
    VOICE = "voice"
    REASONING = "reasoning"
    CODING = "coding"
    FAST_MODE = "fast_mode"
    CHEAP_MODE = "cheap_mode"
    LARGE_CONTEXT = "large_context"
    JSON_MODE = "json_mode"
    TOOL_USE = "tool_use"


class ProviderStatus(Enum):
    """Provider availability status."""
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXCEEDED = "quota_exceeded"


@dataclass
class ModelInfo:
    """Model metadata."""
    model_id: str
    name: str
    provider: str
    context_window: int
    max_output_tokens: int
    capabilities: list[ProviderCapability]
    pricing: dict[str, float]  # input/output per 1M tokens
    latency_p50_ms: int = 0
    latency_p99_ms: int = 0
    reliability: float = 1.0  # 0-1


@dataclass
class ProviderHealth:
    """Provider health snapshot."""
    status: ProviderStatus
    latency_ms: float
    error_rate: float
    quota_remaining: Optional[int] = None
    quota_reset_at: Optional[datetime] = None
    last_check: datetime = field(default_factory=datetime.utcnow)
    failure_reason: Optional[str] = None


@dataclass
class StreamChunk:
    """Streaming response chunk."""
    chunk_id: str
    content: str
    delta: str
    finish_reason: Optional[str] = None
    model: str
    usage: Optional[dict] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ProviderResponse:
    """Complete non-streaming response."""
    response_id: str
    content: str
    model: str
    provider: str
    usage: dict
    finish_reason: str
    metadata: dict = field(default_factory=dict)
    latency_ms: float = 0.0


class ProviderBase(ABC):
    """
    Abstract base class for all AI providers.

    Every provider must implement:
    - chat completion (streaming & non-streaming)
    - health checks
    - model listing
    - embeddings (if supported)
    - proper error handling & retry logic
    """

    def __init__(
        self,
        provider_name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        organization: Optional[str] = None,
        **kwargs
    ):
        self.provider_name = provider_name
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model
        self.organization = organization
        self._health = ProviderHealth(
            status=ProviderStatus.AVAILABLE,
            latency_ms=0.0,
            error_rate=0.0
        )
        self._request_count = 0
        self._error_count = 0
        self._total_latency = 0.0

    @abstractmethod
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
        """Send chat completion request."""
        pass

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Check provider health and availability."""
        pass

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """List available models."""
        pass

    async def embeddings(
        self,
        texts: list[str],
        model: Optional[str] = None,
        **kwargs
    ) -> list[list[float]]:
        """
        Generate embeddings. Override if provider supports.
        Default: Not Supported
        """
        raise NotImplementedError(f"{self.provider_name} does not support embeddings")

    @abstractmethod
    async def close(self):
        """Cleanup resources."""
        pass

    def _record_request(self, latency_ms: float, error: bool = False):
        """Track request metrics."""
        self._request_count += 1
        self._total_latency += latency_ms
        if error:
            self._error_count += 1

    def get_health(self) -> ProviderHealth:
        """Get current health status."""
        if self._request_count > 0:
            self._health.latency_ms = self._total_latency / self._request_count
            self._health.error_rate = self._error_count / self._request_count
        self._health.last_check = datetime.utcnow()
        return self._health

    def _build_headers(self) -> dict[str, str]:
        """Build request headers."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.organization:
            headers["OpenAI-Organization"] = self.organization
        return headers

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        body: Optional[dict] = None,
        timeout: float = 30.0
    ) -> dict:
        """Make HTTP request with error handling."""
        import httpx
        url = f"{self.base_url}{endpoint}" if self.base_url else endpoint

        async with httpx.AsyncClient(timeout=timeout) as client:
            start = datetime.utcnow()
            try:
                if method == "GET":
                    response = await client.get(url, headers=self._build_headers())
                elif method == "POST":
                    response = await client.post(
                        url,
                        json=body,
                        headers=self._build_headers()
                    )
                else:
                    raise ValueError(f"Unsupported method: {method}")

                latency_ms = (datetime.utcnow() - start).total_seconds() * 1000
                self._record_request(latency_ms, error=response.status_code >= 400)

                if response.status_code >= 400:
                    raise ProviderError(
                        f"Provider error: {response.status_code}",
                        status_code=response.status_code,
                        provider=self.provider_name
                    )

                return response.json()
            except httpx.TimeoutException as e:
                self._record_request(timeout * 1000, error=True)
                raise ProviderError(
                    f"Request timeout: {timeout}s",
                    timeout=True,
                    provider=self.provider_name
                )
            except httpx.RequestError as e:
                self._record_request(0, error=True)
                raise ProviderError(
                    f"Request failed: {str(e)}",
                    provider=self.provider_name
                )


class ProviderError(Exception):
    """Provider-specific errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        provider: Optional[str] = None,
        timeout: bool = False,
        quota_exceeded: bool = False,
        rate_limited: bool = False
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.provider = provider
        self.timeout = timeout
        self.quota_exceeded = quota_exceeded
        self.rate_limited = rate_limited

        # Determine status from error
        if quota_exceeded or (status_code == 429):
            self.status = ProviderStatus.QUOTA_EXCEEDED
        elif rate_limited or (status_code == 429):
            self.status = ProviderStatus.RATE_LIMITED
        elif timeout or status_code == 504:
            self.status = ProviderStatus.DEGRADED
        elif status_code and status_code >= 500:
            self.status = ProviderStatus.UNAVAILABLE
        else:
            self.status = ProviderStatus.DEGRADED


class CircuitBreaker:
    """
    Circuit breaker for provider resilience.
    Prevents cascade failures when provider is down.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_requests: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_requests = half_open_requests

        self._failure_count = 0
        self._last_failure: Optional[datetime] = None
        self._state = "closed"  # closed, open, half-open
        self._half_open_successes = 0

    def record_success(self):
        """Record successful request."""
        if self._state == "half-open":
            self._half_open_successes += 1
            if self._half_open_successes >= self.half_open_requests:
                self._state = "closed"
                self._failure_count = 0
                logger.info("circuit_breaker_closed", provider="unknown")
        elif self._state == "closed":
            self._failure_count = max(0, self._failure_count - 1)

    def record_failure(self):
        """Record failed request."""
        self._failure_count += 1
        self._last_failure = datetime.utcnow()

        if self._state == "half-open":
            self._state = "open"
            logger.warning("circuit_breaker_opened", provider="unknown")
        elif self._failure_count >= self.failure_threshold:
            self._state = "open"
            logger.warning("circuit_breaker_opened", provider="unknown")

    def can_execute(self) -> bool:
        """Check if requests can proceed."""
        if self._state == "closed":
            return True

        if self._state == "open":
            if self._last_failure:
                elapsed = (datetime.utcnow() - self._last_failure).total_seconds()
                if elapsed >= self.recovery_timeout:
                    self._state = "half-open"
                    self._half_open_successes = 0
                    return True
            return False

        # half-open: allow limited requests
        return True

    def get_state(self) -> str:
        return self._state