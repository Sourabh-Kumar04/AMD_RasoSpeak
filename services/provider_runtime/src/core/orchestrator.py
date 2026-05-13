"""
Provider Orchestrator
=====================
Intelligent routing, live hot-swapping, and failover orchestration.
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable, Any
import uuid

from ..core.provider_base import (
    ProviderBase, ProviderHealth, ProviderStatus, ModelInfo,
    ProviderCapability, StreamChunk, ProviderError
)
from .provider_registry import ProviderRegistry, ProviderConfig
import structlog

logger = structlog.get_logger("rasospeak.orchestrator")


class RoutingStrategy(Enum):
    """How to select provider."""
    LATENCY_AWARE = "latency_aware"  # Fastest response
    COST_OPTIMIZED = "cost_optimized"  # Cheapest
    QUALITY_FIRST = "quality_first"  # Best model
    CAPABILITY_MATCH = "capability_match"  # Has required capability
    ROUND_ROBIN = "round_robin"  # Distribute load
    FALLBACK = "fallback"  # Try in order until one works


@dataclass
class RequestContext:
    """Context for a request - enables smart routing."""
    request_id: str
    user_id: str
    session_id: Optional[str] = None

    # Request requirements
    required_capabilities: list[ProviderCapability] = field(default_factory=list)
    preferred_models: list[str] = field(default_factory=list)
    max_latency_ms: Optional[float] = None
    max_cost: Optional[float] = None

    # Current state (for continuity during failover)
    conversation_history: list[dict] = field(default_factory=list)
    current_provider_id: Optional[str] = None
    current_model: Optional[str] = None

    # Routing preferences
    strategy: RoutingStrategy = RoutingStrategy.CAPABILITY_MATCH
    allowed_providers: list[str] = field(default_factory=list)
    excluded_providers: list[str] = field(default_factory=list)

    # Metadata
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class OrchestratorResponse:
    """Response from orchestrator with metadata."""
    response_id: str
    content: str
    provider: str
    model: str
    usage: dict
    finish_reason: str
    latency_ms: float
    metadata: dict = field(default_factory=dict)
    failover_occurred: bool = False
    failover_history: list[str] = field(default_factory=list)


class ProviderOrchestrator:
    """
    Main orchestrator for intelligent provider routing and hot-swapping.

    Features:
    - Live provider switching during active sessions
    - Automatic failover on errors
    - Context preservation during provider changes
    - Intelligent routing based on request requirements
    - Token usage tracking and cost optimization
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        on_provider_switch: Optional[Callable] = None  # Callback for UI updates
    ):
        self._registry = registry
        self._on_provider_switch = on_provider_switch

        # Session state - preserves context across provider switches
        self._session_contexts: dict[str, RequestContext] = {}

        # Metrics
        self._request_counts: dict[str, int] = {}
        self._total_costs: dict[str, float] = {}

        # Fallback chain
        self._fallback_chains: dict[str, list[str]] = {}

    async def chat_complete(
        self,
        messages: list[dict],
        context: Optional[RequestContext] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> tuple[OrchestratorResponse, AsyncGenerator[StreamChunk, None] | None]:
        """
        Main entry point for chat completion with intelligent routing.

        Returns tuple of (response for non-streaming, generator for streaming)
        """
        # Create context if not provided
        if context is None:
            context = RequestContext(
                request_id=str(uuid.uuid4()),
                user_id="default"
            )

        # Apply conversation history to messages for context continuity
        if context.conversation_history and messages:
            combined_messages = context.conversation_history + messages
        else:
            combined_messages = messages

        # Try to find best provider
        provider, config = await self._select_provider(context, model)

        if not provider:
            raise ProviderError("No available provider found", provider="orchestrator")

        # Attempt request with automatic failover
        response, stream_gen, failover_history = await self._execute_with_fallback(
            provider=provider,
            config=config,
            messages=combined_messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            context=context,
            **kwargs
        )

        # Update session context
        context.conversation_history.extend(messages)
        context.conversation_history.append({
            "role": "assistant",
            "content": response.content if not stream else "[stream]"
        })
        context.current_provider_id = config.provider_id
        context.current_model = model or config.default_model

        # Return appropriate response type
        if stream:
            orch_response = OrchestratorResponse(
                response_id=response.response_id,
                content="",
                provider=config.provider_type,
                model=model or config.default_model,
                usage=response.usage,
                finish_reason="",
                latency_ms=response.latency_ms,
                metadata=response.metadata,
                failover_occurred=len(failover_history) > 0,
                failover_history=failover_history
            )
            return orch_response, stream_gen
        else:
            return OrchestratorResponse(
                response_id=response.response_id,
                content=response.content,
                provider=config.provider_type,
                model=model or config.default_model,
                usage=response.usage,
                finish_reason=response.finish_reason,
                latency_ms=response.latency_ms,
                metadata=response.metadata,
                failover_occurred=len(failover_history) > 0,
                failover_history=failover_history
            ), None

    async def _select_provider(
        self,
        context: RequestContext,
        preferred_model: Optional[str] = None
    ) -> tuple[Optional[ProviderBase], Optional[ProviderConfig]]:
        """Select best provider based on context and strategy."""

        # If model specified, find provider that has it
        if preferred_model:
            model_info = self._registry.find_model(preferred_model)
            if model_info:
                # Find provider that owns this model
                for config in self._registry.get_enabled_providers():
                    if config.provider_type == model_info.provider:
                        if self._registry.can_use_provider(config.provider_id):
                            return self._registry.get_provider(config.provider_id), config

        # Strategy-based selection
        if context.strategy == RoutingStrategy.CAPABILITY_MATCH:
            for cap in context.required_capabilities:
                result = await self._registry.get_provider_by_capability(
                    cap,
                    exclude_provider_id=context.current_provider_id
                )
                if result:
                    return result

            # Fallback to any enabled provider
            for config in self._registry.get_enabled_providers():
                if config.provider_id not in context.excluded_providers:
                    if self._registry.can_use_provider(config.provider_id):
                        return self._registry.get_provider(config.provider_id), config

        elif context.strategy == RoutingStrategy.LATENCY_AWARE:
            best = None
            best_latency = float('inf')
            for config in self._registry.get_enabled_providers():
                health = self._registry.get_health(config.provider_id)
                if health and health.latency_ms < best_latency:
                    best = config
                    best_latency = health.latency_ms

            if best:
                return self._registry.get_provider(best.provider_id), best

        elif context.strategy == RoutingStrategy.COST_OPTIMIZED:
            for config in self._registry.get_enabled_providers():
                if self._registry.can_use_provider(config.provider_id):
                    return self._registry.get_provider(config.provider_id), config

        # Default: use highest priority
        for config in self._registry.get_enabled_providers():
            if self._registry.can_use_provider(config.provider_id):
                return self._registry.get_provider(config.provider_id), config

        return None, None

    async def _execute_with_fallback(
        self,
        provider: ProviderBase,
        config: ProviderConfig,
        messages: list[dict],
        model: Optional[str],
        temperature: float,
        max_tokens: Optional[int],
        stream: bool,
        context: RequestContext,
        **kwargs
    ) -> tuple[Any, Any, list[str]]:
        """Execute request with automatic failover."""

        failover_history = []
        tried_providers = {config.provider_id} if config else set()

        while True:
            if not provider or not config:
                break

            try:
                if stream:
                    response = await provider.chat_complete(
                        messages=messages,
                        model=model or config.default_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                        **kwargs
                    )
                    return response, response, failover_history
                else:
                    response = await provider.chat_complete(
                        messages=messages,
                        model=model or config.default_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=False,
                        **kwargs
                    )
                    return response, None, failover_history

            except ProviderError as e:
                logger.warning(
                    "provider_error",
                    provider=config.provider_id,
                    error=e.message,
                    status=e.status.value
                )

                # Find next fallback
                next_provider, next_config = await self._find_fallback(
                    context=context,
                    tried_providers=tried_providers,
                    error=e
                )

                if next_provider and next_config:
                    failover_history.append(f"{config.provider_id} -> {next_config.provider_id}")

                    # Notify about provider switch
                    if self._on_provider_switch:
                        await self._on_provider_switch(
                            old_provider=config.provider_id,
                            new_provider=next_config.provider_id,
                            reason=str(e)
                        )

                    # Update for next iteration
                    provider = next_provider
                    config = next_config
                    tried_providers.add(config.provider_id)

                    logger.info(
                        "failover_triggered",
                        old_provider=failover_history[-1].split(" -> ")[0],
                        new_provider=config.provider_id,
                        reason=e.message
                    )
                else:
                    # No more fallbacks
                    raise e

    async def _find_fallback(
        self,
        context: RequestContext,
        tried_providers: set[str],
        error: ProviderError
    ) -> tuple[Optional[ProviderBase], Optional[ProviderConfig]]:
        """Find fallback provider."""

        # Get fallback chain based on error type
        if error.quota_exceeded:
            fallback_order = self._fallback_chains.get("quota_exceeded", [])
        elif error.rate_limited:
            fallback_order = self._fallback_chains.get("rate_limited", [])
        elif error.timeout:
            fallback_order = self._fallback_chains.get("timeout", [])
        else:
            fallback_order = []

        # Try fallback chain
        for fallback_id in fallback_order:
            if fallback_id not in tried_providers:
                if self._registry.can_use_provider(fallback_id):
                    return (
                        self._registry.get_provider(fallback_id),
                        self._registry.get_config(fallback_id)
                    )

        # Try any enabled provider not yet tried
        for config in self._registry.get_enabled_providers():
            if config.provider_id not in tried_providers:
                if self._registry.can_use_provider(config.provider_id):
                    return (
                        self._registry.get_provider(config.provider_id),
                        config
                    )

        return None, None

    def set_fallback_chain(self, error_type: str, provider_ids: list[str]):
        """Configure fallback chain for specific error types."""
        self._fallback_chains[error_type] = provider_ids
        logger.info("fallback_chain_configured", error_type=error_type, providers=provider_ids)

    def get_active_context(self, session_id: str) -> Optional[RequestContext]:
        """Get current context for a session."""
        return self._session_contexts.get(session_id)

    def create_session_context(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        **kwargs
    ) -> RequestContext:
        """Create new session context."""
        session_id = session_id or str(uuid.uuid4())
        context = RequestContext(
            request_id=str(uuid.uuid4()),
            user_id=user_id,
            session_id=session_id,
            **kwargs
        )
        self._session_contexts[session_id] = context
        return context

    def update_session_context(self, session_id: str, **updates):
        """Update session context with new values."""
        if session_id in self._session_contexts:
            ctx = self._session_contexts[session_id]
            for key, value in updates.items():
                if hasattr(ctx, key):
                    setattr(ctx, key, value)

    def get_provider_stats(self) -> dict:
        """Get provider usage statistics."""
        stats = {}
        for config in self._registry.list_providers():
            stats[config.provider_id] = {
                "requests": self._request_counts.get(config.provider_id, 0),
                "cost": self._total_costs.get(config.provider_id, 0),
                "health": self._registry.get_health(config.provider_id).__dict__ if self._registry.get_health(config.provider_id) else None,
                "enabled": config.enabled
            }
        return stats

    async def switch_provider(
        self,
        session_id: str,
        target_provider_id: str,
        preserve_context: bool = True
    ) -> bool:
        """
        Manually switch provider for a session.

        Used for voice commands like "Hey Raso, switch to NVIDIA"
        """
        context = self._session_contexts.get(session_id)
        if not context:
            return False

        if not self._registry.can_use_provider(target_provider_id):
            return False

        # Update context
        context.current_provider_id = target_provider_id
        logger.info(
            "manual_provider_switch",
            session_id=session_id,
            new_provider=target_provider_id
        )

        return True