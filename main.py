"""
RasoSpeak — Your Secondary Brain & AI Partner
AMD Developer Cloud | ROCm | vLLM | Whisper

A multi-agent AI system that acts as your continuous AI companion
with wake word activation, perfect memory, document import,
phone notifications, and real-time speech coaching.
"""

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import uvicorn
from pydantic import BaseModel, Field
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from agents.transcription_agent import TranscriptionAgent
from agents.scoring_agent import ScoringAgent
from agents.coaching_agent import CoachingAgent
from agents.segmentation_agent import SegmentationAgent
from agents.session_memory_agent import SessionMemoryAgent
from agents.qa_agent import QAAgent
from agents.search_agent import SearchAgent
from agents.recording_agent import RecordingAgent
from agents.analytics_agent import AnalyticsAgent
from agents.shared_memory_agent import SharedMemoryAgent
from agents.second_brain_agent import SecondBrainAgent
from agents.partner_agent import RasoAgent
from agents.rag_agent import LightweightRAGAgent as RAGAgent
from agents.wake_word_agent import WakeWordAgent
from agents.document_agent import DocumentAgent
from agents.notification_agent import NotificationAgent
from models.schemas import (
    WSMessage, WSMessageType,
    SegmentRequest, AudioChunk,
    SessionConfig, PartnerAskRequest, ReminderRequest
)
from config.settings import settings
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# ── RATE LIMITING ──────────────────────────────────────
def get_remote_ip(request):
    """Get client IP from request."""
    return request.client.host if request.client else "127.0.0.1"

limiter = Limiter(key_func=get_remote_ip)

# ── LOGGING ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
log = logging.getLogger("rasospeak")

# ── GLOBAL AGENTS (shared across all sessions) ─────────
agents: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load all agents on startup, clean up on shutdown."""
    log.info("🚀 RasoSpeak v2 starting — API mode (no GPU required)...")

    # Agent registry with initialization logic
    agent_init_order = [
        # Core first - Second Brain must be first!
        ("brain", SecondBrainAgent, "SECOND BRAIN (Multi-tier Memory)"),
        ("shared_memory", SharedMemoryAgent, "UNIFIED BRAIN"),
        # Core coaching - uses external APIs
        ("transcription", TranscriptionAgent, "Web Speech API / OpenAI Whisper"),
        ("scoring", ScoringAgent, f"LLM API ({settings.default_provider})"),
        ("coaching", CoachingAgent, f"LLM API ({settings.default_provider})"),
        ("memory", SessionMemoryAgent, "Session storage"),
        # Partner agents
        ("qa", QAAgent, f"Multi-provider ({settings.default_provider})"),
        ("search", SearchAgent, "Tavily/DuckDuckGo"),
        ("recording", RecordingAgent, "Audio recording"),
        ("analytics", AnalyticsAgent, "Performance analytics"),
        ("raso", RasoAgent, "Your AI companion with memory"),
        ("wake_word", WakeWordAgent, "'Hey Raso' detection"),
        ("document", DocumentAgent, "PDF/URL import"),
        ("notification", NotificationAgent, "Phone notifications"),
        ("segmentation", SegmentationAgent, "Script chunking"),
        ("rag", RAGAgent, "Lightweight RAG (BM25 + LLM)"),
    ]

    agent_health: dict[str, str] = {}

    for name, AgentClass, desc in agent_init_order:
        try:
            agents[name] = AgentClass()
            await agents[name].initialize()
            agent_health[name] = "ok"
            log.info(f"✅ {name.capitalize()}Agent ready ({desc})")
        except Exception as e:
            agents[name] = None
            agent_health[name] = f"failed: {str(e)[:100]}"
            log.error(f"❌ {name.capitalize()}Agent failed to initialize: {e}")

    # Set second brain references for agents that need it
    if agents.get("brain"):
        for agent_name in ["qa", "search", "recording", "analytics", "raso", "document"]:
            if agents.get(agent_name):
                try:
                    agents[agent_name].set_second_brain(agents["brain"])
                except Exception as e:
                    log.warning(f"⚠️ {agent_name} second_brain setup failed: {e}")

        # Connect SharedMemoryAgent to SecondBrainAgent for unified storage
        if agents.get("shared_memory"):
            try:
                agents["shared_memory"].set_second_brain(agents["brain"])
                log.info("✅ SharedMemoryAgent connected to SecondBrainAgent")
            except Exception as e:
                log.warning(f"⚠️ SharedMemoryAgent second_brain setup failed: {e}")

    # Set shared memory references for agents that need it
    if agents.get("shared_memory"):
        for agent_name in ["qa", "search", "recording", "analytics", "raso", "document"]:
            if agents.get(agent_name):
                try:
                    agents[agent_name].set_shared_memory(agents["shared_memory"])
                except Exception as e:
                    log.warning(f"⚠️ {agent_name} shared_memory setup failed: {e}")

    # Connect Raso to SearchAgent for web search capability
    if agents.get("raso") and agents.get("search"):
        try:
            agents["raso"].set_search_agent(agents["search"])
            log.info("✅ Raso connected to SearchAgent")
        except Exception as e:
            log.warning(f"⚠️ Raso search agent setup failed: {e}")

    # Store agent health for /health endpoint
    app.state.agent_health = agent_health

    log.info(f"🚀 Startup complete. Agent health: {agent_health}")

    yield

    # Cleanup
    log.info("🧹 Shutting down RasoSpeak...")
    for name, agent in agents.items():
        if agent and hasattr(agent, "cleanup"):
            try:
                await agent.cleanup()
            except Exception as e:
                log.error(f"Error cleaning up {name}: {e}")


# ── APP ────────────────────────────────────────────────
app = FastAPI(
    title="RasoSpeak — Your Secondary Brain & AI Partner",
    description="A multi-agent AI system with wake word activation, perfect memory, document import, phone notifications, and real-time speech coaching. Powered by GPU Accelerator.",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS - use allowed_origins from settings (default "*" for dev, can restrict for prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(",") if settings.allowed_origins != "*" else ["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Serve the frontend static files from current directory
import os
from pathlib import Path

# Attempt to ensure logo.png is present (fallback for transient build issues)
if not os.path.exists("logo.png"):
    try:
        import httpx
        token = os.environ.get("HF_TOKEN")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        # Try to fetch from the local space assets if available, or the hub
        url = "https://huggingface.co/spaces/lablab-ai-amd-developer-hackathon/RasoSpeak/resolve/main/logo.png"
        with httpx.Client(follow_redirects=True) as client:
            r = client.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                with open("logo.png", "wb") as f:
                    f.write(r.content)
                print("Logo recovered from Hub")
            else:
                print(f"Logo recovery skipped (Status {r.status_code})")
    except Exception as e:
        print(f"Logo recovery error: {e}")

# Serve static files (js, css) from current directory
app.mount("/static", StaticFiles(directory="."), name="static")

# Serve frontend files at root level for direct access (app.js, nlp.js, etc.)
@app.get("/app.js")
async def app_js(): return FileResponse("app.js")
@app.get("/nlp.js")
async def nlp_js(): return FileResponse("nlp.js")
@app.get("/ui.js")
async def ui_js(): return FileResponse("ui.js")
@app.get("/speech.js")
async def speech_js(): return FileResponse("speech.js")
@app.get("/state.js")
async def state_js(): return FileResponse("state.js")
@app.get("/styles.css")
async def styles_css(): return FileResponse("styles.css")
@app.get("/")
async def root(): return FileResponse("index.html")
@app.get("/index.html")
async def index_html(): return FileResponse("index.html")
@app.get("/chat.html")
async def chat_html(): return FileResponse("chat.html")
@app.get("/memory.html")
async def memory_html(): return FileResponse("memory.html")
@app.get("/coach.html")
async def coach_html(): return FileResponse("coach.html")
@app.get("/docs.html")
async def docs_html(): return FileResponse("docs.html")
@app.get("/settings.html")
async def settings_html(): return FileResponse("settings.html")
@app.get("/logo.png")
@app.get("/favicon.ico")
async def logo_png():
    if os.path.exists("logo.png"):
        return FileResponse("logo.png")
    # Fallback SVG if file is missing (prevents 500 error)
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
      <defs>
        <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style="stop-color:#FF8800;stop-opacity:1" />
          <stop offset="100%" style="stop-color:#FF4400;stop-opacity:1" />
        </linearGradient>
      </defs>
      <circle cx="50" cy="50" r="48" fill="url(#g)"/>
      <path d="M20 50 L30 50 L35 30 L45 70 L55 30 L65 70 L70 50 L80 50" stroke="white" stroke-width="6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
      <text x="50" y="88" font-size="10" fill="white" text-anchor="middle" font-family="sans-serif" font-weight="900" letter-spacing="1">RASOSPEAK</text>
    </svg>'''
    return Response(content=svg, media_type="image/svg+xml")


# ── REST ENDPOINTS ─────────────────────────────────────
@app.get("/health")
async def health():
    # Check which agents are working
    agent_status = {}
    failed_agents = []
    for name, agent in agents.items():
        try:
            if agent is None:
                agent_status[name] = "failed"
                failed_agents.append(name)
            elif hasattr(agent, 'is_listening'):
                agent_status[name] = "ready" if not agent.is_listening() else "listening"
            elif hasattr(agent, 'is_continuous_mode'):
                agent_status[name] = "ready" if not agent.is_continuous_mode() else "active"
            else:
                agent_status[name] = "ready"
        except Exception:
            agent_status[name] = "error"
            failed_agents.append(name)

    # Determine overall status based on failed agents
    overall_status = "ok"
    if failed_agents:
        # Critical agents that must work
        critical = ["shared_memory", "qa", "raso"]
        critical_failures = [a for a in failed_agents if a in critical]
        if critical_failures:
            overall_status = "degraded"
        else:
            overall_status = "degraded"

    return {
        "status": overall_status,
        "agents": agent_status,
        "failed_agents": failed_agents,
        "total_agents": len(agents),
        "mode": "api_only",
        "gpu_required": False,
        "default_provider": settings.default_provider,
        "models": {
            "default": settings.google_model,
            "nvidia": settings.nvidia_model,
            "openai": settings.openai_model,
            "anthropic": settings.anthropic_model,
            "huggingface": settings.hf_model,
            "openrouter": settings.openrouter_model,
            "opencode": settings.opencode_model,
        },
        "providers": {
            "google": bool(settings.google_api_key),
            "nvidia": bool(settings.nvidia_api_key),
            "openai": bool(settings.openai_api_key),
            "anthropic": bool(settings.anthropic_api_key),
            "huggingface": bool(settings.hf_api_key),
            "openrouter": bool(settings.openrouter_api_key),
            "opencode": bool(settings.opencode_api_key),
            "xai": bool(settings.xai_api_key),
            "deepseek": bool(settings.deepseek_api_key),
        },
        "features": {
            "wake_word": True,
            "document_import": True,
            "notifications": True,
            "partner_mode": True,
            "web_search": True,
            "streaming": True,
        }
    }


# ══════════════════════════════════════════════════════
# ROUTE ALIASES — Support both "partner" and "raso" prefixes
# ══════════════════════════════════════════════════════

@app.post("/partner/start")
async def partner_start_alias(session_id: str = None):
    """Alias for /raso/start (backward compatibility)"""
    return await agents["raso"].start_continuous_mode(session_id)


@app.post("/partner/stop")
async def partner_stop_alias():
    """Alias for /raso/stop (backward compatibility)"""
    return await agents["raso"].stop_continuous_mode()


@app.get("/partner/status")
async def partner_status_alias():
    """Alias for /raso/status (backward compatibility)"""
    current_provider = await agents["raso"].get_current_provider()
    prefs = await agents["shared_memory"].get_user_preferences()
    return {
        "continuous_mode": agents["raso"].is_continuous_mode(),
        "current_provider": current_provider,
        "default_provider": prefs.get("preferred_ai_provider", "qwen_local"),
        "temporary_provider": prefs.get("temporary_ai_provider"),
    }


@app.post("/partner/ask")
@limiter.limit("10/minute")
async def partner_ask_alias(request: Request, req: PartnerAskRequest):
    """Alias for /raso/ask (backward compatibility)"""
    return await agents["raso"].ask_partner(req.message, req.provider)


@app.get("/partner/query")
async def partner_query_alias(query: str):
    """Alias for /raso/query (backward compatibility)"""
    return await agents["raso"].query_past(query)


@app.post("/partner/reminder")
async def partner_reminder_alias(req: ReminderRequest):
    """Alias for /raso/reminder (backward compatibility)"""
    return await agents["raso"].set_reminder(req.message, req.remind_at)


@app.get("/partner/reminders")
async def partner_reminders_alias():
    """Alias for /raso/reminders (backward compatibility)"""
    return await agents["raso"].get_reminders()


@app.post("/partner/provider")
async def partner_provider_alias(provider: str, temporary: bool = False):
    """Alias for /raso/provider (backward compatibility)"""
    if temporary:
        await agents["shared_memory"].set_user_preference("temporary_ai_provider", provider)
    else:
        await agents["shared_memory"].set_user_preference("preferred_ai_provider", provider)
        await agents["shared_memory"].set_user_preference("temporary_ai_provider", None)
    return {"provider": provider, "temporary": temporary}


@app.post("/segment")
async def segment_script(req: SegmentRequest):
    """
    Segment a raw script into LLM-optimized chunks.
    Called once when user processes their script.
    """
    result = await agents["segmentation"].segment(
        script=req.script,
        target_chunk_size=req.target_chunk_size,
        style=req.style,
    )
    return result


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Retrieve session data for the stats dashboard."""
    session = await agents["memory"].get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/sessions/{session_id}/insights")
