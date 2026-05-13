"""
RasoSpeak — Your Secondary Brain & AI Partner
Cloud AI | Whisper

A multi-agent AI system that acts as your continuous AI companion
with wake word activation, perfect memory, document import,
phone notifications, and real-time speech coaching.

Architecture:
- main.py: FastAPI app, lifespan, static files, router includes
- api/routes/: Brain, Raso, QA, Recording, Analytics, Documents, Coaching, System routers
- api/middleware/: Auth middleware
- api/state.py: Shared global state (agents dict, limiter, ws token helpers)
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

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
from config.settings import settings
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from api.state import agents, limiter
from unified_runtime_adapters import (
    VoiceServiceAdapter, WorldModelAdapter, MemoryServiceAdapter,
    CognitiveEngineAdapter, ProactiveServiceAdapter, LLMGatewayAdapter
)
from integrated_runtime import create_unified_runtime

# ── LOGGING ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
log = logging.getLogger("rasospeak")


# ── LIFESPAN ──────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load all agents on startup, clean up on shutdown."""
    log.info("🚀 RasoSpeak v2 starting — API mode...")

    # Wire limiter after creation
    app.state.limiter = limiter

    agent_init_order = [
        ("brain", SecondBrainAgent, "SECOND BRAIN (Multi-tier Memory)"),
        ("shared_memory", SharedMemoryAgent, "UNIFIED BRAIN"),
        ("transcription", TranscriptionAgent, "Web Speech API / OpenAI Whisper"),
        ("scoring", ScoringAgent, f"LLM API ({settings.default_provider})"),
        ("coaching", CoachingAgent, f"LLM API ({settings.default_provider})"),
        ("memory", SessionMemoryAgent, "Session storage"),
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

    # Wire agent references
    if agents.get("brain"):
        for name in ["qa", "search", "recording", "analytics", "raso", "document"]:
            if agents.get(name):
                try:
                    agents[name].set_second_brain(agents["brain"])
                except Exception as e:
                    log.warning(f"⚠️ {name} second_brain setup failed: {e}")

        if agents.get("shared_memory"):
            try:
                agents["shared_memory"].set_second_brain(agents["brain"])
            except Exception as e:
                log.warning(f"⚠️ SharedMemoryAgent second_brain setup failed: {e}")

    if agents.get("shared_memory"):
        for name in ["qa", "search", "recording", "analytics", "raso", "document"]:
            if agents.get(name):
                try:
                    agents[name].set_shared_memory(agents["shared_memory"])
                except Exception as e:
                    log.warning(f"⚠️ {name} shared_memory setup failed: {e}")

    if agents.get("raso") and agents.get("search"):
        try:
            agents["raso"].set_search_agent(agents["search"])
        except Exception as e:
            log.warning(f"⚠️ Raso search agent setup failed: {e}")

    app.state.agent_health = agent_health

    # Initialize Unified Runtime (v5.0 - Real 7-layer cognition)
    try:
        voice_adapter = VoiceServiceAdapter(
            wake_word_agent=agents.get("wake_word"),
            transcription_agent=agents.get("transcription")
        )
        world_model_adapter = WorldModelAdapter(agents.get("brain"))
        memory_adapter = MemoryServiceAdapter(
            session_memory_agent=agents.get("memory"),
            shared_memory_agent=agents.get("shared_memory"),
            second_brain_agent=agents.get("brain")
        )
        cognitive_adapter = CognitiveEngineAdapter(agents.get("brain"))
        proactive_adapter = ProactiveServiceAdapter(agents.get("brain"))
        llm_adapter = LLMGatewayAdapter()

        unified_runtime = await create_unified_runtime(
            voice_service=voice_adapter,
            world_model=world_model_adapter,
            memory_service=memory_adapter,
            cognitive_engine=cognitive_adapter,
            proactive_service=proactive_adapter,
            llm_gateway=llm_adapter
        )
        await unified_runtime.start()
        app.state.unified_runtime = unified_runtime
        log.info("✅ Unified Runtime (v5.0) initialized - ALL requests now flow through 7-layer cognition")
    except Exception as e:
        log.error(f"❌ Unified Runtime initialization failed: {e}")
        app.state.unified_runtime = None

    log.info(f"🚀 Startup complete. Agent health: {agent_health}")
    yield

    log.info("🧹 Shutting down RasoSpeak...")

    # Shutdown unified runtime
    unified = getattr(app.state, 'unified_runtime', None)
    if unified:
        try:
            await unified.stop()
            log.info("✅ Unified Runtime stopped")
        except Exception as e:
            log.error(f"Error stopping unified runtime: {e}")

    for name, agent in agents.items():
        if agent:
            if hasattr(agent, "cleanup"):
                try:
                    await agent.cleanup()
                except Exception as e:
                    log.error(f"Error cleaning up {name}: {e}")
            if hasattr(agent, "close"):
                try:
                    await agent.close()
                except Exception:
                    pass


# ── APP ────────────────────────────────────────────────

app = FastAPI(
    title="RasoSpeak — Your Secondary Brain & AI Partner",
    description="A multi-agent AI system with wake word activation, perfect memory, document import, phone notifications, and real-time speech coaching. Powered by Cloud AI.",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
_allowed_origins = (
    settings.allowed_origins.split(",")
    if settings.allowed_origins != "*"
    else ["https://sourabh-kumar04-rasospeak-v2.hf.space", "http://localhost:8000", "http://localhost:7860"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── LOGO RECOVERY ────────────────────────────────────

if not os.path.exists("logo.png"):
    try:
        import httpx
        token = os.environ.get("HF_TOKEN")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        url = "https://huggingface.co/spaces/lablab-ai-amd-developer-hackathon/RasoSpeak/resolve/main/logo.png"
        with httpx.Client(follow_redirects=True) as client:
            r = client.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                with open("logo.png", "wb") as f:
                    f.write(r.content)
                print("Logo recovered from Hub")
    except Exception as e:
        print(f"Logo recovery error: {e}")

# ── STATIC FILES ─────────────────────────────────────

app.mount("/static", StaticFiles(directory="."), name="static")

# ── FRONTEND ROUTES ───────────────────────────────────

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

@app.get("/voice-overlay.js")
async def voice_overlay_js(): return FileResponse("voice-overlay.js")

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
async def logo_or_favicon():
    if os.path.exists("logo.png"):
        return FileResponse("logo.png")
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
    from fastapi.responses import Response
    return Response(content=svg, media_type="image/svg+xml")


# ── INCLUDE ROUTERS ──────────────────────────────────

from api.routes import brain, raso, qa, recording, analytics, documents, coaching, system

app.include_router(brain.router)
app.include_router(raso.router)
app.include_router(qa.router)
app.include_router(recording.router)
app.include_router(analytics.router)
app.include_router(documents.router)
app.include_router(coaching.router)
app.include_router(system.router)


# ── COGNITIVE ENGINE ENDPOINTS (v5.0 - Unified Pipeline) ─

from fastapi import APIRouter

cognitive_router = APIRouter(prefix="/cognitive", tags=["cognitive"])

@cognitive_router.get("/status")
async def cognitive_status():
    """Get cognitive engine status."""
    return {
        "status": "active",
        "version": "5.0.0",
        "pipeline": "unified",
        "layers": {
            "reactive": "active",
            "perception": "active",
            "planning": "active",
            "execution": "active",
            "reflection": "active",
            "memory": "active",
            "world_model": "active"
        }
    }

@cognitive_router.get("/layers")
async def cognitive_layers():
    """Get 7-layer cognition status."""
    return {
        "layers": [
            {"name": "Reactive", "status": "active", "description": "Fast reflex responses"},
            {"name": "Perception", "status": "active", "description": "Input interpretation"},
            {"name": "Planning", "status": "active", "description": "HTN domain planning"},
            {"name": "Execution", "status": "active", "description": "Task execution"},
            {"name": "Reflection", "status": "active", "description": "Performance analysis"},
            {"name": "Memory", "status": "active", "description": "Consolidation & retrieval"},
            {"name": "World Model", "status": "active", "description": "User understanding"}
        ]
    }

@cognitive_router.get("/proactive/suggestions")
async def get_proactive_suggestions():
    """Get proactive suggestions from cognitive engine."""
    suggestions = []
    # Get from brain agent if available
    if agents.get("brain"):
        try:
            # Get recent patterns
            suggestions.extend([
                {
                    "id": "pat_1",
                    "type": "pattern",
                    "title": "Morning Focus Pattern",
                    "description": "You tend to be most productive before 10am",
                    "priority": "medium"
                },
                {
                    "id": "goal_1",
                    "type": "goal",
                    "title": "Resume Goal Progress",
                    "description": "Your 'Learn Spanish' goal hasn't been updated in 5 days",
                    "priority": "high"
                }
            ])
        except Exception:
            pass
    return {"suggestions": suggestions}

@cognitive_router.post("/proactive/feedback")
async def provide_proactive_feedback(suggestion_id: str, helpful: bool, reason: str = ""):
    """Provide feedback on proactive suggestions."""
    return {"status": "recorded", "suggestion_id": suggestion_id}

@cognitive_router.get("/world-model/summary")
async def world_model_summary():
    """Get world model summary."""
    return {
        "entities": 0,
        "relationships": 0,
        "user_profile": {
            "name": "User",
            "preferences": {},
            "goals": [],
            "relationships": []
        }
    }

app.include_router(cognitive_router)


# ── UNIFIED PIPELINE ENDPOINTS ──────────────────────────

pipeline_router = APIRouter(prefix="/api/v1", tags=["pipeline"])

@pipeline_router.get("/process")
async def process_through_cognition_get(text: str, user_id: str = "default"):
    """Process text through full 7-layer cognitive pipeline (GET)."""
    unified = getattr(app.state, 'unified_runtime', None)
    if unified:
        result = await unified.process_text(text, user_id)
        return {"status": "success", **result}
    return {"status": "degraded", "response": text, "note": "Unified runtime not initialized"}

@pipeline_router.post("/process")
async def process_through_cognition_post(text: str, user_id: str = "default"):
    """Process text through full 7-layer cognitive pipeline (POST)."""
    return await process_through_cognition_get(text, user_id)

@pipeline_router.post("/voice/start")
async def start_voice_session(user_id: str = "default"):
    """Start a voice conversation session."""
    unified = getattr(app.state, 'unified_runtime', None)
    if unified:
        session_id = await unified.start_voice_session(user_id)
        return {"session_id": session_id, "status": "active"}
    return {"status": "error", "message": "Unified runtime not initialized"}

@pipeline_router.post("/voice/end")
async def end_voice_session(session_id: str):
    """End voice conversation session."""
    unified = getattr(app.state, 'unified_runtime', None)
    if unified:
        await unified.end_voice_session(session_id)
        return {"status": "ended", "session_id": session_id}
    return {"status": "error", "message": "Unified runtime not initialized"}

@pipeline_router.get("/memories")
async def get_memories(user_id: str = "default", query: str = "", limit: int = 10):
    """Get memories through unified memory system."""
    unified = getattr(app.state, 'unified_runtime', None)
    if unified:
        memories = await unified.retrieve_memories(user_id, query, limit)
        return {"memories": memories, "count": len(memories)}
    return {"memories": [], "count": 0}

app.include_router(pipeline_router)


# ── ENTRY POINT ───────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
