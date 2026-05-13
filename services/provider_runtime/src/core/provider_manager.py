"""
Provider Manager - Unified Provider Runtime
==========================================
Production-grade provider orchestration with hot-swapping.
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any
import uuid

from .runtime_state import (
    ProviderRuntimeState, ProviderOwnership, get_provider_runtime_state,
    ActiveProviderState, SessionProviderContext
)
from .model_discovery import ModelDiscoveryService, get_model_discovery
from .provider_base import ProviderBase, ProviderHealth, ProviderStatus
from .orchestrator import ProviderOrchestrator, RequestContext, RoutingStrategy
import structlog

logger = structlog.get_logger("rasospeak.provider_manager")


@dataclass
class ProviderSwitchEvent:
    """Event emitted when provider switches."""
    session_id: str
    from_provider: str
    from_model: str
    to_provider: str
    to_model: str
    reason: str  # manual, failover, quota_exceeded
    preserved_context: bool
    timestamp: datetime


class ProviderManager:
    """
    Unified Provider Runtime Manager.

    Single source of truth for ALL provider operations.
    Replaces disconnected provider states.
    """

    def __init__(self):
        # State management
        self._state = get_provider_runtime_state()
        self._discovery = get_model_discovery()

        # Orchestrator (lazy init)
        self._orchestrator: Optional[ProviderOrchestrator] = None

        # Provider instances (lazy init)
        self._providers: dict[str, ProviderBase] = {}

        # Callbacks
        self._switch_callbacks: list[callable] = []

        # Initialize synchronously (model discovery is synchronous)
        self._sync_initialize()

        logger.info("provider_manager_initialized")

    def _sync_initialize(self):
        """Synchronous initialization."""
        # Discover models (these are pre-defined, not API calls)
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            models = loop.run_until_complete(self._discovery.discover_all_models())

            # Register models in state
            for provider_type, model_list in models.items():
                models_dict = [m.to_dict() for m in model_list]
                self._state.register_models(provider_type, models_dict)

            loop.close()
        except Exception as e:
            logger.warning("model_discovery_init_failed", error=str(e))

    async def _initialize(self):
        """Async initialization (for later use)."""
        # Discover all models
        models = await self._discovery.discover_all_models()

        # Register models in state
        for provider_type, model_list in models.items():
            models_dict = [m.to_dict() for m in model_list]
            self._state.register_models(provider_type, models_dict)

        logger.info("provider_manager_ready", models=len(models))

    # ─────────────────────────────────────────────────────────────
    # Provider Registration
    # ─────────────────────────────────────────────────────────────

    async def register_provider(
        self,
        provider_type: str,
        api_key: Optional[str] = None,
        ownership: ProviderOwnership = ProviderOwnership.PLATFORM,
        priority: int = 100,
        tags: list[str] = None,
        base_url: Optional[str] = None
    ) -> str:
        """Register a provider with optional API key."""
        provider_id = f"{provider_type}_{uuid.uuid4().hex[:8]}"

        # Set provider config
        self._state.set_provider_config(
            provider_id=provider_id,
            provider_type=provider_type,
            api_key=api_key,
            ownership=ownership,
            priority=priority,
            enabled=True,
            tags=tags or []
        )

        # Create provider instance if API key provided
        if api_key:
            await self._create_provider_instance(provider_id, provider_type, api_key, base_url)

        logger.info(
            "provider_registered",
            provider_id=provider_id,
            provider_type=provider_type,
            ownership=ownership.value
        )

        return provider_id

    async def _create_provider_instance(
        self,
        provider_id: str,
        provider_type: str,
        api_key: str,
        base_url: Optional[str]
    ):
        """Create provider instance."""
        # Lazy import to avoid circular dependencies
        try:
            from ..providers import OpenAIProvider, AnthropicProvider, GoogleProvider

            if provider_type == "openai":
                self._providers[provider_id] = OpenAIProvider(api_key=api_key, base_url=base_url)
            elif provider_type == "anthropic":
                self._providers[provider_id] = AnthropicProvider(api_key=api_key, base_url=base_url)
            elif provider_type == "google":
                self._providers[provider_id] = GoogleProvider(api_key=api_key)
            # Add more providers as needed
        except Exception as e:
            logger.error("provider_creation_failed", provider_type=provider_type, error=str(e))

    # ─────────────────────────────────────────────────────────────
    # Provider Switching
    # ─────────────────────────────────────────────────────────────

    async def switch_provider(
        self,
        provider_id: str,
        model: Optional[str] = None,
        session_id: str = "default",
        reason: str = "manual"
    ) -> bool:
        """
        Switch provider instantly with context preservation.
        """
        # Get current context
        ctx = self._state.get_session_context(session_id)
        if not ctx:
            ctx = self._state.create_session_context(session_id)

        # Determine target model
        if not model:
            model = self._state.get_model_for_provider(provider_id)

        # Store checkpoint
        checkpoint = {
            "message_history": ctx.message_history.copy(),
            "working_memory": ctx.working_memory.copy(),
            "stream_position": ctx.stream_position
        }

        # Perform switch
        success = await self._state.switch_provider_preserve(
            session_id=session_id,
            target_provider_id=provider_id,
            target_model=model
        )

        if success:
            # Emit switch event
            event = ProviderSwitchEvent(
                session_id=session_id,
                from_provider=ctx.previous_provider_id or "",
                from_model=ctx.previous_model or "",
                to_provider=provider_id,
                to_model=model,
                reason=reason,
                preserved_context=True,
                timestamp=datetime.utcnow()
            )

            # Notify callbacks
            for callback in self._switch_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    logger.error("switch_callback_error", error=str(e))

            logger.info(
                "provider_switch_complete",
                session=session_id,
                to_provider=provider_id,
                to_model=model
            )

        return success

    async def switch_by_type(
        self,
        provider_type: str,
        model: Optional[str] = None,
        session_id: str = "default"
    ) -> bool:
        """Switch by provider type (openai, anthropic, google, etc)."""
        # Find provider ID for type
        configs = self._state._provider_configs
        for pid, cfg in configs.items():
            if cfg["provider_type"] == provider_type and cfg["enabled"]:
                return await self.switch_provider(pid, model, session_id)

        # If not found, use default mapping
        provider_id = f"{provider_type}_default"
        return await self.switch_provider(provider_id, model, session_id)

    def register_switch_callback(self, callback: callable):
        """Register callback for provider switches."""
        self._switch_callbacks.append(callback)

    # ─────────────────────────────────────────────────────────────
    # State Queries
    # ─────────────────────────────────────────────────────────────

    def get_active_state(self) -> Optional[ActiveProviderState]:
        """Get current active provider state."""
        return self._state.get_active_provider()

    def get_session_context(self, session_id: str) -> Optional[SessionProviderContext]:
        """Get session context."""
        return self._state.get_session_context(session_id)

    def get_all_providers(self) -> list[dict]:
        """Get all registered providers."""
        configs = self._state._provider_configs
        return [
            {
                **cfg,
                "active": cfg["provider_id"] == self._state.get_active_provider_id()
            }
            for cfg in configs.values()
        ]

    def get_all_models(self) -> list[dict]:
        """Get all available models."""
        return self._discovery.get_all_models_flat()

    def get_models_by_provider(self, provider_type: str) -> list[dict]:
        """Get models for specific provider."""
        models = self._discovery._discovered_models.get(provider_type, [])
        return [m.to_dict() for m in models]

    def get_provider_by_capability(self, capability: str) -> list[dict]:
        """Find providers with capability."""
        models = self._discovery.get_models_by_capability(capability)
        return [m.to_dict() for m in models]

    def get_cheapest_model(self, provider_type: Optional[str] = None) -> Optional[dict]:
        """Get cheapest model."""
        model = self._discovery.get_cheapest_model(provider_type)
        return model.to_dict() if model else None

    def get_fastest_model(self, provider_type: Optional[str] = None) -> Optional[dict]:
        """Get fastest model."""
        model = self._discovery.get_fastest_model(provider_type)
        return model.to_dict() if model else None

    # ─────────────────────────────────────────────────────────────
    # Audio Command Integration
    # ─────────────────────────────────────────────────────────────

    async def handle_voice_command(self, transcript: str) -> tuple[bool, str]:
        """
        Handle voice command for provider switching.

        Examples:
        - "Switch to NVIDIA" -> provider_type="nvidia"
        - "Use Claude for reasoning" -> provider_type="anthropic", purpose="reasoning"
        - "Switch to DeepSeek for coding" -> provider_type="deepseek", purpose="coding"
        """
        transcript_lower = transcript.lower()

        # Provider mappings
        provider_commands = {
            "nvidia": ["nvidia", "nemotron"],
            "openai": ["openai", "gpt"],
            "anthropic": ["claude", "anthropic"],
            "google": ["google", "gemini", "google ai"],
            "deepseek": ["deepseek"],
            "openrouter": ["openrouter"]
        }

        # Model purpose mappings
        purpose_commands = {
            "reasoning": ["reasoning", "think", "thinker"],
            "coding": ["coding", "code", "programmer", "developer"],
            "voice": ["voice", "speak", "speaking", "fast"],
            "fast": ["fast", "quick", "speed"],
            "cheap": ["cheap", "budget", "affordable"],
        }

        # Detect provider
        detected_provider = None
        for provider, keywords in provider_commands.items():
            for keyword in keywords:
                if keyword in transcript_lower:
                    detected_provider = provider
                    break
            if detected_provider:
                break

        if not detected_provider:
            return False, "No provider detected in command"

        # Detect purpose (for model selection)
        detected_purpose = None
        for purpose, keywords in purpose_commands.items():
            for keyword in keywords:
                if keyword in transcript_lower:
                    detected_purpose = purpose
                    break
            if detected_purpose:
                break

        # Select model based on purpose
        selected_model = None
        if detected_purpose:
            purpose_models = {
                "reasoning": {"anthropic": "claude-opus-4-20250514", "openai": "o1-mini"},
                "coding": {"deepseek": "deepseek-coder", "openai": "gpt-4o"},
                "voice": {"google": "gemini-2.0-flash-exp"},
                "fast": {"google": "gemini-1.5-flash-8b", "openai": "gpt-4o-mini"},
                "cheap": {"deepseek": "deepseek-chat", "google": "gemini-1.5-flash-8b"}
            }
            selected_model = purpose_models.get(detected_purpose, {}).get(detected_provider)

        # Perform switch
        success = await self.switch_by_type(
            provider_type=detected_provider,
            model=selected_model
        )

        if success:
            provider_names = {
                "nvidia": "NVIDIA Nemotron",
                "openai": "OpenAI GPT",
                "anthropic": "Anthropic Claude",
                "google": "Google Gemini",
                "deepseek": "DeepSeek",
                "openrouter": "OpenRouter"
            }
            name = provider_names.get(detected_provider, detected_provider)
            return True, f"Switched to {name} while preserving your conversation"
        else:
            return False, f"Failed to switch to {detected_provider}"

    # ─────────────────────────────────────────────────────────────
    # Metrics
    # ─────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get manager statistics."""
        return {
            **self._state.get_stats(),
            "models_total": len(self.get_all_models()),
            "providers_registered": len(self._state._provider_configs)
        }


# Global manager
_provider_manager: Optional[ProviderManager] = None


def get_provider_manager() -> ProviderManager:
    """Get global provider manager."""
    global _provider_manager
    if _provider_manager is None:
        _provider_manager = ProviderManager()
    return _provider_manager