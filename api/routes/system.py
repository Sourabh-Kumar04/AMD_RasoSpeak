"""
System routes — /health, /test, /notifications/*, and deprecated /memory/* endpoints.
"""

from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel
from typing import Any

from api.state import agents
from api.middleware.auth import verify_api_key
from config.settings import settings

router = APIRouter(tags=["⚙️ System"])


# ── HEALTH ───────────────────────────────────────────────

@router.get("/health")
async def health():
    """System health check and agent status."""
    agent_status = {}
    failed_agents = []
    for name, agent in agents.items():
        try:
            if agent is None:
                agent_status[name] = "failed"
                failed_agents.append(name)
            elif hasattr(agent, "is_listening"):
                agent_status[name] = "ready" if not agent.is_listening() else "listening"
            elif hasattr(agent, "is_continuous_mode"):
                agent_status[name] = "ready" if not agent.is_continuous_mode() else "active"
            else:
                agent_status[name] = "ready"
        except Exception:
            agent_status[name] = "error"
            failed_agents.append(name)

    critical = ["shared_memory", "qa", "raso"]
    critical_failures = [a for a in failed_agents if a in critical]
    overall_status = "degraded" if failed_agents else "ok"

    return {
        "status": overall_status, "agents": agent_status,
        "failed_agents": failed_agents, "total_agents": len(agents),
        "mode": "api_only", "gpu_required": False,
        "default_provider": settings.default_provider,
        "models": {
            "default": settings.google_model, "nvidia": settings.nvidia_model,
            "openai": settings.openai_model, "anthropic": settings.anthropic_model,
            "huggingface": settings.hf_model, "openrouter": settings.openrouter_model,
            "opencode": settings.opencode_model,
        },
        "providers": {
            "google": bool(settings.google_api_key), "nvidia": bool(settings.nvidia_api_key),
            "openai": bool(settings.openai_api_key), "anthropic": bool(settings.anthropic_api_key),
            "huggingface": bool(settings.hf_api_key), "openrouter": bool(settings.openrouter_api_key),
            "opencode": bool(settings.opencode_api_key), "xai": bool(settings.xai_api_key),
            "deepseek": bool(settings.deepseek_api_key),
        },
        "features": {
            "wake_word": True, "document_import": True, "notifications": True,
            "partner_mode": True, "web_search": True, "streaming": True,
        }
    }


# ── TEST ────────────────────────────────────────────────

class AgentTestResult(BaseModel):
    name: str
    status: str
    duration_ms: float
    detail: str = ""


class SystemTestResult(BaseModel):
    total: int
    passed: int
    failed: int
    duration_ms: float
    agents: list[AgentTestResult]


