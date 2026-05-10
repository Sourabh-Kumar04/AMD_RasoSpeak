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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
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
from agents.partner_agent import PartnerAgent
from agents.wake_word_agent import WakeWordAgent
from agents.document_agent import DocumentAgent
from agents.notification_agent import NotificationAgent
from models.schemas import (
    WSMessage, WSMessageType,
    SegmentRequest, AudioChunk,
    SessionConfig
)
from config.settings import settings

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
    log.info("🚀 RasoSpeak v2 starting — loading agents on AMD MI300X...")

    # Agent registry with initialization logic
    agent_init_order = [
        # Core first - Shared Memory must be first!
        ("shared_memory", SharedMemoryAgent, "UNIFIED BRAIN"),
        # Core coaching
        ("transcription", TranscriptionAgent, "Whisper Large v3 on ROCm"),
        ("scoring", ScoringAgent, "Qwen2.5-7B on vLLM"),
        ("coaching", CoachingAgent, "Qwen2.5-7B on vLLM"),
        ("segmentation", SegmentationAgent, "Qwen2.5-3B on vLLM"),
        ("memory", SessionMemoryAgent, "Session storage"),
        # Partner agents
        ("qa", QAAgent, "OpenAI/Anthropic/Google/xAI/Qwen"),
        ("search", SearchAgent, "Tavily/DuckDuckGo"),
        ("recording", RecordingAgent, "Audio recording"),
        ("analytics", AnalyticsAgent, "Performance analytics"),
        ("partner", PartnerAgent, "Your AI companion"),
        ("wake_word", WakeWordAgent, "'Hey Raso' detection"),
        ("document", DocumentAgent, "PDF/URL import"),
        ("notification", NotificationAgent, "Phone notifications"),
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

    # Set shared memory references for agents that need it
    if agents.get("shared_memory"):
        for agent_name in ["qa", "search", "recording", "analytics", "partner", "document"]:
            if agents.get(agent_name):
                try:
                    agents[agent_name].set_shared_memory(agents["shared_memory"])
                except Exception as e:
                    log.warning(f"⚠️ {agent_name} shared_memory setup failed: {e}")

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
    description="A multi-agent AI system with wake word activation, perfect memory, document import, phone notifications, and real-time speech coaching. Powered by AMD MI300X.",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS - use ALLOWED_ORIGINS from settings (default "*" for dev, can restrict for prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(",") if settings.ALLOWED_ORIGINS != "*" else ["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

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
@app.get("/index.html")
async def index_html(): return FileResponse("index.html")
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


# ── ROOT ROUTE ─────────────────────────────────────────
@app.get("/")
async def root():
    return FileResponse("index.html")


# ── REST ENDPOINTS ─────────────────────────────────────
@app.get("/health")
async def health():
    # Check which agents are working
    agent_status = {}
    for name, agent in agents.items():
        try:
            # Try to get status from each agent
            if hasattr(agent, 'is_listening'):
                agent_status[name] = "ready" if not agent.is_listening() else "listening"
            elif hasattr(agent, 'is_continuous_mode'):
                agent_status[name] = "ready" if not agent.is_continuous_mode() else "active"
            else:
                agent_status[name] = "ready"
        except Exception:
            agent_status[name] = "error"

    return {
        "status": "ok",
        "agents": agent_status,
        "total_agents": len(agents),
        "amd_device": settings.AMD_DEVICE,
        "models": {
            "transcription": settings.WHISPER_MODEL,
            "scoring":       settings.SCORING_MODEL,
            "coaching":      settings.COACHING_MODEL,
            "segmentation":  settings.SEGMENTATION_MODEL,
            "qa":            settings.QA_MODEL,
        },
        "providers": {
            "openai": bool(settings.OPENAI_API_KEY),
            "anthropic": bool(settings.ANTHROPIC_API_KEY),
            "google": bool(settings.GOOGLE_API_KEY),
            "xai": bool(settings.XAI_API_KEY),
        },
        "features": {
            "wake_word": True,
            "document_import": True,
            "notifications": True,
            "partner_mode": True,
            "web_search": True,
        }
    }


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
    provider: str | None = Field(default=None, pattern="^(openai|anthropic|google|xai|qwen_local)$")
    context: str | None = Field(default=None, max_length=10_000)
    stream_to_earpiece: bool = True


@app.post("/qa")
async def ask_question(req: QARequest, session_id: str = None):
    """
    Ask a question to AI and get answer (streams to earpiece).
    Connect to OpenAI GPT, Anthropic Claude, Google Gemini, xAI Grok, or local Qwen.
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
    return {
        "available": list(agents["qa"]._clients.keys()),
        "default": agents["qa"]._default_provider,
    }


# ══════════════════════════════════════════════════════
# NEW: SEARCH ENDPOINTS — Web search for real-time info
# ══════════════════════════════════════════════════════

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    num_results: int = Field(default=5, ge=1, le=20)
    include_summary: bool = True


@app.post("/search")
async def web_search(req: SearchRequest):
    """
    Search the web for real-time information.
    Uses Tavily (if API key), SerpAPI, Brave Search, or DuckDuckGo (fallback).
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
# PARTNER AGENT — Your AI Partner / Secondary Brain
# ══════════════════════════════════════════════════════

class PartnerAskRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4_000)
    provider: str | None


class ReminderRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    remind_at: str | None  # ISO timestamp or "in 1 hour"


@app.post("/partner/start")
async def start_partner_mode(session_id: str = None):
    """Start continuous partner mode - partner is always listening."""
    return await agents["partner"].start_continuous_mode(session_id)


@app.post("/partner/stop")
async def stop_partner_mode():
    """Stop continuous partner mode."""
    return await agents["partner"].stop_continuous_mode()


@app.get("/partner/status")
async def get_partner_status():
    """Get partner mode status."""
    current_provider = await agents["partner"].get_current_provider()

    # Get preference info
    prefs = await agents["shared_memory"].get_user_preferences()
    default_provider = prefs.get("preferred_ai_provider", "qwen_local")
    temp_provider = prefs.get("temporary_ai_provider")

    return {
        "continuous_mode": agents["partner"].is_continuous_mode(),
        "current_provider": current_provider,
        "default_provider": default_provider,
        "temporary_provider": temp_provider,
    }


@app.post("/partner/provider")
async def set_partner_provider(provider: str, temporary: bool = False):
    """
    Set the AI provider for the partner.

    Examples:
    - POST /partner/provider?provider=openai (permanent)
    - POST /partner/provider?provider=google&temporary=true (one question)
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


@app.post("/partner/ask")
async def ask_partner(req: PartnerAskRequest):
    """
    Ask your AI partner anything.
    Uses past conversations + web search + knowledge.
    """
    return await agents["partner"].ask_partner(req.message, req.provider)


@app.post("/partner/listen")
async def partner_listen(user_input: str, audio_b64: str = None):
    """
    In continuous mode, let partner listen and remember.
    """
    return await agents["partner"].listen_and_remember(user_input, audio_b64)


@app.get("/partner/query")
async def query_past_conversations(query: str):
    """
    Query past conversations.
    Example: "What did I say about AI?" "When did I talk about X?"
    """
    return await agents["partner"].query_past(query)


@app.post("/partner/reminder")
async def set_partner_reminder(req: ReminderRequest):
    """Set a reminder."""
    return await agents["partner"].set_reminder(req.message, req.remind_at)


@app.get("/partner/reminders")
async def get_partner_reminders():
    """Get all reminders."""
    return await agents["partner"].get_reminders()


@app.delete("/partner/reminder/{reminder_id}")
async def delete_partner_reminder(reminder_id: str):
    """Delete a reminder."""
    return await agents["partner"].delete_reminder(reminder_id)


@app.get("/partner/summarize")
async def summarize_partner_conversations(days: int = 7):
    """Summarize conversations over past N days."""
    return await agents["partner"].summarize_conversations(days)


# ══════════════════════════════════════════════════════
# WAKE WORD — "Hey Raso"
# ══════════════════════════════════════════════════════

class WakeAudioRequest(BaseModel):
    audio_b64: str
    transcript: str = None


@app.post("/wake/start")
async def start_wake_listening():
    """Start listening for 'Hey Raso' wake word."""
    return await agents["wake_word"].start_listening()


@app.post("/wake/stop")
async def stop_wake_listening():
    """Stop wake word listening."""
    return await agents["wake_word"].stop_listening()


@app.get("/wake/status")
async def get_wake_status():
    """Get wake word listening status."""
    return {
        "listening": agents["wake_word"].is_listening(),
        "wake_word": "Hey Raso",
    }


@app.post("/wake/process")
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
    return await agents["documents"].import_text(
        content=req.content,
        title=req.title,
        tags=req.tags,
        category=req.category,
    )


@app.post("/documents/url")
async def import_url_document(req: ImportURLRequest):
    """Import content from a URL."""
    return await agents["documents"].import_url(
        url=req.url,
        title=req.title,
        tags=req.tags,
    )


@app.post("/documents/snippet")
async def import_snippet(req: ImportSnippetRequest):
    """Import a quick snippet/clipboard."""
    return await agents["documents"].import_snippet(
        content=req.content,
        label=req.label,
    )


@app.get("/documents")
async def list_documents(category: str = None, limit: int = 20):
    """List all imported documents."""
    return await agents["documents"].list_documents(category, limit)


@app.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    """Get a specific document."""
    return await agents["documents"].get_document(doc_id)


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document."""
    return await agents["documents"].delete_document(doc_id)


@app.get("/documents/search")
async def search_documents(query: str, limit: int = 10):
    """Search within imported documents."""
    return await agents["documents"].search_documents(query, limit)


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
                    "message": "Session initialized — agents ready on AMD MI300X"
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
                session = await agents["memory"].get_session(session_id)
                script_context = None
                if session:
                    # Include current script chunks as context
                    chunks = session.get("chunk_records", {})
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
                result = await agents["partner"].start_continuous_mode(session_id)
                await send(websocket, WSMessageType.PARTNER_READY, {
                    "status": "active",
                    "session_id": session_id,
                    "message": result.get("message", "Partner mode started"),
                })
                log.info(f"🎧 Partner mode started: {session_id}")

            # ── PARTNER_STOP ────────────────────────────────
            elif msg.type == WSMessageType.PARTNER_STOP:
                result = await agents["partner"].stop_continuous_mode()
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
                result = await agents["partner"].ask_partner(
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
                await agents["partner"].listen_and_remember(
                    user_input=message,
                    timestamp=datetime.utcnow().isoformat()
                )

                log.info(f"✅ Partner response sent: {result.get('answer', '')[:50]}...")

            # ── WAKE_DETECTED ───────────────────────────────
            elif msg.type == WSMessageType.WAKE_DETECTED:
                transcript = msg.data.get("transcript", "")
                command = msg.data.get("command", "")

                log.info(f"🔔 Wake word detected: {transcript[:50]}...")

                # Activate partner
                result = await agents["partner"].start_continuous_mode(session_id)

                # If there's a command after wake word, process it
                if command:
                    await send(websocket, WSMessageType.PARTNER_READY, {
                        "status": "active",
                        "command": command,
                        "message": "I'm here! Processing your request...",
                    })

                    # Process the command
                    result = await agents["partner"].ask_partner(command)
                    await send(websocket, WSMessageType.PARTNER_RESPONSE, {
                        "response": result.get("answer", ""),
                        "command": command,
                    })

            # ── IMPORT_DOCUMENT ────────────────────────────
            elif msg.type == WSMessageType.IMPORT_DOCUMENT:
                content = msg.data.get("content", "")
                title = msg.data.get("title", "")
                doc_type = msg.data.get("type", "note")  # note, url, snippet

                log.info(f"📄 Import document: {title or 'Untitled'}")

                if doc_type == "url":
                    result = await agents["documents"].import_url(content)
                elif doc_type == "snippet":
                    result = await agents["documents"].import_snippet(content, title)
                else:
                    result = await agents["documents"].import_text(content, title)

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
    All inference on AMD MI300X via ROCm.
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


# ── ENTRY POINT ────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
