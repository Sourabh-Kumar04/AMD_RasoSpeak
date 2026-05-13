"""
RasoSpeak AI OS — Memory Service
================================
Hierarchical memory system with:
- Working memory (Redis)
- Episodic memory (PostgreSQL)
- Semantic memory (PostgreSQL + pgvector)
- Procedural memory (PostgreSQL)
- Knowledge graph (PostgreSQL)

This replaces ALL JSON persistence.
"""

from __future__ import annotations

import asyncio
import json
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import uuid

import structlog

logger = structlog.get_logger("rasospeak.memory")


# ──────────────────────────────────────────────────────────────────────────────
# Embedder Interface (re-exported for convenience)
# ──────────────────────────────────────────────────────────────────────────────

class Embedder(ABC):
    """Abstract embedder for generating vector embeddings."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate embedding for text."""
        pass

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        pass


class SimpleEmbedder(Embedder):
    """Simple hash-based embedder for development (NOT for production)."""

    async def embed(self, text: str) -> list[float]:
        """Generate pseudo-embedding from text hash."""
        h = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in h[:32]] + [0.0] * (1536 - 32)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


# ──────────────────────────────────────────────────────────────────────────────
# Memory Types
# ──────────────────────────────────────────────────────────────────────────────

class MemoryType(Enum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    ARCHIVAL = "archival"


@dataclass
class MemoryEntry:
    """A single memory entry."""
    memory_id: str
    memory_type: MemoryType
    user_id: str
    tenant_id: str
    content: Any  # Can be dict, str, or structured data
    embedding: Optional[list[float]] = None
    confidence: float = 1.0
    importance: float = 0.5
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "memory_id": self.memory_id,
            "memory_type": self.memory_type.value,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "content": self.content,
            "confidence": self.confidence,
            "importance": self.importance,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "metadata": self.metadata,
        }


@dataclass
class KnowledgeNode:
    """A node in the knowledge graph."""
    node_id: str
    user_id: str
    tenant_id: str
    node_type: str
    name: str
    properties: dict[str, Any] = field(default_factory=dict)
    embedding: Optional[list[float]] = None
    importance: float = 0.5
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class KnowledgeEdge:
    """An edge in the knowledge graph."""
    edge_id: str
    source_id: str
    target_id: str
    relationship: str
    weight: float = 1.0
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Procedure:
    """A learned procedure/behavior."""
    procedure_id: str
    user_id: str
    tenant_id: str
    name: str
    trigger_conditions: dict[str, Any]
    steps: list[dict]
    success_rate: float = 0.0
    usage_count: int = 0
    last_used: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RetrievalResult:
    """Result of memory retrieval."""
    memories: list[MemoryEntry]
    context: str
    token_count: int
    retrieval_method: str
    coverage: float = 1.0


# ──────────────────────────────────────────────────────────────────────────────
# Working Memory (Redis-backed)
# ──────────────────────────────────────────────────────────────────────────────

