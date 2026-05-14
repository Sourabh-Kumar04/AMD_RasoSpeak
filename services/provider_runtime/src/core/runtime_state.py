"""
Provider Runtime State Manager
===============================
Centralized state management for provider/model switching.
Single source of truth for active provider/model across all subsystems.
"""

from __future__ import annotations
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
import uuid
import structlog

logger = structlog.get_logger("rasospeak.provider_state")


class ProviderOwnership(Enum):
    """API ownership model."""
    PLATFORM = "platform"      # Uses platform API
    USER = "user"              # Uses user's API key
    HYBRID = "user_first"      # User key first, platform fallback


class ProviderStatus(Enum):
    """Runtime provider status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    SWITCHING = "switching"


@dataclass
class ActiveProviderState:
    """Current active provider state."""
    provider_id: str
    provider_type: str
    model: str
    ownership: ProviderOwnership
    session_id: str
    stream_active: bool = False
    context_window: list = field(default_factory=list)
    switched_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)


@dataclass
class SessionProviderContext:
    """Context preserved during provider switching."""
    session_id: str
    user_id: str
    current_provider_id: str
    current_model: str

    # Provider state before switch
    previous_provider_id: Optional[str] = None
    previous_model: Optional[str] = None

    # Conversation context (for continuity)
    message_history: list = field(default_factory=list)
    active_workflow_id: Optional[str] = None
    voice_session_active: bool = False

    # Memory context
    memory_checkpoint: Optional[dict] = None
    working_memory: list = field(default_factory=list)

    # Stream state
    stream_position: int = 0
    partial_response: Optional[str] = None

    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class ProviderRuntimeState:
    """
    Single source of truth for provider/model state.

    Manages:
    - Active provider/model
    - Session contexts
    - Provider switching events
    - State propagation to all subsystems
    """

    def __init__(self, event_bus=None):
        # Active state
        self._active_provider: Optional[ActiveProviderState] = None

        # Default settings
        self._default_provider_id: str = "google"
        self._default_model: str = "gemini-1.5-flash-8b"

        # Model registry (dynamically discovered)
        self._model_registry: dict[str, list[dict]] = {}  # provider_type -> models

        # Session contexts
        self._session_contexts: dict[str, SessionProviderContext] = {}

        # Provider configs
        self._provider_configs: dict[str, dict] = {}

        # Event bus for state changes
        self._event_bus = event_bus

        # Callbacks for state changes
        self._state_change_callbacks: list[callable] = []

        # Metrics
        self._switch_count = 0
        self._failover_count = 0

        logger.info("provider_runtime_state_initialized")

    # ─────────────────────────────────────────────────────────────
    # State Management
    # ─────────────────────────────────────────────────────────────

    def set_state_change_callback(self, callback: callable):
        """Register callback for state changes."""
        self._state_change_callbacks.append(callback)

    async def _notify_state_change(self, event_type: str, data: dict):
        """Notify all subsystems of state change."""
        for callback in self._state_change_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event_type, data)
                else:
                    callback(event_type, data)
            except Exception as e:
                logger.error("state_change_callback_error", error=str(e))

        # Publish event if event bus available
        if self._event_bus:
            await self._event_bus.publish(CognitEvent(
                event_type=f"provider_{event_type}",
                source="provider_runtime_state",
                payload=data
            ))

    async def set_active_provider(
        self,
        provider_id: str,
        model: str,
        ownership: ProviderOwnership = ProviderOwnership.PLATFORM,
        session_id: Optional[str] = None,
        preserve_context: bool = True
    ) -> bool:
        """
        Set active provider/model.

        This is the PRIMARY method for provider switching.
        Propagates to all subsystems instantly.
        """
        # Get previous state for context preservation
        previous_provider = self._active_provider.provider_id if self._active_provider else None
        previous_model = self._active_provider.model if self._active_provider else None

        # Update active state
        self._active_provider = ActiveProviderState(
            provider_id=provider_id,
            provider_type=self._get_provider_type(provider_id),
            model=model,
            ownership=ownership,
            session_id=session_id or "default",
            switched_at=datetime.utcnow()
        )

        # Update session context if exists
        if session_id and session_id in self._session_contexts:
            ctx = self._session_contexts[session_id]
            ctx.previous_provider_id = previous_provider
            ctx.previous_model = previous_model
            ctx.current_provider_id = provider_id
            ctx.current_model = model
            ctx.updated_at = datetime.utcnow()

        self._switch_count += 1

        # Notify all subsystems
        await self._notify_state_change("switch", {
            "provider_id": provider_id,
            "model": model,
            "previous_provider": previous_provider,
            "previous_model": previous_model,
            "session_id": session_id,
            "preserved": preserve_context
        })

        logger.info(
            "provider_switched",
            provider=provider_id,
            model=model,
            previous=previous_provider,
            session=session_id
        )

        return True

    def get_active_provider(self) -> Optional[ActiveProviderState]:
        """Get current active provider."""
        return self._active_provider

    def get_active_model(self) -> str:
        """Get current active model."""
        return self._active_provider.model if self._active_provider else self._default_model

    def get_active_provider_id(self) -> str:
        """Get current active provider ID."""
        return self._active_provider.provider_id if self._active_provider else self._default_provider_id

    # ─────────────────────────────────────────────────────────────
    # Defaults
    # ─────────────────────────────────────────────────────────────

    def set_default_provider(self, provider_id: str, model: str):
        """Set default provider/model."""
        self._default_provider_id = provider_id
        self._default_model = model

        # If no active provider, set as active
        if not self._active_provider:
            self._active_provider = ActiveProviderState(
                provider_id=provider_id,
                provider_type=self._get_provider_type(provider_id),
                model=model,
                ownership=ProviderOwnership.PLATFORM,
                session_id="default"
            )

    def get_default_provider(self) -> tuple[str, str]:
        """Get default provider and model."""
        return self._default_provider_id, self._default_model

    def _get_provider_type(self, provider_id: str) -> str:
        """Extract provider type from provider ID."""
        # Map provider IDs to types
        type_map = {
            "google": "google",
            "openai": "openai",
            "anthropic": "anthropic",
            "nvidia": "nvidia",
            "deepseek": "deepseek",
            "openrouter": "openrouter"
        }

        # Check if provider_id contains known type
        for ptype, ptype in type_map.items():
            if ptype in provider_id.lower():
                return ptype

        # Default mapping
        return "google"

    # ─────────────────────────────────────────────────────────────
    # Model Registry (Dynamic Discovery)
    # ─────────────────────────────────────────────────────────────

    def register_models(self, provider_type: str, models: list[dict]):
        """Register dynamically discovered models."""
        self._model_registry[provider_type] = models
        logger.info("models_registered", provider=provider_type, count=len(models))

    def get_available_models(self, provider_type: Optional[str] = None) -> list[dict]:
        """Get available models."""
        if provider_type:
            return self._model_registry.get(provider_type, [])

        all_models = []
        for models in self._model_registry.values():
            all_models.extend(models)
        return all_models

    def get_model_info(self, provider_type: str, model_id: str) -> Optional[dict]:
        """Get model metadata."""
        models = self._model_registry.get(provider_type, [])
        for m in models:
            if m.get("model_id") == model_id:
                return m
        return None

    # ─────────────────────────────────────────────────────────────
    # Provider Configuration
    # ─────────────────────────────────────────────────────────────

    def set_provider_config(
        self,
        provider_id: str,
        provider_type: str,
        api_key: Optional[str] = None,
        ownership: ProviderOwnership = ProviderOwnership.PLATFORM,
        priority: int = 100,
        enabled: bool = True,
        tags: list[str] = None
    ):
        """Set provider configuration."""
        self._provider_configs[provider_id] = {
            "provider_id": provider_id,
            "provider_type": provider_type,
            "api_key": api_key,
            "ownership": ownership.value,
            "priority": priority,
            "enabled": enabled,
            "tags": tags or []
        }

    def get_provider_config(self, provider_id: str) -> Optional[dict]:
        """Get provider configuration."""
        return self._provider_configs.get(provider_id)

    def get_providers_by_ownership(self, ownership: ProviderOwnership) -> list[dict]:
        """Get providers by ownership type."""
        return [
            cfg for cfg in self._provider_configs.values()
            if cfg.get("ownership") == ownership.value and cfg.get("enabled")
        ]

    # ─────────────────────────────────────────────────────────────
    # Session Context Management
    # ─────────────────────────────────────────────────────────────

    def create_session_context(
        self,
        session_id: str,
        user_id: str = "default"
    ) -> SessionProviderContext:
        """Create new session context."""
        ctx = SessionProviderContext(
            session_id=session_id,
            user_id=user_id,
            current_provider_id=self._default_provider_id,
            current_model=self._default_model
        )
        self._session_contexts[session_id] = ctx
        return ctx

    def get_session_context(self, session_id: str) -> Optional[SessionProviderContext]:
        """Get session context."""
        return self._session_contexts.get(session_id)

    async def update_session_context(self, session_id: str, **updates):
        """Update session context."""
        if session_id in self._session_contexts:
            ctx = self._session_contexts[session_id]
            for key, value in updates.items():
                if hasattr(ctx, key):
                    setattr(ctx, key, value)
            ctx.updated_at = datetime.utcnow()

    # ─────────────────────────────────────────────────────────────
    # Provider Switching with Context Preservation
    # ─────────────────────────────────────────────────────────────

    async def switch_provider_preserve(
        self,
        session_id: str,
        target_provider_id: str,
        target_model: Optional[str] = None
    ) -> bool:
        """
        Switch provider while preserving session context.

        Used for hot-swapping during active sessions.
        """
        ctx = self._session_contexts.get(session_id)
        if not ctx:
            ctx = self.create_session_context(session_id)

        # Store checkpoint before switch
        checkpoint = {
            "message_history": ctx.message_history.copy(),
            "working_memory": ctx.working_memory.copy(),
            "stream_position": ctx.stream_position,
            "previous_provider": ctx.current_provider_id,
            "previous_model": ctx.current_model
        }

        # Determine target model
        if not target_model:
            target_model = self.get_model_for_provider(target_provider_id)

        # Update session context
        ctx.previous_provider_id = ctx.current_provider_id
        ctx.previous_model = ctx.current_model
        ctx.current_provider_id = target_provider_id
        ctx.current_model = target_model
        ctx.memory_checkpoint = checkpoint
        ctx.updated_at = datetime.utcnow()

        # Update active provider
        await self.set_active_provider(
            provider_id=target_provider_id,
            model=target_model,
            session_id=session_id,
            preserve_context=True
        )

        logger.info(
            "provider_switched_preserve",
            session=session_id,
            from_provider=ctx.previous_provider_id,
            to_provider=target_provider_id
        )

        return True

    def get_model_for_provider(self, provider_id: str) -> str:
        """Get default model for provider."""
        provider_model_map = {
            "google": "gemini-1.5-flash-8b",
            "openai": "gpt-4o",
            "anthropic": "claude-3-5-sonnet-20241022",
            "nvidia": "meta/llama-3.1-70b-instruct",
            "deepseek": "deepseek-chat",
            "openrouter": "google/gemini-2.0-flash"
        }
        return provider_model_map.get(provider_id, "gpt-4o")

    # ─────────────────────────────────────────────────────────────
    # Metrics
    # ─────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get runtime statistics."""
        return {
            "active_provider": self._active_provider.provider_id if self._active_provider else None,
            "active_model": self._active_provider.model if self._active_provider else None,
            "default_provider": self._default_provider_id,
            "default_model": self._default_model,
            "switch_count": self._switch_count,
            "failover_count": self._failover_count,
            "active_sessions": len(self._session_contexts),
            "registered_providers": len(self._provider_configs),
            "model_counts": {p: len(m) for p, m in self._model_registry.items()}
        }


# Global runtime state
_runtime_state: Optional[ProviderRuntimeState] = None


def get_provider_runtime_state() -> ProviderRuntimeState:
    """Get global provider runtime state."""
    global _runtime_state
    if _runtime_state is None:
        _runtime_state = ProviderRuntimeState()
        # Set defaults
        _runtime_state.set_default_provider("google", "gemini-1.5-flash-8b")
    return _runtime_state