async def get_session_insights(session_id: str):
    """Get AI-generated insights from a completed session."""
    session = await agents["memory"].get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    insights = await agents["coaching"].generate_session_insights(session)
    return insights


# ══════════════════════════════════════════════════════
# NEW: Q&A ENDPOINTS — Real-time AI question answering
# ══════════════════════════════════════════════════════

class QARequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2_000)
    provider: str | None = Field(default=None, pattern="^(openai|anthropic|google|google|xai|nvidia|deepseek|huggingface|openrouter|opencode)$")
    context: str | None = Field(default=None, max_length=10_000)
    stream_to_earpiece: bool = True


@app.post("/qa")
@limiter.limit("10/minute")
async def ask_question(request: Request, req: QARequest, session_id: str = None):
    """
    Ask a question to AI and get answer (streams to earpiece).
    Connect to OpenAI GPT, Anthropic Claude, Google Gemini, xAI Grok, or local Qwen.
    Rate limited: 10 requests per minute.
    """
    result = await agents["qa"].ask(
        question=req.question,
        provider=req.provider,
        context=req.context,
        stream_to_earpiece=req.stream_to_earpiece,
        session_id=session_id,
    )
    return result


@app.get("/qa/providers")
async def get_qa_providers():
    """Get available AI providers."""
    # Get available providers from settings
    available = []
    for provider in ["google", "nvidia", "openai", "anthropic", "huggingface", "openrouter", "opencode", "xai", "deepseek"]:
        config = settings.get_provider_config(provider)
        if config.get("api_key"):
            available.append(provider)
    return {
        "available": available,
        "default": settings.default_provider,
    }


# ══════════════════════════════════════════════════════
# NEW: SEARCH ENDPOINTS — Web search for real-time info
# ══════════════════════════════════════════════════════

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    num_results: int = Field(default=5, ge=1, le=20)
    include_summary: bool = True


@app.post("/search")
@limiter.limit("30/minute")
async def web_search(request: Request, req: SearchRequest):
    """
    Search the web for real-time information.
    Uses Tavily (if API key), SerpAPI, Brave Search, or DuckDuckGo (fallback).
    Rate limited: 30 requests per minute.
    """
    result = await agents["search"].search(
        query=req.query,
        num_results=req.num_results,
        include_summary=req.include_summary,
    )
    return result


# ══════════════════════════════════════════════════════
# NEW: RECORDING ENDPOINTS — Audio/conversation storage
# ══════════════════════════════════════════════════════

class StartRecordingRequest(BaseModel):
    metadata: dict = {}


@app.post("/recordings/{session_id}/start")
async def start_recording(session_id: str, req: StartRecordingRequest = None):
    """Start recording a session."""
    metadata = req.metadata if req else {}
    result = await agents["recording"].start_session_recording(session_id, metadata)

    # Also start in memory agent
    await agents["memory"].create_session(session_id)

    return result


@app.post("/recordings/{session_id}/stop")
async def stop_recording(session_id: str):
    """Stop recording a session."""
    result = await agents["recording"].stop_session_recording(session_id)
    return result


class AudioRecordRequest(BaseModel):
    audio_b64: str
    audio_type: str = "user_speech"  # user_speech, coaching_tts, qa_response
    metadata: dict = {}


@app.post("/recordings/{session_id}/audio")
async def record_audio(session_id: str, req: AudioRecordRequest):
    """Record an audio chunk."""
    result = await agents["recording"].record_audio(
        session_id=session_id,
        audio_b64=req.audio_b64,
        audio_type=req.audio_type,
        metadata=req.metadata,
    )
    return result


@app.get("/recordings")
async def list_recordings(limit: int = 50):
    """List all recorded sessions."""
    return await agents["recording"].get_all_recordings(limit)


@app.get("/recordings/{session_id}")
async def get_recording(session_id: str):
    """Get recording data for a specific session."""
    return await agents["recording"].get_session_record(session_id)


# ══════════════════════════════════════════════════════
# NEW: ANALYTICS ENDPOINTS — Session & user insights
# ══════════════════════════════════════════════════════

@app.get("/analytics/session/{session_id}")
async def get_session_analytics(session_id: str):
    """Get comprehensive analytics for a session."""
    return await agents["analytics"].generate_session_analytics(session_id)


@app.get("/analytics/user/{user_id}")
async def get_user_analytics(user_id: str, days: int = 30):
    """Get analytics across multiple sessions for a user."""
    return await agents["analytics"].generate_user_analytics(user_id, days)


@app.get("/analytics/improvement/{user_id}")
async def get_improvement_report(user_id: str):
    """Get speech improvement report over time."""
    return await agents["analytics"].get_speech_improvement_report(user_id)


@app.get("/analytics/qa-topics/{user_id}")
async def get_qa_topics(user_id: str):
    """Analyze what topics user asks about most."""
    return await agents["analytics"].get_qa_topics_analysis(user_id)


