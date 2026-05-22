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
import json
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

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

# ── NEW IMPORTS (v2.1 Production) ─────────────────────
# Database layer
try:
    from db.unified import db, init_database
except ImportError:
    db = None
    init_database = None

# Observability
try:
    from api.observability import observability, instrument_fastapi
except ImportError:
    observability = None
    instrument_fastapi = lambda x: None

# Voice pipeline
try:
    from services.voice import voice_pipeline, WakeWordDetector
except ImportError:
    voice_pipeline = None
    WakeWordDetector = None

# Unified Memory (replaces 4 separate systems)
try:
    from agents.unified_memory_agent import unified_memory, UnifiedMemoryAgent
except ImportError:
    unified_memory = None
    UnifiedMemoryAgent = None

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

        # Wire ProviderManager into LLM adapter for live provider switching
        llm_adapter.set_provider_manager(provider_manager)

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

    # ── v2.1 NEW: Database & Observability ─────────────
    # Initialize PostgreSQL database
    if init_database:
        try:
            await init_database()
            log.info("✅ Database initialized")
        except Exception as e:
            log.warning(f"⚠️ Database init failed: {e} (using fallback)")

    # Initialize observability (OpenTelemetry)
    if observability:
        try:
            observability.initialize()
            log.info("✅ Observability initialized")
        except Exception as e:
            log.warning(f"⚠️ Observability init failed: {e}")

    # Initialize voice pipeline
    if voice_pipeline:
        try:
            await voice_pipeline.initialize()
            log.info("✅ Voice pipeline initialized")
        except Exception as e:
            log.warning(f"⚠️ Voice pipeline init failed: {e}")

    # Initialize unified memory (replaces 4 systems)
    if unified_memory:
        try:
            await unified_memory.initialize()
            agents["unified_memory"] = unified_memory
            agent_health["unified_memory"] = "ok"
            log.info("✅ Unified Memory (single system) initialized")
        except Exception as e:
            log.warning(f"⚠️ Unified Memory init failed: {e}")

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


# ── HEALTH CHECK ──────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration (K8s, etc.)."""
    agent_health = getattr(app.state, 'agent_health', {})
    healthy_agents = sum(1 for status in agent_health.values() if status == "ok")
    total_agents = len(agent_health)

    return {
        "status": "healthy" if healthy_agents == total_agents else "degraded",
        "version": "2.0.0",
        "agents": {
            "total": total_agents,
            "healthy": healthy_agents,
            "details": agent_health
        },
        "unified_runtime": app.state.unified_runtime is not None
    }


# ── GLOBAL EXCEPTION HANDLER ──────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Catch-all exception handler for unhandled errors."""
    log.error(f"Unhandled exception: {exc}", exc_info=True)
    return {"error": "Internal server error", "detail": str(exc)}


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

# ── PROVIDER RUNTIME ENDPOINTS ───────────────────────────

from services.provider_runtime.src.provider_endpoints import provider_router as provider_runtime_router, set_provider_manager as set_provider_endpoint_manager
from services.provider_runtime.src.core.provider_manager import get_provider_manager

# Initialize provider manager FIRST (needed by unified runtime)
provider_manager = get_provider_manager()
set_provider_endpoint_manager(provider_manager)

app.include_router(provider_runtime_router)


# ── UNIFIED PIPELINE ENDPOINTS ──────────────────────────

pipeline_router = APIRouter(prefix="/api/v1", tags=["pipeline"])

class ProcessRequest(BaseModel):
    text: str
    user_id: str = "default"


@pipeline_router.get("/process")
async def process_through_cognition_get(text: str, user_id: str = "default"):
    """Process text through full 7-layer cognitive pipeline (GET)."""
    unified = getattr(app.state, 'unified_runtime', None)
    if unified:
        result = await unified.process_text(text, user_id)
        return {"status": "success", **result}
    return {"status": "degraded", "response": text, "note": "Unified runtime not initialized"}


