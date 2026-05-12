"""
RasoSpeak v2 — Advanced Second Brain Memory System
Phase 4 & 5: Persona, Goals, Skills, Memory Compression & Intelligence
Phase 6: Embeddings, Sync, Security, Visualization, Proactive Intelligence, Integrations

This extends the Second Brain with:
- User Persona extraction and tracking
- Goal management and progress tracking
- Skills/knowledge tracking
- Memory summarization and compression
- Cross-reference automatic linking
- Emotional intelligence
- Memory quality scoring
- Predictive memory
- Vector embeddings for semantic search
- Cross-device sync and backup/restore
- Encrypted storage and privacy controls
- Memory visualization
- Obsidian/external API sync
- Proactive memory surfacing
- Pattern detection
"""

import asyncio
import base64
import gzip
import hashlib
import json
import logging
import os
import pickle
import re
import time
import uuid
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING
from dataclasses import dataclass, field
from typing import Callable

from .base_agent import BaseAgent
from config.settings import settings

log = logging.getLogger("rasospeak.brain")


# ══════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════

class MemoryTier(Enum):
    WORKING = "working"
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


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
    SKILL = "skill"
    PERSONA = "persona"
    EMOTION = "emotion"


class Importance(Enum):
    CRITICAL = 5
    HIGH = 4
    MEDIUM = 3
    LOW = 2
    FORGOTTEN = 1


class GoalStatus(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"
    ABANDONED = "abandoned"


class SkillLevel(Enum):
    EXPERT = 5
    ADVANCED = 4
    INTERMEDIATE = 3
    BEGINNER = 2
    NOVICE = 1


class PrivacyLevel(Enum):
    PUBLIC = "public"          # Can be shared/exported freely
    PRIVATE = "private"        # Encrypted, requires auth to access
    RESTRICTED = "restricted" # Only accessible via explicit API call
    SENSITIVE = "sensitive"    # Encrypted + masked in exports


class SyncStatus(Enum):
    SYNCED = "synced"
    PENDING_UPLOAD = "pending_upload"
    PENDING_DOWNLOAD = "pending_download"
    CONFLICT = "conflict"


class SyncProvider(Enum):
    LOCAL = "local"
    HUGGINGFACE = "huggingface"
    OBSIDIAN = "obsidian"
    NOTION = "notion"


# ══════════════════════════════════════════════════════
# PHASE 6: EMBEDDINGS & SEMANTIC SEARCH
# ══════════════════════════════════════════════════════

class EmbeddingIndex:
    """Lightweight vector index using numpy for semantic search."""

    def __init__(self, embedding_dim: int = 384):
        self._dim = embedding_dim
        self._node_ids: list[str] = []
        self._vectors: list[list[float]] = []
        self._index_path: Optional[Path] = None
        self._model = None
        self._model_name = "all-MiniLM-L6-v2"
        self._model_lock = asyncio.Lock()

    async def _load_model(self):
        """Lazily load the embedding model."""
        async with self._model_lock:
            if self._model is not None:
                return
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
                log.info(f"✅ Embedding model loaded: {self._model_name}")
            except ImportError:
                log.warning("sentence-transformers not available, using TF-IDF fallback")
                self._model = "tfidf"
            except Exception as e:
                log.warning(f"Failed to load embedding model: {e}, using TF-IDF fallback")
                self._model = "tfidf"

    def _encode_tfidf(self, texts: list[str]) -> list[list[float]]:
        """TF-IDF fallback when sentence-transformers unavailable."""
        if not texts:
            return []
        vocab = set()
        for text in texts:
            vocab.update(text.lower().split())
        vocab = sorted(list(vocab))[:1000]
        vocab_map = {w: i for i, w in enumerate(vocab)}

        vectors = []
        for text in texts:
            vec = [0.0] * len(vocab)
            words = text.lower().split()
            tf = Counter(words)
            for word, count in tf.items():
                if word in vocab_map:
                    idf = 1.0  # Simplified
                    vec[vocab_map[word]] = count * idf
            # Normalize
            norm = (sum(v * v for v in vec) ** 0.5) or 1.0
            vec = [v / norm for v in vec]
            vectors.append(vec)
        return vectors

    def _cosine_sim(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = (sum(x * x for x in a) ** 0.5) or 1.0
        norm_b = (sum(x * x for x in b) ** 0.5) or 1.0
        return dot / (norm_a * norm_b)

    async def encode(self, text: str) -> list[float]:
        """Encode a single text to a vector."""
        await self._load_model()
        if self._model == "tfidf":
            return self._encode_tfidf([text])[0]
        try:
            return self._model.encode(text).tolist()
        except Exception:
            return self._encode_tfidf([text])[0]

    async def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Encode multiple texts."""
        await self._load_model()
        if self._model == "tfidf":
            return self._encode_tfidf(texts)
        try:
            return self._model.encode(texts).tolist()
        except Exception:
            return self._encode_tfidf(texts)

    def add(self, node_id: str, vector: list[float]):
        """Add a vector to the index."""
        self._node_ids.append(node_id)
        self._vectors.append(vector)

    def remove(self, node_id: str) -> bool:
        """Remove a vector from the index."""
        try:
            idx = self._node_ids.index(node_id)
            self._node_ids.pop(idx)
            self._vectors.pop(idx)
            return True
        except ValueError:
            return False

    def search(self, query_vector: list[float], k: int = 10) -> list[tuple[str, float]]:
        """Find top-k nearest neighbors. Returns list of (node_id, score)."""
        scores = [(node_id, self._cosine_sim(query_vector, vec)) for node_id, vec in zip(self._node_ids, self._vectors)]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:k]

    def save(self, path: Path):
        """Save index to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"node_ids": self._node_ids, "vectors": self._vectors, "dim": self._dim}
        with open(path, "wb") as f:
            pickle.dump(data, f)

    def load(self, path: Path):
        """Load index from disk."""
        if path.exists():
            try:
                with open(path, "rb") as f:
                    data = pickle.load(f)
                self._node_ids = data["node_ids"]
                self._vectors = data["vectors"]
                self._dim = data.get("dim", self._dim)
                log.info(f"Loaded embedding index: {len(self._node_ids)} vectors")
            except Exception as e:
                log.warning(f"Failed to load embedding index: {e}")

    def clear(self):
        """Clear the index."""
        self._node_ids.clear()
        self._vectors.clear()


# ══════════════════════════════════════════════════════
# PHASE 6: BACKUP & SYNC TRACKING
# ══════════════════════════════════════════════════════

@dataclass
class SyncRecord:
    node_id: str
    action: str  # "created" | "updated" | "deleted"
    timestamp: str
    hash: str
    sync_status: SyncStatus = SyncStatus.SYNCED
    synced_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "action": self.action,
            "timestamp": self.timestamp,
            "hash": self.hash,
            "sync_status": self.sync_status.value,
            "synced_at": self.synced_at,
        }


# ══════════════════════════════════════════════════════
# PHASE 6: MEMORY VERSION SNAPSHOT
# ══════════════════════════════════════════════════════

@dataclass
class MemorySnapshot:
    id: str
    timestamp: str
    node_count: int
    edge_count: int
    size_mb: float
    checksum: str
    description: str = ""
    tags: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "size_mb": self.size_mb,
            "checksum": self.checksum,
            "description": self.description,
            "tags": self.tags,
        }


# ══════════════════════════════════════════════════════
# PHASE 6: MEMORY PATTERN
# ══════════════════════════════════════════════════════

@dataclass
class MemoryPattern:
    id: str
    pattern_type: str  # "temporal" | "sequential" | "topical"
    description: str
    nodes: list  # node IDs involved
    confidence: float
    first_seen: str
    last_seen: str
    occurrences: int = 1

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pattern_type": self.pattern_type,
            "description": self.description,
            "nodes": self.nodes,
            "confidence": self.confidence,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "occurrences": self.occurrences,
        }


# ══════════════════════════════════════════════════════
# ENHANCED NODES & EDGES
# ══════════════════════════════════════════════════════

@dataclass
class MemoryNode:
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
    entities: list = field(default_factory=list)
    relationships: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    source: str = "unknown"
    confidence: float = 1.0  # Quality score
    version: int = 1  # For tracking changes

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
            "confidence": self.confidence,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryNode":
        return cls(
            id=data["id"],
            type=MemoryType(data["type"]),
            content=data["content"],
            tier=MemoryTier(data.get("tier", "long_term")),
            importance=Importance(data.get("importance", 3)),
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
            confidence=data.get("confidence", 1.0),
            version=data.get("version", 1),
        )


@dataclass
class MemoryEdge:
    id: str
    source_id: str
    target_id: str
    relation_type: str
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


@dataclass
class AudioMemory:
    id: str
    session_id: str
    timestamp: str
    duration_seconds: float
    transcription: str
    summary: str
    speakers: list = field(default_factory=list)
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
# PERSONA & USER PROFILE
# ══════════════════════════════════════════════════════

@dataclass
class UserPersona:
    """Complete user profile extracted from conversations."""
    id: str
    name: str = "Unknown"
    bio: str = ""
    interests: list = field(default_factory=list)
    goals: list = field(default_factory=list)
    skills: dict = field(default_factory=dict)  # skill_name -> level
    preferences: dict = field(default_factory=dict)
    communication_style: str = "neutral"
    values: list = field(default_factory=list)
    personality_traits: list = field(default_factory=list)
    strengths: list = field(default_factory=list)
    weaknesses: list = field(default_factory=list)
    relationships: dict = field(default_factory=dict)  # person_name -> relationship_type
    emotional_patterns: dict = field(default_factory=dict)
    learning_style: str = "unknown"
    work_style: str = "unknown"
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    confidence: float = 0.0  # How confident we are in this persona

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "bio": self.bio,
            "interests": self.interests,
            "goals": self.goals,
            "skills": self.skills,
            "preferences": self.preferences,
            "communication_style": self.communication_style,
            "values": self.values,
            "personality_traits": self.personality_traits,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "relationships": self.relationships,
            "emotional_patterns": self.emotional_patterns,
            "learning_style": self.learning_style,
            "work_style": self.work_style,
            "last_updated": self.last_updated,
            "confidence": self.confidence,
        }


# ══════════════════════════════════════════════════════
# GOAL TRACKING
# ══════════════════════════════════════════════════════

@dataclass
class Goal:
    """A tracked goal with progress."""
    id: str
    title: str
    description: str
    status: GoalStatus = GoalStatus.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    deadline: str = None
    progress: float = 0.0  # 0.0 to 1.0
    milestones: list = field(default_factory=list)
    sub_goals: list = field(default_factory=list)
    blockers: list = field(default_factory=list)
    related_memories: list = field(default_factory=list)  # node IDs
    priority: int = 3  # 1 (highest) to 5 (lowest)
    tags: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "created_at": self.created_at,
            "deadline": self.deadline,
            "progress": self.progress,
            "milestones": self.milestones,
            "sub_goals": self.sub_goals,
            "blockers": self.blockers,
            "related_memories": self.related_memories,
            "priority": self.priority,
            "tags": self.tags,
        }


# ══════════════════════════════════════════════════════
# SKILL TRACKING
# ══════════════════════════════════════════════════════

@dataclass
class Skill:
    """A tracked skill with proficiency."""
    id: str
    name: str
    category: str
    level: SkillLevel = SkillLevel.NOVICE
    experience_years: float = 0.0
    last_practiced: str = None
    practice_count: int = 0
    certifications: list = field(default_factory=list)
    projects: list = field(default_factory=list)  # node IDs
    related_skills: list = field(default_factory=list)  # skill IDs
    learning_resources: list = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "level": self.level.value,
            "experience_years": self.experience_years,
            "last_practiced": self.last_practiced,
            "practice_count": self.practice_count,
            "certifications": self.certifications,
            "projects": self.projects,
            "related_skills": self.related_skills,
            "learning_resources": self.learning_resources,
            "notes": self.notes,
        }


# ══════════════════════════════════════════════════════
# MEMORY VERSION TRACKING
# ══════════════════════════════════════════════════════

@dataclass
class MemoryVersion:
    """Tracks changes to memory over time."""
    id: str
    node_id: str
    version: int
    old_content: Any
    new_content: Any
    change_type: str  # "created", "updated", "revised", "forgotten"
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "node_id": self.node_id,
            "version": self.version,
            "old_content": self.old_content,
            "new_content": self.new_content,
            "change_type": self.change_type,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


# ══════════════════════════════════════════════════════
# MEMORY SUMMARY (for compression)
# ══════════════════════════════════════════════════════