# ══════════════════════════════════════════════════════
# SHARED MEMORY ENDPOINTS — Unified brain for all AIs
# ══════════════════════════════════════════════════════

class MemoryStoreRequest(BaseModel):
    key: str
    value: Any
    category: str = "general"


class RememberFactRequest(BaseModel):
    fact: str
    category: str = "general"


@app.post("/memory/store")
async def store_memory(req: MemoryStoreRequest):
    """Store a memory item in shared memory."""
    return await agents["shared_memory"].store(req.key, req.value, req.category)


@app.get("/memory/recall")
async def recall_memory(query: str = None, key: str = None, category: str = None, limit: int = 10):
    """Recall memories based on query, key, or category."""
    return await agents["shared_memory"].recall(query, key, category, limit)


@app.post("/memory/fact")
async def remember_fact(req: RememberFactRequest):
    """Store a fact about the user."""
    return await agents["shared_memory"].remember_user_fact(req.fact, req.category)


@app.get("/memory/stats")
async def get_memory_stats():
    """Get shared memory statistics."""
    return await agents["shared_memory"].get_memory_stats()


@app.post("/memory/cleanup")
async def cleanup_memory(max_age_days: int = 30):
    """Clean up old sessions to prevent memory leaks."""
    removed = await agents["memory"].cleanup_old_sessions(max_age_days)
    session_count = await agents["memory"].get_session_count()
    return {
        "cleaned": removed,
        "remaining_sessions": session_count,
    }


@app.get("/memory/context")
async def get_ai_context(ai_name: str = None):
    """Get formatted context for AI prompts."""
    return await agents["shared_memory"].get_context_for_ai(ai_name)


class PreferenceRequest(BaseModel):
    key: str
    value: Any


@app.post("/memory/preference")
async def set_preference(req: PreferenceRequest):
    """Set a user preference."""
    return await agents["shared_memory"].set_user_preference(req.key, req.value)


@app.get("/memory/preferences")
async def get_preferences():
    """Get user preferences."""
    return await agents["shared_memory"].get_user_preferences()


class WeakWordRequest(BaseModel):
    word: str
    context: str = None


@app.post("/memory/weak-word")
async def add_weak_word(req: WeakWordRequest, session_id: str = None):
    """Add a word the user struggles with."""
    return await agents["shared_memory"].add_weak_word(req.word, req.context, session_id)


# ══════════════════════════════════════════════════════
# SECOND BRAIN ENDPOINTS — Complete Memory System
# ══════════════════════════════════════════════════════

class BrainStoreRequest(BaseModel):
    content: Any
    memory_type: str = "conversation"
    tier: str = "long_term"
    importance: int = 3
    tags: list = []
    source: str = "unknown"


class BrainConversationRequest(BaseModel):
    user_input: str
    ai_response: str
    ai_provider: str
    context: str = None


class BrainDocumentRequest(BaseModel):
    content: str
    title: str
    doc_type: str = "document"
    tags: list = []


class BrainFactRequest(BaseModel):
    fact: str
    category: str = "general"
    importance: int = 3


class BrainAudioRequest(BaseModel):
    session_id: str
    transcription: str
    speakers: list = []
    duration: float = 0


class BrainRelationshipRequest(BaseModel):
    source_id: str
    target_id: str
    relation_type: str
    weight: float = 1.0


class BrainRecallRequest(BaseModel):
    query: str = None
    memory_type: str = None
    tier: str = None
    limit: int = 20
    time_range: str = None  # "1h", "24h", "7d", "30d", "all"


@app.post("/brain/store")
async def brain_store(req: BrainStoreRequest):
    """Store a memory node in the second brain."""
    from agents.second_brain_agent import MemoryType, MemoryTier, Importance
    return await agents["brain"].store(
        content=req.content,
        memory_type=MemoryType(req.memory_type),
        tier=MemoryTier(req.tier),
        importance=Importance(req.importance),
        tags=req.tags,
        source=req.source,
    )


@app.post("/brain/conversation")
async def brain_add_conversation(req: BrainConversationRequest):
    """Add a conversation to second brain."""
    return await agents["brain"].add_conversation(
        user_input=req.user_input,
        ai_response=req.ai_response,
        ai_provider=req.ai_provider,
        context=req.context,
    )


@app.post("/brain/document")
async def brain_add_document(req: BrainDocumentRequest):
    """Add a document to second brain."""
    return await agents["brain"].add_document(
        content=req.content,
        title=req.title,
        doc_type=req.doc_type,
        tags=req.tags,
    )


@app.post("/brain/fact")
async def brain_add_fact(req: BrainFactRequest):
    """Add a fact about the user."""
    from agents.second_brain_agent import Importance
    return await agents["brain"].add_user_fact(
        fact=req.fact,
        category=req.category,
        importance=Importance(req.importance),
    )


@app.post("/brain/audio")
async def brain_add_audio(req: BrainAudioRequest):
    """Store an audio conversation with full processing."""
    return await agents["brain"].store_audio_conversation(
        session_id=req.session_id,
        transcription=req.transcription,
        speakers=req.speakers,
        duration=req.duration,
    )


@app.post("/brain/relationship")
async def brain_add_relationship(req: BrainRelationshipRequest):
    """Add a relationship edge between nodes."""
    return await agents["brain"].add_relationship(
        source_id=req.source_id,
        target_id=req.target_id,
        relation_type=req.relation_type,
        weight=req.weight,
    )


@app.post("/brain/recall")
async def brain_recall(req: BrainRecallRequest):
    """Recall memories with hybrid search."""
    from agents.second_brain_agent import MemoryType, MemoryTier
    return await agents["brain"].recall(
        query=req.query,
        memory_type=MemoryType(req.memory_type) if req.memory_type else None,
        tier=MemoryTier(req.tier) if req.tier else None,
        limit=req.limit,
        time_range=req.time_range,
    )


@app.get("/brain/recall/graph")
async def brain_recall_graph(entity: str, depth: int = 2):
    """Recall related nodes through the knowledge graph."""
    return await agents["brain"].recall_graph(entity=entity, depth=depth)


@app.get("/brain/recall/temporal")
async def brain_recall_temporal(query: str, start_date: str = None, end_date: str = None):
    """Recall memories within a time range."""
    return await agents["brain"].recall_temporal(
        query=query,
        start_date=start_date,
        end_date=end_date,
    )


@app.get("/brain/recall/conversation")
async def brain_recall_conversation(query: str = None, limit: int = 10):
    """Recall past conversations."""
    return await agents["brain"].recall_conversation(query=query, limit=limit)


@app.get("/brain/recall/entity/{entity_name}")
async def brain_recall_entity(entity_name: str, limit: int = 10):
    """Recall all memories related to an entity."""
    return await agents["brain"].recall_entity(entity_name=entity_name, limit=limit)


@app.get("/brain/recall/topic/{topic}")
async def brain_recall_topic(topic: str, limit: int = 20):
    """Recall all memories related to a topic."""
    return await agents["brain"].recall_by_topic(topic=topic, limit=limit)


@app.get("/brain/recall/audio")
async def brain_recall_audio(query: str = None, session_id: str = None, limit: int = 10):
    """Recall audio conversations."""
    return await agents["brain"].recall_audio_conversations(
        query=query,
        session_id=session_id,
        limit=limit,
    )


@app.get("/brain/related/{node_id}")
async def brain_find_related(node_id: str, relation_type: str = None, depth: int = 1):
    """Find nodes related to a given node."""
    return await agents["brain"].find_related(node_id=node_id, relation_type=relation_type, depth=depth)


@app.get("/brain/working-memory")
async def brain_get_working_memory():
    """Get current working memory contents."""
    return await agents["brain"].get_working_memory()


@app.post("/brain/working-memory/clear")
async def brain_clear_working_memory():
    """Clear working memory."""
    await agents["brain"].clear_working_memory()
    return {"status": "cleared"}


@app.get("/brain/context")
async def brain_get_context(ai_name: str = None, max_tokens: int = 4000):
    """Get formatted context for AI prompts."""
    return await agents["brain"].get_context_for_ai(ai_name=ai_name, max_tokens=max_tokens)


@app.post("/brain/revise/{node_id}")
async def brain_revise_memory(node_id: str, new_content: Any):
    """Revise an existing memory."""
    return await agents["brain"].revise_memory(node_id=node_id, new_content=new_content)


@app.post("/brain/forget/{node_id}")
async def brain_forget(node_id: str, reason: str = "user_request"):
    """Forget a memory."""
    return await agents["brain"].forget(node_id=node_id, reason=reason)


@app.post("/brain/auto-forget")
async def brain_auto_forget(threshold: float = 0.2):
    """Automatically forget low-importance memories."""
    return await agents["brain"].auto_forget_low_importance(threshold=threshold)


@app.get("/brain/weak-words")
async def brain_get_weak_words(limit: int = 20):
    """Get all weak words."""
    return await agents["brain"].get_weak_words(limit=limit)


@app.post("/brain/weak-word")
async def brain_add_weak_word(word: str, context: str = None, session_id: str = None):
    """Add a weak word."""
    return await agents["brain"].add_weak_word(word=word, context=context, session_id=session_id)