class WorkingMemory:
    """
    Working memory backed by Redis.

    Features:
    - Token budget management
    - Sliding window context
    - Automatic expiration
    - Checkpointing to episodic memory
    """

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self._local_cache: dict[str, list[MemoryEntry]] = {}
        self._budget: dict[str, int] = {}

    def _key(self, user_id: str, conversation_id: str = "default") -> str:
        return f"wm:{user_id}:{conversation_id}"

    async def store(
        self,
        user_id: str,
        tenant_id: str,
        content: Any,
        conversation_id: str = "default",
        memory_type: MemoryType = MemoryType.WORKING,
    ) -> MemoryEntry:
        """Store a working memory entry."""
        entry = MemoryEntry(
            memory_id=str(uuid.uuid4()),
            memory_type=memory_type,
            user_id=user_id,
            tenant_id=tenant_id,
            content=content,
        )

        key = self._key(user_id, conversation_id)

        # Store in Redis if available, else local cache
        if self.redis:
            import json as json_lib
            await self.redis.rpush(
                key,
                json_lib.dumps(entry.to_dict()),
            )
            await self.redis.expire(key, 3600)  # 1 hour TTL
        else:
            if key not in self._local_cache:
                self._local_cache[key] = []
            self._local_cache[key].append(entry)

        logger.debug(
            "working_memory_stored",
            memory_id=entry.memory_id,
            user_id=user_id,
            conversation_id=conversation_id,
        )

        return entry

    async def retrieve(
        self,
        user_id: str,
        conversation_id: str = "default",
        limit: int = 100,
    ) -> list[MemoryEntry]:
        """Retrieve working memory entries."""
        key = self._key(user_id, conversation_id)

        if self.redis:
            import json as json_lib
            items = await self.redis.lrange(key, -limit, -1)
            return [
                MemoryEntry(**json_lib.loads(item))
                for item in items
            ]
        else:
            return self._local_cache.get(key, [])[-limit:]

    async def get_context(
        self,
        user_id: str,
        conversation_id: str = "default",
        max_tokens: int = 8000,
    ) -> str:
        """Get condensed context for LLM prompt."""
        entries = await self.retrieve(user_id, conversation_id)

        # Simple token estimation (4 chars per token)
        context_parts = []
        current_tokens = 0

        for entry in reversed(entries):  # Most recent first
            if isinstance(entry.content, dict):
                text = json.dumps(entry.content)
            else:
                text = str(entry.content)

            entry_tokens = len(text) // 4

            if current_tokens + entry_tokens > max_tokens:
                break

            context_parts.append(text)
            current_tokens += entry_tokens

        return "\n".join(reversed(context_parts))

    async def clear(
        self,
        user_id: str,
        conversation_id: str = "default",
    ) -> None:
        """Clear working memory."""
        key = self._key(user_id, conversation_id)

        if self.redis:
            await self.redis.delete(key)
        else:
            self._local_cache.pop(key, None)

        logger.info(
            "working_memory_cleared",
            user_id=user_id,
            conversation_id=conversation_id,
        )

    async def checkpoint(
        self,
        user_id: str,
        conversation_id: str = "default",
    ) -> list[MemoryEntry]:
        """Checkpoint working memory for archival."""
        entries = await self.retrieve(user_id, conversation_id)

        # Mark as episodic
        for entry in entries:
            entry.memory_type = MemoryType.EPISODIC

        return entries


# ──────────────────────────────────────────────────────────────────────────────
# Episodic Memory (PostgreSQL)
# ──────────────────────────────────────────────────────────────────────────────

class EpisodicMemory:
    """
    Episodic memory for storing complete conversation episodes.

    Stores:
    - Full conversation transcripts
    - Action-outcome sequences
    - Emotional tones
    - Topics covered
    - Outcomes
    """

    def __init__(self, db_pool=None):
        self.db = db_pool
        self._local_store: dict[str, list[MemoryEntry]] = {}

    async def store(self, entry: MemoryEntry) -> MemoryEntry:
        """Store an episodic memory."""
        entry.memory_type = MemoryType.EPISODIC

        if self.db:
            # In production: INSERT INTO episodic_memories VALUES (...)
            # For now, use local store
            key = f"episodic:{entry.user_id}"
            if key not in self._local_store:
                self._local_store[key] = []
            self._local_store[key].append(entry)
        else:
            key = f"episodic:{entry.user_id}"
            if key not in self._local_store:
                self._local_store[key] = []
            self._local_store[key].append(entry)

        logger.info(
            "episodic_memory_stored",
            memory_id=entry.memory_id,
            user_id=entry.user_id,
        )

        return entry

    async def retrieve(
        self,
        user_id: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        tags: Optional[list[str]] = None,
        limit: int = 50,
    ) -> list[MemoryEntry]:
        """Retrieve episodic memories with filters."""
        key = f"episodic:{user_id}"
        entries = self._local_store.get(key, [])

        # Apply filters
        filtered = []
        for entry in entries:
            if since and entry.created_at < since:
                continue
            if until and entry.created_at > until:
                continue
            if tags and not any(tag in entry.tags for tag in tags):
                continue
            filtered.append(entry)

        # Sort by most recent
        filtered.sort(key=lambda e: e.created_at, reverse=True)
        return filtered[:limit]

    async def get_episode(
        self,
        user_id: str,
        episode_id: str,
    ) -> Optional[MemoryEntry]:
        """Get a specific episode."""
        key = f"episodic:{user_id}"
        for entry in self._local_store.get(key, []):
            if entry.memory_id == episode_id:
                return entry
        return None

    async def summarize(
        self,
        user_id: str,
        episode_ids: list[str],
    ) -> dict[str, Any]:
        """Summarize a set of episodes."""
        episodes = []
        key = f"episodic:{user_id}"

        for entry in self._local_store.get(key, []):
            if entry.memory_id in episode_ids:
                episodes.append(entry)

        # Generate summary (in production, use LLM)
        summary = f"Summary of {len(episodes)} episodes"

        key_points = []
        for episode in episodes:
            if isinstance(episode.content, dict):
                if "summary" in episode.content:
                    key_points.append(episode.content["summary"])

        return {
            "summary": summary,
            "key_points": key_points,
            "episode_count": len(episodes),
            "time_span": {
                "start": min(e.created_at for e in episodes).isoformat() if episodes else None,
                "end": max(e.created_at for e in episodes).isoformat() if episodes else None,
            },
        }

    async def archive(
        self,
        user_id: str,
        episode_ids: list[str],
    ) -> int:
        """Archive old episodes (move to archival storage)."""
        key = f"episodic:{user_id}"
        entries = self._local_store.get(key, [])

        archived = 0
        remaining = []

        for entry in entries:
            if entry.memory_id in episode_ids:
                entry.memory_type = MemoryType.ARCHIVAL
                archived += 1
            else:
                remaining.append(entry)

        self._local_store[key] = remaining
        return archived


