"""
Unified Runtime Adapters
Wraps existing RasoSpeak agents to provide interfaces required by IntegratedRuntime.
"""

import asyncio
import json
from typing import Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid


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
    """Wraps memory agents for UnifiedRuntime."""

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
        """Store memory."""
        node_id = str(uuid.uuid4())
        if self._brain and hasattr(self._brain, 'add_memory'):
            await self._brain.add_memory(user_id, content, memory_type)
        return {"node_id": node_id, "content": content, "type": memory_type}

    async def retrieve(self, user_id: str, query: str, limit: int = 10) -> list:
        """Semantic memory retrieval."""
        memories = []
        if self._brain and hasattr(self._brain, 'search_memories'):
            results = await self._brain.search_memories(user_id, query, limit)
            memories = [{"content": r.get("content", ""), "type": r.get("type", "episodic"), "importance": r.get("importance", 0.5)} for r in results]
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
        """Generate LLM response - uses active provider from ProviderManager."""
        # Check if provider was switched via ProviderManager
        if self._provider_manager:
            state = self._provider_manager.get_active_state()
            if state:
                self._active_provider = state.provider_type
                self._active_model = state.model

        # Use actual LLM client if available
        if self._client and hasattr(self._client, 'generate'):
            return await self._client.generate(prompt, provider=self._active_provider, model=self._active_model, **kwargs)

        # Fallback - use provider manager directly if available
        if self._provider_manager:
            try:
                return await self._call_provider(prompt)
            except Exception as e:
                return f"I'm thinking... (provider: {self._active_provider}, model: {self._active_model})"

        return "I'm here to help. How can I assist you?"

    async def _call_provider(self, prompt: str) -> str:
        """Call provider via ProviderManager."""
        # This would integrate with actual provider API calls
        # For now, just return a response indicating provider is active
        return f"I'm thinking using {self._active_provider}/{self._active_model}"

    def get_active_provider(self) -> tuple[str, str]:
        """Get current active provider and model."""
        return self._active_provider, self._active_model