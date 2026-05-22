"""
RasoSpeak OS — Unified Memory System
Single memory architecture replacing 4 separate systems:
- SecondBrainAgent
- SharedMemoryAgent
- SessionMemoryAgent
- EpisodicMemory

This unifies:
- episodic memory (events, conversations)
- semantic memory (facts, knowledge)
- procedural memory (skills, workflows)
- social memory (people, context)
"""

import asyncio
import json
import logging
import time
from typing import Optional, Any, list
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import uuid

from .base_agent import BaseAgent
from config.settings import settings

log = logging.getLogger("rasospeak.unified_memory")


class MemoryType(Enum):
    """Types of memory in unified system."""
    EPISODIC = "episodic"     # Events, conversations
    SEMANTIC = "semantic"     # Facts, knowledge
    PROCEDURAL = "procedural" # Skills, workflows
    SOCIAL = "social"         # People, relationships
    PREFERENCE = "preference"  # User preferences
    WORKING = "working"       # Short-term context


class MemoryImportance(Enum):
    CRITICAL = 5
    HIGH = 4
    MEDIUM = 3
    LOW = 2
    MINIMAL = 1


@dataclass
class Memory:
    """Unified memory entry."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    memory_type: MemoryType = MemoryType.EPISODIC
    importance: MemoryImportance = MemoryImportance.MEDIUM

    # Content
    content: str = ""
    embedding: Optional[list[float]] = None

    # Metadata
    user_id: str = "default"
    session_id: Optional[str] = None
    source: str = "unknown"  # voice, chat, document, system

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    accessed_at: datetime = field(default_factory=datetime.utcnow)
    last_modified: datetime = field(default_factory=datetime.utcnow)

    # Associations
    tags: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)  # Linked memory IDs

    # Context
    context: dict = field(default_factory=dict)  # Additional metadata


class UnifiedMemoryAgent(BaseAgent):
    """
    Single unified memory system replacing:
    - SecondBrainAgent
    - SharedMemoryAgent
    - SessionMemoryAgent

    All interactions flow through this ONE memory system.
    """

    def __init__(self):
        super().__init__("unified_memory")
        self._memories: dict[str, Memory] = {}
        self._session_memories: dict[str, list[str]] = {}
        self._user_preferences: dict[str, Any] = {}
        self._embedding_cache: dict[str, list[float]] = {}

    async def initialize(self) -> None:
        """Initialize unified memory."""
        log.info("🧠 Unified Memory Agent initializing...")

        # Load from database if available
        try:
            from db.unified import db
            if db._connected:
                log.info("✅ Using PostgreSQL for memory storage")
            else:
                log.info("📁 Using in-memory storage (fallback)")
        except ImportError:
            log.info("📁 Using in-memory storage (no DB module)")

        log.info("✅ Unified Memory Agent ready")

    # ── CORE STORAGE ─────────────────────────────────────

    async def store(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.EPISODIC,
        importance: MemoryImportance = MemoryImportance.MEDIUM,
        user_id: str = "default",
        session_id: Optional[str] = None,
        source: str = "unknown",
        embedding: Optional[list[float]] = None,
        tags: Optional[list[str]] = None,
        **context,
    ) -> str:
        """Store a memory entry."""
        memory = Memory(
            content=content,
            memory_type=memory_type,
            importance=importance,
            user_id=user_id,
            session_id=session_id,
            source=source,
            embedding=embedding or await self._get_embedding(content),
            tags=tags or [],
            context=context,
        )

        self._memories[memory.id] = memory

        # Track session memories
        if session_id:
            if session_id not in self._session_memories:
                self._session_memories[session_id] = []
            self._session_memories[session_id].append(memory.id)

        # Try to persist to database
        await self._persist_to_db(memory)

        log.debug(f"Stored {memory_type.value} memory: {memory.id[:8]}")
        return memory.id

    async def recall(
        self,
        query: str,
        memory_type: Optional[MemoryType] = None,
        user_id: str = "default",
        limit: int = 10,
        min_importance: MemoryImportance = MemoryImportance.LOW,
    ) -> list[Memory]:
        """Recall memories matching query."""
        query_lower = query.lower()

        # Filter by user and type
        candidates = [
            m for m in self._memories.values()
            if m.user_id == user_id
            and m.importance.value >= min_importance.value
            and (memory_type is None or m.memory_type == memory_type)
        ]

        # Score by relevance
        scored = []
        for mem in candidates:
            score = self._score_relevance(query_lower, mem)
            scored.append((score, mem))

        # Sort by score and importance
        scored.sort(key=lambda x: (x[0], x[1].importance.value), reverse=True)

        # Update access time
        for _, mem in scored[:limit]:
            mem.accessed_at = datetime.utcnow()

        return [mem for _, mem in scored[:limit]]

    def _score_relevance(self, query: str, memory: Memory) -> float:
        """Score memory relevance to query."""
        score = 0.0

        # Content match
        if query in memory.content.lower():
            score += 1.0

        # Tag match
        for tag in memory.tags:
            if tag.lower() in query:
                score += 0.5

        # Recency boost
        age_hours = (datetime.utcnow() - memory.accessed_at).total_seconds() / 3600
        score += max(0, 0.3 - (age_hours / 24))  # Decay over 24 hours

        return score

    # ── CONVERSATION HANDLING ───────────────────────────

    async def store_conversation(
        self,
        user_message: str,
        ai_response: str,
        user_id: str = "default",
        session_id: Optional[str] = None,
        provider: str = "unknown",
        metadata: Optional[dict] = None,
    ) -> str:
        """Store a conversation turn (replaces SharedMemoryAgent.add_conversation)."""
        content = f"User: {user_message}\nAI: {ai_response}"

        return await self.store(
            content=content,
            memory_type=MemoryType.EPISODIC,
            importance=MemoryImportance.MEDIUM,
            user_id=user_id,
            session_id=session_id,
            source="conversation",
            tags=["conversation", provider],
            provider=provider,
            **(metadata or {}),
        )

    async def get_conversation_history(
        self,
        user_id: str = "default",
        session_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get conversation history (replaces SessionMemoryAgent)."""
        if session_id:
            # Get specific session
            memory_ids = self._session_memories.get(session_id, [])
            memories = [self._memories[mid] for mid in memory_ids if mid in self._memories]
        else:
            # Get recent across all sessions
            memories = await self.recall(
                query="",
                memory_type=MemoryType.EPISODIC,
                user_id=user_id,
                limit=limit,
            )

        return [
            {
                "id": m.id,
                "content": m.content,
                "source": m.source,
                "created_at": m.created_at.isoformat(),
                "context": m.context,
            }
            for m in memories
        ]

    # ── USER PREFERENCES (replaces SharedMemoryAgent.get_user_preferences) ─

    async def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference."""
        return self._user_preferences.get(key, default)

    async def set_preference(self, key: str, value: Any) -> None:
        """Set a user preference."""
        self._user_preferences[key] = value
        await self.store(
            content=f"Preference: {key} = {value}",
            memory_type=MemoryType.PREFERENCE,
            importance=MemoryImportance.HIGH,
            source="system",
            tags=["preference", key],
        )

    async def get_all_preferences(self) -> dict:
        """Get all user preferences."""
        return self._user_preferences.copy()

    # ── SEMANTIC MEMORY (facts, knowledge) ───────────────

    async def store_fact(
        self,
        fact: str,
        user_id: str = "default",
        importance: MemoryImportance = MemoryImportance.MEDIUM,
    ) -> str:
        """Store a factual memory."""
        return await self.store(
            content=fact,
            memory_type=MemoryType.SEMANTIC,
            importance=importance,
            user_id=user_id,
            source="knowledge",
            tags=["fact"],
        )

    async def search_knowledge(self, query: str, user_id: str = "default") -> list[str]:
        """Search semantic memory for facts."""
        results = await self.recall(
            query=query,
            memory_type=MemoryType.SEMANTIC,
            user_id=user_id,
            limit=5,
        )
        return [m.content for m in results]

    # ── PROCEDURAL MEMORY (skills, workflows) ───────────

    async def store_skill(
        self,
        skill_name: str,
        description: str,
        steps: list[str],
        user_id: str = "default",
    ) -> str:
        """Store a procedural skill."""
        content = f"Skill: {skill_name}\nDescription: {description}\nSteps: {' -> '.join(steps)}"
        return await self.store(
            content=content,
            memory_type=MemoryType.PROCEDURAL,
            importance=MemoryImportance.HIGH,
            user_id=user_id,
            source="skill",
            tags=["skill", skill_name],
        )

    # ── WORKING MEMORY (short-term) ─────────────────────

    async def update_working_memory(
        self,
        key: str,
        value: Any,
        user_id: str = "default",
    ) -> None:
        """Update working memory context."""
        await self.store(
            content=f"Working: {key} = {value}",
            memory_type=MemoryType.WORKING,
            importance=MemoryImportance.CRITICAL,
            user_id=user_id,
            source="runtime",
            tags=["working", key],
            ttl_seconds=300,  # 5 minute TTL
        )

    async def get_working_memory(self, user_id: str = "default") -> dict:
        """Get current working memory context."""
        results = await self.recall(
            query="",
            memory_type=MemoryType.WORKING,
            user_id=user_id,
            limit=20,
        )
        return {m.tags[1] if len(m.tags) > 1 else m.id: m.content for m in results}

    # ── DATABASE PERSISTENCE ─────────────────────────────

    async def _persist_to_db(self, memory: Memory) -> None:
        """Persist memory to database if available."""
        try:
            from db.unified import db
            if db._connected:
                await db.store_memory(
                    user_id=memory.user_id,
                    memory_type=memory.memory_type.value,
                    content=memory.content,
                    embedding=memory.embedding,
                    metadata={
                        "importance": memory.importance.value,
                        "source": memory.source,
                        "tags": memory.tags,
                        "context": memory.context,
                    },
                )
        except Exception as e:
            log.debug(f"DB persistence skipped: {e}")

    async def _get_embedding(self, text: str) -> list[float]:
        """Get embedding for text (placeholder - integrate with actual embedding model)."""
        # TODO: Replace with actual embedding model (OpenAI ada, sentence-transformers, etc.)
        # For now, return random vector
        if text in self._embedding_cache:
            return self._embedding_cache[text]

        import random
        embedding = [random.uniform(-1, 1) for _ in range(1536)]
        self._embedding_cache[text] = embedding
        return embedding

    # ── SECOND BRAIN COMPATIBILITY ──────────────────────

    async def add_conversation(
        self,
        user_input: str,
        ai_response: str,
        ai_provider: str = "unknown",
        context: str = "",
    ) -> str:
        """Compatibility method for SecondBrainAgent interface."""
        return await self.store_conversation(
            user_message=user_input,
            ai_response=ai_response,
            provider=ai_provider,
            metadata={"context": context},
        )

    async def recall_conversation(
        self,
        query: str = "",
        limit: int = 10,
    ) -> list[dict]:
        """Compatibility method for SecondBrainAgent interface."""
        memories = await self.recall(
            query=query,
            memory_type=MemoryType.EPISODIC,
            limit=limit,
        )
        return [{"node": {"content": {"user": m.content.split('\n')[0], "ai_provider": m.source}}} for m in memories]


# Singleton
unified_memory = UnifiedMemoryAgent()