"""
Provider Registry
=================
Central registry for all AI providers with hot-swapping support.
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid

from ..core.provider_base import (
    ProviderBase, ProviderHealth, ProviderStatus, ModelInfo,
    ProviderCapability, CircuitBreaker
)
import structlog

logger = structlog.get_logger("rasospeak.provider_registry")


@dataclass
class ProviderConfig:
    """Configuration for a provider instance."""
    provider_id: str
    provider_type: str  # openai, anthropic, google, etc.
    api_key: str
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    is_platform: bool = False  # Platform-managed vs user-provided
    priority: int = 100  # Higher = preferred
    enabled: bool = True
    tags: list[str] = field(default_factory=list)  # coding, reasoning, voice, etc.
    metadata: dict = field(default_factory=dict)


class ProviderRegistry:
    """
    Central registry for managing multiple AI providers.

    Responsibilities:
    - Provider registration/deregistration
    - Health monitoring
    - Model listing
    - Provider lookup by capability
    """

    def __init__(self):
        self._providers: dict[str, ProviderBase] = {}
        self._configs: dict[str, ProviderConfig] = {}
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._model_cache: dict[str, list[ModelInfo]] = {}
        self._health_cache: dict[str, ProviderHealth] = {}
        self._health_check_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def register_provider(
        self,
        config: ProviderConfig,
        provider_instance: ProviderBase
    ) -> str:
        """Register a provider instance."""
        async with self._lock:
            self._providers[config.provider_id] = provider_instance
            self._configs[config.provider_id] = config
            self._circuit_breakers[config.provider_id] = CircuitBreaker()

            logger.info(
                "provider_registered",
                provider_id=config.provider_id,
                provider_type=config.provider_type,
                is_platform=config.is_platform
            )

            # Fetch and cache models
            try:
                models = await provider_instance.list_models()
                self._model_cache[config.provider_id] = models
            except Exception as e:
                logger.warning("model_list_failed", provider_id=config.provider_id, error=str(e))
                self._model_cache[config.provider_id] = []

            return config.provider_id

    async def unregister_provider(self, provider_id: str) -> bool:
        """Unregister a provider."""
        async with self._lock:
            if provider_id in self._providers:
                provider = self._providers.pop(provider_id)
                await provider.close()
                self._configs.pop(provider_id, None)
                self._circuit_breakers.pop(provider_id, None)
                self._model_cache.pop(provider_id, None)
                self._health_cache.pop(provider_id, None)

                logger.info("provider_unregistered", provider_id=provider_id)
                return True
            return False

    def get_provider(self, provider_id: str) -> Optional[ProviderBase]:
        """Get provider instance by ID."""
        return self._providers.get(provider_id)

    def get_config(self, provider_id: str) -> Optional[ProviderConfig]:
        """Get provider configuration."""
        return self._configs.get(provider_id)

    def list_providers(self) -> list[ProviderConfig]:
        """List all registered provider configs."""
        return list(self._configs.values())

    def get_enabled_providers(self) -> list[ProviderConfig]:
        """List enabled providers sorted by priority."""
        return sorted(
            [c for c in self._configs.values() if c.enabled],
            key=lambda c: c.priority,
            reverse=True
        )

    async def get_provider_by_capability(
        self,
        capability: ProviderCapability,
        exclude_provider_id: Optional[str] = None
    ) -> Optional[tuple[ProviderBase, ProviderConfig]]:
        """Find provider that supports a specific capability."""
        for config in self.get_enabled_providers():
            if exclude_provider_id and config.provider_id == exclude_provider_id:
                continue

            provider = self._providers.get(config.provider_id)
            if not provider:
                continue

            # Check cached models for capability
            models = self._model_cache.get(config.provider_id, [])
            for model in models:
                if capability in model.capabilities:
                    return provider, config

        return None

    def get_health(self, provider_id: str) -> ProviderHealth:
        """Get cached health status."""
        return self._health_cache.get(provider_id)

    async def check_all_health(self):
        """Check health of all providers."""
        tasks = []
        for provider_id, provider in self._providers.items():
            tasks.append(self._check_provider_health(provider_id, provider))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_provider_health(self, provider_id: str, provider: ProviderBase):
        """Check health of a single provider."""
        try:
            health = await provider.health_check()
            self._health_cache[provider_id] = health

            # Update circuit breaker
            breaker = self._circuit_breakers.get(provider_id)
            if breaker:
                if health.status == ProviderStatus.AVAILABLE:
                    breaker.record_success()
                else:
                    breaker.record_failure()

        except Exception as e:
            logger.warning("health_check_failed", provider_id=provider_id, error=str(e))
            self._health_cache[provider_id] = ProviderHealth(
                status=ProviderStatus.UNAVAILABLE,
                latency_ms=0,
                error_rate=1.0,
                failure_reason=str(e)
            )

    def can_use_provider(self, provider_id: str) -> bool:
        """Check if provider can be used (circuit breaker + enabled)."""
        config = self._configs.get(provider_id)
        if not config or not config.enabled:
            return False

        breaker = self._circuit_breakers.get(provider_id)
        if breaker:
            return breaker.can_execute()

        return True

    def get_all_models(self) -> list[ModelInfo]:
        """Get all models from all providers."""
        models = []
        for model_list in self._model_cache.values():
            models.extend(model_list)
        return models

    def find_model(self, model_id: str) -> Optional[ModelInfo]:
        """Find model by ID across all providers."""
        for models in self._model_cache.values():
            for model in models:
                if model.model_id == model_id:
                    return model
        return None

    async def start_health_monitoring(self, interval_seconds: int = 30):
        """Start background health monitoring."""
        async def monitor():
            while True:
                await self.check_all_health()
                await asyncio.sleep(interval_seconds)

        self._health_check_task = asyncio.create_task(monitor())
        logger.info("health_monitoring_started", interval_seconds=interval_seconds)

    async def stop_health_monitoring(self):
        """Stop background health monitoring."""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        logger.info("health_monitoring_stopped")