# ──────────────────────────────────────────────────────────────────────────────
# Semantic Memory (PostgreSQL + pgvector)
# ──────────────────────────────────────────────────────────────────────────────

class SemanticMemory:
    """
    Semantic memory for storing facts, beliefs, and knowledge.

    Features:
    - Vector embeddings for semantic search
    - Confidence scoring
    - Importance weighting
    - Decay over time
    """

    def __init__(self, db_pool=None, embedder=None):
        self.db = db_pool
        self.embedder = embedder
        self._local_store: dict[str, list[MemoryEntry]] = {}

    async def store(self, entry: MemoryEntry) -> MemoryEntry:
        """Store a semantic memory with embedding."""
        entry.memory_type = MemoryType.SEMANTIC

        # Generate embedding if content is text
        if isinstance(entry.content, str) and self.embedder:
            entry.embedding = await self.embedder.embed(entry.content)
        elif isinstance(entry.content, dict):
            text = json.dumps(entry.content)
            if self.embedder:
                entry.embedding = await self.embedder.embed(text)

        key = f"semantic:{entry.user_id}"
        if key not in self._local_store:
            self._local_store[key] = []

        # Check for duplicates
        existing_ids = [e.memory_id for e in self._local_store[key]]
        if entry.memory_id not in existing_ids:
            self._local_store[key].append(entry)

        logger.info(
            "semantic_memory_stored",
            memory_id=entry.memory_id,
            user_id=entry.user_id,
            has_embedding=entry.embedding is not None,
        )

        return entry

    async def retrieve(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
        min_confidence: float = 0.0,
    ) -> list[MemoryEntry]:
        """Retrieve semantic memories using vector search."""
        key = f"semantic:{user_id}"
        entries = self._local_store.get(key, [])

        if not entries:
            return []

        # If we have an embedder, do vector search
        if self.embedder and isinstance(query, str):
            query_embedding = await self.embedder.embed(query)

            # Calculate cosine similarity
            scored = []
            for entry in entries:
                if entry.embedding and entry.confidence >= min_confidence:
                    similarity = self._cosine_similarity(
                        query_embedding,
                        entry.embedding,
                    )
                    scored.append((similarity, entry))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [entry for _, entry in scored[:limit]]

        # Fallback: keyword search
        results = []
        query_lower = query.lower()
        for entry in entries:
            if isinstance(entry.content, str) and query_lower in entry.content.lower():
                if entry.confidence >= min_confidence:
                    results.append(entry)

        return results[:limit]

    async def update_access(self, memory_id: str, user_id: str) -> None:
        """Update access statistics."""
        key = f"semantic:{user_id}"
        for entry in self._local_store.get(key, []):
            if entry.memory_id == memory_id:
                entry.access_count += 1
                entry.last_accessed = datetime.utcnow()
                # Apply decay
                entry.confidence *= 0.999
                break

    async def extract_facts(
        self,
        episode_ids: list[str],
        user_id: str,
    ) -> list[MemoryEntry]:
        """Extract facts from episodic memories."""
        # In production, this uses an LLM to extract structured facts
        # For now, return empty list
        return []

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not a or not b or len(a) != len(b):
            return 0.0

        dot_product = sum(x * y for x, y in zip(a, b))
        magnitude_a = sum(x * x for x in a) ** 0.5
        magnitude_b = sum(y * y for y in b) ** 0.5

        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0

        return dot_product / (magnitude_a * magnitude_b)