@dataclass
class MemorySummary:
    """Compressed summary of old memories."""
    id: str
    original_ids: list  # IDs of compressed nodes
    summary_text: str
    key_entities: list = field(default_factory=list)
    key_points: list = field(default_factory=list)
    sentiment: str = "neutral"
    time_range: tuple = None  # (start, end)
    compression_ratio: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "original_ids": self.original_ids,
            "summary_text": self.summary_text,
            "key_entities": self.key_entities,
            "key_points": self.key_points,
            "sentiment": self.sentiment,
            "time_range": self.time_range,
            "compression_ratio": self.compression_ratio,
            "created_at": self.created_at,
        }


# ══════════════════════════════════════════════════════
# PROMPTS FOR LLM ANALYSIS
# ══════════════════════════════════════════════════════

PERSONA_EXTRACTION_PROMPT = """Analyze the user's conversation and extract their persona information.

Return a JSON object with:
- "name": User's name if mentioned
- "bio": Brief biography/description
- "interests": List of interests/hobbies
- "communication_style": How they communicate (formal/casual/technical/etc)
- "personality_traits": Key personality traits observed
- "values": What they seem to value
- "strengths": Observed strengths
- "weaknesses": Observed weaknesses or areas for improvement
- "work_style": How they approach work
- "learning_style": How they learn best
- "relationships": Important relationships mentioned

Be specific and only include information that is clearly present in the conversation.
If something is not mentioned, don't make it up.

Conversation: {conversation}

Return ONLY valid JSON."""

GOAL_EXTRACTION_PROMPT = """Extract goals and intentions from the conversation.

Return a JSON object with:
- "goals": List of {title, description, deadline, priority} for each goal mentioned
- "decisions": List of decisions made
- "commitments": Things the user committed to
- "plans": Future plans mentioned

Conversation: {conversation}

Return ONLY valid JSON."""

SKILL_EXTRACTION_PROMPT = """Extract skills and knowledge from the conversation.

Return a JSON object with:
- "skills": List of {name, category, level, context} for skills mentioned
- "learning": Things the user wants to learn
- "knowledge_areas": Topics they seem knowledgeable about

Conversation: {conversation}

Return ONLY valid JSON."""

MEMORY_COMPRESSION_PROMPT = """Compress the following memories into a concise summary.

Keep:
- Key facts and decisions
- Important entities mentioned
- Main topics discussed
- User's goals or intentions
- Any emotional tone

Memories: {memories}

Return a JSON with:
- "summary": Compressed summary text (max 500 words)
- "key_entities": List of important entities
- "key_points": List of 5-10 most important points
- "sentiment": Overall emotional tone
- "topics": Main topics covered

Return ONLY valid JSON."""

CONFLICT_DETECTION_PROMPT = """Detect conflicts between old and new information.

Old information: {old}
New information: {new}

Return a JSON with:
- "is_conflict": true/false
- "conflict_type": "contradiction", "update", or "clarification"
- "resolution_suggestion": How to resolve the conflict

Return ONLY valid JSON."""

CROSS_REFERENCE_PROMPT = """Find connections between memories.

Memory 1: {memory1}
Memory 2: {memory2}

Return a JSON with:
- "has_connection": true/false
- "relation_type": "related", "causes", "contradicts", "part_of", "temporal", "unknown"
- "connection_strength": 0.0 to 1.0
- "explanation": Brief explanation of the connection

Return ONLY valid JSON."""

EMOTION_ANALYSIS_PROMPT = """Analyze the emotional content of this conversation.

Return a JSON with:
- "overall_sentiment": "positive", "negative", "neutral", "mixed"
- "emotions": List of specific emotions detected
- "emotional_arc": How emotions changed during the conversation
- "key_moments": Emotional highlights
- "user_mood": User's mood at end

Conversation: {conversation}

Return ONLY valid JSON."""


# ══════════════════════════════════════════════════════
# ENHANCED SECOND BRAIN AGENT
# ══════════════════════════════════════════════════════

