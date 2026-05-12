"""
RasoSpeak v2 — Shared Memory Agent (Legacy Proxy)
DEPRECATED: All functionality now lives in SecondBrainAgent.
This module provides backward compatibility for /memory/* API endpoints.

New code should use SecondBrainAgent directly via /brain/* endpoints.
"""

import logging
from typing import Any, Optional

from .base_agent import BaseAgent
from config.settings import settings

log = logging.getLogger("rasospeak.shared_memory")


class SharedMemoryAgent(BaseAgent):
    """
    Legacy proxy — all functionality moved to SecondBrainAgent.
    This class exists for backward compatibility only.

    DEPRECATED: Use /brain/* endpoints directly.
    """

    name = "SharedMemoryAgent"

    def __init__(self):
        self._second_brain = None  # Reference to SecondBrainAgent
        self._user_profile: dict = {}
        self._user_facts: dict = {}

    def set_second_brain(self, second_brain):
        """Connect to SecondBrainAgent for all operations."""
        self._second_brain = second_brain
        log.info("SharedMemoryAgent connected to SecondBrainAgent (proxy mode)")

    async def initialize(self):
        """Load minimal profile for backward compat."""
        log.info("⚠️  SharedMemoryAgent running in DEPRECATED proxy mode — use /brain/* endpoints")

    # ══════════════════════════════════════════════════════
    # PROXY METHODS — delegate to Second Brain
    # ══════════════════════════════════════════════════════

    async def store(
        self,
        key: str,
        value: Any,
        category: str = "general",
    ) -> dict:
        """Proxy to Second Brain. Deprecated — use /brain/memory instead."""
        if self._second_brain:
            # Map legacy categories to Second Brain memory types
            type_map = {
                "conversation": "conversation",
                "fact": "semantic",
                "profile": "persona",
                "session": "episodic",
                "coaching": "coaching",
            }
            memory_type = type_map.get(category, "general")

            # Handle value as dict or string
            if isinstance(value, dict):
                content = f"{key}: {value}"
            else:
                content = str(value)

            return await self._second_brain.store(
                content=content,
                memory_type=memory_type,
                tier="long_term",
                importance=3,
                tags=[category, key],
            )
        return {"stored": False, "error": "SecondBrainAgent not connected"}

    async def recall(
        self,
        query: str = None,
        key: str = None,
        category: str = None,
        limit: int = 10,
    ) -> dict:
        """Proxy to Second Brain recall. Deprecated — use /brain/recall instead."""
        if self._second_brain:
            result = await self._second_brain.recall(query=query, limit=limit)
            return {
                "query": query,
                "results": result.get("results", []),
                "total_found": result.get("total", 0),
                "source": "second_brain",
            }
        return {"query": query, "results": [], "total_found": 0, "source": "deprecated"}

    async def get_context_for_ai(
        self,
        ai_name: str = None,
        include_recent: int = 5,
    ) -> str:
        """Proxy to Second Brain context. Deprecated — use /brain/context instead."""
        if self._second_brain:
            return await self._second_brain.get_context_for_ai(ai_name, max_tokens=3000)
        return ""

    async def get_memory_stats(self) -> dict:
        """Get stats from Second Brain. Deprecated — use /brain/stats instead."""
        if self._second_brain:
            stats = await self._second_brain.get_stats()
            return {
                "total_memories": stats.get("total_memories", 0),
                "total_conversations": stats.get("conversations", 0),
                "total_facts": stats.get("semantic", 0),
                "total_sessions": stats.get("episodes", 0),
                "quality_score": stats.get("quality_score", 0),
                "weak_words_count": 0,
                "top_weak_words": [],
                "source": "second_brain",
            }
        return {"source": "deprecated", "error": "SecondBrainAgent not connected"}

    async def remember_user_fact(self, fact: str, category: str = "general") -> dict:
        """Proxy to Second Brain. Deprecated."""
        return await self.store(f"fact_{fact[:30]}", {"fact": fact, "category": category}, category="fact")

    async def add_conversation(
        self,
        user_input: str,
        ai_response: str,
        ai_provider: str,
        context: str = None,
    ) -> dict:
        """Proxy to Second Brain. Deprecated."""
        return await self.store(
            f"conv_{ai_provider}",
            {"user": user_input, "ai": ai_response, "provider": ai_provider},
            category="conversation",
        )

    async def add_weak_word(self, word: str, context: str = None, session_id: str = None) -> dict:
        """Proxy to Second Brain. Deprecated."""
        return await self.store(
            f"weak_word_{word}",
            {"word": word, "context": context, "session": session_id},
            category="coaching",
        )

    async def set_user_preference(self, key: str, value: Any) -> dict:
        """Proxy to Second Brain persona. Deprecated."""
        if self._second_brain:
            await self._second_brain.update_persona_field(key, value)
            return {"stored": True, "key": key, "value": value}
        return {"stored": False}

    async def get_user_preferences(self) -> dict:
        """Get from Second Brain persona. Deprecated."""
        if self._second_brain:
            persona = self._second_brain.get_persona()
            return {
                "preferred_provider": persona.get("preferred_provider", "qwen_local"),
                "preferred_coaching_mode": persona.get("preferred_coaching_mode", "hint"),
                "strictness_level": persona.get("strictness_level", 3),
                "chunk_size": persona.get("chunk_size", 8),
            }
        return {}

    async def save_session_summary(self, session_id: str, summary: dict) -> dict:
        """Proxy to Second Brain episodic memory. Deprecated."""
        if self._second_brain:
            return await self._second_brain.store(
                content=f"Session {session_id}: {summary}",
                memory_type="episodic",
                tier="long_term",
                importance=3,
                tags=["session", session_id],
            )
        return {"stored": False}

    async def shutdown(self):
        log.info("SharedMemoryAgent shut down")