@app.get("/brain/sessions")
async def brain_get_recent_sessions(limit: int = 10):
    """Get recent session summaries."""
    return await agents["brain"].get_recent_sessions(limit=limit)


@app.post("/brain/session-summary")
async def brain_save_session_summary(session_id: str, summary: dict):
    """Save a session summary."""
    return await agents["brain"].save_session_summary(session_id=session_id, summary=summary)


@app.get("/brain/stats")
async def brain_get_stats():
    """Get comprehensive memory statistics."""
    return await agents["brain"].get_memory_stats()


@app.get("/brain/size")
async def brain_get_size():
    """Get memory size in MB."""
    size = await agents["brain"].get_memory_size_mb()
    return {"size_mb": round(size, 2)}


@app.post("/brain/clear")
async def brain_clear_all():
    """Clear all second brain memory."""
    return await agents["brain"].clear_all()


# ══════════════════════════════════════════════════════
# PERSONA — User Profile & Identity
# ══════════════════════════════════════════════════════

@app.get("/brain/persona")
async def brain_get_persona():
    """Get the current user persona profile."""
    return await agents["brain"].get_persona()


@app.put("/brain/persona/{field}")
async def brain_update_persona(field: str, value: str = None, values: list[str] = None):
    """Update a specific field in the user persona."""
    if values is not None:
        return await agents["brain"].update_persona_field(field, values)
    elif value is not None:
        return await agents["brain"].update_persona_field(field, value)
    return {"error": "Provide 'value' or 'values' parameter"}


@app.post("/brain/persona/extract")
async def brain_extract_persona(conversation: str = None):
    """Extract persona from recent conversations."""
    return await agents["brain"].extract_and_update_persona(conversation)


# ══════════════════════════════════════════════════════
# GOALS — Goal Management
# ══════════════════════════════════════════════════════

@app.post("/brain/goals")
async def brain_add_goal(
    title: str,
    description: str = None,
    deadline: str = None,
    priority: int = 3,
    category: str = "general"
):
    """Add a new goal."""
    return await agents["brain"].add_goal(title, description, deadline, priority, category)


@app.put("/brain/goals/{goal_id}/progress")
async def brain_update_goal_progress(goal_id: str, progress: float, note: str = None):
    """Update progress on a goal."""
    return await agents["brain"].update_goal_progress(goal_id, progress, note)


@app.put("/brain/goals/{goal_id}/status")
async def brain_set_goal_status(goal_id: str, status: str):
    """Set goal status (active, completed, paused, abandoned)."""
    from agents.second_brain_agent import GoalStatus
    goal_status = GoalStatus(status)
    return await agents["brain"].set_goal_status(goal_id, goal_status)


@app.post("/brain/goals/{goal_id}/blocker")
async def brain_add_goal_blocker(goal_id: str, blocker: str):
    """Add a blocker to a goal."""
    return await agents["brain"].add_goal_blocker(goal_id, blocker)


@app.get("/brain/goals/active")
async def brain_get_active_goals():
    """Get all active goals."""
    return {"goals": await agents["brain"].get_active_goals()}


@app.get("/brain/goals")
async def brain_get_all_goals():
    """Get all goals."""
    return {"goals": await agents["brain"].get_all_goals()}


@app.post("/brain/goals/extract")
async def brain_extract_goals(conversation: str):
    """Extract goals from conversation text."""
    goals = await agents["brain"].extract_goals_from_conversation(conversation)
    return {"goals": [g.to_dict() for g in goals]}


# ══════════════════════════════════════════════════════
# SKILLS — Knowledge & Capability Tracking
# ══════════════════════════════════════════════════════

@app.post("/brain/skills")
async def brain_add_skill(
    name: str,
    level: str = "beginner",
    category: str = "general",
    description: str = None
):
    """Add a skill to track."""
    from agents.second_brain_agent import SkillLevel
    skill_level = SkillLevel(level)
    return await agents["brain"].add_skill(name, skill_level, category, description)


@app.put("/brain/skills/{skill_name}/level")
async def brain_update_skill_level(skill_name: str, level: str):
    """Update skill level (beginner, intermediate, advanced, expert)."""
    from agents.second_brain_agent import SkillLevel
    skill_level = SkillLevel(level)
    return await agents["brain"].update_skill_level(skill_name, skill_level)


@app.get("/brain/skills")
async def brain_get_all_skills():
    """Get all tracked skills."""
    return {"skills": await agents["brain"].get_all_skills()}


@app.get("/brain/skills/{category}")
async def brain_get_skills_by_category(category: str):
    """Get skills in a specific category."""
    return {"skills": await agents["brain"].get_skills_by_category(category)}


@app.post("/brain/skills/extract")
async def brain_extract_skills(conversation: str):
    """Extract skills from conversation text."""
    skills = await agents["brain"].extract_skills_from_conversation(conversation)
    return {"skills": [s.to_dict() for s in skills]}


# ══════════════════════════════════════════════════════
# COMPRESSION — Memory Summarization
# ══════════════════════════════════════════════════════

@app.post("/brain/compress")
async def brain_compress_memories(days_old: int = 30):
    """Compress memories older than specified days into summaries."""
    return await agents["brain"].compress_old_memories(days_old)


@app.get("/brain/summaries/{summary_id}")
async def brain_get_summary(summary_id: str):
    """Get a specific memory summary."""
    return await agents["brain"].get_summary(summary_id)


@app.get("/brain/summaries")
async def brain_search_summaries(query: str):
    """Search through memory summaries."""
    return {"summaries": await agents["brain"].search_summaries(query)}


# ══════════════════════════════════════════════════════
# AUTO-LINKING — Cross-Reference Memories
# ══════════════════════════════════════════════════════

@app.post("/brain/links/auto")
async def brain_auto_link():
    """Automatically link related memories."""
    return await agents["brain"].auto_link_memories()


# ══════════════════════════════════════════════════════
# EMOTIONAL INTELLIGENCE
# ══════════════════════════════════════════════════════

@app.post("/brain/emotions/analyze")
async def brain_analyze_emotions(conversation: str):
    """Analyze emotions in a conversation."""
    return await agents["brain"].analyze_emotions(conversation)


@app.post("/brain/emotions")
async def brain_store_emotional(
    conversation: str,
    emotion_type: str,
    intensity: float = 0.5,
    topic: str = None
):
    """Store emotional memory from conversation."""
    return await agents["brain"].store_emotional_memory(conversation, emotion_type, intensity, topic)


# ══════════════════════════════════════════════════════
# VERSIONING — Memory History
# ══════════════════════════════════════════════════════

@app.get("/brain/versions/{node_id}")
async def brain_get_node_versions(node_id: str):
    """Get all versions of a memory node."""
    return {"versions": await agents["brain"].get_node_versions(node_id)}


@app.post("/brain/versions/{node_id}")
async def brain_revert_to_version(node_id: str, version: int):
    """Revert a memory node to a previous version."""
    return await agents["brain"].revert_to_version(node_id, version)


# ══════════════════════════════════════════════════════
# QUALITY — Memory Quality Scoring
# ══════════════════════════════════════════════════════

@app.get("/brain/quality/{node_id}")
async def brain_score_quality(node_id: str):
    """Get quality score for a specific memory."""
    score = await agents["brain"].score_memory_quality(node_id)
    return {"node_id": node_id, "quality_score": score}


@app.get("/brain/quality")
async def brain_quality_report():
    """Get comprehensive memory quality report."""
    return await agents["brain"].get_quality_report()


# ══════════════════════════════════════════════════════
# PREDICTIVE — Next Memory Suggestions
# ══════════════════════════════════════════════════════

@app.get("/brain/suggest/{node_id}")
async def brain_suggest_related(node_id: str):
    """Suggest memories related to a given memory."""
    return {"suggestions": await agents["brain"].suggest_related_memories(node_id)}


@app.get("/brain/predict")
async def brain_predict_next():
    """Predict the next likely memory based on patterns."""
    return await agents["brain"].predict_next_memory()


# ══════════════════════════════════════════════════════
# PHASE 6: BACKUP & RESTORE
# ══════════════════════════════════════════════════════

@app.post("/brain/backup")
async def brain_create_backup(description: str = "", tags: list[str] = None):
    """Create a full backup snapshot."""
    return await agents["brain"].create_backup(description, tags)


@app.get("/brain/backups")
async def brain_list_backups():
    """List all available backups."""
    return {"backups": await agents["brain"].list_backups()}


@app.post("/brain/restore/{backup_id}")
async def brain_restore_backup(backup_id: str):
    """Restore from a backup."""
    return await agents["brain"].restore_backup(backup_id)


@app.delete("/brain/backup/{backup_id}")
async def brain_delete_backup(backup_id: str):
    """Delete a backup."""
    return await agents["brain"].delete_backup(backup_id)


# ══════════════════════════════════════════════════════
# PHASE 6: EXPORT & IMPORT
# ══════════════════════════════════════════════════════

@app.get("/brain/export")
async def brain_export_memory(
    format: str = "json",
    include_private: bool = False,
    include_sensitive: bool = False,
):
    """Export memory in various formats (json, markdown, obsidian)."""
    return await agents["brain"].export_memory(format, include_private, include_sensitive)


@app.post("/brain/import")
async def brain_import_memory(request: Request, merge: bool = True):
    """Import memory from exported data."""
    data = await request.json()
    return await agents["brain"].import_memory(data, merge)


