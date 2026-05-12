"""
RasoSpeak v2 — Complete Second Brain Memory System
Multi-tier, graph-based, AI-native memory architecture.

Memory Layers:
- Working Memory (WM): Immediate context, last 5 minutes
- Short-term Memory (STM): Recent context, last 24 hours
- Long-term Memory (LTM): Permanent storage, organized in knowledge graph
- Episodic Memory: Timestamped events and conversations
- Semantic Memory: Facts, concepts, relationships

Features:
- Graph-based entity and relationship storage
- LLM-powered entity extraction
- Temporal indexing and retrieval
- Active forgetting based on importance/decay
- Memory revision and conflict resolution
- Audio conversation processing and storage
- Cross-session persistence with temporal reasoning
"""

import asyncio
import json
import logging
import re
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Callable
from dataclasses import dataclass, field
from queue import PriorityQueue

from .base_agent import BaseAgent
from config.settings import settings

log = logging.getLogger("rasospeak.brain")


# ══════════════════════════════════════════════════════
# MEMORY ENUMS & CONSTANTS
# ══════════════════════════════════════════════════════

class MemoryTier(Enum):
    WORKING = "working"      # Last 5 minutes
    SHORT_TERM = "short_term" # Last 24 hours
    LONG_TERM = "long_term"   # Permanent storage
    EPISODIC = "episodic"     # Timestamped events
    SEMANTIC = "semantic"     # Facts and concepts


class MemoryType(Enum):
    CONVERSATION = "conversation"
    FACT = "fact"
    ENTITY = "entity"
    EVENT = "event"
    DOCUMENT = "document"
    AUDIO = "audio"
    RELATIONSHIP = "relationship"
    PREFERENCE = "preference"
    GOAL = "goal"
    WEAK_WORD = "weak_word"


class Importance(Enum):
    CRITICAL = 5
    HIGH = 4
    MEDIUM = 3
    LOW = 2
    FORGOTTEN = 1


# ══════════════════════════════════════════════════════
# GRAPH NODES & EDGES
# ══════════════════════════════════════════════════════

