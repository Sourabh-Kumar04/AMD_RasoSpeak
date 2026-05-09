"""
RasoSpeak v2 — FastAPI Backend
AMD Developer Cloud | ROCm | vLLM | Whisper

Entry point for the multi-agent speech coaching system.
Handles WebSocket connections for real-time audio streaming.
"""

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agents.transcription_agent import TranscriptionAgent
from agents.scoring_agent import ScoringAgent
from agents.coaching_agent import CoachingAgent
from agents.segmentation_agent import SegmentationAgent
from agents.session_memory_agent import SessionMemoryAgent
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

    agents["transcription"] = TranscriptionAgent()
    await agents["transcription"].initialize()
    log.info("✅ TranscriptionAgent ready (Whisper Large v3 on ROCm)")

    agents["scoring"] = ScoringAgent()
    await agents["scoring"].initialize()
    log.info("✅ ScoringAgent ready (Qwen2.5-7B on vLLM)")

    agents["coaching"] = CoachingAgent()
    await agents["coaching"].initialize()
    log.info("✅ CoachingAgent ready (Qwen2.5-7B on vLLM)")

    agents["segmentation"] = SegmentationAgent()
    await agents["segmentation"].initialize()
    log.info("✅ SegmentationAgent ready (Qwen2.5-3B on vLLM)")

    agents["memory"] = SessionMemoryAgent()
    await agents["memory"].initialize()
    log.info("✅ SessionMemoryAgent ready")

    log.info("🎙 All agents online — RasoSpeak v2 ready")
    yield

    # Cleanup
    for name, agent in agents.items():
        if hasattr(agent, "shutdown"):
            await agent.shutdown()
    log.info("👋 RasoSpeak v2 shut down cleanly")


# ── APP ────────────────────────────────────────────────
app = FastAPI(
    title="RasoSpeak v2",
    description="Agentic AI Speech Coach — AMD Developer Cloud",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the frontend
app.mount("/static", StaticFiles(directory=".."), name="static")


# ── REST ENDPOINTS ─────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agents": list(agents.keys()),
        "amd_device": settings.AMD_DEVICE,
        "models": {
            "transcription": settings.WHISPER_MODEL,
            "scoring":       settings.SCORING_MODEL,
            "coaching":      settings.COACHING_MODEL,
            "segmentation":  settings.SEGMENTATION_MODEL,
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
        return {"error": "Session not found"}, 404
    return session


@app.get("/sessions/{session_id}/insights")
async def get_session_insights(session_id: str):
    """Get AI-generated insights from a completed session."""
    session = await agents["memory"].get_session(session_id)
    if not session:
        return {"error": "Session not found"}, 404
    insights = await agents["coaching"].generate_session_insights(session)
    return insights


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