class SecondBrainAgent(BaseAgent):
    """
    Agent 0: SecondBrainAgent — Complete Second Brain Memory System
    Phase 4 & 5: Persona, Goals, Skills, Compression & Intelligence

    Extended Features:
    - User Persona extraction and tracking
    - Goal management with progress tracking
    - Skills/knowledge tracking
    - Memory compression and summarization
    - Cross-reference automatic linking
    - Emotional intelligence
    - Memory quality scoring
    - Predictive memory suggestions
    """

    name = "SecondBrainAgent"

    def __init__(self):
        self._storage_path = Path(settings.shared_memory_path or "./memory")
        self._brain_path = self._storage_path / "second_brain"
        self._nodes: dict[str, MemoryNode] = {}
        self._edges: dict[str, MemoryEdge] = {}
        self._audio_memories: dict[str, AudioMemory] = {}
        self._working_memory: list[str] = []
        self._short_term: list[str] = []
        self._entity_index: dict[str, list[str]] = defaultdict(list)
        self._topic_index: dict[str, list[str]] = defaultdict(list)
        # O(1) content-hash → node-id lookup for deduplication
        self._content_index: dict[str, str] = {}
        # Write protection for shared dicts
        self._node_lock = asyncio.Lock()
        self._goal_lock = asyncio.Lock()
        # Graceful shutdown flag
        self._running = True
        # Memory cap
        self._MAX_NODES = 100_000
        self._llm_client = None
        self._persona: Optional[UserPersona] = None
        self._goals: dict[str, Goal] = {}
        self._skills: dict[str, Skill] = {}
        self._versions: dict[str, list[MemoryVersion]] = defaultdict(list)
        self._summaries: dict[str, MemorySummary] = {}

        # ══════════════════════════════════════════════════════
        # PHASE 6: EMBEDDINGS & SEMANTIC SEARCH
        # ══════════════════════════════════════════════════════
        self._embedding_index = EmbeddingIndex()
        self._embeddings_path = self._brain_path / "embeddings.pkl"

        # ══════════════════════════════════════════════════════
        # PHASE 6: BACKUP & SYNC
        # ══════════════════════════════════════════════════════
        self._sync_log: dict[str, SyncRecord] = {}
        self._sync_path = self._brain_path / "sync_log.json"
        self._encryption_key: Optional[bytes] = None
        self._privacy_overrides: dict[str, PrivacyLevel] = {}  # Per-node privacy

        # ── Lifecycle management ────────────────────────────
        self._tasks: list[asyncio.Task] = []  # Track background tasks for cleanup

        # ══════════════════════════════════════════════════════
        # PHASE 6: PATTERNS & PROACTIVE
        # ══════════════════════════════════════════════════════
        self._patterns: dict[str, MemoryPattern] = {}
        self._patterns_path = self._brain_path / "patterns.json"
        self._proactive_queue: list[dict] = []
        self._last_proactive_check = None

        # ══════════════════════════════════════════════════════
        # PHASE 6: VISUALIZATION
        # ══════════════════════════════════════════════════════
        self._snapshots: list[MemorySnapshot] = []
        self._snapshots_path = self._brain_path / "snapshots.json"

        self._ensure_storage()

    def _ensure_storage(self):
        """Create storage directories."""
        self._brain_path.mkdir(parents=True, exist_ok=True)
        (self._brain_path / "nodes").mkdir(exist_ok=True)
        (self._brain_path / "edges").mkdir(exist_ok=True)
        (self._brain_path / "audio").mkdir(exist_ok=True)
        (self._brain_path / "persona").mkdir(exist_ok=True)
        (self._brain_path / "goals").mkdir(exist_ok=True)
        (self._brain_path / "skills").mkdir(exist_ok=True)
        (self._brain_path / "summaries").mkdir(exist_ok=True)
        (self._brain_path / "encrypted").mkdir(exist_ok=True)
        (self._brain_path / "sync").mkdir(exist_ok=True)
        (self._brain_path / "backups").mkdir(exist_ok=True)
        log.info(f"Second Brain storage: {self._brain_path}")

    async def initialize(self):
        """Initialize the second brain."""
        log.info("🧠 Initializing Second Brain Memory System (Phase 4-6)...")

        try:
            from .llm_client import create_llm_client
            self._llm_client = create_llm_client(settings.default_provider)
        except Exception as e:
            log.warning(f"LLM client not available: {e}")

        await self._load_memory()

        # Load Phase 6 components
        self._embedding_index.load(self._embeddings_path)
        self._load_sync_log()
        self._load_patterns()
        self._load_snapshots()

        # Phase 4-5 background loops (tracked for cleanup)
        self._tasks.append(asyncio.create_task(self._memory_maintenance_loop()))
        self._tasks.append(asyncio.create_task(self._tier_migration_loop()))
        self._tasks.append(asyncio.create_task(self._persona_update_loop()))
        self._tasks.append(asyncio.create_task(self._goal_check_loop()))
        self._tasks.append(asyncio.create_task(self._auto_link_loop()))

        # Phase 6 background loops (tracked for cleanup)
        self._tasks.append(asyncio.create_task(self._pattern_detection_loop()))
        self._tasks.append(asyncio.create_task(self._proactive_surfacing_loop()))
        self._tasks.append(asyncio.create_task(self._embedding_update_loop()))

        # Rebuild embeddings for nodes without them
        await self._rebuild_embeddings()

        log.info(f"✅ Second Brain ready: {len(self._nodes)} nodes, {len(self._edges)} edges")
        if self._persona:
            log.info(f"   User Persona loaded: confidence={self._persona.confidence:.2f}")
        log.info(f"   Goals: {len(self._goals)}, Skills: {len(self._skills)}")
        log.info(f"   Embeddings: {len(self._embedding_index._node_ids)}, Patterns: {len(self._patterns)}")

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
        privacy: PrivacyLevel = PrivacyLevel.PRIVATE,
    ) -> MemoryNode:
        """Store a memory node with full processing."""
        # Generate stable ID from content hash for deduplication
        content_hash = hashlib.sha256(str(content).encode()).hexdigest()[:16]
        node_id = f"node_{int(time.time() * 1000)}_{content_hash[:8]}"

        # O(1) deduplication via content index (whitespace-normalized)
        normalized = " ".join(str(content).split())
        if normalized in self._content_index:
            log.debug(f"Duplicate content detected, returning existing node: {self._content_index[normalized]}")
            return self._nodes[self._content_index[normalized]]

        # Memory cap — evict lowest-importance, least-accessed nodes
        if len(self._nodes) >= self._MAX_NODES:
            evict_candidates = sorted(
                [n for n in self._nodes.values() if n.tier == MemoryTier.LONG_TERM],
                key=lambda n: (n.importance.value, n.access_count, n.decay_score)
            )
            if evict_candidates:
                await self.forget(evict_candidates[0].id, "memory_cap_eviction")

        entities = []
        topics = []

        if extract_entities and self._llm_client and isinstance(content, str):
            extracted = await self._extract_entities(content)
            entities = extracted.get("entities", [])
            topics = extracted.get("topics", [])

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
            confidence=0.8,
        )

        async with self._node_lock:
            self._nodes[node_id] = node
        self._update_indexes(node)
        self._add_to_tier(node_id, tier)
        # Update O(1) content index
        self._content_index[normalized] = node_id

        # Phase 6: Generate and store embedding
        await self._embed_node(node)

        # Track version
        await self._track_version(node_id, None, content, "created")

        await self._save_node(node)

        # Phase 6: Log sync record
        self._log_sync_action(node_id, "created")

        log.debug(f"Stored memory: {memory_type.value}/{node_id}")

        return node

    async def recall(
        self,
        query: str = None,
        memory_type: MemoryType = None,
        tier: MemoryTier = None,
        limit: int = 20,
        time_range: str = None,
    ) -> list[dict]:
        """Recall memories with hybrid search."""
        results = []
        filtered_nodes = list(self._nodes.values())

        if time_range:
            cutoff = self._get_time_cutoff(time_range)
            filtered_nodes = [
                n for n in filtered_nodes
                if datetime.fromisoformat(n.created_at) > cutoff
            ]

        if memory_type:
            filtered_nodes = [n for n in filtered_nodes if n.type == memory_type]

        if tier:
            filtered_nodes = [n for n in filtered_nodes if n.tier == tier]

        if query:
            query_lower = query.lower()
            query_words = set(query_lower.split())

            # Hybrid: keyword + semantic search
            semantic_results = {}
            if self._embedding_index._vectors:
                try:
                    query_vec = await self._embedding_index.encode(query)
                    semantic = self._embedding_index.search(query_vec, k=limit * 2)
                    for node_id, sim_score in semantic:
                        if node_id in self._nodes and any(node_id in [n.id for n in filtered_nodes]):
                            semantic_results[node_id] = sim_score
                except Exception as e:
                    log.debug(f"Semantic search unavailable: {e}")

            for node in filtered_nodes:
                score = self._calculate_relevance_score(node, query_words, query_lower)
                # Boost with semantic similarity
                semantic_boost = semantic_results.get(node.id, 0.0)
                combined_score = score * 0.6 + semantic_boost * 0.4
                if combined_score > 0:
                    results.append({
                        "node": node.to_dict(),
                        "score": combined_score,
                        "keyword_score": score,
                        "semantic_score": semantic_boost,
                        "reason": self._explain_score(node, query_words),
                    })
        else:
            results = [
                {"node": n.to_dict(), "score": 1.0, "reason": "recent"}
                for n in sorted(filtered_nodes, key=lambda x: x.last_accessed, reverse=True)[:limit]
            ]

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def _calculate_relevance_score(self, node: MemoryNode, query_words: set, query_lower: str) -> float:
        """Calculate relevance score for a node."""
        score = 0.0

        if isinstance(node.content, str):
            content_lower = node.content.lower()
            content_words = set(content_lower.split())
            overlap = len(query_words & content_words)
            score += overlap * 0.3

            if query_lower in content_lower:
                score += 2.0

        for entity in node.entities:
            if query_lower in entity.lower():
                score += 1.5

        for tag in node.tags:
            if query_lower in tag.lower():
                score += 1.0

        age_hours = (datetime.utcnow() - datetime.fromisoformat(node.created_at)).total_seconds() / 3600
        if age_hours < 1:
            score *= 1.5
        elif age_hours < 24:
            score *= 1.2

        score *= (node.importance.value / 3.0)
        score *= (1 + node.access_count * 0.05)
        score *= node.confidence

        return score

    # ══════════════════════════════════════════════════════
    # PERSONA EXTRACTION & MANAGEMENT
    # ══════════════════════════════════════════════════════

    async def extract_and_update_persona(self, conversation: str = None) -> dict:
        """
        Extract persona from recent conversations.
        Returns status dict instead of raw persona object.
        """
        if not self._llm_client:
            return {"status": "skipped", "reason": "LLM not available", "persona": self._persona.to_dict() if self._persona else None}

        if not conversation:
            conversation = self._get_recent_conversation_text()

        if len(conversation) < 50:
            return {"status": "skipped", "reason": "conversation too short", "persona": self._persona.to_dict() if self._persona else None}

        try:
            messages = [
                {"role": "system", "content": "You are a persona extraction system. Return ONLY valid JSON."},
                {"role": "user", "content": PERSONA_EXTRACTION_PROMPT.format(conversation=conversation[:4000])}
            ]

            result = await asyncio.wait_for(
                self._llm_client.chat(messages, temperature=0.1, max_tokens=2048),
                timeout=30.0,
            )
            raw_content = result.get("content", "{}")

            json_match = re.search(r'\{.*\}', raw_content, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group())

                    if self._persona:
                        # Update existing persona
                        self._update_persona_fields(data)
                    else:
                        # Create new persona
                        self._persona = UserPersona(
                            id=f"persona_{int(time.time())}",
                            name=data.get("name", "Unknown"),
                            bio=data.get("bio", ""),
                            interests=data.get("interests", []),
                            communication_style=data.get("communication_style", "neutral"),
                            personality_traits=data.get("personality_traits", []),
                            values=data.get("values", []),
                            strengths=data.get("strengths", []),
                            weaknesses=data.get("weaknesses", []),
                            work_style=data.get("work_style", "unknown"),
                            learning_style=data.get("learning_style", "unknown"),
                            confidence=0.7,
                        )

                    self._persona.last_updated = datetime.utcnow().isoformat()
                    self._persona.confidence = min(1.0, self._persona.confidence + 0.1)

                    await self._save_persona()
                    log.info(f"Persona updated: {self._persona.name}, confidence={self._persona.confidence:.2f}")
                    return {"status": "success", "persona": self._persona.to_dict()}
                except (json.JSONDecodeError, ValueError):
                    return {"status": "failed", "reason": "JSON parse failed", "persona": self._persona.to_dict() if self._persona else None}
            else:
                return {"status": "failed", "reason": "no JSON found in LLM response", "persona": self._persona.to_dict() if self._persona else None}

        except asyncio.TimeoutError:
            log.warning("Persona extraction timed out after 30s")
            return {"status": "failed", "reason": "timeout", "persona": self._persona.to_dict() if self._persona else None}
        except Exception as e:
            log.warning(f"Persona extraction failed: {e}")
            return {"status": "failed", "reason": str(e), "persona": self._persona.to_dict() if self._persona else None}

    def _update_persona_fields(self, data: dict):
        """Update persona fields with new data."""
        if not self._persona:
            return

        for key, value in data.items():
            if hasattr(self._persona, key) and value:
                current = getattr(self._persona, key)
                if isinstance(current, list) and isinstance(value, list):
                    # Guard against non-list merge on list fields
                    setattr(self._persona, key, list(set(current + value)))
                else:
                    setattr(self._persona, key, value)

    async def get_persona(self) -> dict:
        """Get the current user persona."""
        if not self._persona:
            return {"error": "No persona extracted yet"}

        return self._persona.to_dict()

    async def update_persona_field(self, field: str, value: Any) -> dict:
        """Update a specific persona field."""
        if not self._persona:
            return {"error": "No persona exists"}

        if hasattr(self._persona, field):
            setattr(self._persona, field, value)
            self._persona.last_updated = datetime.utcnow().isoformat()
            await self._save_persona()
            return {"updated": True, "field": field}

        return {"error": "Invalid field"}

    def _get_recent_conversation_text(self) -> str:
        """Get text from recent conversations for analysis."""
        conversations = [
            n.content for n in self._nodes.values()
            if n.type == MemoryType.CONVERSATION
        ]
        return "\n\n".join([
            str(c) if isinstance(c, dict) else c
            for c in conversations[-20:]
        ])

    async def _persona_update_loop(self) -> None:
        """Background task to update persona periodically."""
        while self._running:
            try:
                await asyncio.sleep(3600)  # Check every hour

                recent_text = self._get_recent_conversation_text()
                if len(recent_text) > 100:
                    result = await self.extract_and_update_persona(recent_text)
                    log.debug(f"Persona update: {result.get('status')}")

            except Exception as e:
                log.error(f"Persona update error: {e}")

    # ══════════════════════════════════════════════════════
    # GOAL MANAGEMENT
    # ══════════════════════════════════════════════════════

    async def add_goal(
        self,
        title: str,
        description: str = "",
        deadline: str = None,
        priority: int = 3,
        tags: list = None,
    ) -> Goal:
        """Add a new goal."""
        goal = Goal(
            id=f"goal_{hashlib.sha256(title.encode()).hexdigest()[:16]}",
            title=title,
            description=description,
            deadline=deadline,
            priority=priority,
            tags=tags or [],
        )

        async with self._goal_lock:
            self._goals[goal.id] = goal
        await self._save_goal(goal)

        log.info(f"Goal added: {title}")

        return goal

    async def update_goal_progress(self, goal_id: str, progress: float, note: str = None) -> dict:
        """Update goal progress."""
        if goal_id not in self._goals:
            return {"error": "Goal not found"}

        goal = self._goals[goal_id]
        goal.progress = max(0.0, min(1.0, progress))

        if note:
            goal.milestones.append({
                "timestamp": datetime.utcnow().isoformat(),
                "progress": progress,
                "note": note,
            })

        if goal.progress >= 1.0:
            goal.status = GoalStatus.COMPLETED

        await self._save_goal(goal)

        return {"goal_id": goal_id, "progress": goal.progress, "status": goal.status.value}

    async def get_active_goals(self) -> list[dict]:
        """Get all active goals sorted by priority."""
        active = [g for g in self._goals.values() if g.status == GoalStatus.ACTIVE]
        active.sort(key=lambda x: x.priority)
        return [g.to_dict() for g in active]

    async def get_all_goals(self) -> list[dict]:
        """Get all goals regardless of status."""
        return [g.to_dict() for g in self._goals.values()]

    async def set_goal_status(self, goal_id: str, status: GoalStatus) -> dict:
        """Set goal status."""
        if goal_id not in self._goals:
            return {"error": "Goal not found"}

        self._goals[goal_id].status = status
        await self._save_goal(self._goals[goal_id])

        return {"goal_id": goal_id, "status": status.value}

    async def add_goal_blocker(self, goal_id: str, blocker: str) -> dict:
        """Add a blocker to a goal."""
        if goal_id not in self._goals:
            return {"error": "Goal not found"}

        self._goals[goal_id].blockers.append(blocker)
        await self._save_goal(self._goals[goal_id])

        return {"added": True, "blocker": blocker}

    async def extract_goals_from_conversation(self, conversation: str) -> list[Goal]:
        """Extract goals from a conversation."""
        if not self._llm_client:
            return []

        try:
            messages = [
                {"role": "system", "content": "You are a goal extraction system. Return ONLY valid JSON."},
                {"role": "user", "content": GOAL_EXTRACTION_PROMPT.format(conversation=conversation[:3000])}
            ]

            result = await asyncio.wait_for(
                self._llm_client.chat(messages, temperature=0.1, max_tokens=1024),
                timeout=30.0,
            )
            content = result.get("content", "{}")

            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    goals_data = data.get("goals", [])

                    for goal_data in goals_data:
                        existing = [g for g in self._goals.values() if g.title == goal_data.get("title")]
                        if not existing:
                            await self.add_goal(
                                title=goal_data.get("title", "Untitled"),
                                description=goal_data.get("description", ""),
                                deadline=goal_data.get("deadline"),
                                priority=goal_data.get("priority", 3),
                            )

                    return self.get_active_goals()
                except (json.JSONDecodeError, ValueError):
                    pass

        except asyncio.TimeoutError:
            log.warning("Goal extraction timed out after 30s")
        except Exception as e:
            log.warning(f"Goal extraction failed: {e}")

        return []

    async def _goal_check_loop(self) -> None:
        """Background task to check goal deadlines."""
        while self._running:
            try:
                await asyncio.sleep(1800)  # Check every 30 minutes

                now = datetime.utcnow()
                for goal in self._goals.values():
                    if goal.status == GoalStatus.ACTIVE and goal.deadline:
                        deadline = datetime.fromisoformat(goal.deadline)
                        if deadline < now:
                            # Goal is overdue - could send notification
                            log.info(f"Goal overdue: {goal.title}")

            except Exception as e:
                log.error(f"Goal check error: {e}")

    # ══════════════════════════════════════════════════════
    # SKILL TRACKING
    # ══════════════════════════════════════════════════════

    async def add_skill(
        self,
        name: str,
        category: str,
        level: SkillLevel = SkillLevel.NOVICE,
        notes: str = "",
    ) -> Skill:
        """Add or update a skill."""
        existing = [s for s in self._skills.values() if s.name.lower() == name.lower()]

        if existing:
            skill = existing[0]
            skill.level = level
            skill.practice_count += 1
            skill.last_practiced = datetime.utcnow().isoformat()
        else:
            skill = Skill(
                id=f"skill_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}",
                name=name,
                category=category,
                level=level,
                last_practiced=datetime.utcnow().isoformat(),
                notes=notes,
            )
            self._skills[skill.id] = skill

        await self._save_skill(skill)

        # Store in memory
        await self.store(
            content={"skill_name": name, "category": category, "level": level.value},
            memory_type=MemoryType.SKILL,
            importance=Importance.MEDIUM,
            tags=["skill", category],
        )

        log.info(f"Skill added/updated: {name} ({level.name})")

        return skill

    async def update_skill_level(self, skill_name: str, level: SkillLevel) -> dict:
        """Update skill proficiency level."""
        existing = [s for s in self._skills.values() if s.name.lower() == skill_name.lower()]

        if not existing:
            return {"error": "Skill not found"}

        skill = existing[0]
        skill.level = level
        skill.practice_count += 1
        skill.last_practiced = datetime.utcnow().isoformat()

        await self._save_skill(skill)

        return {"skill": skill_name, "level": level.value}

    async def get_skills_by_category(self, category: str = None) -> list[dict]:
        """Get skills, optionally filtered by category."""
        skills = list(self._skills.values())
        if category:
            skills = [s for s in skills if s.category.lower() == category.lower()]

        skills.sort(key=lambda x: x.level.value, reverse=True)
        return [s.to_dict() for s in skills]

    async def get_all_skills(self) -> list[dict]:
        """Get all tracked skills."""
        return [s.to_dict() for s in self._skills.values()]

    async def extract_skills_from_conversation(self, conversation: str) -> list[Skill]:
        """Extract skills from conversation."""
        if not self._llm_client:
            return []

        try:
            messages = [
                {"role": "system", "content": "You are a skill extraction system. Return ONLY valid JSON."},
                {"role": "user", "content": SKILL_EXTRACTION_PROMPT.format(conversation=conversation[:3000])}
            ]

            result = await self._llm_client.chat(messages, temperature=0.1, max_tokens=1024)
            content = result.get("content", "{}")

            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                skills_data = data.get("skills", [])

                for skill_data in skills_data:
                    await self.add_skill(
                        name=skill_data.get("name", "Unknown"),
                        category=skill_data.get("category", "general"),
                        level=SkillLevel(skill_data.get("level", 1)),
                    )

                return self.get_all_skills()

        except Exception as e:
            log.warning(f"Skill extraction failed: {e}")

        return []

    # ══════════════════════════════════════════════════════
    # MEMORY COMPRESSION & SUMMARIZATION
    # ══════════════════════════════════════════════════════

    async def compress_old_memories(self, days_old: int = 30) -> dict:
        """Compress old memories into summaries."""
        cutoff = datetime.utcnow() - timedelta(days=days_old)

        old_nodes = [
            n for n in self._nodes.values()
            if n.tier == MemoryTier.LONG_TERM
            and datetime.fromisoformat(n.created_at) < cutoff
            and n.type in [MemoryType.CONVERSATION, MemoryType.EVENT]
        ]

        if len(old_nodes) < 5:
            return {"compressed": 0, "message": "Not enough old memories to compress"}

        compressed = 0
        batch_size = 10

        for i in range(0, len(old_nodes), batch_size):
            batch = old_nodes[i:i + batch_size]

            if not self._llm_client:
                break

            memories_text = "\n\n".join([
                f"[{n.created_at}] {str(n.content)[:500]}"
                for n in batch
            ])

            try:
                messages = [
                    {"role": "system", "content": "You are a memory compression system. Return ONLY valid JSON."},
                    {"role": "user", "content": MEMORY_COMPRESSION_PROMPT.format(memories=memories_text[:3000])}
                ]

                result = await self._llm_client.chat(messages, temperature=0.1, max_tokens=1024)
                content = result.get("content", "{}")

                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    data = json.loads(json_match.group())

                    summary = MemorySummary(
                        id=f"summary_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}",
                        original_ids=[n.id for n in batch],
                        summary_text=data.get("summary", ""),
                        key_entities=data.get("key_entities", []),
                        key_points=data.get("key_points", []),
                        sentiment=data.get("sentiment", "neutral"),
                        compression_ratio=1 - (len(data.get("summary", "")) / max(1, len(memories_text))),
                    )

                    self._summaries[summary.id] = summary
                    await self._save_summary(summary)

                    # Remove old nodes from active memory but keep reference
                    for node in batch:
                        node.metadata["compressed"] = True
                        node.metadata["summary_id"] = summary.id
                        await self._save_node(node)

                    compressed += len(batch)

            except Exception as e:
                log.warning(f"Compression batch failed: {e}")

        log.info(f"Compressed {compressed} old memories into {len(self._summaries)} summaries")

        return {
            "compressed": compressed,
            "summaries_created": len(self._summaries),
        }

    async def get_summary(self, summary_id: str) -> dict:
        """Get a memory summary by ID."""
        if summary_id in self._summaries:
            return self._summaries[summary_id].to_dict()
        return {"error": "Summary not found"}

    async def search_summaries(self, query: str) -> list[dict]:
        """Search within compressed summaries."""
        query_lower = query.lower()
        results = []

        for summary in self._summaries.values():
            if query_lower in summary.summary_text.lower():
                score = summary.summary_text.lower().count(query_lower)
                results.append({
                    "summary": summary.to_dict(),
                    "score": score,
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:10]

    # ══════════════════════════════════════════════════════
    # CROSS-REFERENCE AUTOMATIC LINKING
    # ══════════════════════════════════════════════════════

    async def auto_link_memories(self) -> dict:
        """Automatically find and create links between memories."""
        if not self._llm_client:
            return {"linked": 0}

        linked = 0
        unlinked = [n for n in self._nodes.values() if len(n.relationships) == 0]

        for i, node1 in enumerate(unlinked[:20]):
            for node2 in unlinked[i + 1:]:
                if self._should_link(node1, node2):
                    await self.add_relationship(
                        source_id=node1.id,
                        target_id=node2.id,
                        relation_type="auto_linked",
                        weight=0.5,
                    )
                    linked += 1

        log.info(f"Auto-linked {linked} memory pairs")

        return {"linked": linked}

    def _should_link(self, node1: MemoryNode, node2: MemoryNode) -> bool:
        """Check if two nodes should be linked."""
        # Check entities
        for entity in node1.entities:
            if entity in node2.entities:
                return True

        # Check tags
        for tag in node1.tags:
            if tag in node2.tags:
                return True

        # Check content similarity
        if isinstance(node1.content, str) and isinstance(node2.content, str):
            words1 = set(node1.content.lower().split())
            words2 = set(node2.content.lower().split())
            overlap = len(words1 & words2)
            if overlap > 5:
                return True

        return False

    async def _auto_link_loop(self) -> None:
        """Background task to auto-link memories."""
        while self._running:
            try:
                await asyncio.sleep(7200)  # Check every 2 hours

                await asyncio.wait_for(self.auto_link_memories(), timeout=300.0)

            except asyncio.TimeoutError:
                log.warning("Auto-link timed out after 300s")
            except Exception as e:
                log.error(f"Auto-link error: {e}")

    # ══════════════════════════════════════════════════════
    # EMOTIONAL INTELLIGENCE
    # ══════════════════════════════════════════════════════

    async def analyze_emotions(self, conversation: str) -> dict:
        """Analyze emotional content of conversation."""
        if not self._llm_client:
            return {"error": "LLM not available"}

        try:
            messages = [
                {"role": "system", "content": "You are an emotion analysis system. Return ONLY valid JSON."},
                {"role": "user", "content": EMOTION_ANALYSIS_PROMPT.format(conversation=conversation[:3000])}
            ]

            result = await asyncio.wait_for(
                self._llm_client.chat(messages, temperature=0.1, max_tokens=1024),
                timeout=30.0,
            )
            content = result.get("content", "{}")

            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except (json.JSONDecodeError, ValueError):
                    pass

        except asyncio.TimeoutError:
            log.warning("Emotion analysis timed out after 30s")
        except Exception as e:
            log.warning(f"Emotion analysis failed: {e}")

        return {"error": "Analysis failed"}

    async def store_emotional_memory(
        self,
        conversation: str,
        sentiment: str,
        emotions: list,
        context: str = None,
    ) -> MemoryNode:
        """Store emotional context from conversation."""
        emotion_data = {
            "sentiment": sentiment,
            "emotions": emotions,
            "context": context,
            "conversation": conversation[:500],
        }

        node = await self.store(
            content=emotion_data,
            memory_type=MemoryType.EMOTION,
            importance=Importance.MEDIUM,
            tags=["emotion", sentiment] + emotions,
            extract_entities=False,
        )

        # Update persona emotional patterns
        if self._persona:
            pattern_key = sentiment
            if pattern_key in self._persona.emotional_patterns:
                self._persona.emotional_patterns[pattern_key] += 1
            else:
                self._persona.emotional_patterns[pattern_key] = 1

            await self._save_persona()

        return node

    # ══════════════════════════════════════════════════════
    # MEMORY VERSIONING
    # ══════════════════════════════════════════════════════

    async def _track_version(
        self,
        node_id: str,
        old_content: Any,
        new_content: Any,
        change_type: str,
    ) -> None:
        """Track memory version history."""
        node = self._nodes.get(node_id)
        if not node:
            return

        version = MemoryVersion(
            id=f"ver_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}",
            node_id=node_id,
            version=node.version,
            old_content=old_content,
            new_content=new_content,
            change_type=change_type,
        )

        self._versions[node_id].append(version)
        node.version += 1

    async def get_node_versions(self, node_id: str) -> list[dict]:
        """Get version history for a node."""
        versions = self._versions.get(node_id, [])
        return [v.to_dict() for v in versions[-10:]]  # Last 10 versions

    async def revert_to_version(self, node_id: str, version: int) -> dict:
        """Revert a node to a previous version."""
        versions = self._versions.get(node_id, [])
        target = [v for v in versions if v.version == version]

        if not target:
            return {"error": "Version not found"}

        node = self._nodes.get(node_id)
        if not node:
            return {"error": "Node not found"}

        old_content = node.content
        node.content = target[0].old_content
        node.version += 1

        await self._track_version(node_id, old_content, node.content, "reverted")
        await self._save_node(node)

        return {"reverted": True, "node_id": node_id, "version": node.version}

    # ══════════════════════════════════════════════════════
    # MEMORY QUALITY SCORING
    # ══════════════════════════════════════════════════════

    async def score_memory_quality(self, node_id: str) -> float:
        """Score the quality of a memory node."""
        node = self._nodes.get(node_id)
        if not node:
            return 0.0

        score = 0.5  # Base score

        # Entity presence
        if len(node.entities) > 0:
            score += 0.1

        # Tag presence
        if len(node.tags) >= 3:
            score += 0.1

        # Access frequency
        if node.access_count > 5:
            score += 0.1

        # Recency of access
        last_access = datetime.fromisoformat(node.last_accessed)
        hours_ago = (datetime.utcnow() - last_access).total_seconds() / 3600
        if hours_ago < 24:
            score += 0.1

        # Importance
        score += (node.importance.value - 3) * 0.05

        # Has relationships
        if len(node.relationships) > 0:
            score += 0.1

        node.confidence = min(1.0, max(0.0, score))
        await self._save_node(node)

        return node.confidence

    async def get_quality_report(self) -> dict:
        """Get overall memory quality report."""
        total = len(self._nodes)
        if total == 0:
            return {"total": 0, "avg_quality": 0, "high_quality": 0, "low_quality": 0}

        quality_scores = [n.confidence for n in self._nodes.values()]
        avg_quality = sum(quality_scores) / total

        high_quality = sum(1 for q in quality_scores if q >= 0.8)
        low_quality = sum(1 for q in quality_scores if q < 0.4)

        return {
            "total": total,
            "avg_quality": round(avg_quality, 3),
            "high_quality": high_quality,
            "low_quality": low_quality,
            "quality_distribution": {
                "excellent": sum(1 for q in quality_scores if q >= 0.9),
                "good": sum(1 for q in quality_scores if 0.7 <= q < 0.9),
                "fair": sum(1 for q in quality_scores if 0.5 <= q < 0.7),
                "poor": sum(1 for q in quality_scores if q < 0.5),
            }
        }

    # ══════════════════════════════════════════════════════
    # PREDICTIVE MEMORY SUGGESTIONS
    # ══════════════════════════════════════════════════════

    async def suggest_related_memories(self, node_id: str) -> list[dict]:
        """Suggest related memories based on patterns."""
        node = self._nodes.get(node_id)
        if not node:
            return []

        suggestions = []

        # Based on entities
        for entity in node.entities[:3]:
            related = await self.recall_entity(entity.lower(), limit=3)
            for r in related:
                if r.get("node", {}).get("id") != node_id:
                    suggestions.append({
                        "type": "entity_match",
                        "node": r["node"],
                        "score": r["score"],
                        "entity": entity,
                    })

        # Based on tags
        for tag in node.tags[:3]:
            related = await self.recall_by_topic(tag, limit=3)
            for r in related:
                if r.get("node", {}).get("id") != node_id and r not in suggestions:
                    suggestions.append({
                        "type": "topic_match",
                        "node": r["node"],
                        "score": r["score"],
                        "topic": tag,
                    })

        # Sort by score
        suggestions.sort(key=lambda x: x["score"], reverse=True)
        return suggestions[:10]

    async def predict_next_memory(self) -> dict:
        """Predict what memory might be needed next based on patterns."""
        if len(self._nodes) < 10:
            return {"suggestion": None, "reason": "Not enough data"}

        # Analyze recent conversation topics
        recent_convs = [
            n for n in self._nodes.values()
            if n.type == MemoryType.CONVERSATION
        ][-5:]

        if not recent_convs:
            return {"suggestion": None}

        # Extract common topics/entities
        all_entities = []
        all_topics = []
        for conv in recent_convs:
            all_entities.extend(conv.entities)
            all_topics.extend(conv.tags)

        if not all_entities and not all_topics:
            return {"suggestion": None}

        most_common_entity = Counter(all_entities).most_common(1)
        most_common_topic = Counter(all_topics).most_common(1)

        return {
            "suggestion": {
                "entity": most_common_entity[0][0] if most_common_entity else None,
                "topic": most_common_topic[0][0] if most_common_topic else None,
            },
            "reason": "Based on recent conversation patterns"
        }

    # ══════════════════════════════════════════════════════
    # CONVERSATION & DOCUMENT STORAGE
    # ══════════════════════════════════════════════════════

    async def add_conversation(
        self,
        user_input: str,
        ai_response: str,
        ai_provider: str,
        context: str = None,
        metadata: dict = None,
    ) -> MemoryNode:
        """Add conversation with full processing."""
        conversation = {
            "user": user_input,
            "ai": ai_response,
            "provider": ai_provider,
            "context": context,
            "timestamp": datetime.utcnow().isoformat(),
        }

        importance = Importance.MEDIUM
        if any(word in user_input.lower() for word in ["remember", "important", "note"]):
            importance = Importance.HIGH
        if any(word in user_input.lower() for word in ["critical", "urgent", "must"]):
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

        # Extract facts
        if len(user_input) > 20 and len(user_input) < 200:
            extracted = await self._extract_entities(user_input)
            if extracted.get("entities") or extracted.get("key_points"):
                await self.store(
                    content={
                        "fact": user_input,
                        "source": "conversation",
                        "conversation_id": node.id,
                    },
                    memory_type=MemoryType.FACT,
                    importance=importance,
                    tags=["extracted_fact"],
                )

        # Extract goals if mentioned
        if any(word in user_input.lower() for word in ["goal", "plan", "want to", "need to", "should"]):
            await self.extract_goals_from_conversation(user_input)

        # Extract skills if mentioned
        if any(word in user_input.lower() for word in ["know", "skill", "experienced", "expert"]):
            await self.extract_skills_from_conversation(user_input)

        # Update persona
        await self.extract_and_update_persona()

        return node

    async def add_document(
        self,
        content: str,
        title: str,
        doc_type: str = "document",
        tags: list = None,
        metadata: dict = None,
    ) -> MemoryNode:
        """Add document with entity extraction."""
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

        # Extract and store key points
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
            )

        return node

    async def add_user_fact(
        self,
        fact: str,
        category: str = "general",
        importance: Importance = Importance.MEDIUM,
    ) -> MemoryNode:
        """Add a fact about the user."""
        return await self.store(
            content={"fact": fact, "category": category},
            memory_type=MemoryType.FACT,
            importance=importance,
            tags=["user_fact", category],
            source="user",
        )

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
        """Store audio conversation with full processing."""
        audio_id = f"audio_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        extracted = await self._extract_entities(transcription)
        summary = await self._summarize(transcription)
        emotions = await self.analyze_emotions(transcription)

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
            sentiment=emotions.get("overall_sentiment", "neutral"),
            key_points=extracted.get("key_points", []),
            questions_asked=extracted.get("questions", []),
            decisions_made=extracted.get("decisions", []),
            metadata=metadata or {},
        )

        self._audio_memories[audio_id] = audio_memory
        await self._save_audio_memory(audio_memory)

        # Store as conversation node
        await self.store(
            content={
                "summary": summary,
                "transcription": transcription,
                "speakers": speakers,
                "duration": duration,
                "key_points": extracted.get("key_points", []),
                "sentiment": emotions.get("overall_sentiment", "neutral"),
            },
            memory_type=MemoryType.AUDIO,
            importance=Importance.MEDIUM,
            tags=["audio", "conversation"] + audio_memory.topics,
            source=f"audio_session_{session_id}",
        )

        log.info(f"Stored audio: {audio_id} ({duration:.1f}s)")

        return audio_memory

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
        """Add relationship between nodes."""
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

        if source_id in self._nodes:
            self._nodes[source_id].relationships.append(target_id)
        if target_id in self._nodes:
            self._nodes[target_id].relationships.append(source_id)

        await self._save_edge(edge)

        return edge

    # ══════════════════════════════════════════════════════
    # RECALL METHODS
    # ══════════════════════════════════════════════════════

    async def recall_graph(
        self,
        entity: str,
        depth: int = 2,
        relation_types: list = None,
    ) -> dict:
        """Recall via knowledge graph."""
        if entity.lower() not in self._entity_index:
            return {"entity": entity, "connections": [], "depth": depth}

        visited = set()
        queue = [(eid, 0) for eid in self._entity_index[entity.lower()]]
        graph_results = []

        while queue:
            node_id, current_depth = queue.pop(0)
            if node_id in visited or current_depth > depth:
                continue

            visited.add(node_id)
            node = self._nodes.get(node_id)
            if not node:
                continue

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
        """Recall within time range."""
        results = []

        start = datetime.fromisoformat(start_date) if start_date else datetime.min
        end = datetime.fromisoformat(end_date) if end_date else datetime.utcnow()

        for node in self._nodes.values():
            created = datetime.fromisoformat(node.created_at)
            if start <= created <= end:
                score = self._calculate_relevance_score(
                    node, set(query.lower().split()), query.lower()
                )
                if score > 0:
                    results.append({
                        "node": node.to_dict(),
                        "score": score,
                        "timestamp": node.created_at,
                    })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    async def recall_conversation(self, query: str = None, limit: int = 10) -> list[dict]:
        """Recall conversations."""
        conv_nodes = [n for n in self._nodes.values() if n.type == MemoryType.CONVERSATION]
        results = []

        for node in conv_nodes:
            score = 1.0
            if query:
                score = self._calculate_relevance_score(
                    node, set(query.lower().split()), query.lower()
                )

            if score > 0:
                results.append({"node": node.to_dict(), "score": score})

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    async def recall_entity(self, entity_name: str, limit: int = 10) -> list[dict]:
        """Recall by entity."""
        entity_lower = entity_name.lower()
        matching = []

        for node in self._nodes.values():
            if any(entity_lower in e.lower() for e in node.entities):
                matching.append({
                    "node": node.to_dict(),
                    "score": node.access_count + 1,
                })

        matching.sort(key=lambda x: x["score"], reverse=True)
        return matching[:limit]

    async def recall_by_topic(self, topic: str, limit: int = 20) -> list[dict]:
        """Recall by topic."""
        topic_lower = topic.lower()
        results = []

        for node in self._nodes.values():
            if topic_lower in [t.lower() for t in node.tags]:
                results.append({
                    "node": node.to_dict(),
                    "score": node.access_count + 1,
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

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

            if score > 0 or not query:
                results.append({"audio": audio.to_dict(), "score": score})

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    # ══════════════════════════════════════════════════════
    # WORKING MEMORY
    # ══════════════════════════════════════════════════════

    async def add_to_working_memory(self, node_id: str) -> None:
        """Add to working memory."""
        if node_id not in self._working_memory:
            self._working_memory.append(node_id)
            if len(self._working_memory) > 20:
                self._working_memory = self._working_memory[-20:]

    async def get_working_memory(self) -> list[dict]:
        """Get working memory contents."""
        results = []
        for node_id in self._working_memory[-10:]:
            if node_id in self._nodes:
                node = self._nodes[node_id]
                node.last_accessed = datetime.utcnow().isoformat()
                node.access_count += 1
                results.append(node.to_dict())
        return results

    async def clear_working_memory(self) -> None:
        """Clear working memory."""
        self._working_memory = []

    # ══════════════════════════════════════════════════════
    # AI CONTEXT
    # ══════════════════════════════════════════════════════

    async def get_context_for_ai(self, ai_name: str = None, max_tokens: int = 4000) -> str:
        """Get formatted context for AI prompts."""
        context_parts = []

        # Working memory
        wm = await self.get_working_memory()
        if wm:
            wm_content = " | ".join([
                f"{n['type']}: {str(n['content'])[:100]}"
                for n in wm[-5:]
            ])
            context_parts.append(f"[Recent: {wm_content}]")

        # Persona
        if self._persona:
            persona_info = f"User: {self._persona.name}"
            if self._persona.interests:
                persona_info += f", Interests: {', '.join(self._persona.interests[:5])}"
            if self._persona.communication_style:
                persona_info += f", Style: {self._persona.communication_style}"
            context_parts.append(f"[Persona: {persona_info}]")

        # Active goals
        active_goals = [g for g in self._goals.values() if g.status == GoalStatus.ACTIVE]
        if active_goals:
            goals_str = ", ".join([g.title for g in active_goals[:3]])
            context_parts.append(f"[Active Goals: {goals_str}]")

        # Recent conversations
        recent_convs = await self.recall_conversation(limit=5)
        if recent_convs:
            conv_summary = " | ".join([
                str(n['node']['content']).split('user')[1][:80] if 'user' in str(n['node']['content']) else '...'
                for n in recent_convs
            ])
            context_parts.append(f"[Recent Chats: {conv_summary}]")

        # High importance facts
        fact_nodes = [
            n for n in self._nodes.values()
            if n.type == MemoryType.FACT and n.importance.value >= Importance.HIGH.value
        ]
        if fact_nodes:
            facts = ", ".join([str(f.content.get("fact", f.content))[:50] for f in fact_nodes[:5]])
            context_parts.append(f"[Key Facts: {facts}]")

        # Skills
        if self._skills:
            top_skills = ", ".join([s.name for s in sorted(self._skills.values(), key=lambda x: x.level.value, reverse=True)[:5]])
            context_parts.append(f"[Skills: {top_skills}]")

        return "\n".join(context_parts) if context_parts else ""

    # ══════════════════════════════════════════════════════
    # STATISTICS
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

        quality_report = await self.get_quality_report()

        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "total_audio": len(self._audio_memories),
            "total_goals": len(self._goals),
            "total_skills": len(self._skills),
            "total_summaries": len(self._summaries),
            "type_counts": dict(type_counts),
            "tier_counts": dict(tier_counts),
            "importance_counts": dict(importance_counts),
            "entity_index_size": len(self._entity_index),
            "quality": quality_report,
            "persona_confidence": self._persona.confidence if self._persona else 0,
            "active_goals": len([g for g in self._goals.values() if g.status == GoalStatus.ACTIVE]),
        }

    async def get_memory_size_mb(self) -> float:
        """Estimate memory size in MB."""
        import sys
        total = 0

        total += sum(sys.getsizeof(str(n.to_dict())) for n in self._nodes.values())
        total += sum(sys.getsizeof(str(e.to_dict())) for e in self._edges.values())
        total += sum(sys.getsizeof(str(a.to_dict())) for a in self._audio_memories.values())
        total += sum(sys.getsizeof(str(g.to_dict())) for g in self._goals.values())
        total += sum(sys.getsizeof(str(s.to_dict())) for s in self._skills.values())

        return total / (1024 * 1024)

    # ══════════════════════════════════════════════════════
    # HELPER METHODS
    # ══════════════════════════════════════════════════════

    async def _extract_entities(self, text: str) -> dict:
        """Extract entities using LLM or fallback."""
        if not self._llm_client:
            return self._simple_entity_extraction(text)

        try:
            prompt = """Extract entities from text. Return JSON with:
- "entities": [{name, type, context}]
- "topics": [topics]
- "key_points": [important statements]
- "questions": [questions asked]

Text: {text}

Return ONLY JSON."""

            messages = [
                {"role": "system", "content": "You are a knowledge extraction system. Return ONLY valid JSON."},
                {"role": "user", "content": prompt.format(text=text[:4000])}
            ]

            result = await asyncio.wait_for(
                self._llm_client.chat(messages, temperature=0.1, max_tokens=2048),
                timeout=30.0,
            )
            content = result.get("content", "{}")

            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except (json.JSONDecodeError, ValueError):
                    pass

        except asyncio.TimeoutError:
            log.warning("Entity extraction timed out after 30s")
        except Exception as e:
            log.warning(f"Entity extraction failed: {e}")

        return self._simple_entity_extraction(text)

    def _simple_entity_extraction(self, text: str) -> dict:
        """Fallback entity extraction."""
        entities = []
        capitalized = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        for word in capitalized[:10]:
            if len(word) > 2:
                entities.append({"name": word, "type": "unknown", "context": ""})

        common_topics = ["meeting", "project", "code", "bug", "feature", "design", "review", "testing"]
        topics = [t for t in common_topics if t in text.lower()]

        return {
            "entities": entities,
            "topics": topics,
            "key_points": [],
            "questions": [],
        }

    async def _summarize(self, text: str) -> str:
        """Generate summary."""
        if not self._llm_client:
            sentences = re.split(r'[.!?]+', text)
            return ". ".join(sentences[:3])[:500]

        try:
            messages = [
                {"role": "system", "content": "You are a summarization assistant. Return ONLY the summary."},
                {"role": "user", "content": f"Summarize this in 2-3 sentences:\n{text[:2000]}"}
            ]

            result = await self._llm_client.chat(messages, temperature=0.3, max_tokens=256)
            return result.get("content", text[:500])[:500]

        except Exception:
            return text[:500]

    def _get_time_cutoff(self, time_range: str) -> datetime:
        """Get time cutoff based on range."""
        now = datetime.utcnow()
        if time_range == "1h":
            return now - timedelta(hours=1)
        elif time_range == "24h":
            return now - timedelta(hours=24)
        elif time_range == "7d":
            return now - timedelta(days=7)
        elif time_range == "30d":
            return now - timedelta(days=30)
        return datetime.min

    def _explain_score(self, node: MemoryNode, query_words: set) -> str:
        """Explain relevance score."""
        reasons = []

        if isinstance(node.content, str):
            content_lower = node.content.lower()
            for word in query_words:
                if word in content_lower:
                    reasons.append(f"contains '{word}'")
                    break

        if node.entities:
            reasons.append(f"{len(node.entities)} entities")

        if node.access_count > 5:
            reasons.append(f"accessed {node.access_count} times")

        return ", ".join(reasons) if reasons else "recent"

    def _update_indexes(self, node: MemoryNode) -> None:
        """Update indexes."""
        for entity in node.entities:
            entity_lower = entity.lower()
            if entity_lower not in self._entity_index:
                self._entity_index[entity_lower] = []
            self._entity_index[entity_lower].append(node.id)

        for tag in node.tags:
            tag_lower = tag.lower()
            if tag_lower not in self._topic_index:
                self._topic_index[tag_lower] = []
            self._topic_index[tag_lower].append(node.id)

    def _add_to_tier(self, node_id: str, tier: MemoryTier) -> None:
        """Add node to tier."""
        if tier == MemoryTier.WORKING:
            self._add_to_working_memory(node_id)
        elif tier == MemoryTier.SHORT_TERM:
            if node_id not in self._short_term:
                self._short_term.append(node_id)
                if len(self._short_term) > 1000:
                    self._short_term = self._short_term[-1000:]

    def _add_to_working_memory(self, node_id: str) -> None:
        """Add to working memory."""
        if node_id not in self._working_memory:
            self._working_memory.append(node_id)
            if len(self._working_memory) > 20:
                self._working_memory = self._working_memory[-20:]

    # ══════════════════════════════════════════════════════
    # PHASE 6: EMBEDDING HELPERS
    # ══════════════════════════════════════════════════════

    async def _embed_node(self, node: MemoryNode) -> None:
        """Generate and store embedding for a node."""
        if not isinstance(node.content, str):
            return
        try:
            text = node.content
            if isinstance(node.content, dict):
                text = json.dumps(node.content)
            vec = await self._embedding_index.encode(text)
            self._embedding_index.add(node.id, vec)
        except Exception as e:
            log.debug(f"Failed to embed node {node.id}: {e}")

    async def _rebuild_embeddings(self) -> None:
        """Rebuild embedding index for nodes that don't have one."""
        indexed_ids = set(self._embedding_index._node_ids)
        missing = [n for n in self._nodes.values() if n.id not in indexed_ids and isinstance(n.content, str)]
        if not missing:
            return
        log.info(f"Rebuilding embeddings for {len(missing)} nodes...")
        texts = [n.content if isinstance(n.content, str) else json.dumps(n.content) for n in missing]
        try:
            vectors = await self._embedding_index.encode_batch(texts)
            for node, vec in zip(missing, vectors):
                self._embedding_index.add(node.id, vec)
            self._embedding_index.save(self._embeddings_path)
            log.info(f"Rebuilt {len(vectors)} embeddings")
        except Exception as e:
            log.warning(f"Embedding rebuild failed: {e}")

    async def _embedding_update_loop(self) -> None:
        """Periodically save embedding index."""
        while self._running:
            try:
                await asyncio.sleep(300)
                self._embedding_index.save(self._embeddings_path)
                log.debug("Embedding index saved")
            except Exception as e:
                log.debug(f"Embedding save: {e}")

    # ══════════════════════════════════════════════════════
    # PHASE 6: SYNC & BACKUP HELPERS
    # ══════════════════════════════════════════════════════

    def _log_sync_action(self, node_id: str, action: str) -> None:
        """Log a sync action."""
        node = self._nodes.get(node_id)
        content_hash = hashlib.sha256(json.dumps(node.content if node else {}, sort_keys=True).encode()).hexdigest()[:16]
        self._sync_log[node_id] = SyncRecord(
            node_id=node_id,
            action=action,
            timestamp=datetime.utcnow().isoformat(),
            hash=content_hash,
            sync_status=SyncStatus.PENDING_UPLOAD,
        )

    def _load_sync_log(self) -> None:
        """Load sync log from disk."""
        if self._sync_path.exists():
            try:
                data = json.loads(self._sync_path.read_text())
                for node_id, rec in data.items():
                    self._sync_log[node_id] = SyncRecord(
                        node_id=rec["node_id"],
                        action=rec["action"],
                        timestamp=rec["timestamp"],
                        hash=rec["hash"],
                        sync_status=SyncStatus(rec.get("sync_status", "synced")),
                        synced_at=rec.get("synced_at"),
                    )
            except Exception as e:
                log.warning(f"Failed to load sync log: {e}")

    def _save_sync_log(self) -> None:
        """Save sync log to disk (non-blocking)."""
        data = {k: v.to_dict() for k, v in self._sync_log.items()}
        asyncio.create_task(asyncio.to_thread(
            self._sync_path.write_text, json.dumps(data, indent=2)
        ))

    def _compute_checksum(self) -> str:
        """Compute checksum of all memory."""
        data = {
            "nodes": {k: v.to_dict() for k, v in self._nodes.items()},
            "edges": {k: v.to_dict() for k, v in self._edges.items()},
            "persona": self._persona.to_dict() if self._persona else None,
            "goals": {k: v.to_dict() for k, v in self._goals.items()},
            "skills": {k: v.to_dict() for k, v in self._skills.items()},
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    # ══════════════════════════════════════════════════════
    # PHASE 6: PATTERN DETECTION
    # ══════════════════════════════════════════════════════

    def _load_patterns(self) -> None:
        """Load patterns from disk."""
        if self._patterns_path.exists():
            try:
                data = json.loads(self._patterns_path.read_text())
                for p in data:
                    self._patterns[p["id"]] = MemoryPattern(**p)
            except Exception as e:
                log.warning(f"Failed to load patterns: {e}")

    def _save_patterns(self) -> None:
        """Save patterns to disk (non-blocking)."""
        data = [p.to_dict() for p in self._patterns.values()]
        asyncio.create_task(asyncio.to_thread(
            self._patterns_path.write_text, json.dumps(data, indent=2)
        ))

    def _load_snapshots(self) -> None:
        """Load snapshots from disk."""
        if self._snapshots_path.exists():
            try:
                data = json.loads(self._snapshots_path.read_text())
                self._snapshots = [MemorySnapshot(**s) for s in data]
            except Exception as e:
                log.warning(f"Failed to load snapshots: {e}")

    def _save_snapshots(self) -> None:
        """Save snapshots to disk (non-blocking)."""
        data = [s.to_dict() for s in self._snapshots]
        asyncio.create_task(asyncio.to_thread(
            self._snapshots_path.write_text, json.dumps(data, indent=2)
        ))

    async def _pattern_detection_loop(self) -> None:
        """Detect patterns in memory access and content."""
        while self._running:
            try:
                await asyncio.sleep(3600)
                await self._detect_patterns()
            except Exception as e:
                log.debug(f"Pattern detection: {e}")

    async def _detect_patterns(self) -> None:
        """Detect temporal and sequential patterns."""
        recent = sorted(self._nodes.values(), key=lambda n: n.last_accessed, reverse=True)[:100]
        if len(recent) < 10:
            return

        for i in range(len(recent) - 1):
            curr, prev = recent[i], recent[i + 1]
            # Temporal pattern: memories accessed within same hour
            try:
                curr_time = datetime.fromisoformat(curr.last_accessed)
                prev_time = datetime.fromisoformat(prev.last_accessed)
                if abs((curr_time - prev_time).total_seconds()) < 3600:
                    self._merge_or_create_pattern(curr, prev, "temporal")
            except Exception:
                pass

            # Sequential pattern: same type accessed consecutively
            if curr.type == prev.type and curr.type.value in ["conversation", "fact"]:
                self._merge_or_create_pattern(curr, prev, "sequential")

            # Topical pattern: shared entities
            shared_entities = set(curr.entities) & set(prev.entities)
            if len(shared_entities) >= 2:
                self._merge_or_create_pattern(curr, prev, "topical")

    def _merge_or_create_pattern(self, node1: MemoryNode, node2: MemoryNode, pattern_type: str) -> None:
        """Merge into existing pattern or create new one."""
        node_ids = {node1.id, node2.id}
        for pat in self._patterns.values():
            if pat.pattern_type == pattern_type and node_ids & set(pat.nodes):
                for nid in node_ids:
                    if nid not in pat.nodes:
                        pat.nodes.append(nid)
                pat.last_seen = datetime.utcnow().isoformat()
                pat.occurrences += 1
                return

        pattern = MemoryPattern(
            id=f"pattern_{int(time.time() * 1000)}",
            pattern_type=pattern_type,
            description=f"{pattern_type} pattern involving {len(node_ids)} nodes",
            nodes=[node1.id, node2.id],
            confidence=0.7,
            first_seen=datetime.utcnow().isoformat(),
            last_seen=datetime.utcnow().isoformat(),
        )
        self._patterns[pattern.id] = pattern

    # ══════════════════════════════════════════════════════
    # PHASE 6: PROACTIVE SURFACING
    # ══════════════════════════════════════════════════════

    async def _proactive_surfacing_loop(self) -> None:
        """Periodically surface relevant memories proactively."""
        while self._running:
            try:
                await asyncio.sleep(7200)
                await self._surface_proactive_memories()
            except Exception as e:
                log.debug(f"Proactive surfacing: {e}")

    async def _surface_proactive_memories(self) -> None:
        """Surface memories that might be relevant now."""
        now = datetime.utcnow()
        self._proactive_queue.clear()

        # Surfaces memories not accessed in a while but are important
        for node in self._nodes.values():
            if node.importance.value >= Importance.HIGH.value:
                try:
                    last_access = datetime.fromisoformat(node.last_accessed)
                    days_since = (now - last_access).days
                    if 7 <= days_since <= 30:
                        self._proactive_queue.append({
                            "node": node.to_dict(),
                            "reason": f"Not accessed in {days_since} days",
                            "urgency": node.importance.value / 5.0,
                        })
                except Exception:
                    pass

        # Sort by urgency
        self._proactive_queue.sort(key=lambda x: x["urgency"], reverse=True)
        self._proactive_queue = self._proactive_queue[:10]

    # ══════════════════════════════════════════════════════
    # BACKGROUND LOOPS
    # ══════════════════════════════════════════════════════

    async def _memory_maintenance_loop(self) -> None:
        """Background maintenance."""
        while self._running:
            try:
                await asyncio.sleep(600)

                for node_id, node in list(self._nodes.items()):
                    node.decay_score = self._calculate_decay(node)

                    if node.decay_score < 0.05 and node.importance.value <= Importance.LOW.value:
                        await self.forget(node_id, "decay_below_threshold")

                for edge_id, edge in list(self._edges.items()):
                    if edge.source_id not in self._nodes or edge.target_id not in self._nodes:
                        del self._edges[edge_id]

            except Exception as e:
                log.error(f"Memory maintenance error: {e}")

    async def _tier_migration_loop(self) -> None:
        """Background tier migration."""
        while self._running:
            try:
                await asyncio.sleep(300)

                now = datetime.utcnow()

                for node_id in list(self._short_term):
                    node = self._nodes.get(node_id)
                    if node:
                        age_hours = (now - datetime.fromisoformat(node.created_at)).total_seconds() / 3600
                        if age_hours > 24:
                            node.tier = MemoryTier.LONG_TERM
                            self._short_term.remove(node_id)
                            await self._save_node(node)

                if self._working_memory:
                    oldest = self._working_memory[0] if self._working_memory else None
                    if oldest and oldest in self._nodes:
                        node = self._nodes[oldest]
                        age_minutes = (now - datetime.fromisoformat(node.last_accessed)).total_seconds() / 60
                        if age_minutes > 5:
                            self._working_memory.pop(0)

            except Exception as e:
                log.error(f"Tier migration error: {e}")

    def _calculate_decay(self, node: MemoryNode) -> float:
        """Calculate decay score."""
        age_days = (datetime.utcnow() - datetime.fromisoformat(node.created_at)).days
        days_since_access = (datetime.utcnow() - datetime.fromisoformat(node.last_accessed)).days

        base_decay = 0.9 ** (age_days / 30)
        access_boost = 1 + (node.access_count * 0.02)
        importance_factor = 1 + (node.importance.value / 10)
        access_decay = 0.95 ** days_since_access

        return min(1.0, max(0.0, base_decay * access_boost * importance_factor * access_decay))

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
                    node = MemoryNode.from_dict(json.loads(node_file.read_text()))
                    self._nodes[node.id] = node
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

        # Load audio
        audio_dir = self._brain_path / "audio"
        if audio_dir.exists():
            for audio_file in audio_dir.glob("*.json"):
                try:
                    audio = AudioMemory(**json.loads(audio_file.read_text()))
                    self._audio_memories[audio.id] = audio
                except Exception as e:
                    log.warning(f"Failed to load audio {audio_file}: {e}")

        # Load persona
        persona_file = self._brain_path / "persona" / "persona.json"
        if persona_file.exists():
            try:
                self._persona = UserPersona(**json.loads(persona_file.read_text()))
            except Exception as e:
                log.warning(f"Failed to load persona: {e}")

        # Load goals
        goals_dir = self._brain_path / "goals"
        if goals_dir.exists():
            for goal_file in goals_dir.glob("*.json"):
                try:
                    goal = Goal(**json.loads(goal_file.read_text()))
                    self._goals[goal.id] = goal
                except Exception as e:
                    log.warning(f"Failed to load goal {goal_file}: {e}")

        # Load skills
        skills_dir = self._brain_path / "skills"
        if skills_dir.exists():
            for skill_file in skills_dir.glob("*.json"):
                try:
                    skill = Skill(**json.loads(skill_file.read_text()))
                    self._skills[skill.id] = skill
                except Exception as e:
                    log.warning(f"Failed to load skill {skill_file}: {e}")

        log.info(f"Loaded: {len(self._nodes)} nodes, {len(self._edges)} edges, {len(self._audio_memories)} audio")

    async def _save_node(self, node: MemoryNode) -> None:
        """Save node to disk (non-blocking)."""
        node_file = self._brain_path / "nodes" / f"{node.id}.json"
        await asyncio.to_thread(node_file.write_text, json.dumps(node.to_dict(), indent=2))

    async def _save_edge(self, edge: MemoryEdge) -> None:
        """Save edge to disk (non-blocking)."""
        edge_file = self._brain_path / "edges" / f"{edge.id}.json"
        await asyncio.to_thread(edge_file.write_text, json.dumps(edge.to_dict(), indent=2))

    async def _save_audio_memory(self, audio: AudioMemory) -> None:
        """Save audio memory (non-blocking)."""
        audio_file = self._brain_path / "audio" / f"{audio.id}.json"
        await asyncio.to_thread(audio_file.write_text, json.dumps(audio.to_dict(), indent=2))

    async def _save_persona(self) -> None:
        """Save persona (non-blocking)."""
        persona_file = self._brain_path / "persona" / "persona.json"
        await asyncio.to_thread(persona_file.write_text, json.dumps(self._persona.to_dict(), indent=2))

    async def _save_goal(self, goal: Goal) -> None:
        """Save goal (non-blocking)."""
        goal_file = self._brain_path / "goals" / f"{goal.id}.json"
        await asyncio.to_thread(goal_file.write_text, json.dumps(goal.to_dict(), indent=2))

    async def _save_skill(self, skill: Skill) -> None:
        """Save skill (non-blocking)."""
        skill_file = self._brain_path / "skills" / f"{skill.id}.json"
        await asyncio.to_thread(skill_file.write_text, json.dumps(skill.to_dict(), indent=2))

    async def _save_summary(self, summary: MemorySummary) -> None:
        """Save memory summary (non-blocking)."""
        summary_file = self._brain_path / "summaries" / f"{summary.id}.json"
        await asyncio.to_thread(summary_file.write_text, json.dumps(summary.to_dict(), indent=2))

    # ══════════════════════════════════════════════════════
    # MEMORY OPERATIONS
    # ══════════════════════════════════════════════════════

    async def revise_memory(self, node_id: str, new_content: Any) -> MemoryNode:
        """Revise memory with version tracking."""
        if node_id not in self._nodes:
            raise ValueError(f"Node {node_id} not found")

        node = self._nodes[node_id]
        old_content = node.content
        node.content = new_content
        node.updated_at = datetime.utcnow().isoformat()
        node.metadata["revised"] = True
        node.metadata["old_content"] = str(old_content)[:500]

        await self._track_version(node_id, old_content, new_content, "revised")
        await self._save_node(node)

        return node

    async def forget(self, node_id: str, reason: str = "user_request") -> dict:
        """Forget a memory."""
        if node_id not in self._nodes:
            return {"error": "Node not found"}

        node = self._nodes[node_id]
        node.metadata["forgotten"] = True
        node.metadata["forgotten_at"] = datetime.utcnow().isoformat()
        node.metadata["forget_reason"] = reason

        await self._track_version(node_id, node.content, None, "forgotten")
        del self._nodes[node_id]
        # Remove from O(1) content index (whitespace-normalized)
        normalized = " ".join(str(node.content).split())
        if normalized in self._content_index:
            del self._content_index[normalized]

        log.info(f"Forgotten: {node_id}")

        return {"forgotten": node_id}

    async def auto_forget_low_importance(self, threshold: float = 0.2) -> dict:
        """Auto-forget low importance memories."""
        forgotten = []

        for node_id, node in list(self._nodes.items()):
            if node.decay_score < threshold and node.importance.value <= Importance.LOW.value:
                last_access = datetime.fromisoformat(node.last_accessed)
                days_since_access = (datetime.utcnow() - last_access).days

                if days_since_access > 30:
                    result = await self.forget(node_id, "auto_decay")
                    forgotten.append(node_id)

        return {"forgotten_count": len(forgotten), "forgotten_ids": forgotten}

    async def clear_all(self) -> dict:
        """Clear all memory."""
        self._nodes.clear()
        self._edges.clear()
        self._audio_memories.clear()
        self._working_memory.clear()
        self._short_term.clear()
        self._entity_index.clear()
        self._topic_index.clear()
        self._goals.clear()
        self._skills.clear()
        self._summaries.clear()
        self._persona = None

        for f in (self._brain_path / "nodes").glob("*.json"):
            f.unlink()
        for f in (self._brain_path / "edges").glob("*.json"):
            f.unlink()
        for f in (self._brain_path / "audio").glob("*.json"):
            f.unlink()
        for f in (self._brain_path / "goals").glob("*.json"):
            f.unlink()
        for f in (self._brain_path / "skills").glob("*.json"):
            f.unlink()

        log.info("All memory cleared")

        # Clear Phase 6 data
        self._embedding_index.clear()
        self._patterns.clear()
        self._proactive_queue.clear()
        self._snapshots.clear()
        self._sync_log.clear()

        return {"status": "cleared"}

    # ══════════════════════════════════════════════════════
    # PHASE 6: BACKUP & RESTORE
    # ══════════════════════════════════════════════════════

    async def create_backup(self, description: str = "", tags: list = None) -> dict:
        """Create a full backup snapshot."""
        snapshot_id = f"backup_{int(time.time())}"
        backup_dir = self._brain_path / "backups" / snapshot_id
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Export all data
        export = {
            "version": "6.0",
            "created_at": datetime.utcnow().isoformat(),
            "description": description,
            "nodes": {k: v.to_dict() for k, v in self._nodes.items()},
            "edges": {k: v.to_dict() for k, v in self._edges.items()},
            "audio_memories": {k: v.to_dict() for k, v in self._audio_memories.items()},
            "persona": self._persona.to_dict() if self._persona else None,
            "goals": {k: v.to_dict() for k, v in self._goals.items()},
            "skills": {k: v.to_dict() for k, v in self._skills.items()},
            "summaries": {k: v.to_dict() for k, v in self._summaries.items()},
            "patterns": [p.to_dict() for p in self._patterns.values()],
            "privacy_overrides": {k: v.value for k, v in self._privacy_overrides.items()},
        }

        (backup_dir / "export.json").write_text(json.dumps(export, indent=2))

        # Save compressed backup
        zip_path = self._brain_path / "backups" / f"{snapshot_id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(backup_dir / "export.json", "data/export.json")

        # Create snapshot record
        import os
        size_mb = sum(f.stat().st_size for f in backup_dir.rglob("*") if f.is_file()) / (1024 * 1024)
        snapshot = MemorySnapshot(
            id=snapshot_id,
            timestamp=datetime.utcnow().isoformat(),
            node_count=len(self._nodes),
            edge_count=len(self._edges),
            size_mb=size_mb,
            checksum=self._compute_checksum(),
            description=description,
            tags=tags or [],
        )
        self._snapshots.append(snapshot)
        self._save_snapshots()

        log.info(f"Backup created: {snapshot_id} ({size_mb:.2f} MB, {len(self._nodes)} nodes)")

        return {
            "backup_id": snapshot_id,
            "node_count": len(self._nodes),
            "edge_count": len(self._edges),
            "size_mb": round(size_mb, 2),
            "checksum": snapshot.checksum,
        }

    async def restore_backup(self, backup_id: str) -> dict:
        """Restore from a backup."""
        backup_file = self._brain_path / "backups" / f"{backup_id}.zip"
        if not backup_file.exists():
            return {"error": f"Backup not found: {backup_id}"}

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(backup_file, "r") as zf:
                zf.extractall(tmpdir)

            export_file = Path(tmpdir) / "data" / "export.json"
            if not export_file.exists():
                export_file = Path(tmpdir) / "export.json"

            data = json.loads(export_file.read_text())

            if data.get("version", "0") < "6.0":
                return {"error": f"Backup version {data.get('version')} not compatible"}

            # Clear current data
            self._nodes.clear()
            self._edges.clear()
            self._audio_memories.clear()
            self._patterns.clear()

            # Restore nodes
            for node_id, node_data in data.get("nodes", {}).items():
                node_data_copy = node_data.copy()
                node_data_copy["type"] = MemoryType(node_data["type"])
                node_data_copy["tier"] = MemoryTier(node_data["tier"])
                node_data_copy["importance"] = Importance(node_data["importance"])
                self._nodes[node_id] = MemoryNode(**node_data_copy)

            # Restore edges
            for edge_id, edge_data in data.get("edges", {}).items():
                edge_data_copy = edge_data.copy()
                self._edges[edge_id] = MemoryEdge(**edge_data_copy)

            # Restore persona
            if data.get("persona"):
                self._persona = UserPersona(**data["persona"])

            # Restore goals
            for goal_id, goal_data in data.get("goals", {}).items():
                self._goals[goal_id] = Goal(**goal_data)

            # Restore skills
            for skill_id, skill_data in data.get("skills", {}).items():
                self._skills[skill_id] = Skill(**skill_data)

            # Restore patterns
            for p in data.get("patterns", []):
                self._patterns[p["id"]] = MemoryPattern(**p)

            # Restore privacy overrides
            for k, v in data.get("privacy_overrides", {}).items():
                self._privacy_overrides[k] = PrivacyLevel(v)

            # Rebuild indexes
            self._entity_index.clear()
            self._topic_index.clear()
            for node in self._nodes.values():
                self._update_indexes(node)

            # Rebuild embeddings
            await self._rebuild_embeddings()

            log.info(f"Restored backup {backup_id}: {len(self._nodes)} nodes, {len(self._edges)} edges")
            return {
                "restored": True,
                "backup_id": backup_id,
                "nodes": len(self._nodes),
                "edges": len(self._edges),
            }

    async def list_backups(self) -> list[dict]:
        """List all available backups."""
        return [s.to_dict() for s in sorted(self._snapshots, key=lambda x: x.timestamp, reverse=True)]

    async def delete_backup(self, backup_id: str) -> dict:
        """Delete a backup."""
        zip_file = self._brain_path / "backups" / f"{backup_id}.zip"
        folder = self._brain_path / "backups" / backup_id
        if zip_file.exists():
            zip_file.unlink()
        if folder.exists():
            import shutil
            shutil.rmtree(folder)
        self._snapshots = [s for s in self._snapshots if s.id != backup_id]
        self._save_snapshots()
        return {"deleted": backup_id}

    async def export_memory(
        self,
        format: str = "json",
        include_private: bool = False,
        include_sensitive: bool = False,
    ) -> dict:
        """Export memory in various formats."""
        nodes_to_export = {}
        for node_id, node in self._nodes.items():
            privacy = self._privacy_overrides.get(node_id, PrivacyLevel.PRIVATE)
            if privacy == PrivacyLevel.SENSITIVE and not include_sensitive:
                continue
            if privacy == PrivacyLevel.PRIVATE and not include_private:
                continue
            nodes_to_export[node_id] = node.to_dict()

        if format == "json":
            return {
                "format": "json",
                "version": "6.0",
                "exported_at": datetime.utcnow().isoformat(),
                "nodes": nodes_to_export,
                "edges": {k: v.to_dict() for k, v in self._edges.items()},
                "persona": self._persona.to_dict() if self._persona else None,
                "goals": {k: v.to_dict() for k, v in self._goals.items()},
                "skills": {k: v.to_dict() for k, v in self._skills.items()},
            }

        elif format == "markdown":
            lines = ["# RasoSpeak Memory Export\n", f"Exported: {datetime.utcnow().isoformat()}\n"]
            for node in sorted(nodes_to_export.values(), key=lambda x: x["created_at"], reverse=True):
                content = node.get("content", "")
                if isinstance(content, dict):
                    content = json.dumps(content)
                lines.append(f"\n## {node['type']}: {node['id']}\n")
                lines.append(f"**Created:** {node['created_at']}\n")
                lines.append(f"**Tags:** {', '.join(node.get('tags', []))}\n")
                lines.append(f"\n{content}\n")
            return {"format": "markdown", "content": "\n".join(lines)}

        elif format == "obsidian":
            """Export as Obsidian-compatible markdown vault."""
            vault_dir = self._brain_path / "exports" / "obsidian_vault"
            vault_dir.mkdir(parents=True, exist_ok=True)

            for node_id, node in nodes_to_export.items():
                content = node.get("content", "")
                if isinstance(content, dict):
                    content = json.dumps(content)
                safe_title = re.sub(r'[<>:"/\\|?*]', '_', str(node_id))
                tags_str = " ".join([f"#{t}" for t in node.get("tags", [])])
                md_content = f"---\nid: {node_id}\ntype: {node['type']}\ncreated: {node['created_at']}\ntags: [{', '.join(node.get('tags', []))}]\n---\n\n# {safe_title}\n\n{content}\n\n{tags_str}\n"
                (vault_dir / f"{safe_title}.md").write_text(md_content)

            return {
                "format": "obsidian",
                "path": str(vault_dir),
                "nodes_exported": len(nodes_to_export),
            }

        return {"error": f"Unknown format: {format}"}

    async def import_memory(self, data: dict, merge: bool = True) -> dict:
        """Import memory from export."""
        if not merge:
            self._nodes.clear()
            self._edges.clear()

        imported_nodes = 0
        for node_id, node_data in data.get("nodes", {}).items():
            if node_id in self._nodes and merge:
                continue
            try:
                node_data_copy = node_data.copy()
                node_data_copy["type"] = MemoryType(node_data["type"])
                node_data_copy["tier"] = MemoryTier(node_data["tier"])
                node_data_copy["importance"] = Importance(node_data["importance"])
                node = MemoryNode(**node_data_copy)
                self._nodes[node_id] = node
                self._update_indexes(node)
                await self._embed_node(node)
                imported_nodes += 1
            except Exception as e:
                log.warning(f"Failed to import node {node_id}: {e}")

        for edge_id, edge_data in data.get("edges", {}).items():
            try:
                edge = MemoryEdge(**edge_data)
                self._edges[edge_id] = edge
            except Exception:
                pass

        log.info(f"Imported {imported_nodes} nodes")
        return {"imported": imported_nodes}

    # ══════════════════════════════════════════════════════
    # PHASE 6: ENCRYPTED STORAGE
    # ══════════════════════════════════════════════════════

    def set_encryption_key(self, key: str) -> dict:
        """Set encryption key for sensitive memories."""
        self._encryption_key = hashlib.sha256(key.encode()).digest()
        return {"encryption": "enabled"}

    def clear_encryption_key(self) -> dict:
        """Clear encryption key."""
        self._encryption_key = None
        return {"encryption": "disabled"}

    async def encrypt_node(self, node_id: str, privacy: PrivacyLevel = PrivacyLevel.PRIVATE) -> dict:
        """Encrypt and protect a node."""
        if node_id not in self._nodes:
            return {"error": "Node not found"}

        node = self._nodes[node_id]
        self._privacy_overrides[node_id] = privacy

        if privacy in (PrivacyLevel.PRIVATE, PrivacyLevel.SENSITIVE) and self._encryption_key:
            try:
                content = json.dumps(node.content).encode()
                nonce = os.urandom(12)
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                aesgcm = AESGCM(self._encryption_key)
                encrypted = aesgcm.encrypt(nonce, content, None)
                node.content = base64.b64encode(nonce + encrypted).decode()
                node.metadata["encrypted"] = True
                node.metadata["privacy"] = privacy.value
                await self._save_node(node)
                return {"encrypted": True, "node_id": node_id}
            except ImportError:
                log.warning("cryptography not available for AESGCM, storing without encryption")
                return {"encrypted": False, "node_id": node_id, "note": "encryption library not available"}
            except Exception as e:
                return {"error": f"Encryption failed: {e}"}

        await self._save_node(node)
        return {"updated": True, "node_id": node_id}

    async def decrypt_node(self, node_id: str) -> dict:
        """Decrypt a protected node."""
        if node_id not in self._nodes:
            return {"error": "Node not found"}

        node = self._nodes[node_id]
        if not node.metadata.get("encrypted"):
            return {"decrypted": False, "note": "not encrypted"}

        if not self._encryption_key:
            return {"error": "Encryption key required"}

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            data = base64.b64decode(node.content)
            nonce, ciphertext = data[:12], data[12:]
            aesgcm = AESGCM(self._encryption_key)
            decrypted = aesgcm.decrypt(nonce, ciphertext, None)
            node.content = json.loads(decrypted.decode())
            node.metadata["encrypted"] = False
            self._privacy_overrides.pop(node_id, None)
            await self._save_node(node)
            return {"decrypted": True, "node_id": node_id}
        except Exception as e:
            return {"error": f"Decryption failed: {e}"}

    def set_node_privacy(self, node_id: str, privacy: PrivacyLevel) -> dict:
        """Set privacy level for a node."""
        if node_id not in self._nodes:
            return {"error": "Node not found"}
        self._privacy_overrides[node_id] = privacy
        return {"node_id": node_id, "privacy": privacy.value}

    def get_node_privacy(self, node_id: str) -> PrivacyLevel:
        """Get privacy level for a node."""
        return self._privacy_overrides.get(node_id, PrivacyLevel.PRIVATE)

    # ══════════════════════════════════════════════════════
    # PHASE 6: VISUALIZATION DATA
    # ══════════════════════════════════════════════════════

    def get_graph_data(self, max_nodes: int = 200) -> dict:
        """Get graph data for visualization."""
        nodes = []
        edges = []

        recent_nodes = sorted(self._nodes.values(), key=lambda n: n.last_accessed, reverse=True)[:max_nodes]
        node_ids = {n.id for n in recent_nodes}

        for node in recent_nodes:
            nodes.append({
                "id": node.id,
                "label": str(node.content)[:50] if isinstance(node.content, str) else node.type.value,
                "type": node.type.value,
                "tier": node.tier.value,
                "importance": node.importance.value,
                "created_at": node.created_at,
                "access_count": node.access_count,
            })

        for edge in self._edges.values():
            if edge.source_id in node_ids and edge.target_id in node_ids:
                edges.append({
                    "id": edge.id,
                    "source": edge.source_id,
                    "target": edge.target_id,
                    "relationship": edge.relationship_type,
                    "strength": edge.strength,
                })

        return {"nodes": nodes, "edges": edges}

    def get_timeline_data(self, days: int = 30) -> dict:
        """Get timeline data for visualization."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        entries = []

        for node in self._nodes.values():
            try:
                created = datetime.fromisoformat(node.created_at)
                if created > cutoff:
                    entries.append({
                        "id": node.id,
                        "timestamp": node.created_at,
                        "type": node.type.value,
                        "content": str(node.content)[:100],
                        "importance": node.importance.value,
                    })
            except Exception:
                pass

        entries.sort(key=lambda x: x["timestamp"])
        return {"entries": entries}

    def get_entity_map(self) -> dict:
        """Get entity relationship map."""
        entity_nodes = defaultdict(list)
        for node in self._nodes.values():
            for entity in node.entities:
                entity_nodes[entity].append({
                    "id": node.id,
                    "type": node.type.value,
                    "content": str(node.content)[:80],
                })

        connections = []
        for entity, nodes_list in entity_nodes.items():
            if len(nodes_list) > 1:
                for i in range(len(nodes_list) - 1):
                    connections.append({
                        "entity": entity,
                        "source": nodes_list[i]["id"],
                        "target": nodes_list[i + 1]["id"],
                    })

        return {
            "entities": [{"name": k, "connections": len(v)} for k, v in entity_nodes.items() if len(v) > 1],
            "connections": connections,
        }

    # ══════════════════════════════════════════════════════
    # PHASE 6: SEMANTIC SEARCH
    # ══════════════════════════════════════════════════════

    async def semantic_search(self, query: str, limit: int = 10) -> list[dict]:
        """Pure semantic search using embeddings."""
        if not self._embedding_index._vectors:
            return []

        try:
            query_vec = await self._embedding_index.encode(query)
            results = self._embedding_index.search(query_vec, k=limit)
            return [
                {
                    "node": self._nodes[node_id].to_dict(),
                    "score": score,
                    "reason": "semantic_similarity",
                }
                for node_id, score in results
                if node_id in self._nodes
            ]
        except Exception as e:
            log.warning(f"Semantic search failed: {e}")
            return []

    # ══════════════════════════════════════════════════════
    # PHASE 6: PROACTIVE & PATTERNS API
    # ══════════════════════════════════════════════════════

    def get_proactive_memories(self) -> list[dict]:
        """Get memories surfaced proactively."""
        return self._proactive_queue

    def get_patterns(self, pattern_type: str = None) -> list[dict]:
        """Get detected patterns."""
        patterns = list(self._patterns.values())
        if pattern_type:
            patterns = [p for p in patterns if p.pattern_type == pattern_type]
        return [p.to_dict() for p in sorted(patterns, key=lambda x: x.last_seen, reverse=True)]

    def get_sync_status(self) -> dict:
        """Get sync status."""
        synced = sum(1 for r in self._sync_log.values() if r.sync_status == SyncStatus.SYNCED)
        pending = sum(1 for r in self._sync_log.values() if r.sync_status != SyncStatus.SYNCED)
        return {
            "total": len(self._sync_log),
            "synced": synced,
            "pending": pending,
            "conflicts": sum(1 for r in self._sync_log.values() if r.sync_status == SyncStatus.CONFLICT),
        }

    def mark_synced(self, node_ids: list[str]) -> dict:
        """Mark nodes as synced."""
        count = 0
        for nid in node_ids:
            if nid in self._sync_log:
                self._sync_log[nid].sync_status = SyncStatus.SYNCED
                self._sync_log[nid].synced_at = datetime.utcnow().isoformat()
                count += 1
        self._save_sync_log()
        return {"marked": count}

    async def shutdown(self):
        """Cleanup — cancel all background tasks, save all state."""
        self._running = False

        # Cancel all tracked background tasks
        for task in self._tasks:
            task.cancel()
        # Wait for all to confirm cancellation
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # Save all in-memory state (non-blocking via to_thread)
        for node in self._nodes.values():
            await self._save_node(node)
        for edge in self._edges.values():
            await self._save_edge(edge)

        # Phase 6: Save all state
        self._embedding_index.save(self._embeddings_path)
        self._save_sync_log()
        self._save_patterns()
        self._save_snapshots()

        # Save persona and goals if present
        if self._persona:
            await self._save_persona()
        for goal_id, goal in self._goals.items():
            try:
                await asyncio.to_thread(
                    (self._brain_path / "goals" / f"{goal_id}.json").write_text,
                    json.dumps(goal.to_dict(), indent=2)
                )
            except Exception:
                pass

        # Zeroize encryption key
        if hasattr(self, '_encryption_key') and self._encryption_key:
            self._encryption_key = b'\x00' * len(self._encryption_key)
            self._encryption_key = None

        log.info("SecondBrainAgent shut down cleanly")