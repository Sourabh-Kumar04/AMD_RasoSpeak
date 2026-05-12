"""
RasoSpeak v2 — Recording Agent
Records all audio, conversations, and interactions for analytics.

Tracks:
- All speech/audio recordings
- Q&A interactions
- Coaching sessions
- User questions and AI responses
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from .base_agent import BaseAgent
from config.settings import settings

log = logging.getLogger("rasospeak.recording")


class RecordingAgent(BaseAgent):
    """
    Agent for recording and storing all interactions.

    Records:
    - Audio chunks during sessions
    - Q&A conversations
    - User questions and AI answers
    - Coaching feedback given

    Enables analytics on speech patterns, common questions,
    improvement over time, etc.
    """

    name = "RecordingAgent"

    def __init__(self):
        self._storage_path = Path(settings.recordings_path or "./recordings")
        self._current_session: Optional[str] = None
        self._session_records: dict = {}
        self._audio_lock = asyncio.Lock()  # Prevent race conditions in audio recording
        self._shared_memory = None
        self._second_brain = None  # Second Brain for enhanced audio memory
        self._ensure_storage()

    def _ensure_storage(self):
        """Create storage directories if they don't exist."""
        self._storage_path.mkdir(parents=True, exist_ok=True)
        (self._storage_path / "audio").mkdir(exist_ok=True)
        (self._storage_path / "conversations").mkdir(exist_ok=True)
        (self._storage_path / "qa_history").mkdir(exist_ok=True)
        log.info(f"Recording storage: {self._storage_path}")

    async def initialize(self):
        """Initialize recording system."""
        log.info("✅ RecordingAgent initialized")
        log.info(f"   Storage: {self._storage_path}")
        self._shared_memory = None

    def set_second_brain(self, second_brain):
        """Connect to Second Brain for enhanced audio memory storage."""
        self._second_brain = second_brain
        log.info("RecordingAgent connected to SecondBrainAgent")

    def set_shared_memory(self, shared_memory):
        """Connect to shared memory."""
        self._shared_memory = shared_memory

    async def start_session_recording(self, session_id: str, metadata: dict = None) -> dict:
        """Start recording a new session."""
        self._current_session = session_id
        self._session_records[session_id] = {
            "session_id": session_id,
            "started_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
            "audio_files": [],
            "qa_interactions": [],
            "coaching_events": [],
            "transcripts": [],
            "questions_asked": [],
            "answers_received": [],
        }
        log.info(f"📹 Recording started: {session_id}")
        return {"session_id": session_id, "status": "recording"}

    async def stop_session_recording(self, session_id: str) -> dict:
        """Stop recording and save session data to both memory systems."""
        if session_id in self._session_records:
            record = self._session_records[session_id]
            record["ended_at"] = datetime.utcnow().isoformat()
            record["duration_seconds"] = self._calculate_duration(record)

            # Save to disk
            await self._save_session_record(session_id, record)

            # Store in Second Brain (primary - with semantic search, entity extraction)
            if self._second_brain:
                # Store audio conversation transcript
                if record.get("transcripts"):
                    await self._second_brain.store_audio_conversation(
                        session_id=session_id,
                        transcription="\n".join(record["transcripts"]),
                        speakers=["user", "coach"],
                        duration=record["duration_seconds"],
                    )

                # Store Q&A interactions as conversations
                for qa in record.get("qa_interactions", []):
                    await self._second_brain.add_conversation(
                        user_input=qa.get("question", ""),
                        ai_response=qa.get("answer", ""),
                        ai_provider="recording_agent",
                        context=f"session:{session_id}",
                    )

            # Store in shared memory (backward compatibility)
            if self._shared_memory:
                await self._shared_memory.store(
                    f"session_{session_id}",
                    record,
                    category="session"
                )

            log.info(f"📹 Recording stopped: {session_id}, duration={record['duration_seconds']}s")
            del self._session_records[session_id]

        if self._current_session == session_id:
            self._current_session = None

        return {"session_id": session_id, "status": "saved"}

    async def record_audio(
        self,
        session_id: str,
        audio_b64: str,
        audio_type: str = "user_speech",
        metadata: dict = None,
    ) -> dict:
        """
        Record an audio chunk.

        Args:
            session_id: The session ID
            audio_b64: Base64-encoded audio
            audio_type: Type of audio (user_speech, coaching_tts, etc.)
            metadata: Additional metadata

        Returns:
            RecordingResult with file info
        """
        async with self._audio_lock:  # Prevent race conditions
            t_start = time.perf_counter()
            record = self._session_records.get(session_id)

            if not record:
                return {"error": "Session not recording"}

            # Save audio file
            filename = f"{session_id}_{audio_type}_{int(time.time())}.wav"
            filepath = self._storage_path / "audio" / filename

            try:
                import base64
                audio_bytes = base64.b64decode(audio_b64)
                filepath.write_bytes(audio_bytes)

                record["audio_files"].append({
                    "filename": filename,
                    "type": audio_type,
                    "timestamp": datetime.utcnow().isoformat(),
                    "size_bytes": len(audio_bytes),
                    "metadata": metadata or {},
                })

                elapsed_ms = int((time.perf_counter() - t_start) * 1000)
                return {
                    "recorded": True,
                    "filename": filename,
                    "size_bytes": len(audio_bytes),
                    "processing_ms": elapsed_ms,
                }
            except Exception as e:
                log.error(f"Failed to record audio: {e}")
                return {"error": str(e)}

    async def record_qa_interaction(
        self,
        session_id: str,
        question: str,
        answer: str,
        provider: str,
        metadata: dict = None,
    ) -> dict:
        """
        Record a Q&A interaction.

        Args:
            session_id: The session ID
            question: User's question
            answer: AI's answer
            provider: Which AI provider was used
            metadata: Additional metadata

        Returns:
            RecordingResult
        """
        record = self._session_records.get(session_id)
        if not record:
            return {"error": "Session not recording"}

        interaction = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.utcnow().isoformat(),
            "question": question,
            "answer": answer,
            "provider": provider,
            "metadata": metadata or {},
        }

        record["qa_interactions"].append(interaction)
        record["questions_asked"].append(question)
        record["answers_received"].append(answer)

        log.info(f"💬 Q&A recorded: {interaction['id']} provider={provider}")

        # Also save to dedicated qa_history folder
        await self._save_qa_record(session_id, interaction)

        return {"recorded": True, "interaction_id": interaction["id"]}

    async def record_coaching_event(
        self,
        session_id: str,
        chunk_index: int,
        score: dict,
        coaching_text: str,
        strategy: str,
    ) -> dict:
        """Record a coaching event."""
        record = self._session_records.get(session_id)
        if not record:
            return {"error": "Session not recording"}

        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "chunk_index": chunk_index,
            "score": score,
            "coaching_text": coaching_text,
            "strategy": strategy,
        }

        record["coaching_events"].append(event)
        log.info(f"📝 Coaching event recorded: chunk={chunk_index}, strategy={strategy}")

        return {"recorded": True}

    async def record_transcript(
        self,
        session_id: str,
        chunk_index: int,
        expected: str,
        spoken: str,
        score: dict = None,
    ) -> dict:
        """Record a transcript with score."""
        record = self._session_records.get(session_id)
        if not record:
            return {"error": "Session not recording"}

        transcript = {
            "timestamp": datetime.utcnow().isoformat(),
            "chunk_index": chunk_index,
            "expected": expected,
            "spoken": spoken,
            "score": score,
        }

        record["transcripts"].append(transcript)
        return {"recorded": True}

    async def get_session_record(self, session_id: str) -> dict:
        """Get recording data for a session."""
        if session_id in self._session_records:
            return self._session_records[session_id]

        # Try loading from disk
        filepath = self._storage_path / "conversations" / f"{session_id}.json"
        if filepath.exists():
            return json.loads(filepath.read_text())

        return None

    async def get_all_recordings(self, limit: int = 50) -> list:
        """Get list of all recorded sessions."""
        recordings = []
        conv_path = self._storage_path / "conversations"

        for filepath in sorted(conv_path.glob("*.json"), reverse=True)[:limit]:
            try:
                data = json.loads(filepath.read_text())
                recordings.append({
                    "session_id": data.get("session_id"),
                    "started_at": data.get("started_at"),
                    "ended_at": data.get("ended_at"),
                    "duration_seconds": data.get("duration_seconds"),
                    "qa_count": len(data.get("qa_interactions", [])),
                    "audio_count": len(data.get("audio_files", [])),
                })
            except Exception:
                continue

        return recordings

    async def _save_session_record(self, session_id: str, record: dict):
        """Save session record to disk."""
        filepath = self._storage_path / "conversations" / f"{session_id}.json"
        filepath.write_text(json.dumps(record, indent=2))

    async def _save_qa_record(self, session_id: str, interaction: dict):
        """Save individual Q&A record."""
        filepath = self._storage_path / "qa_history" / f"{session_id}_{interaction['id']}.json"
        filepath.write_text(json.dumps(interaction, indent=2))

    def _calculate_duration(self, record: dict) -> int:
        """Calculate session duration in seconds."""
        try:
            start = datetime.fromisoformat(record["started_at"])
            end = datetime.fromisoformat(record.get("ended_at", datetime.utcnow().isoformat()))
            return int((end - start).total_seconds())
        except Exception:
            return 0

    async def shutdown(self):
        # Save any pending recordings
        for session_id, record in self._session_records.items():
            await self._save_session_record(session_id, record)
        log.info("RecordingAgent shut down")