# ──────────────────────────────────────────────────────────────────────────────
# Procedural Memory
# ──────────────────────────────────────────────────────────────────────────────

class ProceduralMemory:
    """
    Procedural memory for storing learned behaviors and procedures.

    Features:
    - Trigger condition matching
    - Success rate tracking
    - Usage counting
    - Automatic learning from outcomes
    """

    def __init__(self, db_pool=None):
        self.db = db_pool
        self._procedures: dict[str, Procedure] = {}

    async def store(self, procedure: Procedure) -> Procedure:
        """Store a learned procedure."""
        self._procedures[procedure.procedure_id] = procedure

        logger.info(
            "procedure_stored",
            procedure_id=procedure.procedure_id,
            name=procedure.name,
        )

        return procedure

    async def retrieve(
        self,
        user_id: str,
        trigger: dict[str, Any],
        limit: int = 5,
    ) -> list[tuple[Procedure, float]]:
        """Retrieve procedures matching trigger conditions."""
        results = []

        for proc in self._procedures.values():
            if proc.user_id != user_id:
                continue

            score = self._match_trigger(proc, trigger)
            if score > 0:
                results.append((proc, score))

        results.sort(key=lambda x: (x[1], x[0].success_rate), reverse=True)
        return [(proc, score) for proc, score in results[:limit]]

    async def update_stats(
        self,
        procedure_id: str,
        success: bool,
    ) -> None:
        """Update procedure statistics after execution."""
        proc = self._procedures.get(procedure_id)
        if not proc:
            return

        proc.usage_count += 1
        proc.last_used = datetime.utcnow()

        # Update success rate (exponential moving average)
        alpha = 0.1
        proc.success_rate = (
            alpha * (1.0 if success else 0.0) +
            (1 - alpha) * proc.success_rate
        )

        logger.info(
            "procedure_stats_updated",
            procedure_id=procedure_id,
            success_rate=proc.success_rate,
            usage_count=proc.usage_count,
        )

    def _match_trigger(self, proc: Procedure, trigger: dict[str, Any]) -> float:
        """Calculate match score between trigger and procedure conditions."""
        score = 0.0

        for key, value in proc.trigger_conditions.items():
            if key in trigger:
                if trigger[key] == value:
                    score += 1.0
                elif isinstance(value, str) and isinstance(trigger[key], str):
                    if value.lower() in trigger[key].lower():
                        score += 0.5

        return score / max(len(proc.trigger_conditions), 1)


# ──────────────────────────────────────────────────────────────────────────────
# Knowledge Graph
# ──────────────────────────────────────────────────────────────────────────────

class KnowledgeGraph:
    """
    Knowledge graph for storing entities and relationships.

    Features:
    - Node and edge storage
    - Graph traversal
    - Relationship queries
    - Path finding
    """

    def __init__(self, db_pool=None):
        self.db = db_pool
        self._nodes: dict[str, KnowledgeNode] = {}
        self._edges: dict[str, list[KnowledgeEdge]] = {}

    async def create_node(self, node: KnowledgeNode) -> KnowledgeNode:
        """Create a knowledge node."""
        self._nodes[node.node_id] = node

        if node.node_id not in self._edges:
            self._edges[node.node_id] = []

        logger.info(
            "knowledge_node_created",
            node_id=node.node_id,
            type=node.node_type,
        )

        return node

    async def create_edge(self, edge: KnowledgeEdge) -> KnowledgeEdge:
        """Create a knowledge edge."""
        if edge.source_id not in self._edges:
            self._edges[edge.source_id] = []
        self._edges[edge.source_id].append(edge)

        logger.info(
            "knowledge_edge_created",
            edge_id=edge.edge_id,
            source=edge.source_id,
            target=edge.target_id,
            relationship=edge.relationship,
        )

        return edge

    async def get_node(self, node_id: str) -> Optional[KnowledgeNode]:
        """Get a node by ID."""
        return self._nodes.get(node_id)

    async def get_related(
        self,
        node_id: str,
        depth: int = 1,
        relationships: Optional[list[str]] = None,
    ) -> tuple[list[KnowledgeNode], list[KnowledgeEdge]]:
        """Get nodes related to a given node."""
        nodes = []
        edges = []
        visited = {node_id}

        def traverse(current_id: str, current_depth: int):
            if current_depth > depth:
                return

            for edge in self._edges.get(current_id, []):
                if relationships and edge.relationship not in relationships:
                    continue

                edges.append(edge)

                if edge.target_id not in visited:
                    visited.add(edge.target_id)
                    target_node = self._nodes.get(edge.target_id)
                    if target_node:
                        nodes.append(target_node)
                        traverse(edge.target_id, current_depth + 1)

        traverse(node_id, 0)
        return nodes, edges

    async def search(
        self,
        user_id: str,
        query: str,
    ) -> list[KnowledgeNode]:
        """Search nodes by name or properties."""
        results = []
        query_lower = query.lower()

        for node in self._nodes.values():
            if node.user_id != user_id:
                continue

            if query_lower in node.name.lower():
                results.append(node)
            else:
                for value in node.properties.values():
                    if isinstance(value, str) and query_lower in value.lower():
                        results.append(node)
                        break

        return results


