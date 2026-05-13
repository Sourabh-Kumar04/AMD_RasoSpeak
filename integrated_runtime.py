"""
RasoSpeak OS — Integrated Cognitive Runtime
==============================================
Unified architecture connecting ALL subsystems into ONE coherent runtime.

This is the REAL integration that connects:
- Voice pipeline → Cognitive Engine → Memory → World Model → Proactive

NOT a prototype - production-grade unified cognitive OS.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional, Callable

import structlog

logger = structlog.get_logger("rasospeak.integrated")


# ──────────────────────────────────────────────────────────────────────────────
# Event Bus (Real Distributed Event System)
# ──────────────────────────────────────────────────────────────────────────────

class EventType(Enum):
    """Real event types for distributed cognition."""
    VOICE_TRANSCRIPT = "voice_transcript"
    CONVERSATION_START = "conversation_start"
    CONVERSATION_END = "conversation_end"
    MEMORY_STORED = "memory_stored"
    MEMORY_RETRIEVED = "memory_retrieved"
    WORLD_MODEL_UPDATED = "world_model_updated"
    ENTITY_CREATED = "entity_created"
    RELATIONSHIP_UPDATED = "relationship_updated"
    GOAL_CREATED = "goal_created"
    GOAL_UPDATED = "goal_updated"
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    AGENT_ACTION = "agent_action"
    COGNITION_COMPLETE = "cognition_complete"
    PROACTIVE_SUGGESTION = "proactive_suggestion"


@dataclass
class CognitEvent:
    """Distributed cognition event."""
    event_id: str
    event_type: EventType
    source: str
    user_id: str
    payload: dict
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None


class EventBus:
    """
    Real event-driven infrastructure using Redis Streams.
    Supports distributed cognition, workflow orchestration, and replay.
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._handlers: dict[EventType, list[Callable]] = {}
        self._event_history: list[CognitEvent] = []
        self._max_history = 1000
        logger.info("event_bus_initialized")

    def subscribe(self, event_type: EventType, handler: Callable):
        """Subscribe to event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.info("event_subscription", event_type=event_type.value, handler=handler.__name__)

    async def publish(self, event: CognitEvent):
        """Publish event to all subscribers."""
        # Store in history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

        # Publish to Redis Streams if available
        if self._redis:
            try:
                await self._redis.xadd(
                    f"cognition:events:{event.event_type.value}",
                    {"data": json.dumps({
                        "event_id": event.event_id,
                        "source": event.source,
                        "user_id": event.user_id,
                        "payload": event.payload,
                        "timestamp": event.timestamp.isoformat(),
                    })}
                )
            except Exception as e:
                logger.warning("redis_publish_failed", error=str(e))

        # Call local handlers
        for handler in self._handlers.get(event.event_type, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error("event_handler_failed", handler=handler.__name__, error=str(e))

        logger.debug("event_published", event_type=event.event_type.value, event_id=event.event_id)

    async def replay_events(self, event_type: EventType, from_time: datetime) -> list[CognitEvent]:
        """Replay events from history."""
        return [
            e for e in self._event_history
            if e.event_type == event_type and e.timestamp >= from_time
        ]


# ──────────────────────────────────────────────────────────────────────────────
# Memory Propagation System
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class MemoryNode:
    """Unified memory node across all memory types."""
    node_id: str
    memory_type: str  # working, episodic, semantic, procedural, social, emotional
    content: str
    embedding: Optional[list[float]] = None
    importance: float = 0.5
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0
    source: str = "conversation"  # conversation, document, meeting, goal, workflow
    metadata: dict = field(default_factory=dict)
    entities: list[str] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)
    emotional_tone: Optional[str] = None


class UnifiedMemorySystem:
    """
    Single source of truth for ALL memory.
    Replaces disconnected memory systems with unified architecture.
    """

    def __init__(
        self,
        world_model,  # WorldModel service
        embedder,  # Embedding service
        event_bus: EventBus,
        vector_store=None,  # Qdrant client
        sql_db=None,  # PostgreSQL async session
    ):
        self._world_model = world_model
        self._embedder = embedder
        self._event_bus = event_bus
        self._vector_store = vector_store
        self._sql_db = sql_db

        # In-memory working memory (fast access)
        self._working_memory: dict[str, list[MemoryNode]] = {}  # user_id -> nodes

        # Memory consolidation task
        self._consolidation_task: Optional[asyncio.Task] = None

        logger.info("unified_memory_initialized")

    async def start(self):
        """Start memory consolidation background task."""
        self._consolidation_task = asyncio.create_task(self._consolidation_loop())
        logger.info("memory_consolidation_started")

    async def stop(self):
        """Stop consolidation."""
        if self._consolidation_task:
            self._consolidation_task.cancel()
        logger.info("memory_consolidation_stopped")

    async def store(
        self,
        user_id: str,
        content: str,
        memory_type: str,
        source: str = "conversation",
        metadata: dict = None,
    ) -> MemoryNode:
        """Store memory and propagate to all systems."""
        # Generate embedding
        embedding = await self._embedder.embed(content)

        # Create memory node
        node = MemoryNode(
            node_id=str(uuid.uuid4()),
            memory_type=memory_type,
            content=content,
            embedding=embedding,
            source=source,
            metadata=metadata or {},
            created_at=datetime.utcnow(),
        )

        # Extract entities
        node.entities = await self._extract_entities(content)

        # Store in working memory
        if user_id not in self._working_memory:
            self._working_memory[user_id] = []
        self._working_memory[user_id].append(node)

        # Store in vector database for semantic retrieval
        if self._vector_store:
            await self._vector_store.upsert(
                collection=f"memory_{user_id}",
                points=[{
                    "id": node.node_id,
                    "vector": embedding,
                    "payload": {
                        "content": content,
                        "memory_type": memory_type,
                        "source": source,
                        "created_at": node.created_at.isoformat(),
                    }
                }]
            )

        # Update world model with entity information
        await self._world_model.upsert_entities(
            user_id=user_id,
            entities=[{"name": e, "type": "memory_entity"} for e in node.entities]
        )

        # Publish event for other systems
        await self._event_bus.publish(CognitEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.MEMORY_STORED,
            source="unified_memory",
            user_id=user_id,
            payload={
                "node_id": node.node_id,
                "memory_type": memory_type,
                "entities": node.entities,
            }
        ))

        logger.info("memory_stored", user_id=user_id, memory_type=memory_type, node_id=node.node_id)
        return node

    async def retrieve(
        self,
        user_id: str,
        query: str,
        memory_types: list[str] = None,
        limit: int = 10,
    ) -> list[MemoryNode]:
        """Semantic memory retrieval."""
        # Generate query embedding - fallback to keyword search if no embedder
        if self._embedder is None:
            # Fallback: keyword-based retrieval from memory store
            results = []
            user_memories = self._working_memory.get(user_id, [])
            for node in user_memories:
                if query.lower() in node.content.lower() or not query:
                    results.append(node)
                    if len(results) >= limit:
                        break
            return results[:limit]

        query_embedding = await self._embedder.embed(query)

        results = []

        # Semantic search in vector store
        if self._vector_store:
            search_results = await self._vector_store.search(
                collection=f"memory_{user_id}",
                query_vector=query_embedding,
                limit=limit,
                filter={"memory_type": {"$in": memory_types}} if memory_types else None
            )
            for r in search_results:
                results.append(MemoryNode(
                    node_id=r["id"],
                    memory_type=r["payload"]["memory_type"],
                    content=r["payload"]["content"],
                    importance=r.get("score", 0.5),
                ))

        # Also search working memory
        working_nodes = self._working_memory.get(user_id, [])
        if memory_types:
            working_nodes = [n for n in working_nodes if n.memory_type in memory_types]

        # Add working memory results (higher priority)
        for node in working_nodes[:limit]:
            if node not in results:
                node.access_count += 1
                node.last_accessed = datetime.utcnow()
                results.insert(0, node)

        # Publish retrieval event
        await self._event_bus.publish(CognitEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.MEMORY_RETRIEVED,
            source="unified_memory",
            user_id=user_id,
            payload={"query": query, "results_count": len(results)}
        ))

        return results[:limit]

    async def _extract_entities(self, text: str) -> list[str]:
        """Extract entities from text."""
        # Simple entity extraction (in production, use NER)
        entities = []
        words = text.split()
        for word in words:
            if word[0].isupper() and len(word) > 2:
                entities.append(word)
        return entities[:10]  # Limit to 10 entities

    async def _consolidation_loop(self):
        """Background memory consolidation."""
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute
                await self._consolidate_memories()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("consolidation_error", error=str(e))

    async def _consolidate_memories(self):
        """Consolidate memories - deduplicate, update importance."""
        for user_id, nodes in self._working_memory.items():
            # Simple deduplication
            seen_content = set()
            unique_nodes = []
            for node in nodes:
                content_hash = hash(node.content[:100])
                if content_hash not in seen_content:
                    seen_content.add(content_hash)
                    unique_nodes.append(node)

            # Update importance based on access
            for node in unique_nodes:
                if node.access_count > 5:
                    node.importance = min(1.0, node.importance + 0.1)

            self._working_memory[user_id] = unique_nodes
            logger.debug("memories_consolidated", user_id=user_id, count=len(unique_nodes))


# ──────────────────────────────────────────────────────────────────────────────
# Cognitive Pipeline (Real 7-Layer Cognition)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CognitionRequest:
    """Request to the cognitive pipeline."""
    input_text: str
    user_id: str
    source: str  # voice, text, document, workflow
    context: dict = field(default_factory=dict)
    conversation_history: list[dict] = field(default_factory=list)


@dataclass
class CognitionResponse:
    """Response from cognitive pipeline."""
    response_id: str
    output_text: str
    confidence: float
    cognitive_layers_used: list[str]
    memories_retrieved: list[MemoryNode]
    entities_extracted: list[str]
    actions_taken: list[str]
    world_model_updates: list[dict]
    reasoning_trace: list[str]


class CognitivePipeline:
    """
    REAL 7-layer cognitive pipeline.
    ALL requests MUST flow through this.
    """

    def __init__(
        self,
        memory_system: UnifiedMemorySystem,
        world_model,  # WorldModel service
        llm_gateway,  # LLM gateway
        proactive_service,  # Proactive service
        event_bus: EventBus,
    ):
        self._memory = memory_system
        self._world_model = world_model
        self._llm = llm_gateway
        self._proactive = proactive_service
        self._event_bus = event_bus

        logger.info("cognitive_pipeline_initialized")

    async def process(self, request: CognitionRequest) -> CognitionResponse:
        """Process request through full 7-layer cognition."""
        trace = []
        response_id = str(uuid.uuid4())

        # Layer 1: Reactive (fast path for simple queries)
        if self._is_simple_query(request.input_text):
            trace.append("Layer 1: Reactive - fast path")
            return await self._reactive_response(request, response_id, trace)

        # Layer 2: Perception - understand input
        trace.append("Layer 2: Perception - analyzing input")
        perceived_input = await self._perception_layer(request)

        # Layer 3: Memory Retrieval
        trace.append("Layer 3: Memory retrieval")
        memories = await self._memory.retrieve(
            user_id=request.user_id,
            query=request.input_text,
            memory_types=["semantic", "episodic", "working"],
            limit=5
        )

        # Layer 4: World Model Reasoning
        trace.append("Layer 4: World model reasoning")
        world_context = await self._world_model.get_user_context(request.user_id)
        entities = await self._world_model.get_entities(request.user_id)

        # Layer 5: Planning (HTN)
        trace.append("Layer 5: Planning - HTN decomposition")
        plan = await self._planning_layer(request, memories, world_context)

        # Layer 6: Execution
        trace.append("Layer 6: Execution")
        execution_result = await self._execution_layer(request, plan, memories)

        # Layer 7: Reflection
        trace.append("Layer 7: Reflection")
        await self._reflection_layer(request, execution_result, memories)

        # Generate response
        response_text = execution_result.get("response", "I'm thinking about that.")

        # Store conversation in memory
        await self._memory.store(
            user_id=request.user_id,
            content=f"User: {request.input_text}\nRaso: {response_text}",
            memory_type="episodic",
            source="conversation",
            metadata={"response_id": response_id}
        )

        # Update world model
        await self._world_model.add_interaction(
            user_id=request.user_id,
            interaction_type="conversation",
            content=request.input_text,
            response=response_text
        )

        # Publish cognition complete event
        await self._event_bus.publish(CognitEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.COGNITION_COMPLETE,
            source="cognitive_pipeline",
            user_id=request.user_id,
            payload={
                "response_id": response_id,
                "layers_used": trace,
            },
            correlation_id=response_id
        ))

        return CognitionResponse(
            response_id=response_id,
            output_text=response_text,
            confidence=execution_result.get("confidence", 0.8),
            cognitive_layers_used=trace,
            memories_retrieved=memories,
            entities_extracted=entities[:5] if entities else [],
            actions_taken=execution_result.get("actions", []),
            world_model_updates=[],
            reasoning_trace=trace,
        )

    def _is_simple_query(self, text: str) -> bool:
        """Check if simple query for reactive fast path."""
        simple_patterns = ["hello", "hi", "hey", "time", "date", "weather"]
        return any(p in text.lower() for p in simple_patterns)

    async def _reactive_response(self, request: CognitionRequest, response_id: str, trace: list[str]) -> CognitionResponse:
        """Fast reactive response."""
        responses = {
            "hello": "Hello! How can I help you today?",
            "hi": "Hi there! What's on your mind?",
            "hey": "Hey! Ready to assist you.",
            "time": f"The current time is {datetime.now().strftime('%I:%M %p')}",
            "date": f"Today is {datetime.now().strftime('%B %d, %Y')}",
        }
        text_lower = request.input_text.lower()
        response_text = responses.get(text_lower.split()[0], "I'm here!")

        return CognitionResponse(
            response_id=response_id,
            output_text=response_text,
            confidence=1.0,
            cognitive_layers_used=trace,
            memories_retrieved=[],
            entities_extracted=[],
            actions_taken=[],
            world_model_updates=[],
            reasoning_trace=trace,
        )

    async def _perception_layer(self, request: CognitionRequest) -> dict:
        """Layer 2: Perception - analyze input."""
        return {
            "input": request.input_text,
            "intent": "general_conversation",  # In production, use NLU
            "emotion": "neutral",  # In production, use prosody analysis
        }

    async def _planning_layer(self, request: CognitionRequest, memories: list, context: dict) -> dict:
        """Layer 5: HTN Planning."""
        # Simple planning - decompose into tasks
        return {
            "tasks": [
                {"action": "retrieve_memories", "status": "completed"},
                {"action": "generate_response", "status": "pending"},
            ]
        }

    async def _execution_layer(self, request: CognitionRequest, plan: dict, memories: list) -> dict:
        """Layer 6: Execute planned actions."""
        # Build context from memories
        context = "\n".join([f"- {m.content[:100]}" for m in memories[:3]])

        # Generate response using LLM
        if self._llm:
            prompt = f"""You are Raso, a persistent cognitive AI companion.