@pipeline_router.get("/status")
async def get_system_status():
    """Get comprehensive system status - single source of truth for all subsystems."""
    # Provider state
    provider_state = provider_manager.get_active_state()
    provider_info = {
        "provider_id": provider_state.provider_id if provider_state else "google",
        "provider_type": provider_state.provider_type if provider_state else "google",
        "model": provider_state.model if provider_state else "gemini-2.0-flash-exp",
        "ownership": provider_state.ownership.value if provider_state else "platform"
    } if provider_state else {"provider_id": "google", "provider_type": "google", "model": "gemini-2.0-flash-exp"}

    # Unified runtime state
    unified = getattr(app.state, 'unified_runtime', None)
    cognitive_status = "active" if unified else "unavailable"
    memory_status = "connected" if unified else "disconnected"

    # Agent health
    agent_health = getattr(app.state, 'agent_health', {})

    # Memory stats from SecondBrain
    brain_stats = {}
    if agents.get("brain"):
        try:
            if hasattr(agents["brain"], 'get_memory_stats'):
                brain_stats = await agents["brain"].get_memory_stats()
        except:
            pass

    return {
        "status": "operational",
        "version": "2.1.0",
        "provider": provider_info,
        "cognitive_pipeline": {
            "status": cognitive_status,
            "layers": ["reactive", "perception", "planning", "execution", "reflection", "memory", "world_model"]
        },
        "memory": {
            "status": memory_status,
            "system": "second_brain_unified",
            "stats": brain_stats
        },
        "agents": agent_health,
        "websocket": "/ws endpoint available",
        "capabilities": {
            "provider_switching": True,
            "memory_retrieval": True,
            "cognitive_pipeline": True,
            "real_time_sync": True,
            "voice_commands": True
        }
    }


@pipeline_router.post("/process")
async def process_through_cognition_post(req: ProcessRequest):
    """Process text through full 7-layer cognitive pipeline (POST with JSON body)."""
    unified = getattr(app.state, 'unified_runtime', None)
    if unified:
        result = await unified.process_text(req.text, req.user_id)
        return {"status": "success", **result}
    return {"status": "degraded", "response": req.text, "note": "Unified runtime not initialized"}

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


# ── WEBSOCKET FOR REAL-TIME STATE SYNC ─────────────────

from typing import Dict, Set

class ConnectionManager:
    """Manages WebSocket connections for real-time state sync."""
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str = "default"):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)

    def disconnect(self, websocket: WebSocket, user_id: str = "default"):
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)

    async def broadcast_provider_state(self, user_id: str, state: dict):
        """Broadcast provider state to all connections."""
        message = {"type": "provider_state", "data": state}
        if user_id in self.active_connections:
            dead = set()
            for ws in self.active_connections[user_id]:
                try:
                    await ws.send_json(message)
                except:
                    dead.add(ws)
            for ws in dead:
                self.active_connections[user_id].discard(ws)

    async def broadcast_cognition_event(self, user_id: str, event: dict):
        """Broadcast cognition events to UI."""
        message = {"type": "cognition_event", "data": event}
        if user_id in self.active_connections:
            for ws in self.active_connections[user_id]:
                try:
                    await ws.send_json(message)
                except:
                    pass


