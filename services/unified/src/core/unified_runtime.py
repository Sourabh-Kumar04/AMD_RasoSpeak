"""
RasoSpeak AI OS — Unified Cognitive Runtime
============================================
The ONE intelligence runtime that orchestrates all cognitive services.

This service serves as the entry point that integrates:
- Voice processing
- World model (user understanding)
- Cognitive engine (thinking)
- Proactive intelligence (suggestions)
- Memory system (remembering)

All subsystems share state through the world model.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import structlog

from services.voice_service.src.core.voice_service import VoiceService, create_voice_service
from services.world_model.src.core.world_model import create_world_model, WorldModel
from services.memory_service.src.core.memory import MemoryService, SimpleEmbedder
from services.llm_gateway.src.core.gateway import create_gateway
from services.cognitive_engine.src.core.cognitive_engine import create_cognitive_engine, CognitiveEngine
from services.proactive.src.core.proactive_service import create_proactive_service, ProactiveService

logger = structlog.get_logger("rasospeak.unified")


# ──────────────────────────────────────────────────────────────────────────────
# Runtime Types
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Session:
    """User session with full state."""
    session_id: str
    user_id: str
    voice_session_id: Optional[str] = None
    context: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


class ConnectionManager:
    """WebSocket connection manager."""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self.user_sessions: dict[str, Session] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        session_id = str(uuid.uuid4())
        self.active_connections[session_id] = websocket
        self.user_sessions[session_id] = Session(
            session_id=session_id,
            user_id=user_id,
        )
        logger.info("client_connected", session_id=session_id, user_id=user_id)
        return session_id

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
        if session_id in self.user_sessions:
            del self.user_sessions[session_id]
        logger.info("client_disconnected", session_id=session_id)

    async def send(self, session_id: str, message: dict):
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_json(message)

    async def broadcast(self, message: dict):
        for connection in self.active_connections.values():
            await connection.send_json(message)


# ──────────────────────────────────────────────────────────────────────────────
# Unified Runtime
# ──────────────────────────────────────────────────────────────────────────────

class UnifiedRuntime:
    """
    The ONE cognitive runtime that orchestrates all services.

    This is NOT a chatbot - it's a persistent cognitive companion.
    """

    def __init__(
        self,
        voice_service: VoiceService,
        world_model: WorldModel,
        memory_service: MemoryService,
        cognitive_engine: CognitiveEngine,
        proactive_service: ProactiveService,
        llm_gateway: Any = None,
    ):
        self._voice = voice_service
        self._world_model = world_model
        self._memory = memory_service
        self._cognitive = cognitive_engine
        self._proactive = proactive_service
        self._llm = llm_gateway
        self._connections = ConnectionManager()

        # Session state
        self._sessions: dict[str, Session] = {}

        logger.info("unified_runtime_initialized")

    # ─────────────────────────────────────────────────────────────────────────
    # Text Interaction
    # ─────────────────────────────────────────────────────────────────────────

    async def process_text(
        self,
        text: str,
        user_id: str,
    ) -> dict:
        """Process text input through unified cognition."""
        logger.info("processing_text", user_id=user_id, text_length=len(text))

        # Get or create session
        session = await self._get_or_create_session(user_id)

        # Process through cognitive engine
        response = await self._cognitive.process_input(
            input_data=text,
            source="text",
            user_id=user_id,
        )

        # Update session context
        session.context["last_interaction"] = datetime.utcnow().isoformat()
        session.context["last_input"] = text
        session.context["last_response"] = response.output_text

        return {
            "response_id": response.response_id,
            "text": response.output_text,
            "confidence": response.confidence,
            "reasoning": response.reasoning,
            "state": response.state.value,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Voice Interaction
    # ─────────────────────────────────────────────────────────────────────────

    async def process_voice(
        self,
        audio_data: bytes,
        user_id: str,
    ) -> dict:
        """Process voice input through unified cognition."""
        # Get or create session
        session = await self._get_or_create_session(user_id)

        # Start voice session if not started
        if not session.voice_session_id:
            session.voice_session_id = await self._voice.conversation_manager.start_session(user_id)

        # Process audio
        transcript = await self._voice.process_audio(session.voice_session_id, audio_data)

        if transcript:
            # Process transcription through cognitive engine
            response = await self._cognitive.process_input(
                input_data=transcript.text,
                source="voice",
                user_id=user_id,
            )

            # Generate voice response
            audio_chunks = []
            async for chunk in self._voice.conversation_manager.speak(
                session.voice_session_id,
                response.output_text or "I understand.",
            ):
                audio_chunks.append(chunk.audio_data)

            return {
                "transcript": transcript.text,
                "response_text": response.output_text,
                "response_audio": b''.join(audio_chunks),
                "confidence": response.confidence,
            }

        return {"status": "listening"}

    async def speak(
        self,
        text: str,
        user_id: str,
    ) -> bytes:
        """Generate voice output."""
        # Get or create session
        session = await self._get_or_create_session(user_id)

        if not session.voice_session_id:
            session.voice_session_id = await self._voice.conversation_manager.start_session(user_id)

        # Generate speech
        audio_chunks = []
        async for chunk in self._voice.conversation_manager.speak(
            session.voice_session_id,
            text,
        ):
            audio_chunks.append(chunk.audio_data)

        return b''.join(audio_chunks)

    # ─────────────────────────────────────────────────────────────────────────
    # Memory Operations
    # ─────────────────────────────────────────────────────────────────────────

    async def retrieve_memory(
        self,
        user_id: str,
        query: str,
    ) -> dict:
        """Retrieve memories for query."""
        result = await self._memory.retrieve(
            user_id=user_id,
            query=query,
            limit=10,
        )

        return {
            "memories": [m.to_dict() for m in result.memories] if result else [],
            "context": result.context if result else "",
        }

    async def search_conversations(
        self,
        user_id: str,
        person: str = None,
        topic: str = None,
        days_back: int = 30,
    ) -> dict:
        """Search conversation history."""
        events = await self._world_model.get_conversation_history(
            user_id=user_id,
            person_name=person,
            topic=topic,
            days_back=days_back,
        )

        return {
            "events": events,
            "count": len(events),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # World Model Operations
    # ─────────────────────────────────────────────────────────────────────────

    async def get_user_context(self, user_id: str) -> dict:
        """Get comprehensive user context."""
        return await self._world_model.get_user_context(user_id)

    async def add_entity(
        self,
        user_id: str,
        entity_type: str,
        name: str,
        properties: dict = None,
    ) -> dict:
        """Add entity to world model."""
        from services.world_model.src.core.world_model import EntityType

        entity_type_enum = EntityType(entity_type)
        entity = await self._world_model.add_entity(
            user_id=user_id,
            entity_type=entity_enum,
            name=name,
            properties=properties,
        )

        return {"entity_id": entity.entity_id, "name": entity.name}

    async def relate_entities(
        self,
        user_id: str,
        source: str,
        target: str,
        relationship: str,
    ) -> dict:
        """Create relationship between entities."""
        from services.world_model.src.core.world_model import RelationshipType

        rel_type = RelationshipType(relationship)
        relationship = await self._world_model.relate_entities(source, target, rel_type)

        return {"relationship_id": relationship.relationship_id} if relationship else {}

    # ─────────────────────────────────────────────────────────────────────────
    # Proactive Operations
    # ─────────────────────────────────────────────────────────────────────────

    async def get_suggestions(self, user_id: str) -> list[dict]:
        """Get proactive suggestions."""
        suggestions = await self._proactive.get_suggestions(user_id)

        return [
            {
                "suggestion_id": s.suggestion_id,
                "type": s.suggestion_type.value,
                "priority": s.priority.value,
                "title": s.title,
                "description": s.description,
                "confidence": s.confidence,
                "action": s.action_suggested,
            }
            for s in suggestions
        ]

    async def dismiss_suggestion(self, user_id: str, suggestion_id: str):
        """Dismiss a suggestion."""
        await self._proactive.dismiss_suggestion(user_id, suggestion_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Goal/Project Operations
    # ─────────────────────────────────────────────────────────────────────────

    async def create_goal(
        self,
        user_id: str,
        title: str,
        description: str,
        deadline: datetime = None,
    ) -> dict:
        """Create a new goal."""
        goal = await self._world_model.user_model.create_goal(
            user_id=user_id,
            title=title,
            description=description,
            deadline=deadline,
        )

        return {
            "goal_id": goal.goal_id,
            "title": goal.title,
            "status": goal.status,
        }

    async def get_goals(self, user_id: str, status: str = None) -> list[dict]:
        """Get user goals."""
        goals = await self._world_model.user_model.get_user_goals(user_id, status=status)

        return [
            {
                "goal_id": g.goal_id,
                "title": g.title,
                "description": g.description,
                "status": g.status,
                "progress": g.progress,
                "deadline": g.deadline.isoformat() if g.deadline else None,
            }
            for g in goals
        ]

    async def create_project(
        self,
        user_id: str,
        name: str,
        description: str,
    ) -> dict:
        """Create a new project."""
        project = await self._world_model.projects.create_project(
            user_id=user_id,
            name=name,
            description=description,
        )

        return {
            "project_id": project.project_id,
            "name": project.name,
            "status": project.status,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Session Management
    # ─────────────────────────────────────────────────────────────────────────

    async def _get_or_create_session(self, user_id: str) -> Session:
        """Get or create user session."""
        for session in self._sessions.values():
            if session.user_id == user_id:
                return session

        # Create new session
        session = Session(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
        )
        self._sessions[session.session_id] = session

        logger.info("session_created", user_id=user_id, session_id=session.session_id)
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        return self._sessions.get(session_id)

    async def clear_session(self, user_id: str):
        """Clear user session."""
        for session_id, session in list(self._sessions.items()):
            if session.user_id == user_id:
                del self._sessions[session_id]

        logger.info("session_cleared", user_id=user_id)


# ──────────────────────────────────────────────────────────────────────────────
# FastAPI Application
# ──────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan."""
    logger.info("unified_runtime_starting")

    # Initialize services
    voice_service = create_voice_service(stt_provider="openai", tts_provider="openai")
    world_model = create_world_model()
    memory_service = MemoryService(embedder=SimpleEmbedder())
    cognitive_engine = create_cognitive_engine(
        world_model=world_model,
        memory_service=memory_service,
        llm_gateway=None,
        voice_service=voice_service,
    )
    proactive_service = create_proactive_service(world_model, memory_service)

    # Create unified runtime
    runtime = UnifiedRuntime(
        voice_service=voice_service,
        world_model=world_model,
        memory_service=memory_service,
        cognitive_engine=cognitive_engine,
        proactive_service=proactive_service,
    )

    app.state.runtime = runtime
    app.state.voice = voice_service
    app.state.world_model = world_model

    logger.info("unified_runtime_ready")
    yield

    logger.info("unified_runtime_shutting_down")