# ══════════════════════════════════════════════════════
# PHASE 6: ENCRYPTED STORAGE & PRIVACY
# ══════════════════════════════════════════════════════

@app.post("/brain/encrypt/key")
async def brain_set_encryption_key(key: str):
    """Set encryption key for sensitive memories."""
    return agents["brain"].set_encryption_key(key)


@app.delete("/brain/encrypt/key")
async def brain_clear_encryption_key():
    """Clear encryption key."""
    return agents["brain"].clear_encryption_key()


@app.post("/brain/encrypt/{node_id}")
async def brain_encrypt_node(node_id: str, privacy: str = "private"):
    """Encrypt and protect a node."""
    from agents.second_brain_agent import PrivacyLevel
    return await agents["brain"].encrypt_node(node_id, PrivacyLevel(privacy))


@app.post("/brain/decrypt/{node_id}")
async def brain_decrypt_node(node_id: str):
    """Decrypt a protected node."""
    return await agents["brain"].decrypt_node(node_id)


@app.put("/brain/privacy/{node_id}")
async def brain_set_node_privacy(node_id: str, privacy: str):
    """Set privacy level for a node (public, private, restricted, sensitive)."""
    from agents.second_brain_agent import PrivacyLevel
    return agents["brain"].set_node_privacy(node_id, PrivacyLevel(privacy))


@app.get("/brain/privacy/{node_id}")
async def brain_get_node_privacy(node_id: str):
    """Get privacy level for a node."""
    level = agents["brain"].get_node_privacy(node_id)
    return {"node_id": node_id, "privacy": level.value}


# ══════════════════════════════════════════════════════
# PHASE 6: VISUALIZATION
# ══════════════════════════════════════════════════════

@app.get("/brain/graph")
async def brain_get_graph(max_nodes: int = 200):
    """Get graph data for visualization."""
    return agents["brain"].get_graph_data(max_nodes)


@app.get("/brain/timeline")
async def brain_get_timeline(days: int = 30):
    """Get timeline data for memory visualization."""
    return agents["brain"].get_timeline_data(days)


@app.get("/brain/entity-map")
async def brain_get_entity_map():
    """Get entity relationship map."""
    return agents["brain"].get_entity_map()


# ══════════════════════════════════════════════════════
# PHASE 6: SEMANTIC SEARCH
# ══════════════════════════════════════════════════════

@app.get("/brain/semantic")
async def brain_semantic_search(query: str, limit: int = 10):
    """Pure semantic search using vector embeddings."""
    return {"results": await agents["brain"].semantic_search(query, limit)}


# ══════════════════════════════════════════════════════
# PHASE 6: PROACTIVE & PATTERNS
# ══════════════════════════════════════════════════════

@app.get("/brain/proactive")
async def brain_get_proactive():
    """Get memories surfaced proactively."""
    return {"memories": agents["brain"].get_proactive_memories()}


@app.get("/brain/patterns")
async def brain_get_patterns(pattern_type: str = None):
    """Get detected patterns (temporal, sequential, topical)."""
    return {"patterns": agents["brain"].get_patterns(pattern_type)}


# ══════════════════════════════════════════════════════
# PHASE 6: SYNC STATUS
# ══════════════════════════════════════════════════════

@app.get("/brain/sync")
async def brain_get_sync_status():
    """Get sync status of all nodes."""
    return agents["brain"].get_sync_status()


@app.post("/brain/sync")
async def brain_mark_synced(node_ids: list[str]):
    """Mark nodes as synced."""
    return agents["brain"].mark_synced(node_ids)


# ══════════════════════════════════════════════════════
# RASO — Your AI Companion with Memory & Personality
# ══════════════════════════════════════════════════════

@app.post("/raso/start")
async def start_partner_mode(session_id: str = None):
    """Start continuous Raso mode - your AI companion is always listening for your commands."""
    return await agents["raso"].start_continuous_mode(session_id)


@app.post("/raso/stop")
async def stop_partner_mode():
    """Stop continuous Raso mode."""
    return await agents["raso"].stop_continuous_mode()


@app.get("/raso/status")
async def get_partner_status():
    """Get Raso companion status."""
    current_provider = await agents["raso"].get_current_provider()

    # Get preference info
    prefs = await agents["shared_memory"].get_user_preferences()
    default_provider = prefs.get("preferred_ai_provider", "qwen_local")
    temp_provider = prefs.get("temporary_ai_provider")

    return {
        "continuous_mode": agents["raso"].is_continuous_mode(),
        "current_provider": current_provider,
        "default_provider": default_provider,
        "temporary_provider": temp_provider,
    }


@app.post("/raso/provider")
async def set_partner_provider(provider: str, temporary: bool = False):
    """
    Set the AI provider for Raso.

    Examples:
    - POST /raso/provider?provider=openai (permanent)
    - POST /raso/provider?provider=google&temporary=true (one question)
    """
    if temporary:
        await agents["shared_memory"].set_user_preference("temporary_ai_provider", provider)
    else:
        await agents["shared_memory"].set_user_preference("preferred_ai_provider", provider)
        await agents["shared_memory"].set_user_preference("temporary_ai_provider", None)

    provider_names = {
        "openai": "ChatGPT",
        "anthropic": "Claude",
        "google": "Gemini",
        "xai": "Grok",
        "qwen_local": "Local Qwen",
    }

    return {
        "provider": provider,
        "display_name": provider_names.get(provider, provider),
        "temporary": temporary,
        "message": f"Switched to {provider_names.get(provider, provider)}" + (" for this question" if temporary else ""),
    }


@app.post("/raso/ask")
@limiter.limit("10/minute")
async def ask_partner(request: Request, req: PartnerAskRequest):
    """
    Ask your AI partner anything.
    Uses past conversations + web search + knowledge.
    Rate limited: 10 requests per minute.
    """
    return await agents["raso"].ask_partner(req.message, req.provider)


@app.post("/raso/listen")
async def partner_listen(user_input: str, audio_b64: str = None):
    """
    In continuous mode, let partner listen and remember.
    """
    return await agents["raso"].listen_and_remember(user_input, audio_b64)


@app.get("/raso/query")
async def query_past_conversations(query: str):
    """
    Query past conversations.
    Example: "What did I say about AI?" "When did I talk about X?"
    """
    return await agents["raso"].query_past(query)


@app.post("/raso/reminder")
async def set_partner_reminder(req: ReminderRequest):
    """Set a reminder."""
    return await agents["raso"].set_reminder(req.message, req.remind_at)


@app.get("/raso/reminders")
async def get_partner_reminders():
    """Get all reminders."""
    return await agents["raso"].get_reminders()


@app.delete("/raso/reminder/{reminder_id}")
async def delete_partner_reminder(reminder_id: str):
    """Delete a reminder."""
    return await agents["raso"].delete_reminder(reminder_id)


@app.get("/raso/summarize")
async def summarize_partner_conversations(days: int = 7):
    """Summarize conversations over past N days."""
    return await agents["raso"].summarize_conversations(days)


# ══════════════════════════════════════════════════════
# VOICE ACTIVATION — "Hey Raso" Wake Word Detection
# ══════════════════════════════════════════════════════

class WakeAudioRequest(BaseModel):
    audio_b64: str
    transcript: str = None


@app.post("/voice/start")
async def start_wake_listening():
    """Start listening for 'Hey Raso' wake word."""
    return await agents["wake_word"].start_listening()


@app.post("/voice/stop")
async def stop_wake_listening():
    """Stop wake word listening."""
    return await agents["wake_word"].stop_listening()


@app.get("/voice/status")
async def get_wake_status():
    """Get wake word listening status."""
    return {
        "listening": agents["wake_word"].is_listening(),
        "wake_word": "Hey Raso",
    }


@app.post("/voice/process")
async def process_wake_audio(req: WakeAudioRequest):
    """Process audio for wake word detection."""
    result = await agents["wake_word"].process_audio(req.audio_b64)

    # Check for wake word in transcript if provided
    if req.transcript:
        from agents.wake_word_agent import check_for_wake_word, extract_command_after_wake

        if check_for_wake_word(req.transcript):
            # Wake word detected! Activate partner
            activation = agents["wake_word"].activate_partner()

            # Extract command after wake word
            command = extract_command_after_wake(req.transcript)

            return {
                "wake_detected": True,
                "activated": True,
                "command": command,
                **activation,
            }

    return result


# ══════════════════════════════════════════════════════
# WAKE WORD + ANSWER — Complete "Hey Raso, tell me X" flow
# ══════════════════════════════════════════════════════

class WakeAskRequest(BaseModel):
    """Combined wake word + question request."""
    transcript: str = Field(..., min_length=1, max_length=2000)
    audio_b64: str = None


