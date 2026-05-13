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

    async def update_entity(self, user_id: str, entity_type: str, entity_data: dict):
        """Update entity in world model."""
        pass  # Would delegate to brain agent


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
    """Wraps LLM client for cognitive pipeline."""

    def __init__(self, llm_client=None):
        self._client = llm_client

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate LLM response."""
        if self._client and hasattr(self._client, 'generate'):
            return await self._client.generate(prompt, **kwargs)
        return "I'm here to help. How can I assist you?"