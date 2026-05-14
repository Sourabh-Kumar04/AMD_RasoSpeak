"""
Unified Runtime Adapters
Wraps existing RasoSpeak agents to provide interfaces required by IntegratedRuntime.
"""

import asyncio
import json
import logging
from typing import Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid

logger = logging.getLogger("rasospeak.unified_adapters")


class VoiceServiceAdapter:
    """Wraps voice/wake word agents for UnifiedRuntime."""

    def __init__(self, wake_word_agent=None, transcription_agent=None):
        self._wake = wake_word_agent
        self._transcribe = transcription_agent

    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio to text."""
        if self._transcribe and hasattr(self._transcribe, 'transcribe'):
            return await self._transcribe.transcribe(audio_data)
        return ""

    async def detect_wake_word(self, audio_chunk: bytes) -> Optional[str]:
        """Detect wake word in audio."""
        # Placeholder - would integrate with actual wake word detection
        return None


class WorldModelAdapter:
    """Wraps second_brain agent for UnifiedRuntime."""

    def __init__(self, second_brain_agent):
        self._brain = second_brain_agent

    async def get_user_context(self, user_id: str) -> dict:
        """Get complete user context."""
        if self._brain and hasattr(self._brain, 'get_user_context'):
            return await self._brain.get_user_context(user_id)
        return {
            "user_id": user_id,
            "entities": [],
            "relationships": {},
            "preferences": {},
            "goals": []
        }

    async def get_entities(self, user_id: str) -> list:
        """Get all entities for user."""
        if self._brain and hasattr(self._brain, 'get_entities'):
            return await self._brain.get_entities(user_id)
        return []

    async def add_interaction(self, user_id: str, interaction_type: str, content: str, response: str = None):
        """Add interaction to world model."""
        pass

    async def update_entity(self, user_id: str, entity_type: str, entity_data: dict):
        """Update entity in world model."""
        pass  # Would delegate to brain agent

    async def upsert_entities(self, user_id: str, entities: list):
        """Upsert entities into world model."""
        pass


class MemoryServiceAdapter:
    """Wraps memory agents for UnifiedRuntime - UNIFIES all memory through SecondBrainAgent."""

    def __init__(self, session_memory_agent=None, shared_memory_agent=None, second_brain_agent=None):
        self._session = session_memory_agent
        self._shared = shared_memory_agent
        self._brain = second_brain_agent
        self.embedder = None  # For vector embeddings

        # Try to find embedder from brain agent
        if self._brain and hasattr(self._brain, 'embedding_model'):
            try:
                self.embedder = self._brain.embedding_model
            except:
                pass

    async def store(self, user_id: str, content: str, memory_type: str) -> dict:
        """Store memory - delegates to SecondBrainAgent for unified storage."""
        node_id = str(uuid.uuid4())
        if self._brain and hasattr(self._brain, 'store'):
            # Map memory types to brain storage
            node_type_map = {
                "semantic": "semantic",
                "episodic": "conversation",
                "working": "working",
                "procedural": "skill",
                "social": "relationship",
            }
            node_type = node_type_map.get(memory_type, "conversation")
            try:
                await self._brain.store(
                    content=content,
                    node_type=node_type,
                    user_id=user_id,
                    importance=0.5
                )
            except Exception as e:
                # Fallback - create memory without full store
                pass
        return {"node_id": node_id, "content": content, "type": memory_type}

    async def retrieve(self, user_id: str, query: str, limit: int = 10) -> list:
        """Semantic memory retrieval - uses SecondBrainAgent's recall methods."""
        memories = []
        if not self._brain:
            return memories

        # Use brain's recall methods for unified memory retrieval
        try:
            if hasattr(self._brain, 'recall_by_topic'):
                # Search by topic/keywords
                results = await self._brain.recall_by_topic(query, limit=limit)
                memories = [{"content": r.get("content", ""), "type": r.get("type", "episodic"), "importance": r.get("importance", 0.5)} for r in results]
            elif hasattr(self._brain, 'recall'):
                # General recall
                results = await self._brain.recall(query=query, limit=limit)
                memories = [{"content": r.get("content", ""), "type": r.get("type", "episodic"), "importance": r.get("importance", 0.5)} for r in results]
            elif hasattr(self._brain, 'search_memories'):
                results = await self._brain.search_memories(user_id, query, limit)
                memories = [{"content": r.get("content", ""), "type": r.get("type", "episodic"), "importance": r.get("importance", 0.5)} for r in results]
        except Exception as e:
            # Fallback to session memory if brain fails
            if self._session and hasattr(self._session, 'recall'):
                try:
                    results = await self._session.recall(query=query, limit=limit)
                    memories = [{"content": r, "type": "session", "importance": 0.5} for r in results]
                except:
                    pass

        return memories