# Create FastAPI app
app = FastAPI(
    title="RasoSpeak Unified Cognitive Runtime",
    description="The ONE cognitive intelligence for audio-first interaction",
    version="4.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────────────────────
# API Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy", "service": "unified-runtime", "version": "4.0.0"}


@app.get("/ready")
async def ready():
    """Readiness check."""
    return {"ready": True}


# ──────────────────────────────────────────────────────────────────────────────
# Text Interaction
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(
    text: str,
    user_id: str = "default",
):
    """Process text chat."""
    runtime: UnifiedRuntime = app.state.runtime
    result = await runtime.process_text(text, user_id)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Voice Interaction
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/voice/transcribe")
async def transcribe(
    audio: bytes,
    user_id: str = "default",
):
    """Transcribe audio."""
    runtime: UnifiedRuntime = app.state.runtime
    result = await runtime.process_voice(audio, user_id)
    return result


@app.post("/voice/speak")
async def speak(
    text: str,
    user_id: str = "default",
):
    """Generate speech."""
    runtime: UnifiedRuntime = app.state.runtime
    audio = await runtime.speak(text, user_id)
    return {"audio": base64.b64encode(audio).decode()}


# ──────────────────────────────────────────────────────────────────────────────
# Memory Operations
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/memory/search")
async def search_memory(
    query: str,
    user_id: str = "default",
    limit: int = 10,
):
    """Search memories."""
    runtime: UnifiedRuntime = app.state.runtime
    result = await runtime.retrieve_memory(user_id, query)
    return result


@app.get("/conversations/search")
async def search_conversations(
    user_id: str,
    person: str = None,
    topic: str = None,
    days_back: int = 30,
):
    """Search conversation history."""
    runtime: UnifiedRuntime = app.state.runtime
    result = await runtime.search_conversations(user_id, person, topic, days_back)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# World Model Operations
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/user/context")
async def get_user_context(
    user_id: str = "default",
):
    """Get user context."""
    runtime: UnifiedRuntime = app.state.runtime
    return await runtime.get_user_context(user_id)


@app.post("/world/entity")
async def add_entity(
    user_id: str,
    entity_type: str,
    name: str,
    properties: dict = None,
):
    """Add entity to world model."""
    runtime: UnifiedRuntime = app.state.runtime
    return await runtime.add_entity(user_id, entity_type, name, properties)


@app.post("/world/relate")
async def relate_entities(
    user_id: str,
    source: str,
    target: str,
    relationship: str,
):
    """Create entity relationship."""
    runtime: UnifiedRuntime = app.state.runtime
    return await runtime.relate_entities(user_id, source, target, relationship)


# ──────────────────────────────────────────────────────────────────────────────
# Goals & Projects
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/goals")
async def create_goal(
    user_id: str,
    title: str,
    description: str,
    deadline: str = None,
):
    """Create a goal."""
    runtime: UnifiedRuntime = app.state.runtime
    from datetime import datetime
    deadline_dt = datetime.fromisoformat(deadline) if deadline else None
    return await runtime.create_goal(user_id, title, description, deadline_dt)


@app.get("/goals")
async def get_goals(
    user_id: str,
    status: str = None,
):
    """Get user goals."""
    runtime: UnifiedRuntime = app.state.runtime
    return await runtime.get_goals(user_id, status)


@app.post("/projects")
async def create_project(
    user_id: str,
    name: str,
    description: str,
):
    """Create a project."""
    runtime: UnifiedRuntime = app.state.runtime
    return await runtime.create_project(user_id, name, description)


# ──────────────────────────────────────────────────────────────────────────────
# Proactive Suggestions
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/suggestions")
async def get_suggestions(
    user_id: str = "default",
):
    """Get proactive suggestions."""
    runtime: UnifiedRuntime = app.state.runtime
    return await runtime.get_suggestions(user_id)


@app.delete("/suggestions/{suggestion_id}")
async def dismiss_suggestion(
    suggestion_id: str,
    user_id: str = "default",
):
    """Dismiss a suggestion."""
    runtime: UnifiedRuntime = app.state.runtime
    await runtime.dismiss_suggestion(user_id, suggestion_id)
    return {"status": "dismissed"}


# ──────────────────────────────────────────────────────────────────────────────
# WebSocket for Real-time Voice
# ──────────────────────────────────────────────────────────────────────────────

@app.websocket("/ws/voice")
async def websocket_voice(websocket: WebSocket, user_id: str = "default"):
    """WebSocket for real-time voice interaction."""
    runtime: UnifiedRuntime = app.state.runtime

    session_id = await runtime._connections.connect(websocket, user_id)
    voice_session_id = await runtime._voice.conversation_manager.start_session(user_id)

    try:
        # Send ready message
        await websocket.send_json({
            "type": "ready",
            "session_id": session_id,
        })

        # Handle incoming messages
        while True:
            message = await websocket.receive_json()

            if message["type"] == "audio":
                # Process audio
                audio_data = base64.b64decode(message["data"])
                result = await runtime.process_voice(audio_data, user_id)

                if "transcript" in result:
                    await websocket.send_json({
                        "type": "transcript",
                        "text": result["transcript"],
                    })

                    if result.get("response_text"):
                        await websocket.send_json({
                            "type": "response",
                            "text": result["response_text"],
                            "confidence": result["confidence"],
                        })

            elif message["type"] == "text":
                # Process text
                result = await runtime.process_text(message["text"], user_id)
                await websocket.send_json({
                    "type": "response",
                    "text": result["text"],
                    "confidence": result["confidence"],
                })

            elif message["type"] == "interrupt":
                # Handle interruption
                await runtime._voice.conversation_manager.interrupt(voice_session_id)
                await websocket.send_json({"type": "interrupted"})

    except WebSocketDisconnect:
        runtime._connections.disconnect(session_id)
        await runtime._voice.conversation_manager.end_session(voice_session_id)
    except Exception as e:
        logger.error("websocket_error", error=str(e))
        await websocket.send_json({
            "type": "error",
            "message": str(e),
        })


# ──────────────────────────────────────────────────────────────────────────────
# Main Entry Point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    """Start the unified runtime server."""
    uvicorn.run(
        "services.unified.src.main:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()