@router.get("/test", response_model=SystemTestResult, tags=["⚙️ System"])
async def run_system_tests():
    """
    Run integration tests against all agents and endpoints.
    Requires API_KEY to be set to prevent unauthorized access.
    """
    if not settings.api_key:
        return SystemTestResult(total=0, passed=0, failed=0, duration_ms=0, agents=[])

    import asyncio
    import time as time_module

    async def test(name: str, fn, *args, **kwargs):
        t0 = time_module.time()
        try:
            result = fn(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            dur = round((time_module.time() - t0) * 1000, 1)
            return AgentTestResult(name=name, status="pass", duration_ms=dur, detail=str(result)[:200])
        except Exception as e:
            dur = round((time_module.time() - t0) * 1000, 1)
            return AgentTestResult(name=name, status="fail", duration_ms=dur, detail=str(e)[:200])

    tests = []
    tests.append(test("shared_memory.store", agents["shared_memory"].store, "test_key_pytest", {"msg": "hello"}, "test"))
    tests.append(test("shared_memory.recall", agents["shared_memory"].recall, query="hello"))
    tests.append(test("shared_memory.get_context_for_ai", agents["shared_memory"].get_context_for_ai, "hello"))
    tests.append(test("shared_memory.get_user_preferences", agents["shared_memory"].get_user_preferences))
    tests.append(test("shared_memory.get_memory_stats", agents["shared_memory"].get_memory_stats))
    tests.append(test("transcription.transcribe", agents["transcription"].transcribe, "Hello world"))
    tests.append(test("memory.create_session", agents["memory"].create_session, "pytest_session"))
    tests.append(test("memory.get_session", agents["memory"].get_session, "pytest_session"))
    tests.append(test("document.list_documents", agents["document"].list_documents))
    tests.append(test("document.search", agents["document"].search_documents, "test query"))
    tests.append(test("notification.send", agents["notification"].send_notification, "Test notification", "pytest_user"))
    tests.append(test("notification.get_history", agents["notification"].get_notification_history))
    tests.append(test("raso.greet", agents["raso"].greet))
    tests.append(test("raso.think", agents["raso"].think))
    tests.append(test("raso.remember", agents["raso"].remember, "Test content"))
    tests.append(test("raso.start_continuous", agents["raso"].start_continuous_mode, "pytest_session"))
    tests.append(test("raso.stop_continuous", agents["raso"].stop_continuous_mode))
    tests.append(test("raso.query_past", agents["raso"].query_past, "hello"))
    tests.append(test("raso.is_continuous_mode", agents["raso"].is_continuous_mode))
    from agents.wake_word_agent import check_for_wake_word, extract_command_after_wake
    tests.append(test("wake_word.check", check_for_wake_word, "Hey Raso what is that"))
    tests.append(test("wake_word.extract", extract_command_after_wake, "Hey Raso tell me about AMD"))
    tests.append(test("coaching.generate_feedback", agents["coaching"].generate_feedback, "Hello world", "Hello world"))
    tests.append(test("coaching.generate_session_insights", agents["coaching"].generate_session_insights, {"chunks": [{"text": "test"}]}))
    tests.append(test("qa.ask", agents["qa"].ask, "What is RasoSpeak", None))
    tests.append(test("segmentation.segment", agents["segmentation"].segment,
                     "Hello world this is a test presentation about AI and machine learning", 8, "presentation"))

    t0 = time_module.time()
    results = await asyncio.gather(*tests)
    total_dur = round((time_module.time() - t0) * 1000, 1)
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    return SystemTestResult(total=len(results), passed=passed, failed=failed, duration_ms=total_dur, agents=results)


# ── NOTIFICATIONS ──────────────────────────────────────

class NotificationRequest(BaseModel):
    title: str
    message: str
    priority: str = "normal"
    category: str = "general"


class RegisterDeviceRequest(BaseModel):
    device_type: str
    endpoint: str
    token: str = None


@router.post("/notifications/send")
async def send_notification(req: NotificationRequest):
    """Send a notification."""
    return await agents["notifications"].send_notification(
        title=req.title, message=req.message, priority=req.priority, category=req.category,
    )


@router.post("/notifications/register")
async def register_device(req: RegisterDeviceRequest):
    """Register a device for notifications."""
    return await agents["notifications"].register_device(
        device_type=req.device_type, endpoint=req.endpoint, token=req.token,
    )


@router.get("/notifications/history")
async def get_notification_history(limit: int = 20):
    """Get notification history."""
    return await agents["notifications"].get_notification_history(limit)


# ── DEPRECATED /memory/* ROUTES ─────────────────────────

class MemoryStoreRequest(BaseModel):
    key: str
    value: Any
    category: str = "general"


class RememberFactRequest(BaseModel):
    fact: str
    category: str = "general"


class WeakWordRequest(BaseModel):
    word: str
    context: str = None


class PreferenceRequest(BaseModel):
    key: str
    value: Any


@router.post("/memory/store", tags=["⚠️ DEPRECATED"])
async def store_memory(req: MemoryStoreRequest):
    """⚠️ DEPRECATED: Use /brain/store instead. Will be removed in v3.0."""
    return await agents["shared_memory"].store(req.key, req.value, req.category)


@router.get("/memory/recall", tags=["⚠️ DEPRECATED"])
async def recall_memory(query: str = None, key: str = None, category: str = None, limit: int = 10):
    """⚠️ DEPRECATED: Use /brain/recall instead. Will be removed in v3.0."""
    return await agents["shared_memory"].recall(query, key, category, limit)


@router.post("/memory/fact", tags=["⚠️ DEPRECATED"])
async def remember_fact(req: RememberFactRequest):
    """⚠️ DEPRECATED: Use /brain/fact instead. Will be removed in v3.0."""
    return await agents["shared_memory"].remember_user_fact(req.fact, req.category)


@router.get("/memory/stats", tags=["⚠️ DEPRECATED"])
async def get_memory_stats():
    """⚠️ DEPRECATED: Use /brain/stats instead. Will be removed in v3.0."""
    return await agents["shared_memory"].get_memory_stats()


@router.post("/memory/cleanup", tags=["⚠️ DEPRECATED"])
async def cleanup_memory(max_age_days: int = 30):
    """⚠️ DEPRECATED: Second Brain manages memory automatically. Will be removed in v3.0."""
    removed = await agents["memory"].cleanup_old_sessions(max_age_days)
    session_count = await agents["memory"].get_session_count()
    return {"cleaned": removed, "remaining_sessions": session_count}


@router.get("/memory/context", tags=["⚠️ DEPRECATED"])
async def get_ai_context(ai_name: str = None):
    """⚠️ DEPRECATED: Use /brain/context instead. Will be removed in v3.0."""
    return await agents["shared_memory"].get_context_for_ai(ai_name)


@router.post("/memory/preference", tags=["⚠️ DEPRECATED"])
async def set_preference(req: PreferenceRequest):
    """⚠️ DEPRECATED: Use /brain/persona instead. Will be removed in v3.0."""
    return await agents["shared_memory"].set_user_preference(req.key, req.value)


@router.get("/memory/preferences", tags=["⚠️ DEPRECATED"])
async def get_preferences():
    """⚠️ DEPRECATED: Use /brain/persona instead. Will be removed in v3.0."""
    return await agents["shared_memory"].get_user_preferences()


@router.post("/memory/weak-word", tags=["⚠️ DEPRECATED"])
async def add_weak_word(req: WeakWordRequest, session_id: str = None):
    """⚠️ DEPRECATED: Use /brain/weak-word instead. Will be removed in v3.0."""
    return await agents["shared_memory"].add_weak_word(req.word, req.context, session_id)


@router.post("/memory/clear", tags=["⚠️ DEPRECATED"])
async def clear_memory():
    """⚠️ DEPRECATED: Use /brain/clear instead. Will be removed in v3.0."""
    if "brain" in agents:
        return await agents["brain"].clear_all()
    return {"status": "cleared", "warning": "SecondBrainAgent not available"}
