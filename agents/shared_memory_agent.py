"""
RasoSpeak v2 — Shared Memory Agent
A unified memory system that ALL AI agents can access and refer to.

This is the "brain" that maintains:
- User profile and preferences
- Conversation history across all AIs
- Weak words and improvement areas
- Session summaries
- Facts about the user
- Preferred AI provider settings

Every agent can read/write to this shared memory for context-aware responses.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from collections import Counter

from .base_agent import BaseAgent
from config.settings import settings

log = logging.getLogger("rasospeak.shared_memory")


class SharedMemoryAgent(BaseAgent):
    """
    Agent 0: Shared Memory — The brain that connects all agents.

    Provides a unified memory system that:
    - Stores user profile and preferences
    - Maintains conversation history with all AIs
    - Tracks weak words and pronunciation issues
    - Stores session summaries
    - Remembers facts about the user
    - Tracks which AI providers work best

    All other agents (QAAgent, CoachingAgent, ScoringAgent, etc.)
    can read/write to this shared memory for context-aware responses.
    """

    name = "SharedMemoryAgent"

    def __init__(self):
        self._storage_path = Path(settings.shared_memory_path or "./memory")
        self._user_profile: dict = {}
        self._conversation_history: list = []
        self._session_summaries: list = []
        self._user_facts: dict = {}
        self._ensure_storage()

    def _ensure_storage(self):
        """Create storage directories."""
        self._storage_path.mkdir(parents=True, exist_ok=True)
        (self._storage_path / "profile.json").touch(exist_ok=True)
        (self._storage_path / "conversations.json").touch(exist_ok=True)
        (self._storage_path / "facts.json").touch(exist_ok=True)
        (self._storage_path / "sessions").mkdir(exist_ok=True)
        log.info(f"Shared memory storage: {self._storage_path}")

    async def initialize(self):
        """Load existing memory or create new profile."""
        await self._load_memory()
        log.info("✅ SharedMemoryAgent initialized")

    # ══════════════════════════════════════════════════════
    # CORE MEMORY OPERATIONS
    # ══════════════════════════════════════════════════════

    async def store(
        self,
        key: str,
        value: Any,
        category: str = "general",
    ) -> dict:
        """
        Store a memory item.

        Args:
            key: Unique key for this memory
            value: The memory content
            category: Category (profile | conversation | fact | session | preference)

        Returns:
            Result with timestamp
        """
        memory_entry = {
            "key": key,
            "value": value,
            "category": category,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if category == "profile":
            self._user_profile[key] = value
            await self._save_profile()

        elif category == "fact":
            self._user_facts[key] = value
            await self._save_facts()

        elif category == "conversation":
            self._conversation_history.append(memory_entry)
            # Keep last 1000 conversations
            if len(self._conversation_history) > 1000:
                self._conversation_history = self._conversation_history[-1000:]
            await self._save_conversations()

        elif category == "session":
            self._session_summaries.append(memory_entry)
            if len(self._session_summaries) > 100:
                self._session_summaries = self._session_summaries[-100:]
            await self._save_sessions()

        log.debug(f"Stored memory: {category}/{key}")
        return {"stored": True, "key": key, "category": category}

    async def recall(
        self,
        query: str = None,
        key: str = None,
        category: str = None,
        limit: int = 10,
    ) -> dict:
        """
        Recall memories based on query, key, or category.

        Args:
            query: Natural language query (will match keywords)
            key: Specific memory key
            category: Filter by category
            limit: Max results to return

        Returns:
            List of matching memories
        """
        results = []

        # Filter by category
        if category == "profile":
            items = [(k, v) for k, v in self._user_profile.items()]
        elif category == "fact":
            items = [(k, v) for k, v in self._user_facts.items()]
        elif category == "conversation":
            items = [(m["key"], m) for m in self._conversation_history[-100:]]
        elif category == "session":
            items = [(m["key"], m) for m in self._session_summaries[-50:]]
        else:
            # Search all categories
            items = (
                [(k, v) for k, v in self._user_profile.items()] +
                [(k, v) for k, v in self._user_facts.items()] +
                [(m["key"], m) for m in self._conversation_history[-100:]] +
                [(m["key"], m) for m in self._session_summaries[-50:]]
            )

        # Filter by key
        if key:
            items = [(k, v) for k, v in items if key.lower() in k.lower()]

        # Filter by query (keyword matching)
        if query:
            query_words = query.lower().split()
            for k, v in items:
                text = f"{k} {str(v)}".lower()
                if any(word in text for word in query_words):
                    results.append({"key": k, "value": v, "relevance": len([w for w in query_words if w in text])})
            results.sort(key=lambda x: x["relevance"], reverse=True)
        else:
            results = [{"key": k, "value": v} for k, v in items[:limit]]

        return {
            "query": query,
            "results": results[:limit],
            "total_found": len(results),
        }

    # ══════════════════════════════════════════════════════
    # SPECIALIZED MEMORY FUNCTIONS
    # ══════════════════════════════════════════════════════

    async def remember_user_fact(self, fact: str, category: str = "general") -> dict:
        """Store a fact about the user."""
        key = f"fact_{int(time.time())}"
        await self.store(key, {"fact": fact, "category": category}, category="fact")
        return {"stored": True, "fact": fact}

    async def add_conversation(
        self,
        user_input: str,
        ai_response: str,
        ai_provider: str,
        context: str = None,
    ) -> dict:
        """Add a conversation to history."""
        conversation = {
            "user": user_input,
            "ai": ai_response,
            "provider": ai_provider,
            "context": context,
            "timestamp": datetime.utcnow().isoformat(),
        }
        key = f"conv_{int(time.time())}"
        await self.store(key, conversation, category="conversation")
        return {"stored": True}

    async def add_weak_word(self, word: str, context: str = None, session_id: str = None) -> dict:
        """Add a word the user struggles with."""
        weak_words = self._user_profile.get("weak_words", {})

        if word in weak_words:
            weak_words[word]["count"] += 1
            if session_id:
                weak_words[word]["sessions"].append(session_id)
        else:
            weak_words[word] = {
                "count": 1,
                "first_seen": datetime.utcnow().isoformat(),
                "sessions": [session_id] if session_id else [],
                "context": context,
            }

        await self.store("weak_words", weak_words, category="profile")
        return {"stored": True, "word": word}

    async def get_context_for_ai(
        self,
        ai_name: str = None,
        include_recent: int = 5,
    ) -> str:
        """
        Get formatted context string to prepend to AI prompts.
        This helps all AIs know about the user.

        Args:
            ai_name: Which AI (for personalization)
            include_recent: How many recent conversations to include

        Returns:
            Formatted context string for AI prompts
        """
        context_parts = []

        # User profile
        if self._user_profile.get("name"):
            context_parts.append(f"User name: {self._user_profile['name']}")

        if self._user_profile.get("goals"):
            context_parts.append(f"User goals: {self._user_profile['goals']}")

        # Weak words
        weak_words = self._user_profile.get("weak_words", {})
        if weak_words:
            top_weak = [w for w, d in sorted(weak_words.items(), key=lambda x: x[1]["count"], reverse=True)[:5]]
            context_parts.append(f"Words user struggles with: {', '.join(top_weak)}")

        # Recent sessions
        recent_sessions = self._session_summaries[-include_recent:]
        if recent_sessions:
            session_summary = "; ".join([
                f"{s.get('value', {}).get('summary', 'session')[:100]}"
                for s in recent_sessions
            ])
            context_parts.append(f"Recent sessions: {session_summary}")

        # Recent conversations
        recent_convs = self._conversation_history[-include_recent:]
        if recent_convs and False:  # Disabled by default to keep prompts short
            conv_summary = "; ".join([
                f"Q: {c.get('value', {}).get('user', '')[:50]} -> {c.get('value', {}).get('ai_provider', 'AI')}"
                for c in recent_convs
            ])
            context_parts.append(f"Recent chat: {conv_summary}")

        # User facts
        if self._user_facts:
            facts_str = ", ".join([f"{k}: {v}" for k, v in list(self._user_facts.items())[:5]])
            context_parts.append(f"Known facts: {facts_str}")

        if context_parts:
            return "\n".join([f"[User Context: {p}]" for p in context_parts])
        return ""

    async def save_session_summary(
        self,
        session_id: str,
        summary: dict,
    ) -> dict:
        """Save a session summary to memory."""
        session_data = {
            "session_id": session_id,
            "summary": summary,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.store(f"session_{session_id}", session_data, category="session")
        return {"stored": True}

    async def get_user_preferences(self) -> dict:
        """Get user's preferred settings."""
        return {
            "preferred_provider": self._user_profile.get("preferred_provider", "qwen_local"),
            "preferred_coaching_mode": self._user_profile.get("preferred_coaching_mode", "hint"),
            "strictness_level": self._user_profile.get("strictness_level", 3),
            "chunk_size": self._user_profile.get("chunk_size", 8),
        }

    async def set_user_preference(self, key: str, value: Any) -> dict:
        """Set a user preference."""
        await self.store(key, value, category="profile")
        return {"stored": True, "key": key, "value": value}

    # ══════════════════════════════════════════════════════
    # ANALYTICS
    # ══════════════════════════════════════════════════════

    async def get_memory_stats(self) -> dict:
        """Get statistics about the shared memory."""
        weak_words = self._user_profile.get("weak_words", {})

        return {
            "total_conversations": len(self._conversation_history),
            "total_sessions": len(self._session_summaries),
            "total_facts": len(self._user_facts),
            "weak_words_count": len(weak_words),
            "top_weak_words": [
                {"word": w, "count": d["count"]}
                for w, d in sorted(weak_words.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
            ],
            "memory_size_kb": self._estimate_size(),
        }

    def _estimate_size(self) -> int:
        """Estimate memory size in KB."""
        return len(json.dumps(self._user_profile)) // 1024

    # ══════════════════════════════════════════════════════
    # PERSISTENCE
    # ══════════════════════════════════════════════════════

    async def _load_memory(self):
        """Load all memory from disk."""
        # Load profile
        profile_path = self._storage_path / "profile.json"
        if profile_path.exists():
            try:
                self._user_profile = json.loads(profile_path.read_text())
            except Exception:
                self._user_profile = {"weak_words": {}}

        # Load facts
        facts_path = self._storage_path / "facts.json"
        if facts_path.exists():
            try:
                self._user_facts = json.loads(facts_path.read_text())
            except Exception:
                self._user_facts = {}

        # Load recent conversations
        conv_path = self._storage_path / "conversations.json"
        if conv_path.exists():
            try:
                self._conversation_history = json.loads(conv_path.read_text())
            except Exception:
                self._conversation_history = []

        log.info(f"Loaded memory: {len(self._user_profile)} profile items, {len(self._conversation_history)} conversations")

    async def _save_profile(self):
        """Save profile to disk."""
        (self._storage_path / "profile.json").write_text(json.dumps(self._user_profile, indent=2))

    async def _save_facts(self):
        """Save facts to disk."""
        (self._storage_path / "facts.json").write_text(json.dumps(self._user_facts, indent=2))

    async def _save_conversations(self):
        """Save conversations to disk."""
        (self._storage_path / "conversations.json").write_text(
            json.dumps(self._conversation_history[-500:], indent=2)
        )

    async def _save_sessions(self):
        """Save session summaries to disk."""
        (self._storage_path / "sessions").mkdir(exist_ok=True)
        for session in self._session_summaries[-10:]:
            session_id = session.get("key", "").replace("session_", "")
            if session_id:
                path = self._storage_path / "sessions" / f"{session_id}.json"
                path.write_text(json.dumps(session.get("value", {}), indent=2))

    async def clear_old_memory(self, days: int = 30) -> dict:
        """Clear memory older than specified days."""
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)
        original_count = len(self._conversation_history)

        self._conversation_history = [
            c for c in self._conversation_history
            if datetime.fromisoformat(c.get("timestamp", "2020-01-01")) > cutoff
        ]

        await self._save_conversations()

        cleared = original_count - len(self._conversation_history)
        log.info(f"Cleared {cleared} old conversations")
        return {"cleared": cleared}

    async def clear_all(self) -> dict:
        """Clear all memory entries."""
        self._conversation_history = []
        self._session_summaries = []
        self._user_facts = {}
        self._user_profile["preferences"] = {}
        self._user_profile["weak_words"] = {}

        await self._save_profile()
        await self._save_facts()
        await self._save_conversations()

        log.info("All memory cleared")
        return {"status": "cleared", "conversations": 0, "sessions": 0, "facts": 0}

    async def shutdown(self):
        await self._save_profile()
        await self._save_facts()
        await self._save_conversations()
        log.info("SharedMemoryAgent shut down")