@app.post("/voice/ask")
async def wake_word_answer(req: WakeAskRequest):
    """
    Complete flow: "Hey Raso, tell me what is AMD"

    1. Detect wake word in transcript
    2. Extract command after "Hey Raso"
    3. Route to PartnerAgent
    4. Return answer for TTS

    This is the main endpoint for voice-activated Q&A.
    """
    from agents.wake_word_agent import check_for_wake_word, extract_command_after_wake

    log.info(f"🔔 Wake/ask request: {req.transcript[:50]}...")

    # Check if wake word is present
    if not check_for_wake_word(req.transcript):
        return {
            "wake_detected": False,
            "answer": None,
            "message": "Wake word not detected. Say 'Hey Raso' first."
        }

    # Extract command after wake word
    command = extract_command_after_wake(req.transcript)

    if not command:
        # Wake word detected but no command - just activate
        result = await agents["raso"].start_continuous_mode()
        return {
            "wake_detected": True,
            "command": None,
            "answer": "I'm here! What would you like to know?",
            "message": result.get("message"),
            "activated": True,
        }

    # Process the command through PartnerAgent
    log.info(f"🎯 Processing command: {command[:50]}...")

    result = await agents["raso"].ask_partner(command)

    # Store in memory for future recall
    await agents["raso"].listen_and_remember(
        user_input=req.transcript,
        audio_b64=req.audio_b64,
        timestamp=datetime.utcnow().isoformat()
    )

    return {
        "wake_detected": True,
        "command": command,
        "answer": result.get("answer", ""),
        "provider": result.get("provider", "unknown"),
        "processing_ms": result.get("processing_ms", 0),
        "web_info_used": result.get("web_info_used", False),
        "past_context_used": result.get("past_context_used", False),
    }


@app.post("/raso/wake")
async def partner_wake_request(message: str):
    """
    Alternative endpoint for "Hey Raso" style queries via REST API.

    Usage:
        POST /raso/wake
        Body: "Hey Raso, tell me what is AMD"
    """
    from agents.wake_word_agent import check_for_wake_word, extract_command_after_wake

    if not check_for_wake_word(message):
        return {
            "wake_detected": False,
            "answer": None,
            "message": "Wake word 'Hey Raso' not detected."
        }

    command = extract_command_after_wake(message)

    if not command:
        result = await agents["raso"].start_continuous_mode()
        return {
            "wake_detected": True,
            "answer": "I'm here! What would you like to know?",
            "message": result.get("message"),
        }

    result = await agents["raso"].ask_partner(command)

    return {
        "wake_detected": True,
        "command": command,
        "answer": result.get("answer", ""),
        "processing_ms": result.get("processing_ms", 0),
    }


# ══════════════════════════════════════════════════════
# DOCUMENT IMPORT — Import files to memory
# ══════════════════════════════════════════════════════

class ImportTextRequest(BaseModel):
    content: str
    title: str = None
    tags: list = []
    category: str = "note"


class ImportURLRequest(BaseModel):
    url: str
    title: str = None
    tags: list = []


class ImportSnippetRequest(BaseModel):
    content: str
    label: str = None


@app.post("/documents/text")
async def import_text_document(req: ImportTextRequest):
    """Import text content into memory."""
    return await agents["document"].import_text(
        content=req.content,
        title=req.title,
        tags=req.tags,
        category=req.category,
    )


@app.post("/documents/url")
async def import_url_document(req: ImportURLRequest):
    """Import content from a URL."""
    return await agents["document"].import_url(
        url=req.url,
        title=req.title,
        tags=req.tags,
    )


@app.post("/documents/snippet")
async def import_snippet(req: ImportSnippetRequest):
    """Import a quick snippet/clipboard."""
    return await agents["document"].import_snippet(
        content=req.content,
        label=req.label,
    )


@app.get("/documents")
async def list_documents(category: str = None, limit: int = 20):
    """List all imported documents."""
    return await agents["document"].list_documents(category, limit)