class CognitiveEngineAdapter:
    """Wraps second_brain agent as cognitive engine."""

    def __init__(self, second_brain_agent):
        self._brain = second_brain_agent

    async def process(self, input_text: str, context: dict = None) -> dict:
        """Process input through cognitive engine."""
        if self._brain and hasattr(self._brain, 'process'):
            return await self._brain.process(input_text, context or {})
        return {
            "output_text": input_text,
            "confidence": 0.5,
            "cognitive_layers": ["perception", "execution"]
        }


class ProactiveServiceAdapter:
    """Wraps proactive capabilities."""

    def __init__(self, second_brain_agent=None):
        self._brain = second_brain_agent

    async def get_suggestions(self, user_id: str) -> list:
        """Get proactive suggestions."""
        if self._brain and hasattr(self._brain, 'get_suggestions'):
            return await self._brain.get_suggestions(user_id)
        return []


class LLMGatewayAdapter:
    """Wraps LLM client for cognitive pipeline - integrates with ProviderManager for real provider switching."""

    def __init__(self, llm_client=None):
        self._client = llm_client
        self._provider_manager = None
        self._active_provider = "google"  # Default
        self._active_model = "gemini-2.0-flash-exp"

    def set_provider_manager(self, pm):
        """Wire in ProviderManager for live provider switching."""
        self._provider_manager = pm
        if pm:
            state = pm.get_active_state()
            if state:
                self._active_provider = state.provider_type
                self._active_model = state.model

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate LLM response - uses active provider from ProviderManager with REAL LLM API calls."""
        # Check if provider was switched via ProviderManager
        if self._provider_manager:
            state = self._provider_manager.get_active_state()
            if state:
                self._active_provider = state.provider_type
                self._active_model = state.model

        # Build messages for LLM
        messages = [{"role": "user", "content": prompt}]

        # Try using actual LLM client via .chat() method
        if self._client and hasattr(self._client, 'chat'):
            try:
                result = await self._client.chat(
                    messages=messages,
                    model=self._active_model,
                    temperature=0.15,
                    max_tokens=4096,
                    stream=False
                )
                if isinstance(result, dict) and result.get("content"):
                    return result["content"]
            except Exception as e:
                logger.error("llm_call_failed: " + str(e))

        # Fallback: try to create LLMClient directly if not provided
        try:
            from agents.llm_client import LLMClient
            client = LLMClient(provider=self._active_provider)
            result = await client.chat(
                messages=messages,
                model=self._active_model,
                temperature=0.15,
                max_tokens=4096,
                stream=False
            )
            await client.close()
            if isinstance(result, dict) and result.get("content"):
                return result["content"]
        except Exception as e:
            logger.error("llm_fallback_failed: " + str(e))

        # Last resort - indicate provider but with helpful response
        return f"I understand you're asking about '{prompt[:50]}...'. I'm connected to {self._active_provider} ({self._active_model}). Configure your API key in settings to enable full responses."

    async def _call_provider(self, prompt: str) -> str:
        """Call provider via LLM client."""
        return await self.generate(prompt)

    def get_active_provider(self) -> tuple[str, str]:
        """Get current active provider and model."""
        return self._active_provider, self._active_model