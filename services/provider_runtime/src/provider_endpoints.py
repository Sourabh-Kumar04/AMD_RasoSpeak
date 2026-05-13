"""
Provider Management Endpoints
=============================
FastAPI endpoints for provider orchestration.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import structlog

logger = structlog.get_logger("rasospeak.provider_endpoints")

provider_router = APIRouter(prefix="/api/providers", tags=["providers"])

# ─────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────

class ProviderAddRequest(BaseModel):
    provider_type: str  # openai, anthropic, google, etc.
    api_key: str
    base_url: Optional[str] = None
    is_platform: bool = False
    priority: int = 100
    tags: List[str] = []


class ProviderUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    tags: Optional[List[str]] = None


class RouteRequest(BaseModel):
    provider_id: Optional[str] = None
    model: Optional[str] = None
    strategy: str = "capability_match"  # latency_aware, cost_optimized, quality_first
    required_capabilities: List[str] = []


# ─────────────────────────────────────────────────────────────
# Global orchestrator (set from main.py)
# ─────────────────────────────────────────────────────────────

_orchestrator = None
_registry = None


def set_orchestrator(orchestrator, registry):
    """Set global orchestrator from main.py."""
    global _orchestrator, _registry
    _orchestrator = orchestrator
    _registry = registry


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@provider_router.get("/")
async def list_providers():
    """List all registered providers."""
    if not _registry:
        return {"providers": [], "message": "Provider system not initialized"}

    providers = _registry.list_providers()
    return {
        "providers": [
            {
                "provider_id": p.provider_id,
                "provider_type": p.provider_type,
                "is_platform": p.is_platform,
                "priority": p.priority,
                "enabled": p.enabled,
                "tags": p.tags,
                "health": _registry.get_health(p.provider_id).__dict__ if _registry.get_health(p.provider_id) else None
            }
            for p in providers
        ]
    }


@provider_router.get("/{provider_id}")
async def get_provider(provider_id: str):
    """Get provider details."""
    if not _registry:
        raise HTTPException(status_code=500, detail="Provider system not initialized")

    config = _registry.get_config(provider_id)
    if not config:
        raise HTTPException(status_code=404, detail="Provider not found")

    health = _registry.get_health(provider_id)
    models = _registry._model_cache.get(provider_id, [])

    return {
        "provider": {
            "provider_id": config.provider_id,
            "provider_type": config.provider_type,
            "is_platform": config.is_platform,
            "priority": config.priority,
            "enabled": config.enabled,
            "tags": config.tags,
        },
        "health": health.__dict__ if health else None,
        "models": [
            {
                "model_id": m.model_id,
                "name": m.name,
                "context_window": m.context_window,
                "capabilities": [c.value for c in m.capabilities]
            }
            for m in models
        ]
    }


@provider_router.post("/")
async def add_provider(req: ProviderAddRequest):
    """Add new provider."""
    if not _registry:
        raise HTTPException(status_code=500, detail="Provider system not initialized")

    from .core.provider_registry import ProviderConfig
    from .providers import OpenAIProvider, AnthropicProvider, GoogleProvider

    # Create provider instance
    provider_map = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "google": GoogleProvider,
    }

    provider_class = provider_map.get(req.provider_type)
    if not provider_class:
        raise HTTPException(status_code=400, detail=f"Unknown provider type: {req.provider_type}")

    provider = provider_class(api_key=req.api_key, base_url=req.base_url)

    # Create config
    config = ProviderConfig(
        provider_id=f"{req.provider_type}_{req.api_key[:8]}",
        provider_type=req.provider_type,
        api_key=req.api_key,
        base_url=req.base_url,
        is_platform=req.is_platform,
        priority=req.priority,
        enabled=True,
        tags=req.tags
    )

    # Register
    await _registry.register_provider(config, provider)

    return {"status": "added", "provider_id": config.provider_id}


@provider_router.delete("/{provider_id}")
async def remove_provider(provider_id: str):
    """Remove provider."""
    if not _registry:
        raise HTTPException(status_code=500, detail="Provider system not initialized")

    result = await _registry.unregister_provider(provider_id)
    if not result:
        raise HTTPException(status_code=404, detail="Provider not found")

    return {"status": "removed", "provider_id": provider_id}


@provider_router.patch("/{provider_id}")
async def update_provider(provider_id: str, req: ProviderUpdateRequest):
    """Update provider settings."""
    if not _registry:
        raise HTTPException(status_code=500, detail="Provider system not initialized")

    config = _registry.get_config(provider_id)
    if not config:
        raise HTTPException(status_code=404, detail="Provider not found")

    if req.enabled is not None:
        config.enabled = req.enabled
    if req.priority is not None:
        config.priority = req.priority
    if req.tags is not None:
        config.tags = req.tags

    return {"status": "updated", "provider_id": provider_id}


@provider_router.get("/stats")
async def get_provider_stats():
    """Get provider usage statistics."""
    if not _orchestrator:
        return {"message": "Provider system not initialized"}

    stats = _orchestrator.get_provider_stats()
    return {"stats": stats}


@provider_router.get("/models")
async def list_all_models():
    """List all available models across providers."""
    if not _registry:
        return {"models": [], "message": "Provider system not initialized"}

    models = _registry.get_all_models()
    return {
        "models": [
            {
                "model_id": m.model_id,
                "name": m.name,
                "provider": m.provider,
                "context_window": m.context_window,
                "capabilities": [c.value for c in m.capabilities],
                "pricing": m.pricing
            }
            for m in models
        ]
    }


@provider_router.post("/switch")
async def switch_provider(session_id: str, target_provider_id: str):
    """Switch provider for active session."""
    if not _orchestrator:
        raise HTTPException(status_code=500, detail="Provider system not initialized")

    success = await _orchestrator.switch_provider(session_id, target_provider_id)
    if not success:
        raise HTTPException(status_code=400, detail="Switch failed")

    return {"status": "switched", "new_provider": target_provider_id}


@provider_router.post("/fallback-chain")
async def set_fallback_chain(error_type: str, provider_ids: List[str]):
    """Configure fallback chain for error types."""
    if not _orchestrator:
        raise HTTPException(status_code=500, detail="Provider system not initialized")

    _orchestrator.set_fallback_chain(error_type, provider_ids)
    return {"status": "configured", "error_type": error_type}