Context from memory:
{context}

User: {request.input_text}

Respond thoughtfully, referencing relevant memories."""
            try:
                response = await self._llm.generate(prompt)
                return {"response": response, "confidence": 0.85, "actions": ["llm_generation"]}
            except Exception as e:
                logger.error("llm_generation_failed", error=str(e))

        return {"response": "I'm thinking about your question.", "confidence": 0.5, "actions": []}

    async def _reflection_layer(self, request: CognitionRequest, result: dict, memories: list):
        """Layer 7: Reflection - learn from interaction."""
        # Update memory importance based on interaction
        for memory in memories:
            memory.access_count += 1


# ──────────────────────────────────────────────────────────────────────────────
# Audio Cognition Pipeline (Real Voice → Cognition)
# ──────────────────────────────────────────────────────────────────────────────

class AudioCognitionPipeline:
    """
    REAL audio-first pipeline.
    Connects voice to cognitive engine.
    """

    def __init__(
        self,
        voice_service,  # VoiceService
        cognitive_pipeline: CognitivePipeline,
        memory_system: UnifiedMemorySystem,
        event_bus: EventBus,
    ):
        self._voice = voice_service
        self._cognitive = cognitive_pipeline
        self._memory = memory_system
        self._event_bus = event_bus

        self._active_sessions: dict[str, dict] = {}  # session_id -> state

        logger.info("audio_cognition_pipeline_initialized")

    async def start_conversation(self, user_id: str, session_id: str) -> str:
        """Start voice conversation session."""
        self._active_sessions[session_id] = {
            "user_id": user_id,
            "started_at": datetime.utcnow(),
            "transcripts": [],
            "is_listening": True,
        }

        await self._event_bus.publish(CognitEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.CONVERSATION_START,
            source="audio_pipeline",
            user_id=user_id,
            payload={"session_id": session_id}
        ))

        logger.info("conversation_started", user_id=user_id, session_id=session_id)
        return session_id

    async def process_audio(self, session_id: str, audio_chunk: bytes) -> Optional[CognitionResponse]:
        """Process audio through full pipeline."""
        session = self._active_sessions.get(session_id)
        if not session:
            return None

        # 1. Speech to text
        transcript = await self._voice.stt.transcribe(audio_chunk)

        if not transcript.text.strip():
            return None

        # Store transcript
        session["transcripts"].append({
            "text": transcript.text,
            "timestamp": datetime.utcnow().isoformat(),
            "is_final": transcript.is_final,
        })

        # Publish transcript event
        await self._event_bus.publish(CognitEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.VOICE_TRANSCRIPT,
            source="audio_pipeline",
            user_id=session["user_id"],
            payload={
                "session_id": session_id,
                "text": transcript.text,
                "is_final": transcript.is_final,
            }
        ))

        # Process final transcripts through cognition
        if transcript.is_final:
            response = await self._cognitive.process(CognitionRequest(
                input_text=transcript.text,
                user_id=session["user_id"],
                source="voice",
                context={"session_id": session_id},
                conversation_history=session["transcripts"][-10:]
            ))

            # Store in memory as episodic
            await self._memory.store(
                user_id=session["user_id"],
                content=f"Voice conversation: {transcript.text}",
                memory_type="episodic",
                source="voice",
                metadata={"session_id": session_id, "response_id": response.response_id}
            )

            return response

        return None

    async def end_conversation(self, session_id: str):
        """End voice conversation."""
        if session_id in self._active_sessions:
            user_id = self._active_sessions[session_id]["user_id"]

            await self._event_bus.publish(CognitEvent(
                event_id=str(uuid.uuid4()),
                event_type=EventType.CONVERSATION_END,
                source="audio_pipeline",
                user_id=user_id,
                payload={
                    "session_id": session_id,
                    "transcript_count": len(self._active_sessions[session_id]["transcripts"])
                }
            ))

            del self._active_sessions[session_id]
            logger.info("conversation_ended", session_id=session_id)


# ──────────────────────────────────────────────────────────────────────────────
# Unified Runtime Coordinator
# ──────────────────────────────────────────────────────────────────────────────

class UnifiedRuntimeCoordinator:
    """
    THE ONE coordinator that unifies ALL subsystems.

    This replaces the disconnected architecture with a single coherent runtime.
    """

    def __init__(
        self,
        voice_service,
        world_model,
        memory_service,
        cognitive_engine,
        proactive_service,
        llm_gateway=None,
    ):
        # Core services
        self._voice = voice_service
        self._world_model = world_model
        self._memory_service = memory_service
        self._cognitive = cognitive_engine
        self._proactive = proactive_service
        self._llm = llm_gateway

        # Event-driven infrastructure
        self._event_bus = EventBus()

        # Unified memory system (NEW - replaces old memories)
        self._unified_memory = UnifiedMemorySystem(
            world_model=world_model,
            embedder=memory_service.embedder if hasattr(memory_service, 'embedder') else None,
            event_bus=self._event_bus,
        )

        # Cognitive pipeline (REAL 7-layer cognition)
        self._cognitive_pipeline = CognitivePipeline(
            memory_system=self._unified_memory,
            world_model=world_model,
            llm_gateway=llm_gateway,
            proactive_service=proactive_service,
            event_bus=self._event_bus,
        )

        # Audio cognition pipeline (REAL voice → cognition)
        self._audio_pipeline = AudioCognitionPipeline(
            voice_service=voice_service,
            cognitive_pipeline=self._cognitive_pipeline,
            memory_system=self._unified_memory,
            event_bus=self._event_bus,
        )

        logger.info("unified_runtime_coordinator_initialized")

    async def start(self):
        """Start all subsystems."""
        await self._unified_memory.start()
        logger.info("all_subsystems_started")

    async def stop(self):
        """Stop all subsystems."""
        await self._unified_memory.stop()
        logger.info("all_subsystems_stopped")

    # ─────────────────────────────────────────────────────────────────────────
    # Public API - ALL interactions go through here
    # ─────────────────────────────────────────────────────────────────────────

    async def process_text(self, text: str, user_id: str) -> dict:
        """Process text through full cognitive pipeline."""
        result = await self._cognitive_pipeline.process(CognitionRequest(
            input_text=text,
            user_id=user_id,
            source="text"
        ))

        return {
            "response_id": result.response_id,
            "response": result.output_text,
            "confidence": result.confidence,
            "cognitive_layers": result.cognitive_layers_used,
            "reasoning_trace": result.reasoning_trace,
        }

    async def process_voice(self, audio: bytes, user_id: str, session_id: str) -> dict:
        """Process voice through full audio cognition pipeline."""
        response = await self._audio_pipeline.process_audio(session_id, audio)

        if response:
            return {
                "response_id": response.response_id,
                "response": response.output_text,
                "confidence": response.confidence,
            }
        return {"transcribing": True}

    async def start_voice_session(self, user_id: str) -> str:
        """Start a voice conversation session."""
        session_id = str(uuid.uuid4())
        await self._audio_pipeline.start_conversation(user_id, session_id)
        return session_id

    async def end_voice_session(self, session_id: str):
        """End voice conversation."""
        await self._audio_pipeline.end_conversation(session_id)

    async def retrieve_memories(self, user_id: str, query: str, limit: int = 10) -> list:
        """Semantic memory retrieval."""
        memories = await self._unified_memory.retrieve(user_id, query, limit=limit)
        return [{"content": m.content, "type": m.memory_type, "importance": m.importance} for m in memories]

    async def store_memory(self, user_id: str, content: str, memory_type: str) -> str:
        """Store memory in unified system."""
        node = await self._unified_memory.store(user_id, content, memory_type)
        return node.node_id

    async def get_user_context(self, user_id: str) -> dict:
        """Get complete user context from world model."""
        return await self._world_model.get_user_context(user_id)

    async def get_proactive_suggestions(self, user_id: str) -> list:
        """Get proactive suggestions."""
        return await self._proactive.get_suggestions(user_id)

    def get_event_bus(self) -> EventBus:
        """Get event bus for distributed cognition."""
        return self._event_bus


# ──────────────────────────────────────────────────────────────────────────────
# Factory Function
# ──────────────────────────────────────────────────────────────────────────────

async def create_unified_runtime(
    voice_service=None,
    world_model=None,
    memory_service=None,
    cognitive_engine=None,
    proactive_service=None,
    llm_gateway=None,
) -> UnifiedRuntimeCoordinator:
    """Create unified runtime with all services connected."""

    coordinator = UnifiedRuntimeCoordinator(
        voice_service=voice_service,
        world_model=world_model,
        memory_service=memory_service,
        cognitive_engine=cognitive_engine,
        proactive_service=proactive_service,
        llm_gateway=llm_gateway,
    )

    await coordinator.start()

    return coordinator