@dataclass
class MemoryNode:
    """A node in the knowledge graph."""
    id: str
    type: MemoryType
    content: Any
    tier: MemoryTier = MemoryTier.LONG_TERM
    importance: Importance = Importance.MEDIUM
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_accessed: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    access_count: int = 0
    decay_score: float = 1.0
    metadata: dict = field(default_factory=dict)
    entities: list = field(default_factory=list)  # Extracted entities
    relationships: list = field(default_factory=list)  # Connected node IDs
    tags: list = field(default_factory=list)
    source: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "content": self.content,
            "tier": self.tier.value,
            "importance": self.importance.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "decay_score": self.decay_score,
            "metadata": self.metadata,
            "entities": self.entities,
            "relationships": self.relationships,
            "tags": self.tags,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryNode":
        return cls(
            id=data["id"],
            type=MemoryType(data["type"]),
            content=data["content"],
            tier=MemoryTier(data["tier"]),
            importance=Importance(data["importance"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            last_accessed=data["last_accessed"],
            access_count=data["access_count"],
            decay_score=data["decay_score"],
            metadata=data["metadata"],
            entities=data["entities"],
            relationships=data["relationships"],
            tags=data["tags"],
            source=data["source"],
        )


@dataclass
class MemoryEdge:
    """An edge connecting nodes in the knowledge graph."""
    id: str
    source_id: str
    target_id: str
    relation_type: str  # "related_to", "part_of", "caused_by", "temporal", etc.
    weight: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "weight": self.weight,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


# ══════════════════════════════════════════════════════
# AUDIO MEMORY STRUCTURE
# ══════════════════════════════════════════════════════

@dataclass
class AudioMemory:
    """Audio conversation memory with transcription and summary."""
    id: str
    session_id: str
    timestamp: str
    duration_seconds: float
    transcription: str
    summary: str
    speakers: list = field(default_factory=list)  # "user", "raso", "other"
    entities: list = field(default_factory=list)
    topics: list = field(default_factory=list)
    sentiment: str = "neutral"
    key_points: list = field(default_factory=list)
    questions_asked: list = field(default_factory=list)
    decisions_made: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
            "transcription": self.transcription,
            "summary": self.summary,
            "speakers": self.speakers,
            "entities": self.entities,
            "topics": self.topics,
            "sentiment": self.sentiment,
            "key_points": self.key_points,
            "questions_asked": self.questions_asked,
            "decisions_made": self.decisions_made,
            "metadata": self.metadata,
        }


# ══════════════════════════════════════════════════════
# ENTITY EXTRACTION PROMPT
# ══════════════════════════════════════════════════════

ENTITY_EXTRACTION_PROMPT = """Extract entities and relationships from the following text.

Return a JSON object with:
- "entities": list of {name, type, context} for people, places, organizations, concepts, dates, events
- "relationships": list of {subject, predicate, object} for connections between entities
- "topics": list of main topics/themes
- "sentiment": "positive", "negative", or "neutral"
- "key_points": list of important facts or statements
- "questions": list of questions asked
- "decisions": list of decisions made

Text: {text}

Return ONLY valid JSON, no markdown or explanation."""

SUMMARY_PROMPT = """Summarize the following conversation/recording in 2-3 sentences. Include key points, topics discussed, and any important decisions or conclusions.

Text: {text}

Return a brief summary only."""


# ══════════════════════════════════════════════════════
# ENHANCED MEMORY AGENT
# ══════════════════════════════════════════════════════

class SecondBrainAgent(BaseAgent):
    """
    Agent 0: SecondBrainAgent — Complete Second Brain Memory System

    Multi-tier memory architecture with:
    - Working Memory (WM): Immediate context
    - Short-term Memory (STM): Recent 24 hours
    - Long-term Memory (LTM): Permanent knowledge graph
    - Episodic Memory: Timestamped events
    - Semantic Memory: Facts and relationships

    Features:
    - Graph-based storage with entities and relationships
    - LLM-powered entity extraction
    - Temporal indexing and retrieval
    - Active forgetting based on importance decay
    - Memory revision and conflict detection
    - Audio conversation processing
    - Cross-session persistence
    """

    name = "SecondBrainAgent"

    def __init__(self):
        self._storage_path = Path(settings.shared_memory_path or "./memory")
        self._brain_path = self._storage_path / "second_brain"
        self._nodes: dict[str, MemoryNode] = {}
        self._edges: dict[str, MemoryEdge] = {}
        self._audio_memories: dict[str, AudioMemory] = {}
        self._working_memory: list[str] = []  # Node IDs in WM
        self._short_term: list[str] = []  # Node IDs in STM
        self._entity_index: dict[str, list[str]] = defaultdict(list)  # entity_name -> node_ids
        self._topic_index: dict[str, list[str]] = defaultdict(list)  # topic -> node_ids
        self._llm_client = None
        self._ensure_storage()

    def _ensure_storage(self):
        """Create storage directories."""
        self._brain_path.mkdir(parents=True, exist_ok=True)
        (self._brain_path / "nodes").mkdir(exist_ok=True)
        (self._brain_path / "edges").mkdir(exist_ok=True)
        (self._brain_path / "audio").mkdir(exist_ok=True)
        log.info(f"Second Brain storage: {self._brain_path}")

    async def initialize(self):
        """Initialize the second brain."""
        log.info("🧠 Initializing Second Brain Memory System...")

        # Initialize LLM client for entity extraction
        try:
            from .llm_client import create_llm_client
            self._llm_client = create_llm_client(settings.default_provider)
        except Exception as e:
            log.warning(f"LLM client not available: {e}")

        # Load existing memory
        await self._load_memory()

        # Start background tasks
        asyncio.create_task(self._memory_maintenance_loop())
        asyncio.create_task(self._tier_migration_loop())

        log.info(f"✅ Second Brain ready: {len(self._nodes)} nodes, {len(self._edges)} edges")

    # ══════════════════════════════════════════════════════
    # CORE MEMORY OPERATIONS
    # ══════════════════════════════════════════════════════

    async def store(
        self,
        content: Any,
        memory_type: MemoryType,
        tier: MemoryTier = MemoryTier.LONG_TERM,
        importance: Importance = Importance.MEDIUM,
        metadata: dict = None,
        tags: list = None,
        source: str = "unknown",
        extract_entities: bool = True,
    ) -> MemoryNode:
        """Store a memory node in the knowledge graph."""
        node_id = f"node_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        # Extract entities if LLM is available
        entities = []
        relationships = []
        topics = []

        if extract_entities and self._llm_client and isinstance(content, str):
            extracted = await self._extract_entities(content)
            entities = extracted.get("entities", [])
            topics = extracted.get("topics", [])

            # Create relationship edges
            for rel in extracted.get("relationships", []):
                # Relationships stored separately, will be linked later
                pass

        node = MemoryNode(
            id=node_id,
            type=memory_type,
            content=content,
            tier=tier,
            importance=importance,
            metadata=metadata or {},
            entities=[e["name"] for e in entities],
            tags=tags or [],
            source=source,
        )

        # Store node
        self._nodes[node_id] = node
        self._update_indexes(node)

        # Add to appropriate tier
        self._add_to_tier(node_id, tier)

        # Persist
        await self._save_node(node)

        log.debug(f"Stored memory: {memory_type.value}/{node_id}")

        return node

    async def recall(
        self,
        query: str = None,
        memory_type: MemoryType = None,
        tier: MemoryTier = None,
        limit: int = 20,
        include_temporal: bool = True,
        time_range: str = None,  # "1h", "24h", "7d", "30d", "all"
    ) -> list[dict]:
        """Recall memories with hybrid search."""
        results = []

        # Filter by time range
        filtered_nodes = self._nodes.values()
        if time_range:
            cutoff = self._get_time_cutoff(time_range)
            filtered_nodes = [
                n for n in filtered_nodes
                if datetime.fromisoformat(n.created_at) > cutoff
            ]

        # Filter by type
        if memory_type:
            filtered_nodes = [n for n in filtered_nodes if n.type == memory_type]

        # Filter by tier
        if tier:
            filtered_nodes = [n for n in filtered_nodes if n.tier == tier]

        # If query provided, score and rank
        if query:
            query_lower = query.lower()
            query_words = set(query_lower.split())

            for node in filtered_nodes:
                score = 0.0

                # Text similarity
                if isinstance(node.content, str):
                    content_lower = node.content.lower()
                    content_words = set(content_lower.split())

                    # Word overlap
                    overlap = len(query_words & content_words)
                    score += overlap * 0.3

                    # Exact phrase match
                    if query_lower in content_lower:
                        score += 2.0

                # Entity match
                for entity in node.entities:
                    if query_lower in entity.lower():
                        score += 1.5

                # Tag match
                for tag in node.tags:
                    if query_lower in tag.lower():
                        score += 1.0

                # Recency boost
                age_hours = (datetime.utcnow() - datetime.fromisoformat(node.created_at)).total_seconds() / 3600
                if age_hours < 1:
                    score *= 1.5
                elif age_hours < 24:
                    score *= 1.2

                # Importance boost
                score *= (node.importance.value / 3.0)

                # Access count boost
                score *= (1 + node.access_count * 0.05)

                if score > 0:
                    results.append({
                        "node": node.to_dict(),
                        "score": score,
                        "reason": self._explain_score(node, query_words),
                    })
        else:
            # No query, return recent
            results = [
                {"node": n.to_dict(), "score": 1.0, "reason": "recent"}
                for n in sorted(filtered_nodes, key=lambda x: x.last_accessed, reverse=True)[:limit]
            ]

        # Sort by score
        results.sort(key=lambda x: x["score"], reverse=True)

        return results[:limit]

    async def recall_graph(
        self,
        entity: str,
        depth: int = 2,
        relation_types: list = None,
    ) -> dict:
        """Recall related nodes through the knowledge graph."""
        if entity not in self._entity_index:
            return {"entity": entity, "connections": [], "depth": depth}

        # BFS through graph
        visited = set()
        queue = [(eid, 0) for eid in self._entity_index[entity]]
        graph_results = []

        while queue:
            node_id, current_depth = queue.pop(0)
            if node_id in visited or current_depth > depth:
                continue

            visited.add(node_id)
            node = self._nodes.get(node_id)
            if not node:
                continue

            # Get related edges
            related_edges = [
                e for e in self._edges.values()
                if e.source_id == node_id or e.target_id == node_id
            ]

            if relation_types:
                related_edges = [e for e in related_edges if e.relation_type in relation_types]

            connections = []
            for edge in related_edges:
                other_id = edge.target_id if edge.source_id == node_id else edge.source_id
                other_node = self._nodes.get(other_id)
                if other_node and other_id not in visited:
                    connections.append({
                        "node": other_node.to_dict(),
                        "relation": edge.relation_type,
                        "weight": edge.weight,
                    })
                    queue.append((other_id, current_depth + 1))

            graph_results.append({
                "node": node.to_dict(),
                "connections": connections,
                "depth": current_depth,
            })

        return {
            "entity": entity,
            "nodes": graph_results,
            "total_connections": sum(len(n["connections"]) for n in graph_results),
        }

    async def recall_temporal(
        self,
        query: str,
        start_date: str = None,
        end_date: str = None,
        limit: int = 20,
    ) -> list[dict]:
        """Recall memories within a time range."""
        results = []

        start = datetime.fromisoformat(start_date) if start_date else datetime.min
        end = datetime.fromisoformat(end_date) if end_date else datetime.utcnow()

        for node in self._nodes.values():
            created = datetime.fromisoformat(node.created_at)
            if start <= created <= end:
                # Score by relevance
                score = 0.0
                if isinstance(node.content, str):
                    query_lower = query.lower()
                    content_lower = node.content.lower()
                    if query_lower in content_lower:
                        score = 2.0
                    elif any(w in content_lower for w in query_lower.split()):
                        score = 1.0

                if score > 0:
                    results.append({
                        "node": node.to_dict(),
                        "score": score,
                        "timestamp": node.created_at,
                    })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    async def recall_conversation(
        self,
        query: str = None,
        limit: int = 10,
    ) -> list[dict]:
        """Recall past conversations specifically."""
        conv_nodes = [
            n for n in self._nodes.values()
            if n.type == MemoryType.CONVERSATION
        ]

        results = []
        for node in conv_nodes:
            score = 1.0
            if query:
                query_lower = query.lower()
                if isinstance(node.content, dict):
                    content_str = str(node.content).lower()
                    if query_lower in content_str:
                        score = 2.0
                    elif any(w in content_str for w in query_lower.split()):
                        score = 1.0

            results.append({
                "node": node.to_dict(),
                "score": score,
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    async def recall_entity(
        self,
        entity_name: str,
        limit: int = 10,
    ) -> list[dict]:
        """Recall all memories related to an entity."""
        entity_lower = entity_name.lower()
        matching_nodes = []

        for node in self._nodes.values():
            if any(entity_lower in e.lower() for e in node.entities):
                matching_nodes.append({
                    "node": node.to_dict(),
                    "score": node.access_count + 1,
                })

        # Sort by access count (most referenced first)
        matching_nodes.sort(key=lambda x: x["score"], reverse=True)
        return matching_nodes[:limit]

    async def recall_by_topic(
        self,
        topic: str,
        limit: int = 20,
    ) -> list[dict]:
        """Recall all memories related to a topic."""
        topic_lower = topic.lower()

        results = []
        for node in self._nodes.values():
            if topic_lower in [t.lower() for t in node.topics] if hasattr(node, 'topics') else topic_lower in node.tags:
                results.append({
                    "node": node.to_dict(),
                    "score": node.access_count + 1,
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    # ══════════════════════════════════════════════════════
    # ENTITY EXTRACTION (LLM-POWERED)
    # ══════════════════════════════════════════════════════

    async def _extract_entities(self, text: str) -> dict:
        """Extract entities, relationships, topics from text using LLM."""
        if not self._llm_client:
            return self._simple_entity_extraction(text)

        try:
            messages = [
                {"role": "system", "content": "You are a knowledge extraction system. Return ONLY valid JSON."},
                {"role": "user", "content": ENTITY_EXTRACTION_PROMPT.format(text=text[:4000])}
            ]

            result = await self._llm_client.chat(messages, temperature=0.1, max_tokens=2048)
            content = result.get("content", "{}")

            # Parse JSON response
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            log.warning(f"Entity extraction failed: {e}")

        return self._simple_entity_extraction(text)

    def _simple_entity_extraction(self, text: str) -> dict:
        """Simple rule-based entity extraction when LLM unavailable."""
        entities = []
        relationships = []
        topics = []

        # Extract capitalized words as potential entities
        capitalized = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        for word in capitalized[:10]:
            if len(word) > 2:
                entities.append({
                    "name": word,
                    "type": "unknown",
                    "context": "",
                })

        # Extract dates
        dates = re.findall(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b', text, re.IGNORECASE)
        for date in dates[:5]:
            entities.append({
                "name": date,
                "type": "date",
                "context": "",
            })

        # Simple topic extraction
        common_topics = ["meeting", "project", "code", "bug", "feature", "design", "review", "testing", "deployment", "documentation"]
        found_topics = [t for t in common_topics if t in text.lower()]
        topics.extend(found_topics[:5])

        return {
            "entities": entities,
            "relationships": relationships,
            "topics": topics,
            "sentiment": "neutral",
            "key_points": [],
            "questions": [],
            "decisions": [],
        }

    # ══════════════════════════════════════════════════════
    # AUDIO MEMORY PROCESSING
    # ══════════════════════════════════════════════════════

    async def store_audio_conversation(
        self,
        session_id: str,
        transcription: str,
        speakers: list = None,
        duration: float = 0,
        metadata: dict = None,
    ) -> AudioMemory:
        """Store an audio conversation with full processing pipeline."""
        audio_id = f"audio_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        # Extract entities and summarize
        extracted = await self._extract_entities(transcription)
        summary = await self._summarize(transcription)

        audio_memory = AudioMemory(
            id=audio_id,
            session_id=session_id,
            timestamp=datetime.utcnow().isoformat(),
            duration_seconds=duration,
            transcription=transcription,
            summary=summary,
            speakers=speakers or ["user", "raso"],
            entities=[e["name"] for e in extracted.get("entities", [])],
            topics=extracted.get("topics", []),
            sentiment=extracted.get("sentiment", "neutral"),
            key_points=extracted.get("key_points", []),
            questions_asked=extracted.get("questions", []),
            decisions_made=extracted.get("decisions", []),
            metadata=metadata or {},
        )

        # Store audio memory
        self._audio_memories[audio_id] = audio_memory
        await self._save_audio_memory(audio_memory)

        # Also store as conversation node
        await self.store(
            content={
                "summary": summary,
                "full_transcription": transcription,
                "speakers": speakers,
                "duration": duration,
                "key_points": extracted.get("key_points", []),
                "questions": extracted.get("questions", []),
                "decisions": extracted.get("decisions", []),
            },
            memory_type=MemoryType.AUDIO,
            importance=Importance.MEDIUM,
            tags=["audio", "conversation"] + audio_memory.topics,
            source=f"audio_session_{session_id}",
            extract_entities=True,
        )

        log.info(f"Stored audio conversation: {audio_id} ({duration:.1f}s)")

        return audio_memory

    async def recall_audio_conversations(
        self,
        query: str = None,
        session_id: str = None,
        limit: int = 10,
    ) -> list[dict]:
        """Recall audio conversations."""
        results = []

        for audio_id, audio in self._audio_memories.items():
            if session_id and audio.session_id != session_id:
                continue

            score = 0.0

            if query:
                query_lower = query.lower()
                if query_lower in audio.transcription.lower():
                    score = 3.0
                elif query_lower in audio.summary.lower():
                    score = 2.0
                elif any(query_lower in t.lower() for t in audio.topics):
                    score = 1.5
                elif any(query_lower in e.lower() for e in audio.entities):
                    score = 1.0
            else:
                score = 1.0

            if score > 0:
                results.append({
                    "audio": audio.to_dict(),
                    "score": score,
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    async def _summarize(self, text: str) -> str:
        """Generate a summary of the text."""
        if not self._llm_client:
            # Simple extractive summary
            sentences = re.split(r'[.!?]+', text)
            return ". ".join(sentences[:3])[:500]

        try:
            messages = [
                {"role": "system", "content": "You are a summarization assistant. Return ONLY the summary."},
                {"role": "user", "content": SUMMARY_PROMPT.format(text=text[:2000])}
            ]

            result = await self._llm_client.chat(messages, temperature=0.3, max_tokens=256)
            return result.get("content", text[:500])[:500]
        except Exception as e:
            log.warning(f"Summarization failed: {e}")
            return text[:500]

    # ══════════════════════════════════════════════════════
    # CONVERSATION STORAGE
    # ══════════════════════════════════════════════════════

    async def add_conversation(
        self,
        user_input: str,
        ai_response: str,
        ai_provider: str,
        context: str = None,
        metadata: dict = None,
    ) -> MemoryNode:
        """Add a conversation to memory with full processing."""
        conversation = {
            "user": user_input,
            "ai": ai_response,
            "provider": ai_provider,
            "context": context,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Determine importance based on content
        importance = Importance.MEDIUM
        if any(word in user_input.lower() for word in ["remember", "important", "note", "don't forget"]):
            importance = Importance.HIGH
        if any(word in user_input.lower() for word in ["critical", "urgent", "asap", "must"]):
            importance = Importance.CRITICAL

        node = await self.store(
            content=conversation,
            memory_type=MemoryType.CONVERSATION,
            importance=importance,
            metadata=metadata or {},
            tags=["conversation", ai_provider],
            source=f"chat_{ai_provider}",
            extract_entities=True,
        )

        # Also create user fact if appropriate
        if len(user_input) > 20 and len(user_input) < 200:
            # Extract potential facts
            extracted = await self._extract_entities(user_input)
            if extracted.get("entities") or extracted.get("key_points"):
                # Store as fact as well
                await self.store(
                    content={
                        "fact": user_input,
                        "source": "conversation",
                        "conversation_id": node.id,
                        "entities": extracted.get("entities", []),
                    },
                    memory_type=MemoryType.FACT,
                    importance=importance,
                    tags=["extracted_fact"],
                    extract_entities=True,
                )

        return node

    # ══════════════════════════════════════════════════════
    # DOCUMENT STORAGE
    # ══════════════════════════════════════════════════════

    async def add_document(
        self,
        content: str,
        title: str,
        doc_type: str = "document",
        tags: list = None,
        metadata: dict = None,
    ) -> MemoryNode:
        """Add a document to memory with entity extraction."""
        node = await self.store(
            content={
                "title": title,
                "full_content": content,
                "type": doc_type,
            },
            memory_type=MemoryType.DOCUMENT,
            importance=Importance.MEDIUM,
            metadata=metadata or {},
            tags=tags or ["document"],
            source=f"doc_{doc_type}",
            extract_entities=True,
        )

        # Extract key points and store as separate nodes
        extracted = await self._extract_entities(content)
        for point in extracted.get("key_points", [])[:5]:
            await self.store(
                content={
                    "point": point,
                    "source_document": title,
                    "document_id": node.id,
                },
                memory_type=MemoryType.FACT,
                importance=Importance.LOW,
                tags=["key_point", "document"],
                source=f"doc_{node.id}",
            )

        return node

    async def add_user_fact(
        self,
        fact: str,
        category: str = "general",
        importance: Importance = Importance.MEDIUM,
    ) -> MemoryNode:
        """Add a fact about the user."""
        node = await self.store(
            content={
                "fact": fact,
                "category": category,
            },
            memory_type=MemoryType.FACT,
            importance=importance,
            tags=["user_fact", category],
            source="user",
            extract_entities=True,
        )

        return node

    # ══════════════════════════════════════════════════════
    # RELATIONSHIP MANAGEMENT
    # ══════════════════════════════════════════════════════

    async def add_relationship(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        weight: float = 1.0,
        metadata: dict = None,
    ) -> MemoryEdge:
        """Add a relationship edge between two nodes."""
        edge_id = f"edge_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        edge = MemoryEdge(
            id=edge_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            weight=weight,
            metadata=metadata or {},
        )

        self._edges[edge_id] = edge
        await self._save_edge(edge)

        # Update node relationships
        if source_id in self._nodes:
            self._nodes[source_id].relationships.append(target_id)
        if target_id in self._nodes:
            self._nodes[target_id].relationships.append(source_id)

        log.debug(f"Added relationship: {source_id} --[{relation_type}]--> {target_id}")

        return edge

    async def find_related(
        self,
        node_id: str,
        relation_type: str = None,
        depth: int = 1,
    ) -> list[dict]:
        """Find nodes related to a given node."""
        visited = set()
        results = []
        queue = [node_id]

        current_depth = 0
        while queue and current_depth < depth:
            next_queue = []
            for current_id in queue:
                if current_id in visited:
                    continue
                visited.add(current_id)

                for edge in self._edges.values():
                    if edge.source_id == current_id or edge.target_id == current_id:
                        if relation_type and edge.relation_type != relation_type:
                            continue

                        other_id = edge.target_id if edge.source_id == current_id else edge.source_id
                        other_node = self._nodes.get(other_id)

                        if other_node:
                            results.append({
                                "node": other_node.to_dict(),
                                "relation": edge.relation_type,
                                "weight": edge.weight,
                                "depth": current_depth + 1,
                            })
                            next_queue.append(other_id)

            queue = next_queue
            current_depth += 1

        return results

    # ══════════════════════════════════════════════════════
    # MEMORY REVISION & CONFLICT DETECTION
    # ══════════════════════════════════════════════════════

    async def revise_memory(
        self,
        node_id: str,
        new_content: Any,
    ) -> MemoryNode:
        """Revise an existing memory, handling conflicts."""
        if node_id not in self._nodes:
            raise ValueError(f"Node {node_id} not found")

        node = self._nodes[node_id]
        old_content = node.content

        # Detect conflict
        conflict = await self._detect_conflict(old_content, new_content)

        # Update node
        node.content = new_content
        node.updated_at = datetime.utcnow().isoformat()
        node.metadata["revised"] = True
        node.metadata["old_content"] = old_content
        if conflict:
            node.metadata["conflict"] = conflict

        # Re-extract entities
        if isinstance(new_content, (str, dict)):
            text = str(new_content) if isinstance(new_content, dict) else new_content
            extracted = await self._extract_entities(text)
            node.entities = [e["name"] for e in extracted.get("entities", [])]
            node.tags.extend(extracted.get("topics", []))
            node.tags = list(set(node.tags))

        # Save updated node
        await self._save_node(node)

        log.info(f"Revised memory: {node_id} (conflict: {conflict})")

        return node

    async def _detect_conflict(self, old_content: Any, new_content: Any) -> dict:
        """Detect if new content conflicts with old content."""
        # Simple conflict detection for facts
        if isinstance(old_content, dict) and isinstance(new_content, dict):
            if "fact" in old_content and "fact" in new_content:
                old_fact = old_content["fact"].lower()
                new_fact = new_content["fact"].lower()

                # Check for negation indicators
                negation_words = ["not", "no", "never", "don't", "doesn't", "didn't", "won't", "wouldn't"]
                has_negation = any(word in new_fact for word in negation_words)

                if has_negation:
                    # Check if contradicting old fact
                    for word in old_fact.split():
                        if len(word) > 3 and word in new_fact:
                            return {
                                "type": "contradiction",
                                "old": old_content["fact"],
                                "new": new_content["fact"],
                            }

        return None

    # ══════════════════════════════════════════════════════
    # WORKING MEMORY (WM) — Immediate Context
    # ══════════════════════════════════════════════════════

    async def add_to_working_memory(self, node_id: str) -> None:
        """Add a node to working memory (immediate context)."""
        if node_id not in self._working_memory:
            self._working_memory.append(node_id)
            # Keep only last 20 items in WM
            if len(self._working_memory) > 20:
                self._working_memory = self._working_memory[-20:]

    async def get_working_memory(self) -> list[dict]:
        """Get current working memory contents."""
        results = []
        for node_id in self._working_memory[-10:]:  # Last 10 items
            if node_id in self._nodes:
                node = self._nodes[node_id]
                # Update last accessed
                node.last_accessed = datetime.utcnow().isoformat()
                node.access_count += 1
                results.append(node.to_dict())
        return results

    async def clear_working_memory(self) -> None:
        """Clear working memory."""
        self._working_memory = []

    # ══════════════════════════════════════════════════════
    # MEMORY CONTEXT FOR AI
    # ══════════════════════════════════════════════════════

    async def get_context_for_ai(
        self,
        ai_name: str = None,
        max_tokens: int = 4000,
    ) -> str:
        """Get formatted context string for AI prompts."""
        context_parts = []

        # Working memory (most recent)
        wm = await self.get_working_memory()
        if wm:
            wm_content = " | ".join([
                f"{n['type']}: {str(n['content'])[:100]}"
                for n in wm[-5:]
            ])
            context_parts.append(f"[Recent: {wm_content}]")

        # Recent conversations
        recent_convs = await self.recall_conversation(limit=5)
        if recent_convs:
            conv_summary = " | ".join([
                f"Q: {str(n['node']['content']).split('user')[1][:80] if 'user' in str(n['node']['content']) else '...'}"
                for n in recent_convs
            ])
            context_parts.append(f"[Recent Chats: {conv_summary}]")

        # User profile facts
        fact_nodes = [
            n for n in self._nodes.values()
            if n.type == MemoryType.FACT and n.importance.value >= Importance.HIGH.value
        ]
        if fact_nodes:
            facts = ", ".join([
                str(f.content.get("fact", f.content))[:50]
                for f in fact_nodes[:5]
            ])
            context_parts.append(f"[Key Facts: {facts}]")

        # Entity context
        entity_nodes = [
            n for n in self._nodes.values()
            if n.type == MemoryType.ENTITY and n.access_count > 0
        ]
        if entity_nodes:
            entities = ", ".join([n.content.get("name", str(n.content))[:30] for n in entity_nodes[:10]])
            context_parts.append(f"[Known Entities: {entities}]")

        # Weak words if coaching
        weak_nodes = [n for n in self._nodes.values() if n.type == MemoryType.WEAK_WORD]
        if weak_nodes:
            weak_words = ", ".join([str(w.content)[:30] for w in weak_nodes[:10]])
            context_parts.append(f"[Areas to Improve: {weak_words}]")

        return "\n".join(context_parts) if context_parts else ""

    # ══════════════════════════════════════════════════════
    # FORGETTING & DECAY
    # ══════════════════════════════════════════════════════

    async def forget(
        self,
        node_id: str,
        reason: str = "user_request",
    ) -> dict:
        """Remove a memory node (forgetting)."""
        if node_id not in self._nodes:
            return {"error": "Node not found"}

        node = self._nodes[node_id]
        node.metadata["forgotten"] = True
        node.metadata["forgotten_at"] = datetime.utcnow().isoformat()
        node.metadata["forget_reason"] = reason

        # Remove from tier lists
        if node_id in self._working_memory:
            self._working_memory.remove(node_id)

        # Save updated node
        await self._save_node(node)

        # Remove from memory
        del self._nodes[node_id]

        log.info(f"Forgotten: {node_id} ({reason})")

        return {"forgotten": node_id, "reason": reason}

    async def auto_forget_low_importance(self, threshold: float = 0.2) -> dict:
        """Automatically forget memories below importance threshold."""
        forgotten = []

        for node_id, node in list(self._nodes.items()):
            if node.decay_score < threshold and node.importance.value <= Importance.LOW.value:
                # Check if recently accessed
                last_access = datetime.fromisoformat(node.last_accessed)
                days_since_access = (datetime.utcnow() - last_access).days

                if days_since_access > 30:
                    result = await self.forget(node_id, "auto_decay")
                    forgotten.append(node_id)

        return {
            "forgotten_count": len(forgotten),
            "forgotten_ids": forgotten,
        }

    def _calculate_decay(self, node: MemoryNode) -> float:
        """Calculate decay score for a node based on age, importance, access."""
        age_days = (datetime.utcnow() - datetime.fromisoformat(node.created_at)).days
        days_since_access = (datetime.utcnow() - datetime.fromisoformat(node.last_accessed)).days

        # Base decay (0.9 per month)
        base_decay = 0.9 ** (age_days / 30)

        # Access frequency boost
        access_boost = 1 + (node.access_count * 0.02)

        # Importance boost (higher importance = slower decay)
        importance_factor = 1 + (node.importance.value / 10)

        # Recency of access
        access_decay = 0.95 ** days_since_access

        decay = base_decay * access_boost * importance_factor * access_decay

        return min(1.0, max(0.0, decay))

    # ══════════════════════════════════════════════════════
    # PREFERENCES & USER PROFILE
    # ══════════════════════════════════════════════════════

    async def get_user_preferences(self) -> dict:
        """Get user preferences from memory."""
        pref_nodes = [n for n in self._nodes.values() if n.type == MemoryType.PREFERENCE]

        preferences = {}
        for node in pref_nodes:
            if isinstance(node.content, dict):
                preferences.update(node.content)

        return preferences

    async def set_user_preference(self, key: str, value: Any) -> dict:
        """Set a user preference."""
        await self.store(
            content={key: value},
            memory_type=MemoryType.PREFERENCE,
            importance=Importance.HIGH,
            tags=["preference", key],
            source="user_setting",
            extract_entities=False,
        )

        return {"stored": True, "key": key, "value": value}

    # ══════════════════════════════════════════════════════
    # WEAK WORDS TRACKING
    # ══════════════════════════════════════════════════════

    async def add_weak_word(
        self,
        word: str,
        context: str = None,
        session_id: str = None,
    ) -> MemoryNode:
        """Add a word the user struggles with."""
        node = await self.store(
            content={
                "word": word,
                "context": context,
                "session_id": session_id,
                "count": 1,
            },
            memory_type=MemoryType.WEAK_WORD,
            importance=Importance.MEDIUM,
            tags=["weak_word", "speech"],
            source="coaching",
            extract_entities=False,
        )

        return node

    async def get_weak_words(self, limit: int = 20) -> list[dict]:
        """Get all weak words, sorted by frequency."""
        weak_nodes = [n for n in self._nodes.values() if n.type == MemoryType.WEAK_WORD]

        weak_list = []
        for node in weak_nodes:
            count = node.content.get("count", 1) + node.access_count
            weak_list.append({
                "word": node.content.get("word", str(node.content)),
                "count": count,
                "context": node.content.get("context"),
            })

        weak_list.sort(key=lambda x: x["count"], reverse=True)
        return weak_list[:limit]

    # ══════════════════════════════════════════════════════
    # SESSION SUMMARIES
    # ══════════════════════════════════════════════════════

    async def save_session_summary(
        self,
        session_id: str,
        summary: dict,
    ) -> MemoryNode:
        """Save a session summary."""
        node = await self.store(
            content={
                "session_id": session_id,
                "summary": summary,
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "time": datetime.utcnow().strftime("%H:%M"),
            },
            memory_type=MemoryType.EVENT,
            tier=MemoryTier.EPISODIC,
            importance=Importance.MEDIUM,
            tags=["session", session_id],
            source=f"session_{session_id}",
            extract_entities=True,
        )

        return node

    async def get_recent_sessions(self, limit: int = 10) -> list[dict]:
        """Get recent session summaries."""
        event_nodes = [
            n for n in self._nodes.values()
            if n.type == MemoryType.EVENT
        ]

        results = []
        for node in event_nodes:
            if isinstance(node.content, dict) and "session_id" in node.content:
                results.append(node.to_dict())

        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results[:limit]

    # ══════════════════════════════════════════════════════
    # STATISTICS & ANALYTICS
    # ══════════════════════════════════════════════════════

    async def get_memory_stats(self) -> dict:
        """Get comprehensive memory statistics."""
        type_counts = defaultdict(int)
        tier_counts = defaultdict(int)
        importance_counts = defaultdict(int)

        for node in self._nodes.values():
            type_counts[node.type.value] += 1
            tier_counts[node.tier.value] += 1
            importance_counts[node.importance.name] += 1

        # Entity index stats
        entity_count = len(self._entity_index)
        avg_entities_per_node = sum(len(n.entities) for n in self._nodes.values()) / max(1, len(self._nodes))

        # Audio stats
        total_audio_duration = sum(a.duration_seconds for a in self._audio_memories.values())

        # Decay stats
        avg_decay = sum(n.decay_score for n in self._nodes.values()) / max(1, len(self._nodes))

        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "total_audio_conversations": len(self._audio_memories),
            "total_audio_duration_seconds": total_audio_duration,
            "type_counts": dict(type_counts),
            "tier_counts": dict(tier_counts),
            "importance_counts": dict(importance_counts),
            "entity_index_size": entity_count,
            "avg_entities_per_node": round(avg_entities_per_node, 2),
            "avg_decay_score": round(avg_decay, 3),
            "working_memory_size": len(self._working_memory),
        }

    async def get_memory_size_mb(self) -> float:
        """Estimate memory size in MB."""
        import sys

        nodes_size = sum(sys.getsizeof(str(n.to_dict())) for n in self._nodes.values())
        edges_size = sum(sys.getsizeof(str(e.to_dict())) for e in self._edges.values())
        audio_size = sum(sys.getsizeof(str(a.to_dict())) for a in self._audio_memories.values())

        total_bytes = nodes_size + edges_size + audio_size
        return total_bytes / (1024 * 1024)

    # ══════════════════════════════════════════════════════
    # TIER MANAGEMENT
    # ══════════════════════════════════════════════════════

    def _add_to_tier(self, node_id: str, tier: MemoryTier) -> None:
        """Add node to appropriate tier."""
        if tier == MemoryTier.WORKING:
            self._add_to_working_memory(node_id)
        elif tier == MemoryTier.SHORT_TERM:
            if node_id not in self._short_term:
                self._short_term.append(node_id)
                if len(self._short_term) > 1000:
                    self._short_term = self._short_term[-1000:]

    async def _tier_migration_loop(self) -> None:
        """Background task: migrate nodes between tiers based on age."""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes

                now = datetime.utcnow()

                # Migrate STM nodes to LTM after 24 hours
                for node_id in list(self._short_term):
                    node = self._nodes.get(node_id)
                    if node:
                        age_hours = (now - datetime.fromisoformat(node.created_at)).total_seconds() / 3600
                        if age_hours > 24:
                            node.tier = MemoryTier.LONG_TERM
                            self._short_term.remove(node_id)
                            await self._save_node(node)

                # Update working memory (clear after 5 minutes of inactivity)
                if self._working_memory:
                    oldest = self._working_memory[0] if self._working_memory else None
                    if oldest and oldest in self._nodes:
                        node = self._nodes[oldest]
                        age_minutes = (now - datetime.fromisoformat(node.last_accessed)).total_seconds() / 60
                        if age_minutes > 5:
                            self._working_memory.pop(0)

            except Exception as e:
                log.error(f"Tier migration error: {e}")

    async def _memory_maintenance_loop(self) -> None:
        """Background task: decay, cleanup, optimization."""
        while True:
            try:
                await asyncio.sleep(600)  # Check every 10 minutes

                # Update decay scores
                for node_id, node in list(self._nodes.items()):
                    old_decay = node.decay_score
                    node.decay_score = self._calculate_decay(node)

                    # Auto-forget very low decay
                    if node.decay_score < 0.05 and node.importance.value <= Importance.LOW.value:
                        await self.forget(node_id, "decay_below_threshold")

                # Cleanup orphaned edges
                for edge_id, edge in list(self._edges.items()):
                    if edge.source_id not in self._nodes or edge.target_id not in self._nodes:
                        del self._edges[edge_id]

                log.debug(f"Memory maintenance: {len(self._nodes)} nodes, {len(self._edges)} edges")

            except Exception as e:
                log.error(f"Memory maintenance error: {e}")

    # ══════════════════════════════════════════════════════
    # INDEX MANAGEMENT
    # ══════════════════════════════════════════════════════

    def _update_indexes(self, node: MemoryNode) -> None:
        """Update entity and topic indexes."""
        # Entity index
        for entity in node.entities:
            entity_lower = entity.lower()
            if entity_lower not in self._entity_index:
                self._entity_index[entity_lower] = []
            self._entity_index[entity_lower].append(node.id)

        # Topic index
        for tag in node.tags:
            tag_lower = tag.lower()
            if tag_lower not in self._topic_index:
                self._topic_index[tag_lower] = []
            self._topic_index[tag_lower].append(node.id)

    # ══════════════════════════════════════════════════════
    # PERSISTENCE
    # ══════════════════════════════════════════════════════

    async def _load_memory(self) -> None:
        """Load all memory from disk."""
        # Load nodes
        nodes_dir = self._brain_path / "nodes"
        if nodes_dir.exists():
            for node_file in nodes_dir.glob("*.json"):
                try:
                    node_data = json.loads(node_file.read_text())
                    node = MemoryNode.from_dict(node_data)
                    self._nodes[node.id] = node

                    # Rebuild indexes
                    self._update_indexes(node)
                except Exception as e:
                    log.warning(f"Failed to load node {node_file}: {e}")

        # Load edges
        edges_dir = self._brain_path / "edges"
        if edges_dir.exists():
            for edge_file in edges_dir.glob("*.json"):
                try:
                    edge_data = json.loads(edge_file.read_text())
                    edge = MemoryEdge(**edge_data)
                    self._edges[edge.id] = edge
                except Exception as e:
                    log.warning(f"Failed to load edge {edge_file}: {e}")

        # Load audio memories
        audio_dir = self._brain_path / "audio"
        if audio_dir.exists():
            for audio_file in audio_dir.glob("*.json"):
                try:
                    audio_data = json.loads(audio_file.read_text())
                    audio = AudioMemory(**audio_data)
                    self._audio_memories[audio.id] = audio
                except Exception as e:
                    log.warning(f"Failed to load audio {audio_file}: {e}")

        log.info(f"Loaded: {len(self._nodes)} nodes, {len(self._edges)} edges, {len(self._audio_memories)} audio")

    async def _save_node(self, node: MemoryNode) -> None:
        """Save a node to disk."""
        node_file = self._brain_path / "nodes" / f"{node.id}.json"
        node_file.write_text(json.dumps(node.to_dict(), indent=2))

    async def _save_edge(self, edge: MemoryEdge) -> None:
        """Save an edge to disk."""
        edge_file = self._brain_path / "edges" / f"{edge.id}.json"
        edge_file.write_text(json.dumps(edge.to_dict(), indent=2))

    async def _save_audio_memory(self, audio: AudioMemory) -> None:
        """Save an audio memory to disk."""
        audio_file = self._brain_path / "audio" / f"{audio.id}.json"
        audio_file.write_text(json.dumps(audio.to_dict(), indent=2))

    # ══════════════════════════════════════════════════════
    # HELPER METHODS
    # ══════════════════════════════════════════════════════

    def _get_time_cutoff(self, time_range: str) -> datetime:
        """Get time cutoff based on range string."""
        now = datetime.utcnow()
        if time_range == "1h":
            return now - timedelta(hours=1)
        elif time_range == "24h":
            return now - timedelta(hours=24)
        elif time_range == "7d":
            return now - timedelta(days=7)
        elif time_range == "30d":
            return now - timedelta(days=30)
        else:
            return datetime.min

    def _explain_score(self, node: MemoryNode, query_words: set) -> str:
        """Explain why a node scored highly."""
        reasons = []

        if isinstance(node.content, str):
            content_lower = node.content.lower()
            for word in query_words:
                if word in content_lower:
                    reasons.append(f"contains '{word}'")
                    break

        if node.entities:
            reasons.append(f"has {len(node.entities)} entities")

        if node.access_count > 5:
            reasons.append(f"accessed {node.access_count} times")

        if node.importance.value >= Importance.HIGH.value:
            reasons.append("high importance")

        return ", ".join(reasons) if reasons else "recent"

    async def clear_all(self) -> dict:
        """Clear all memory."""
        self._nodes.clear()
        self._edges.clear()
        self._audio_memories.clear()
        self._working_memory.clear()
        self._short_term.clear()
        self._entity_index.clear()
        self._topic_index.clear()

        # Clear disk storage
        for node_file in (self._brain_path / "nodes").glob("*.json"):
            node_file.unlink()
        for edge_file in (self._brain_path / "edges").glob("*.json"):
            edge_file.unlink()
        for audio_file in (self._brain_path / "audio").glob("*.json"):
            audio_file.unlink()

        log.info("All memory cleared")

        return {
            "status": "cleared",
            "nodes": 0,
            "edges": 0,
            "audio": 0,
        }

    async def shutdown(self):
        """Cleanup and save all memory."""
        # Save all pending changes
        for node in self._nodes.values():
            await self._save_node(node)

        for edge in self._edges.values():
            await self._save_edge(edge)

        log.info("SecondBrainAgent shut down")