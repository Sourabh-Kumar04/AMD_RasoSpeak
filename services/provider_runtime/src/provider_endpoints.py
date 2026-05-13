"""
Provider Management Endpoints
=============================
FastAPI endpoints for unified provider runtime.
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
    provider_type: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    ownership: str = "platform"
    priority: int = 100
    tags: List[str] = []


class ProviderUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    tags: Optional[List[str]] = None


class ProviderSwitchRequest(BaseModel):
    provider_type: Optional[str] = None
    provider_id: Optional[str] = None
    model: Optional[str] = None
    session_id: str = "default"


class VoiceCommandRequest(BaseModel):
    transcript: str
    session_id: str = "default"


# ─────────────────────────────────────────────────────────────
# Global manager
# ─────────────────────────────────────────────────────────────

_manager = None


def set_provider_manager(manager):
    global _manager
    _manager = manager


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@provider_router.get("/stats")
async def get_provider_stats():
    """Get provider system statistics."""
    if not _manager:
        return {"status": "initializing"}
    return _manager.get_stats()


@provider_router.get("/")
async def list_providers():
    """List all registered providers with status."""
    if not _manager:
        return {"providers": [], "message": "Provider system initializing", "status": "initializing"}
    providers = _manager.get_all_providers()
    active_state = _manager.get_active_state()
    return {
        "providers": providers,
        "active": {
            "provider_id": active_state.provider_id if active_state else None,
            "model": active_state.model if active_state else None,
            "ownership": active_state.ownership.value if active_state else "platform"
        } if active_state else None,
        "status": "ready"
    }


@provider_router.get("/active")
async def get_active_provider():
    """Get currently active provider."""
    if not _manager:
        raise HTTPException(status_code=500, detail="Provider system not initialized")
    state = _manager.get_active_state()
    if not state:
        raise HTTPException(status_code=404, detail="No active provider")
    return {
        "provider_id": state.provider_id,
        "provider_type": state.provider_type,
        "model": state.model,
        "ownership": state.ownership.value,
        "session_id": state.session_id,
        "switched_at": state.switched_at.isoformat()
    }


@provider_router.get("/models")
async def list_all_models():
    """List all available models across all providers."""
    if not _manager:
        return {"models": [], "status": "initializing"}
    models = _manager.get_all_models()
    return {"models": models, "total": len(models)}


@provider_router.get("/models/by-capability")
async def get_models_by_capability(capability: str):
    """Find models with specific capability."""
    if not _manager:
        raise HTTPException(status_code=500, detail="Provider system not initialized")
    models = _manager.get_provider_by_capability(capability)
    return {"models": models, "capability": capability}


@provider_router.get("/models/cheapest")
async def get_cheapest_model(provider_type: Optional[str] = None):
    """Get cheapest available model."""
    if not _manager:
        raise HTTPException(status_code=500, detail="Provider system not initialized")
    model = _manager.get_cheapest_model(provider_type)
    if not model:
        raise HTTPException(status_code=404, detail="No model found")
    return {"model": model}


@provider_router.get("/models/fastest")
async def get_fastest_model(provider_type: Optional[str] = None):
    """Get fastest available model."""
    if not _manager:
        raise HTTPException(status_code=500, detail="Provider system not initialized")
    model = _manager.get_fastest_model(provider_type)
    if not model:
        raise HTTPException(status_code=404, detail="No model found")
    return {"model": model}


@provider_router.get("/{provider_id}")
async def get_provider(provider_id: str):
    """Get provider details."""
    if not _manager:
        raise HTTPException(status_code=500, detail="Provider system not initialized")
    config = _manager._state.get_provider_config(provider_id)
    if not config:
        raise HTTPException(status_code=404, detail="Provider not found")
    models = _manager.get_models_by_provider(config["provider_type"])
    active_state = _manager.get_active_state()
    is_active = active_state and active_state.provider_id == provider_id
    return {
        "provider": {**config, "is_active": is_active},
        "models": models
    }


@provider_router.post("/")
async def add_provider(req: ProviderAddRequest):
    """Add new provider with optional API key."""
    if not _manager:
        raise HTTPException(status_code=500, detail="Provider system not initialized")
    from .core.runtime_state import ProviderOwnership
    ownership_map = {
        "platform": ProviderOwnership.PLATFORM,
        "user": ProviderOwnership.USER,
        "hybrid": ProviderOwnership.HYBRID
    }
    ownership = ownership_map.get(req.ownership, ProviderOwnership.PLATFORM)
    provider_id = await _manager.register_provider(
        provider_type=req.provider_type,
        api_key=req.api_key,
        ownership=ownership,
        priority=req.priority,
        tags=req.tags,
        base_url=req.base_url
    )
    return {"status": "added", "provider_id": provider_id}


@provider_router.delete("/{provider_id}")
async def remove_provider(provider_id: str):
    """Remove provider."""
    if not _manager:
        raise HTTPException(status_code=500, detail="Provider system not initialized")
    return {"status": "removed", "provider_id": provider_id}


@provider_router.patch("/{provider_id}")
async def update_provider(provider_id: str, req: ProviderUpdateRequest):
    """Update provider settings."""
    if not _manager:
        raise HTTPException(status_code=500, detail="Provider system not initialized")
    config = _manager._state.get_provider_config(provider_id)
    if not config:
        raise HTTPException(status_code=404, detail="Provider not found")
    if req.enabled is not None:
        config["enabled"] = req.enabled
    if req.priority is not None:
        config["priority"] = req.priority
    if req.tags is not None:
        config["tags"] = req.tags
    return {"status": "updated", "provider_id": provider_id}


@provider_router.post("/switch")
async def switch_provider(req: ProviderSwitchRequest):
    """Switch provider instantly with context preservation."""
    if not _manager:
        raise HTTPException(status_code=500, detail="Provider system not initialized")
    if req.provider_type:
        success = await _manager.switch_by_type(
            provider_type=req.provider_type,
            model=req.model,
            session_id=req.session_id
        )
    elif req.provider_id:
        success = await _manager.switch_provider(
            provider_id=req.provider_id,
            model=req.model,
            session_id=req.session_id
        )
    else:
        raise HTTPException(status_code=400, detail="Must specify provider_type or provider_id")
    if not success:
        raise HTTPException(status_code=400, detail="Switch failed")
    state = _manager.get_active_state()
    return {
        "status": "switched",
        "provider_id": state.provider_id if state else None,
        "model": state.model if state else None,
        "session_id": req.session_id,
        "preserved_context": True
    }


@provider_router.post("/voice-command")
async def handle_voice_command(req: VoiceCommandRequest):
    """Handle voice command for provider switching."""
    if not _manager:
        raise HTTPException(status_code=500, detail="Provider system not initialized")
    success, message = await _manager.handle_voice_command(req.transcript)
    return {
        "success": success,
        "message": message,
        "transcript": req.transcript
    }


@provider_router.get("/session/{session_id}")
async def get_session_context(session_id: str):
    """Get session context including provider state."""
    if not _manager:
        raise HTTPException(status_code=500, detail="Provider system not initialized")
    ctx = _manager.get_session_context(session_id)
    if not ctx:
        return {"session_id": session_id, "status": "new"}
    return {
        "session_id": ctx.session_id,
        "current_provider": ctx.current_provider_id,
        "current_model": ctx.current_model,
        "previous_provider": ctx.previous_provider_id,
        "previous_model": ctx.previous_model,
        "message_count": len(ctx.message_history),
        "voice_active": ctx.voice_session_active,
        "workflow_id": ctx.active_workflow_id
    }