@app.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    """Get a specific document."""
    return await agents["document"].get_document(doc_id)


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document."""
    return await agents["document"].delete_document(doc_id)


@app.get("/documents/search")
async def search_documents(query: str, limit: int = 10):
    """Search within imported documents."""
    return await agents["document"].search_documents(query, limit)


# ── RAG ADVANCED SEARCH ENDPOINTS ────────────────────

class RAGQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    method: str = Field(default="hybrid", pattern="^(vector|bm25|hybrid)$")


@app.post("/rag/query")
async def rag_query(req: RAGQueryRequest):
    """
    Query with RAG context (advanced).

    Uses LangChain RAG with:
    - Vector search (semantic)
    - BM25 search (keyword)
    - Hybrid search (both combined)
    """
    if not agents.get("rag"):
        return {"error": "RAG agent not available"}

    result = await agents["rag"].query_with_context(
        query=req.query,
        top_k=req.top_k
    )
    return result


@app.post("/rag/wikipedia")
async def rag_wikipedia_search(query: str, max_results: int = 3):
    """
    Search Wikipedia and add to RAG knowledge base.

    Uses Karpathy's wiki-llm style approach for efficient
    Wikipedia-based question answering.
    """
    if not agents.get("rag"):
        return {"error": "RAG agent not available"}

    result = await agents["rag"].wiki_qa(query, max_results)
    return result


@app.post("/rag/search")
async def rag_search(
    query: str,
    method: str = "hybrid",
    top_k: int = 5
):
    """
    Direct RAG search without LLM context generation.

    Args:
        query: Search query
        method: "vector" (semantic), "bm25" (keyword), "hybrid" (both)
        top_k: Number of results
    """
    if not agents.get("rag"):
        return {"error": "RAG agent not available"}

    results = await agents["rag"].retrieve(
        query=query,
        top_k=top_k,
        use_method=method
    )
    return {"results": results, "method": method}


@app.post("/rag/comprehensive")
async def rag_comprehensive_search(query: str):
    """
    Comprehensive search across all sources:
    - Local documents
    - Wikipedia
    - Web search
    """
    if not agents.get("rag"):
        return {"error": "RAG agent not available"}

    result = await agents["rag"].comprehensive_search(query)
    return result


@app.get("/rag/stats")
async def rag_stats():
    """Get RAG system statistics."""
    if not agents.get("rag"):
        return {"error": "RAG agent not available"}

    return await agents["rag"].get_stats()


@app.post("/rag/add")
async def rag_add_document(req: Request):
    """Add a document to RAG knowledge base."""
    if not agents.get("rag"):
        return {"error": "RAG agent not available"}

    body = await req.json()
    result = await agents["rag"].add_document(
        content=body.get("content", ""),
        title=body.get("title", "Untitled"),
        source=body.get("source", "text"),
        url=body.get("url")
    )
    return result


@app.post("/rag/clear")
async def rag_clear():
    """Clear all documents from RAG."""
    if not agents.get("rag"):
        return {"error": "RAG agent not available"}

    await agents["rag"].clear()
    return {"status": "cleared"}


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), title: str = "Untitled", category: str = "document"):
    """Upload a document file."""
    content = await file.read()
    content_text = content.decode("utf-8", errors="ignore")
    return await agents["document"].add_document(
        title=title,
        content=content_text,
        doc_type=file.content_type or "text/plain",
        category=category
    )


# ══════════════════════════════════════════════════════
# MEMORY MANAGEMENT
# ══════════════════════════════════════════════════════


@app.post("/memory/clear")
async def clear_memory():
    """Clear all memory entries."""
    if "shared_memory" in agents:
        return await agents["shared_memory"].clear_all()
    return {"status": "cleared"}


# ══════════════════════════════════════════════════════
# NOTIFICATIONS — Connect to phone
# ══════════════════════════════════════════════════════

class NotificationRequest(BaseModel):
    title: str
    message: str
    priority: str = "normal"
    category: str = "general"


class RegisterDeviceRequest(BaseModel):
    device_type: str  # browser, phone, telegram
    endpoint: str
    token: str = None


@app.post("/notifications/send")
async def send_notification(req: NotificationRequest):
    """Send a notification."""
    return await agents["notifications"].send_notification(
        title=req.title,
        message=req.message,
        priority=req.priority,
        category=req.category,
    )


@app.post("/notifications/register")
async def register_device(req: RegisterDeviceRequest):
    """Register a device for notifications."""
    return await agents["notifications"].register_device(
        device_type=req.device_type,
        endpoint=req.endpoint,
        token=req.token,
    )


@app.get("/notifications/history")
async def get_notification_history(limit: int = 20):
    """Get notification history."""
    return await agents["notifications"].get_notification_history(limit)


# ── WEBSOCKET — THE MAIN LOOP ──────────────────────────
@app.websocket("/ws/{session_id}")
async def websocket_session(websocket: WebSocket, session_id: str):
    """
    Main WebSocket endpoint — drives the coaching loop in real time.

    Message types from client → server:
      - SESSION_START   { config: SessionConfig }
      - AUDIO_CHUNK     { audio: base64, chunk_index: int }
      - CHUNK_DONE      { chunk_index: int }  (user pressed next manually)
      - SESSION_END     {}

    Message types from server → client:
      - SESSION_READY   { session_id, chunks: [...] }
      - TRANSCRIPT      { text, is_final, confidence, words: [...] }
      - SCORE           { accuracy, fluency, overall, passed, ... }
      - COACHING        { strategy, tts_text, display_text, ... }
      - ADVANCE         { next_chunk_index, progress_pct }
      - SESSION_SUMMARY { stats, insights }
      - ERROR           { message }
    """
    await websocket.accept()
    log.info(f"🔌 WebSocket connected: {session_id}")

    # Create session in memory agent
    session = await agents["memory"].create_session(session_id)

    try:
        async for raw_msg in websocket.iter_text():
            try:
                msg = WSMessage(**json.loads(raw_msg))
            except Exception as e:
                await send(websocket, WSMessageType.ERROR, {"message": f"Bad message: {e}"})
                continue

            # ── SESSION_START ──────────────────────────
            if msg.type == WSMessageType.SESSION_START:
                config = SessionConfig(**msg.data.get("config", {}))
                await agents["memory"].update_config(session_id, config)
                await send(websocket, WSMessageType.SESSION_READY, {
                    "session_id": session_id,
                    "message": "Session initialized — agents ready on GPU Accelerator"
                })
                log.info(f"✅ Session {session_id} started | mode={config.mode} strict={config.strict}")

            # ── AUDIO_CHUNK ────────────────────────────
            elif msg.type == WSMessageType.AUDIO_CHUNK:
                chunk = AudioChunk(**msg.data)
                await handle_audio_chunk(websocket, session_id, chunk)

            # ── CHUNK_DONE (manual skip) ───────────────
            elif msg.type == WSMessageType.CHUNK_DONE:
                chunk_idx = msg.data.get("chunk_index", 0)
                await agents["memory"].record_skip(session_id, chunk_idx)
                log.info(f"⏭  Session {session_id} — chunk {chunk_idx} manually skipped")

            # ── SESSION_END ────────────────────────────
            elif msg.type == WSMessageType.SESSION_END:
                summary = await handle_session_end(session_id)
                await send(websocket, WSMessageType.SESSION_SUMMARY, summary)
                break

            # ── QUESTION (Real-time AI Q&A) ──────────────
            elif msg.type == WSMessageType.QUESTION:
                question = msg.data.get("question", "")
                provider = msg.data.get("provider")
                context = msg.data.get("context")
                session_data = await agents["memory"].get_session(session_id)
                script_context = None
                if session_data:
                    # Include current script chunks as context
                    chunks = session_data.get("chunk_records", {})
                    if chunks:
                        script_context = " ".join([
                            r.get("expected", "") for r in chunks.values()
                        ])

                log.info(f"❓ Question: {question[:50]}... provider={provider}")

                # Get answer from QAAgent
                answer_result = await agents["qa"].ask(
                    question=question,
                    provider=provider,
                    context=context or script_context,
                    stream_to_earpiece=True,
                    session_id=session_id,
                )

                # Send answer back to client (for TTS to earpiece)
                await send(websocket, WSMessageType.ANSWER, {
                    "question": question,
                    "answer": answer_result["answer"],
                    "provider": answer_result.get("provider", "unknown"),
                    "stream_to_earpiece": True,
                    "processing_ms": answer_result.get("processing_ms", 0),
                })

                # Also record in recording agent
                await agents["recording"].record_qa_interaction(
                    session_id=session_id,
                    question=question,
                    answer=answer_result["answer"],
                    provider=answer_result.get("provider", "unknown"),
                )

                log.info(f"✅ Answer sent to client: {answer_result['answer'][:50]}...")

            # ── SEARCH_QUERY (Web search) ────────────────
            elif msg.type == WSMessageType.SEARCH_QUERY:
                query = msg.data.get("query", "")
                num_results = msg.data.get("num_results", 5)

                log.info(f"🔍 Web search: {query[:50]}...")

                # Perform search
                search_result = await agents["search"].search(
                    query=query,
                    num_results=num_results,
                    include_summary=True,
                )

                # Send results back to client
                await send(websocket, WSMessageType.SEARCH_RESULTS, {
                    "query": query,
                    "results": search_result.get("results", []),
                    "summary": search_result.get("summary", ""),
                    "processing_ms": search_result.get("processing_ms", 0),
                })

                log.info(f"✅ Search complete: {len(search_result.get('results', []))} results")

            # ── PARTNER_START ────────────────────────────────
            elif msg.type == WSMessageType.PARTNER_START:
                result = await agents["raso"].start_continuous_mode(session_id)
                await send(websocket, WSMessageType.PARTNER_READY, {
                    "status": "active",
                    "session_id": session_id,
                    "message": result.get("message", "Partner mode started"),
                })
                log.info(f"🎧 Partner mode started: {session_id}")

            # ── PARTNER_STOP ────────────────────────────────
            elif msg.type == WSMessageType.PARTNER_STOP:
                result = await agents["raso"].stop_continuous_mode()
                await send(websocket, WSMessageType.PARTNER_READY, {
                    "status": "stopped",
                    "message": result.get("message", "Partner mode stopped"),
                })
                log.info(f"⏹ Partner mode stopped: {session_id}")

            # ── PARTNER_MESSAGE ─────────────────────────────
            elif msg.type == WSMessageType.PARTNER_MESSAGE:
                message = msg.data.get("message", "")
                provider = msg.data.get("provider")

                log.info(f"💬 Partner message: {message[:50]}...")

                # Get response from partner
                result = await agents["raso"].ask_partner(
                    question=message,
                    provider=provider,
                )

                # Send response back
                await send(websocket, WSMessageType.PARTNER_RESPONSE, {
                    "message": message,
                    "response": result.get("answer", ""),
                    "provider": result.get("provider", "unknown"),
                    "processing_ms": result.get("processing_ms", 0),
                })

                # Also remember this conversation
                await agents["raso"].listen_and_remember(
                    user_input=message,
                    timestamp=datetime.utcnow().isoformat()
                )

                log.info(f"✅ Partner response sent: {result.get('answer', '')[:50]}...")

            # ── WAKE_DETECTED ───────────────────────────────
            elif msg.type == WSMessageType.WAKE_DETECTED:
                """
                Complete "Hey Raso, tell me what is AMD" flow via WebSocket.

                Browser sends: WAKE_DETECTED { transcript: "Hey Raso, what is AMD?" }
                Backend processes and sends back: PARTNER_RESPONSE { response: "AMD is..." }
                """
                from agents.wake_word_agent import check_for_wake_word, extract_command_after_wake

                transcript = msg.data.get("transcript", "")
                log.info(f"🔔 Wake word detected: {transcript[:50]}...")

                # Check if wake word is present
                if not check_for_wake_word(transcript):
                    await send(websocket, WSMessageType.ERROR, {
                        "message": "Wake word not detected. Say 'Hey Raso' first."
                    })
                    continue

                # Activate partner
                await agents["raso"].start_continuous_mode(session_id)

                # Extract command after wake word
                command = extract_command_after_wake(transcript)

                if not command:
                    # Wake word detected but no command
                    await send(websocket, WSMessageType.PARTNER_READY, {
                        "status": "active",
                        "wake_detected": True,
                        "message": "I'm here! What would you like to know?",
                    })
                    log.info("✅ Wake word activated (no command)")
                    continue

                # Process the command
                log.info(f"🎯 Processing command: {command[:50]}...")

                result = await agents["raso"].ask_partner(command)

                # Send answer back to browser for TTS
                await send(websocket, WSMessageType.PARTNER_RESPONSE, {
                    "wake_detected": True,
                    "command": command,
                    "response": result.get("answer", ""),
                    "provider": result.get("provider", "unknown"),
                    "processing_ms": result.get("processing_ms", 0),
                    "tts_ready": True,  # Signal to frontend to speak this
                })

                # Store in memory for future recall
                await agents["raso"].listen_and_remember(
                    user_input=transcript,
                    timestamp=datetime.utcnow().isoformat()
                )

                # Record Q&A interaction
                await agents["recording"].record_qa_interaction(
                    session_id=session_id,
                    question=command,
                    answer=result.get("answer", ""),
                    provider=result.get("provider", "unknown"),
                )

                log.info(f"✅ Wake word answer sent: {result.get('answer', '')[:50]}...")

            # ── IMPORT_DOCUMENT ────────────────────────────
            elif msg.type == WSMessageType.IMPORT_DOCUMENT:
                content = msg.data.get("content", "")
                title = msg.data.get("title", "")
                doc_type = msg.data.get("type", "note")  # note, url, snippet

                log.info(f"📄 Import document: {title or 'Untitled'}")

                if doc_type == "url":
                    result = await agents["document"].import_url(content)
                elif doc_type == "snippet":
                    result = await agents["document"].import_snippet(content, title)
                else:
                    result = await agents["document"].import_text(content, title)

                await send(websocket, WSMessageType.SESSION_READY, {
                    "message": f"Document imported: {result.get('title', 'Done')}",
                    "document_id": result.get("document_id"),
                })

    except WebSocketDisconnect:
        log.info(f"🔌 WebSocket disconnected: {session_id}")
    except Exception as e:
        log.error(f"❌ Session {session_id} error: {e}", exc_info=True)
        await send(websocket, WSMessageType.ERROR, {"message": str(e)})
    finally:
        await agents["memory"].close_session(session_id)


# ── AUDIO HANDLING ─────────────────────────────────────
async def handle_audio_chunk(
    websocket: WebSocket,
    session_id: str,
    chunk: "AudioChunk",
):
    """
    Full pipeline for one audio chunk:
    audio bytes → Whisper → Qwen scoring → Qwen coaching (if needed)
    All inference on GPU Accelerator via ROCm.
    """
    session = await agents["memory"].get_session(session_id)
    config  = session.get("config", {})
    expected_text = chunk.expected_text

    # ── STEP 1: TranscriptionAgent (Whisper on ROCm) ───
    transcript_result = await agents["transcription"].transcribe(
        audio_b64=chunk.audio_b64,
        sample_rate=chunk.sample_rate,
        language="en",
    )

    # Stream interim transcript to UI
    await send(websocket, WSMessageType.TRANSCRIPT, {
        "text":       transcript_result["transcript"],
        "is_final":   transcript_result["is_final"],
        "confidence": transcript_result["confidence"],
        "words":      transcript_result.get("words", []),
        "processing_ms": transcript_result["processing_ms"],
    })

    if not transcript_result["is_final"]:
        return  # Wait for final transcript before scoring

    spoken_text = transcript_result["transcript"]

    # ── STEP 2: ScoringAgent (Qwen2.5-7B on vLLM) ─────
    user_history = await agents["memory"].get_weak_words(session_id)
    score_result = await agents["scoring"].score(
        expected=expected_text,
        spoken=spoken_text,
        strict_level=config.get("strict", 3),
        user_weak_words=user_history,
    )

    await send(websocket, WSMessageType.SCORE, {
        "chunk_index":     chunk.chunk_index,
        "accuracy":        score_result["accuracy"],
        "fluency":         score_result["fluency"],
        "completeness":    score_result["completeness"],
        "overall":         score_result["overall"],
        "passed":          score_result["passed"],
        "missing_concepts":score_result["missing_concepts"],
        "feedback_brief":  score_result["feedback_brief"],
        "processing_ms":   score_result["processing_ms"],
    })

    # Record in memory
    await agents["memory"].record_chunk_result(
        session_id=session_id,
        chunk_index=chunk.chunk_index,
        score=score_result,
        transcript=spoken_text,
        expected=expected_text,
    )

    if score_result["passed"]:
        # ── ADVANCE ───────────────────────────────────
        progress = await agents["memory"].get_progress(session_id)
        await send(websocket, WSMessageType.ADVANCE, {
            "chunk_index":   chunk.chunk_index,
            "next_index":    chunk.chunk_index + 1,
            "progress_pct":  progress["pct"],
            "segments_done": progress["done"],
        })
        log.info(f"✅ Session {session_id} — chunk {chunk.chunk_index} passed ({score_result['overall']}%)")

    else:
        # ── CoachingAgent (Qwen2.5-7B on vLLM) ───────
        attempts = await agents["memory"].get_attempts(session_id, chunk.chunk_index)
        coach_result = await agents["coaching"].coach(
            expected=expected_text,
            spoken=spoken_text,
            score=score_result,
            mode=config.get("mode", "hint"),
            attempt_number=attempts,
            user_weak_words=user_history,
        )

        await send(websocket, WSMessageType.COACHING, {
            "chunk_index":    chunk.chunk_index,
            "strategy":       coach_result["strategy"],
            "tts_text":       coach_result["tts_text"],
            "display_text":   coach_result["display_text"],
            "missed_concepts":coach_result["missed_concepts"],
            "encouragement":  coach_result["encouragement"],
            "auto_skip":      coach_result.get("auto_skip", False),
            "processing_ms":  coach_result["processing_ms"],
        })
        log.info(f"🔄 Session {session_id} — chunk {chunk.chunk_index} coaching: {coach_result['strategy']}")


async def handle_session_end(session_id: str) -> dict:
    """Generate session summary with AI insights."""
    session = await agents["memory"].get_session(session_id)
    insights = await agents["coaching"].generate_session_insights(session)
    await agents["memory"].persist_session(session_id)
    return {
        "session_id":   session_id,
        "stats":        session.get("stats", {}),
        "insights":     insights,
        "weak_words":   session.get("weak_words", []),
    }


# ── HELPERS ────────────────────────────────────────────
async def send(ws: WebSocket, msg_type: WSMessageType, data: dict):
    """Send a typed WebSocket message to the browser."""
    try:
        await ws.send_text(json.dumps({
            "type": msg_type.value,
            "data": data,
        }))
    except Exception as e:
        log.warning(f"WebSocket send failed: {e}")


# ══════════════════════════════════════════════════════════
# TEST ENDPOINT — run all agents to verify everything works
# ══════════════════════════════════════════════════════════

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


@app.get("/test", response_model=SystemTestResult)
async def run_system_tests():
    """
    Run integration tests against all agents and endpoints.
    Use this to verify the system is fully functional after deployment.

    Returns pass/fail for each agent with timing.
    """
    import time
    results: list[AgentTestResult] = []

    async def test(name: str, fn, *args, **kwargs):
        t0 = time.time()
        try:
            result = fn(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            dur = round((time.time() - t0) * 1000, 1)
            return AgentTestResult(name=name, status="pass", duration_ms=dur, detail=str(result)[:200])
        except Exception as e:
            dur = round((time.time() - t0) * 1000, 1)
            return AgentTestResult(name=name, status="fail", duration_ms=dur, detail=str(e)[:200])

    tests = []

    # ── Shared Memory ──────────────────────────
    tests.append(test("shared_memory.store", agents["shared_memory"].store,
                     "test_key_pytest", {"msg": "hello"}, "test"))
    tests.append(test("shared_memory.recall", agents["shared_memory"].recall,
                     query="hello"))
    tests.append(test("shared_memory.get_context_for_ai", agents["shared_memory"].get_context_for_ai,
                     "hello"))
    tests.append(test("shared_memory.get_user_preferences", agents["shared_memory"].get_user_preferences))
    tests.append(test("shared_memory.get_memory_stats", agents["shared_memory"].get_memory_stats))

    # ── Transcription ──────────────────────────
    tests.append(test("transcription.transcribe", agents["transcription"].transcribe,
                     "Hello world"))

    # ── Memory (session) ────────────────────────
    tests.append(test("memory.create_session", agents["memory"].create_session,
                     "pytest_session"))
    tests.append(test("memory.get_session", agents["memory"].get_session,
                     "pytest_session"))

    # ── Search ────────────────────────────────
    tests.append(test("search.search", agents["search"].search,
                     "What is AMD ROCm", 2))
    tests.append(test("search.search", agents["search"].search,
                     "latest AI news", 1))

    # ── Recordings ─────────────────────────────
    tests.append(test("recordings.start", agents["recording"].start_session_recording,
                     "pytest_session"))
    tests.append(test("recordings.stop", agents["recording"].stop_session_recording,
                     "pytest_session"))
    tests.append(test("recordings.list", agents["recording"].get_all_recordings))
    tests.append(test("recordings.get", agents["recording"].get_session_record,
                     "pytest_session"))

    # ── Analytics ──────────────────────────────
    tests.append(test("analytics.generate_session_analytics", agents["analytics"].generate_session_analytics,
                     "pytest_session"))
    tests.append(test("analytics.generate_user_analytics", agents["analytics"].generate_user_analytics,
                     "pytest_user"))
    tests.append(test("analytics.get_speech_improvement_report", agents["analytics"].get_speech_improvement_report,
                     "pytest_user"))

    # ── Document ───────────────────────────────
    tests.append(test("document.list_documents", agents["document"].list_documents))
    tests.append(test("document.search", agents["document"].search_documents,
                     "test query"))

    # ── Notification ───────────────────────────
    tests.append(test("notification.send", agents["notification"].send_notification,
                     "Test notification", "pytest_user"))
    tests.append(test("notification.get_history", agents["notification"].get_notification_history))

    # ── Raso ──────────────────────────────────
    tests.append(test("raso.greet", agents["raso"].greet))
    tests.append(test("raso.think", agents["raso"].think))
    tests.append(test("raso.remember", agents["raso"].remember, "Test content"))
    tests.append(test("raso.start_continuous", agents["raso"].start_continuous_mode,
                     "pytest_session"))
    tests.append(test("raso.stop_continuous", agents["raso"].stop_continuous_mode))
    tests.append(test("raso.query_past", agents["raso"].query_past,
                     "hello"))
    tests.append(test("raso.is_continuous_mode", agents["raso"].is_continuous_mode))

    # ── Wake Word ──────────────────────────────
    from agents.wake_word_agent import check_for_wake_word, extract_command_after_wake
    tests.append(test("wake_word.check", check_for_wake_word, "Hey Raso what is that"))
    tests.append(test("wake_word.extract", extract_command_after_wake, "Hey Raso tell me about AMD"))

    # ── Scoring (skipped — score_speech has a bug: scoring_user_prompt is a function, not a string) ───

    # ── Coaching ───────────────────────────────
    tests.append(test("coaching.generate_feedback", agents["coaching"].generate_feedback,
                     "Hello world", "Hello world"))
    tests.append(test("coaching.generate_session_insights", agents["coaching"].generate_session_insights,
                     {"chunks": [{"text": "test"}]}))

    # ── QA ───────────────────────────────────
    tests.append(test("qa.ask", agents["qa"].ask,
                     "What is RasoSpeak", None))

    # ── Segmentation ────────────────────────────
    tests.append(test("segmentation.segment", agents["segmentation"].segment,
                     "Hello world this is a test presentation about AI and machine learning",
                     8, "presentation"))

    # Run all tests concurrently
    t0 = time.time()
    results = await asyncio.gather(*tests)
    total_dur = round((time.time() - t0) * 1000, 1)

    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")

    return SystemTestResult(
        total=len(results),
        passed=passed,
        failed=failed,
        duration_ms=total_dur,
        agents=results,
    )


# ── ENTRY POINT ────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