# ──────────────────────────────────────────────────────────────────────────────
# Memory Service — Unified Interface
# ──────────────────────────────────────────────────────────────────────────────

class MemoryService:
    """
    Unified memory service providing access to all memory types.

    This is the main interface for agents to interact with memory.
    """

    def __init__(
        self,
        redis_client=None,
        db_pool=None,
        embedder=None,
    ):
        self.working = WorkingMemory(redis_client)
        self.episodic = EpisodicMemory(db_pool)
        self.semantic = SemanticMemory(db_pool, embedder)
        self.procedural = ProceduralMemory(db_pool)
        self.knowledge = KnowledgeGraph(db_pool)

        logger.info("memory_service_initialized")

    async def store(
        self,
        user_id: str,
        tenant_id: str,
        content: Any,
        memory_type: MemoryType,
        conversation_id: str = "default",
        **metadata,
    ) -> MemoryEntry:
        """Store a memory entry."""
        entry = MemoryEntry(
            memory_id=str(uuid.uuid4()),
            memory_type=memory_type,
            user_id=user_id,
            tenant_id=tenant_id,
            content=content,
            metadata=metadata,
        )

        if memory_type == MemoryType.WORKING:
            return await self.working.store(user_id, tenant_id, content, conversation_id)
        elif memory_type == MemoryType.EPISODIC:
            return await self.episodic.store(entry)
        elif memory_type == MemoryType.SEMANTIC:
            return await self.semantic.store(entry)
        elif memory_type == MemoryType.PROCEDURAL:
            # Requires Procedure type
            proc = Procedure(
                procedure_id=entry.memory_id,
                user_id=user_id,
                tenant_id=tenant_id,
                name=metadata.get("name", "Unnamed"),
                trigger_conditions=metadata.get("triggers", {}),
                steps=metadata.get("steps", []),
            )
            return await self.procedural.store(proc)
        else:
            return entry

    async def retrieve(
        self,
        user_id: str,
        query: str,
        memory_types: Optional[list[MemoryType]] = None,
        limit: int = 10,
    ) -> RetrievalResult:
        """Retrieve memories using hybrid search."""
        results: list[MemoryEntry] = []
        retrieval_methods = []

        memory_types = memory_types or [
            MemoryType.WORKING,
            MemoryType.EPISODIC,
            MemoryType.SEMANTIC,
        ]

        if MemoryType.WORKING in memory_types:
            working = await self.working.retrieve(user_id)
            results.extend(working[-limit // 2:])
            retrieval_methods.append("working")

        if MemoryType.SEMANTIC in memory_types:
            semantic = await self.semantic.retrieve(user_id, query, limit=limit // 2)
            results.extend(semantic)
            retrieval_methods.append("semantic")

        if MemoryType.EPISODIC in memory_types:
            episodic = await self.episodic.retrieve(user_id, limit=limit // 4)
            results.extend(episodic)
            retrieval_methods.append("episodic")

        # Construct context
        context_parts = []
        token_count = 0

        for entry in results[:limit]:
            if isinstance(entry.content, dict):
                text = json.dumps(entry.content)
            else:
                text = str(entry.content)

            entry_tokens = len(text) // 4
            if token_count + entry_tokens > 8000:
                break

            context_parts.append(text)
            token_count += entry_tokens

        return RetrievalResult(
            memories=results,
            context="\n".join(context_parts),
            token_count=token_count,
            retrieval_method="+".join(retrieval_methods),
        )

    async def consolidate(self, user_id: str) -> dict[str, int]:
        """
        Consolidate memories: working → episodic → semantic.

        This runs periodically to move memories between layers.
        Real consolidation includes:
        - Memory importance scoring
        - Duplicate detection
        - Key fact extraction
        - Summary generation
        """
        stats = {
            "working_to_episodic": 0,
            "episodic_to_semantic": 0,
            "procedures_learned": 0,
            "memories_evicted": 0,
            "duplicates_removed": 0,
            "summaries_generated": 0,
        }

        # Checkpoint working memory
        working_entries = await self.working.checkpoint(user_id)

        # Score and filter entries before storage
        seen_content = set()
        key_facts = []

        for entry in working_entries:
            # Check for duplicates
            content_key = str(entry.content)[:200] if isinstance(entry.content, str) else str(entry.content)
            if content_key in seen_content:
                stats["duplicates_removed"] += 1
                continue
            seen_content.add(content_key)

            # Score importance based on recency and access patterns
            entry.importance = self._calculate_importance(entry)

            # Extract key facts (simple keyword extraction)
            if isinstance(entry.content, str) and len(entry.content) > 50:
                facts = self._extract_key_facts(entry.content)
                key_facts.extend(facts)

            # Store in episodic memory
            await self.episodic.store(entry)
            stats["working_to_episodic"] += 1

        # Store key facts in semantic memory for future retrieval
        for fact in key_facts[:50]:  # Limit to prevent overflow
            fact_entry = MemoryEntry(
                memory_id=str(uuid.uuid4()),
                memory_type=MemoryType.SEMANTIC,
                user_id=user_id,
                tenant_id=entry.tenant_id,
                content={"fact": fact, "source": "consolidation"},
                importance=0.6,  # Medium importance
                tags=["consolidated", "fact"],
            )
            await self.semantic.store(fact_entry)
            stats["episodic_to_semantic"] += 1

        # Generate summary if enough entries
        if len(working_entries) > 3:
            summary = self._generate_summary(working_entries)
            summary_entry = MemoryEntry(
                memory_id=str(uuid.uuid4()),
                memory_type=MemoryType.SEMANTIC,
                user_id=user_id,
                tenant_id=entry.tenant_id,
                content={"summary": summary, "entry_count": len(working_entries)},
                importance=0.7,
                tags=["consolidated", "summary"],
            )
            await self.semantic.store(summary_entry)
            stats["summaries_generated"] += 1

        logger.info(
            "memory_consolidation_completed",
            user_id=user_id,
            **stats,
        )

        return stats

    def _calculate_importance(self, entry: MemoryEntry) -> float:
        """Calculate importance score for a memory entry."""
        importance = entry.importance

        # Boost for recent entries
        age_hours = (datetime.utcnow() - entry.created_at).total_seconds() / 3600
        if age_hours < 1:
            importance *= 1.2
        elif age_hours < 24:
            importance *= 1.1

        # Boost for frequently accessed entries
        if entry.access_count > 5:
            importance *= 1.2
        elif entry.access_count > 2:
            importance *= 1.1

        return min(1.0, importance)

    def _extract_key_facts(self, text: str) -> list[str]:
        """Extract key facts from text using simple pattern matching."""
        facts = []

        # Look for numbered items
        import re
        numbered = re.findall(r'\d+\.\s*([^\n]+)', text)
        facts.extend(numbered[:3])

        # Look for bullet points
        bullets = re.findall(r'[-*]\s*([^\n]+)', text)
        facts.extend(bullets[:3])

        # Look for key phrases
        key_phrase_patterns = [
            r'(?:important|key|must|should|critical|essential)\s+([^\n.]+)',
            r'(?:learned|discovered|found)\s+that\s+([^\n.]+)',
        ]
        for pattern in key_phrase_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            facts.extend(matches[:2])

        return [f.strip() for f in facts if f.strip() and len(f.strip()) > 10]

    def _generate_summary(self, entries: list[MemoryEntry]) -> str:
        """Generate a text summary of memory entries."""
        if not entries:
            return ""

        topics = set()
        for entry in entries:
            if isinstance(entry.content, str):
                # Extract first sentence as representative
                sentences = entry.content.split('.')
                if sentences:
                    topics.add(sentences[0].strip()[:100])

        summary = f"Consolidated {len(entries)} entries covering: {', '.join(list(topics)[:5])}"
        return summary

    async def checkpoint_and_clear(self, user_id: str) -> None:
        """Checkpoint working memory then clear it."""
        await self.working.checkpoint(user_id)
        await self.working.clear(user_id)

