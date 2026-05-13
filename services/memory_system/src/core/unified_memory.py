"""
Unified Memory System - Single Source of Truth
================================================
Replaces all disconnected memory systems with ONE coherent architecture.

Memory Layers:
- Working Memory: Current conversation context
- Episodic Memory: Past conversations and events
- Semantic Memory: Facts, concepts, knowledge
- Procedural Memory: How to do things, workflows
- Social Memory: Relationships, interactions
- Knowledge Graph: Entities and relationships
- Temporal Memory: Time-based patterns
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Any
import uuid
import structlog

logger = structlog.get_logger("rasospeak.memory")


class MemoryType(Enum):
    """Memory type categories."""
    WORKING = "working"           # Current context
    EPISODIC = "episodic"         # Past events
    SEMANTIC = "semantic"         # Facts/concepts
    PROCEDURAL = "procedural"    # How-to
    SOCIAL = "social"            # Relationships
    EMOTIONAL = "emotional"      # Sentiment/tone
    TEMPORAL = "temporal"         # Time patterns
    GOAL = "goal"                # Active goals
    TASK = "task"                # Action items


class MemoryImportance(Enum):
    """Memory importance levels."""
    CRITICAL = 1.0    # Must remember
    HIGH = 0.8
    MEDIUM = 0.5
    LOW = 0.3
    FORGOTTEN = 0.1   # Can be purged


@dataclass
class MemoryNode:
    """
    Single memory unit.

    Unified representation for ALL memory types.
    """
    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Content
    content: str
    memory_type: MemoryType = MemoryType.EPISODIC

    # Metadata
    importance: float = 0.5
    user_id: str = "default"
    session_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0

    # Source
    source: str = "conversation"  # conversation, document, workflow, voice, etc.
    source_id: Optional[str] = None

    # Content encoding
    embedding: Optional[list[float]] = None
    summary: Optional[str] = None
    keywords: list[str] = field(default_factory=list)

    # Entities & relations
    entities: list[str] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)

    # Context
    speaker: Optional[str] = None
    emotional_tone: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    # Temporal
    expires_at: Optional[datetime] = None

    # Working memory specific
    position: int = 0  # Position in conversation


@dataclass
class MemoryQuery:
    """Memory retrieval query."""
    user_id: str
    query: str = ""

    # Filters
    memory_types: list[MemoryType] = None
    min_importance: float = 0.0
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
    speakers: list[str] = None
    tags: list[str] = None
    limit: int = 10

    # Retrieval strategy
    strategy: str = "semantic"  # semantic, keyword, temporal, hybrid


@dataclass
class MemorySearchResult:
    """Memory retrieval result."""
    memory: MemoryNode
    score: float  # Relevance score
    highlighted: Optional[str] = None


class UnifiedMemorySystem:
    """
    Single source of truth for ALL memory.

    Replaces:
    - SecondBrainAgent memory
    - SharedMemoryAgent
    - SessionMemoryAgent
    - All other disconnected memory systems
    """

    def __init__(
        self,
        embedder=None,  # Embedding service
        vector_store=None,  # Qdrant for vector search
        sql_db=None,  # PostgreSQL for durable storage
        redis_cache=None,  # Redis for fast access
    ):
        self._embedder = embedder
        self._vector_store = vector_store
        self._sql_db = sql_db
        self._redis = redis_cache

        # In-memory layers (for fast access)
        self._working_memory: dict[str, list[MemoryNode]] = {}  # session_id -> nodes
        self._episodic_store: dict[str, dict[str, MemoryNode]] = {}  # user_id -> node_id -> node

        # Background tasks
        self._consolidation_task: Optional[asyncio.Task] = None
        self._gc_task: Optional[asyncio.Task] = None

        logger.info("unified_memory_system_initialized")

    # ─────────────────────────────────────────────────────────────
    # Core Operations
    # ─────────────────────────────────────────────────────────────

    async def store(
        self,
        content: str,
        user_id: str,
        memory_type: MemoryType = MemoryType.EPISODIC,
        session_id: Optional[str] = None,
        importance: float = 0.5,
        metadata: dict = None,
        **kwargs
    ) -> MemoryNode:
        """
        Store a memory.

        This is the primary entry point for ALL memory storage.
        """
        # Create memory node
        node = MemoryNode(
            content=content,
            user_id=user_id,
            memory_type=memory_type,
            session_id=session_id,
            importance=importance,
            source=metadata.get("source", "conversation") if metadata else "conversation",
            **kwargs
        )

        # Generate embedding if embedder available
        if self._embedder:
            try:
                embeddings = await self._embedder.embed([content])
                node.embedding = embeddings[0]
            except Exception as e:
                logger.warning("embedding_failed", error=str(e))

        # Extract entities and keywords
        node.entities = self._extract_entities(content)
        node.keywords = self._extract_keywords(content)

        # Store in appropriate layer
        if memory_type == MemoryType.WORKING:
            await self._store_working_memory(node)
        else:
            await self._store_episodic(node)

        # Store in vector store if available
        if self._vector_store and node.embedding:
            await self._vector_store.upsert(
                collection=f"memory_{user_id}",
                vectors=[node.embedding],
                ids=[node.node_id],
                payloads=[{
                    "content": content,
                    "memory_type": memory_type.value,
                    "importance": importance,
                    "created_at": node.created_at.isoformat()
                }]
            )

        # Store in SQL for durability
        if self._sql_db:
            await self._persist_to_sql(node)

        logger.info(
            "memory_stored",
            node_id=node.node_id,
            memory_type=memory_type.value,
            user_id=user_id
        )

        return node

    async def _store_working_memory(self, node: MemoryNode):
        """Store in working memory (current session)."""
        if not node.session_id:
            node.session_id = "default"

        if node.session_id not in self._working_memory:
            self._working_memory[node.session_id] = []

        # Add position based on order
        node.position = len(self._working_memory[node.session_id])
        self._working_memory[node.session_id].append(node)

        # Keep working memory bounded
        if len(self._working_memory[node.session_id]) > 100:
            self._working_memory[node.session_id] = self._working_memory[node.session_id][-100:]

    async def _store_episodic(self, node: MemoryNode):
        """Store in episodic memory (persistent)."""
        if node.user_id not in self._episodic_store:
            self._episodic_store[node.user_id] = {}

        self._episodic_store[node.user_id][node.node_id] = node

    # ─────────────────────────────────────────────────────────────
    # Retrieval
    # ─────────────────────────────────────────────────────────────

    async def retrieve(self, query: MemoryQuery) -> list[MemorySearchResult]:
        """
        Retrieve memories matching query.

        Uses semantic search when embeddings available,
        falls back to keyword search.
        """
        results = []

        # Try semantic search first
        if self._embedder and self._vector_store:
            try:
                query_embedding = await self._embedder.embed([query.query])
                vector_results = await self._vector_store.search(
                    collection=f"memory_{query.user_id}",
                    query_vector=query_embedding[0],
                    limit=query.limit,
                    filter=self._build_filter(query)
                )

                # Get actual nodes
                for vr in vector_results:
                    node = await self._get_node_by_id(query.user_id, vr.id)
                    if node:
                        results.append(MemorySearchResult(
                            memory=node,
                            score=vr.score,
                            highlighted=self._highlight_match(node.content, query.query)
                        ))
            except Exception as e:
                logger.warning("semantic_search_failed", error=str(e))

        # Fallback to keyword search
        if not results:
            results = await self._keyword_search(query)

        # Update access stats
        for result in results:
            result.memory.access_count += 1
            result.memory.last_accessed = datetime.utcnow()

        # Sort by relevance
        results.sort(key=lambda r: r.score, reverse=True)

        return results[:query.limit]

    async def _keyword_search(self, query: MemoryQuery) -> list[MemorySearchResult]:
        """Keyword-based memory search."""
        results = []
        query_lower = query.query.lower()

        # Search in working memory
        for session_id, nodes in self._working_memory.items():
            for node in nodes:
                if query.user_id == node.user_id:
                    if query_lower in node.content.lower():
                        score = node.importance
                        if query.memory_types and node.memory_type not in query.memory_types:
                            continue
                        if query.min_importance and node.importance < query.min_importance:
                            continue
                        results.append(MemorySearchResult(memory=node, score=score))

        # Search in episodic
        if query.user_id in self._episodic_store:
            for node in self._episodic_store[query.user_id].values():
                if query_lower in node.content.lower():
                    score = node.importance * 0.8  # Slightly lower than working memory
                    results.append(MemorySearchResult(memory=node, score=score))

        return results

    async def _get_node_by_id(self, user_id: str, node_id: str) -> Optional[MemoryNode]:
        """Get memory node by ID."""
        # Check episodic
        if user_id in self._episodic_store:
            if node_id in self._episodic_store[user_id]:
                return self._episodic_store[user_id][node_id]

        return None

    def _build_filter(self, query: MemoryQuery) -> dict:
        """Build vector store filter."""
        filters = {}

        if query.memory_types:
            filters["memory_type"] = {"$in": [mt.value for mt in query.memory_types]}

        if query.min_importance:
            filters["importance"] = {"$gte": query.min_importance}

        if query.from_date or query.to_date:
            filters["created_at"] = {}
            if query.from_date:
                filters["created_at"]["$gte"] = query.from_date.isoformat()
            if query.to_date:
                filters["created_at"]["$lte"] = query.to_date.isoformat()

        return filters if filters else None

    # ─────────────────────────────────────────────────────────────
    # Utility Methods
    # ─────────────────────────────────────────────────────────────

    def _extract_entities(self, text: str) -> list[str]:
        """Extract named entities from text."""
        # Simple extraction - in production use NER
        entities = []
        words = text.split()
        for word in words:
            if word and word[0].isupper() and len(word) > 2:
                entities.append(word)
        return entities[:10]  # Limit

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract keywords from text."""
        # Simple extraction - in production use NLP
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must", "shall", "can", "need", "dare", "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by", "from", "as", "into", "through", "during", "before", "after", "above", "below", "between", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how", "all", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just", "and", "but", "if", "or", "because", "until", "while"}
        words = [w.lower() for w in text.split() if w.lower() not in stop_words and len(w) > 3]
        return list(set(words))[:20]

    def _highlight_match(self, content: str, query: str) -> str:
        """Highlight matching text."""
        # Simple implementation
        return content[:200] + "..." if len(content) > 200 else content

    # ─────────────────────────────────────────────────────────────
    # Context Management
    # ─────────────────────────────────────────────────────────────

    async def get_context(
        self,
        session_id: str,
        max_messages: int = 20
    ) -> list[dict]:
        """Get current conversation context for working memory."""
        if session_id not in self._working_memory:
            return []

        nodes = self._working_memory[session_id][-max_messages:]

        return [
            {
                "role": "user" if i % 2 == 0 else "assistant",
                "content": node.content
            }
            for i, node in enumerate(nodes)
        ]

    async def consolidate_working_memory(
        self,
        session_id: str,
        user_id: str
    ):
        """
        Consolidate working memory to episodic.

        Called when session ends to preserve context.
        """
        if session_id not in self._working_memory:
            return

        # Get all working memory nodes
        nodes = self._working_memory.pop(session_id, [])

        # Summarize and store as episodic
        if nodes:
            summary = self._summarize_conversation(nodes)

            await self.store(
                content=summary,
                user_id=user_id,
                memory_type=MemoryType.EPISODIC,
                session_id=session_id,
                importance=0.7,
                source="session_consolidation",
                metadata={"node_count": len(nodes)}
            )

            logger.info("working_memory_consolidated", session_id=session_id, node_count=len(nodes))

    def _summarize_conversation(self, nodes: list[MemoryNode]) -> str:
        """Summarize conversation nodes."""
        # Simple summary - in production use LLM
        if not nodes:
            return "Empty conversation"

        first = nodes[0].content[:50]
        last = nodes[-1].content[:50]
        count = len(nodes)

        return f"Conversation ({count} messages): Started with '{first}...' Ended with '{last}...'"

    # ─────────────────────────────────────────────────────────────
    # Memory Operations
    # ─────────────────────────────────────────────────────────────

    async def get_recent_conversations(
        self,
        user_id: str,
        limit: int = 10
    ) -> list[MemoryNode]:
        """Get recent conversation memories."""
        if user_id not in self._episodic_store:
            return []

        nodes = sorted(
            self._episodic_store[user_id].values(),
            key=lambda n: n.created_at,
            reverse=True
        )

        return nodes[:limit]

    async def search_by_speaker(
        self,
        user_id: str,
        speaker: str,
        limit: int = 10
    ) -> list[MemoryNode]:
        """Find memories by specific speaker."""
        if user_id not in self._episodic_store:
            return []

        return [
            node for node in self._episodic_store[user_id].values()
            if node.speaker == speaker
        ][:limit]

    async def search_by_date(
        self,
        user_id: str,
        date: datetime,
        range_days: int = 7
    ) -> list[MemoryNode]:
        """Find memories near a specific date."""
        if user_id not in self._episodic_store:
            return []

        start = date - timedelta(days=range_days)
        end = date + timedelta(days=range_days)

        return [
            node for node in self._episodic_store[user_id].values()
            if start <= node.created_at <= end
        ]

    # ─────────────────────────────────────────────────────────────
    # Background Tasks
    # ─────────────────────────────────────────────────────────────

    async def start(self):
        """Start background memory tasks."""
        self._consolidation_task = asyncio.create_task(self._consolidation_loop())
        self._gc_task = asyncio.create_task(self._gc_loop())
        logger.info("memory_system_started")

    async def stop(self):
        """Stop background tasks."""
        if self._consolidation_task:
            self._consolidation_task.cancel()
        if self._gc_task:
            self._gc_task.cancel()
        logger.info("memory_system_stopped")

    async def _consolidation_loop(self):
        """Periodically consolidate memory."""
        while True:
            await asyncio.sleep(60)  # Every minute
            # In production, would consolidate old working memory

    async def _gc_loop(self):
        """Periodically garbage collect low-importance memories."""
        while True:
            await asyncio.sleep(3600)  # Every hour
            # In production, would purge memories below threshold

    # ─────────────────────────────────────────────────────────────
    # SQL Persistence (Placeholder)
    # ─────────────────────────────────────────────────────────────

    async def _persist_to_sql(self, node: MemoryNode):
        """Persist memory to PostgreSQL."""
        # Would implement SQL INSERT/UPDATE here
        pass

    # ─────────────────────────────────────────────────────────────
    # Stats
    # ─────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get memory system statistics."""
        total_nodes = sum(len(store) for store in self._episodic_store.values())
        working_sessions = len(self._working_memory)

        return {
            "total_memories": total_nodes,
            "active_sessions": working_sessions,
            "episodic_stores": len(self._episodic_store),
            "embedding_enabled": self._embedder is not None,
            "vector_store_enabled": self._vector_store is not None,
            "sql_store_enabled": self._sql_db is not None
        }


# Global memory system instance
_memory_system: Optional[UnifiedMemorySystem] = None


def get_memory_system() -> UnifiedMemorySystem:
    """Get global memory system instance."""
    global _memory_system
    if _memory_system is None:
        _memory_system = UnifiedMemorySystem()
    return _memory_system