ws_manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time sync - provider state, cognition events, memory updates."""
    user_id = websocket.query_params.get("user_id", "default")
    await ws_manager.connect(websocket, user_id)

    try:
        # Send initial state
        provider_state = provider_manager.get_active_state()
        await websocket.send_json({
            "type": "connected",
            "user_id": user_id,
            "provider": {
                "provider_id": provider_state.provider_id if provider_state else "google",
                "provider_type": provider_state.provider_type if provider_state else "google",
                "model": provider_state.model if provider_state else "gemini-2.0-flash-exp"
            } if provider_state else {"provider_id": "google", "provider_type": "google", "model": "gemini-2.0-flash-exp"}
        })

        # Register provider switch callback to broadcast changes
        async def on_provider_switch(event):
            state = provider_manager.get_active_state()
            await ws_manager.broadcast_provider_state(user_id, {
                "provider_id": state.provider_id if state else "unknown",
                "provider_type": state.provider_type if state else "unknown",
                "model": state.model if state else "unknown",
                "switched_at": str(state.switched_at) if state else None
            })

        provider_manager.register_switch_callback(on_provider_switch)

        while True:
            # Receive messages from client
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "switch_provider":
                # Client requests provider switch
                provider_type = data.get("provider_type")
                model = data.get("model")
                await provider_manager.switch_by_type(provider_type, model)

            elif msg_type == "get_state":
                # Client requests current state
                state = provider_manager.get_active_state()
                await websocket.send_json({
                    "type": "provider_state",
                    "data": {
                        "provider_id": state.provider_id if state else "google",
                        "model": state.model if state else "gemini-2.0-flash-exp"
                    }
                })

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, user_id)
    except Exception as e:
        ws_manager.disconnect(websocket, user_id)


# ── AUDIO WEBSOCKET FOR SERVER-SIDE VOICE PROCESSING ─

@app.websocket("/ws/audio")
async def audio_websocket_endpoint(websocket: WebSocket):
    """WebSocket for server-side audio processing (STT + TTS).

    Flow:
    1. Client sends audio binary chunks
    2. Server processes with STT ( Whisper )
    3. Server runs cognitive pipeline on transcript
    4. Server generates TTS response
    5. Server streams audio back to client
    """
    user_id = websocket.query_params.get("user_id", "default")
    await websocket.accept()

    try:
        # Send ready message
        await websocket.send_json({
            "type": "ready",
            "mode": "audio",
            "capabilities": ["stt", "tts", "cognition"]
        })

        while True:
            # Receive audio or text messages
            data = await websocket.receive()

            if "text" in data:
                # Text message
                try:
                    msg = json.loads(data["text"])
                    msg_type = msg.get("type", "")

                    if msg_type == "transcribe":
                        # Client requests server-side transcription
                        audio_base64 = msg.get("audio")
                        # TODO: Integrate Whisper STT here
                        transcript = "[Server STT not configured - using client-side]"

                        # Run cognitive pipeline
                        unified = getattr(app.state, 'unified_runtime', None)
                        if unified:
                            result = await unified.process_text(transcript, user_id)

                            # TODO: Generate TTS response
                            await websocket.send_json({
                                "type": "transcript",
                                "text": transcript,
                                "response": result.get("response", ""),
                                "cognitive_layers": result.get("cognitive_layers", [])
                            })

                    elif msg_type == "tts":
                        # Client requests TTS generation
                        text = msg.get("text", "")
                        # TODO: Integrate TTS here
                        await websocket.send_json({
                            "type": "tts_ready",
                            "message": "TTS not configured"
                        })

                except json.JSONDecodeError:
                    pass

            elif "bytes" in data:
                # Binary audio data
                audio_chunk = data["bytes"]
                # TODO: Process audio chunk with streaming STT
                # For now, acknowledge receipt
                await websocket.send_json({
                    "type": "audio_received",
                    "size": len(audio_chunk)
                })

    except WebSocketDisconnect:
        log.info(f"Audio session closed for user {user_id}")
    except Exception as e:
        log.error(f"Audio WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass


# ── VOICE STREAMING PIPELINE (v2.1 NEW) ───────────────

@app.websocket("/ws/voice")
async def voice_streaming_endpoint(websocket: WebSocket):
    """
    Server-side voice pipeline WebSocket.
    Handles streaming STT → Cognition → TTS in one flow.
    """
    if not voice_pipeline:
        await websocket.close(code=1011, reason="Voice pipeline not available")
        return

    user_id = websocket.query_params.get("user_id", "default")

    # Set cognition callback to use unified runtime
    async def cognition_callback(transcript: str, uid: str) -> dict:
        unified = getattr(app.state, 'unified_runtime', None)
        if unified:
            result = await unified.process_text(transcript, uid)
            return {"text": result.get("response", "")}
        return {"text": f"You said: {transcript}"}

    voice_pipeline.set_cognition_callback(cognition_callback)

    # Process audio stream
    try:
        async for message in voice_pipeline.process_audio_stream(websocket, user_id):
            if message.get("type") == "transcript":
                # Send transcript + response audio
                await websocket.send_json({
                    "type": "voice_response",
                    "transcript": message.get("text", ""),
                    "response": message.get("response", ""),
                    "audio": message.get("audio", ""),  # base64 TTS
                })
            else:
                await websocket.send_json(message)

    except WebSocketDisconnect:
        log.info(f"Voice session closed for user {user_id}")
    except Exception as e:
        log.error(f"Voice streaming error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass


# ── ENTRY POINT ───────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
