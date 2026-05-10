"""
RasoSpeak v2 — Data Schemas
Pydantic models for all WebSocket messages and agent I/O.
"""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


# ── WEBSOCKET MESSAGE TYPES ────────────────────────────
class WSMessageType(str, Enum):
    # Client → Server
    SESSION_START  = "SESSION_START"
    AUDIO_CHUNK    = "AUDIO_CHUNK"
    CHUNK_DONE     = "CHUNK_DONE"
    SESSION_END    = "SESSION_END"
    QUESTION       = "QUESTION"        # Ask AI a question
    SEARCH_QUERY   = "SEARCH_QUERY"   # Search the web
    PARTNER_START  = "PARTNER_START"  # Start partner mode
    PARTNER_STOP   = "PARTNER_STOP"   # Stop partner mode
    PARTNER_MESSAGE= "PARTNER_MESSAGE" # Message to partner
    WAKE_DETECTED  = "WAKE_DETECTED"  # Wake word detected
    IMPORT_DOCUMENT = "IMPORT_DOCUMENT" # Import document

    # Server → Client
    SESSION_READY  = "SESSION_READY"
    TRANSCRIPT     = "TRANSCRIPT"
    SCORE          = "SCORE"
    COACHING       = "COACHING"
    ADVANCE        = "ADVANCE"
    SESSION_SUMMARY= "SESSION_SUMMARY"
    ANSWER         = "ANSWER"          # AI answer to question
    SEARCH_RESULTS = "SEARCH_RESULTS" # Web search results
    PARTNER_READY  = "PARTNER_READY"  # Partner mode active
    PARTNER_RESPONSE = "PARTNER_RESPONSE" # Partner's response
    REMINDER       = "REMINDER"       # Reminder notification
    ERROR          = "ERROR"


class WSMessage(BaseModel):
    type: WSMessageType
    data: dict[str, Any] = {}


# ── SESSION CONFIG ─────────────────────────────────────
class SessionConfig(BaseModel):
    mode:         str = "hint"       # silent | hint | full
    strict:       int = 3            # 2 lenient | 3 normal | 4 strict
    chunk_size:   int = 8            # target words per chunk
    auto_advance: bool = True
    language:     str = "en"


# ── SEGMENTATION ───────────────────────────────────────
class SegmentRequest(BaseModel):
    script: str = Field(..., min_length=10, max_length=50_000, description="Script text to segment")
    target_chunk_size: int = Field(default=8, ge=3, le=30)
    style: str = Field(default="presentation", pattern="^(presentation|lecture|speech)$")


class ChunkMeta(BaseModel):
    id:                   int
    text:                 str
    word_count:           int
    type:                 str = "statement"
    emphasis_words:       list[str] = []
    suggested_pace:       str = "normal"   # slow | normal | fast
    breathing_pause_after:bool = True


class SegmentResult(BaseModel):
    chunks:                    list[ChunkMeta]
    total_chunks:              int
    total_words:               int
    estimated_duration_minutes:float
    processing_ms:             int


# ── AUDIO ──────────────────────────────────────────────
class AudioChunk(BaseModel):
    chunk_index:   int
    audio_b64:     str           # base64-encoded audio bytes
    sample_rate:   int = 16000
    expected_text: str           # the chunk text the user should be saying
    is_final:      bool = False  # True = last chunk of this listen window


# ── TRANSCRIPTION ──────────────────────────────────────
class WordTimestamp(BaseModel):
    word:       str
    start:      float
    end:        float
    confidence: float


class TranscriptResult(BaseModel):
    transcript:    str
    is_final:      bool
    confidence:    float
    words:         list[WordTimestamp] = []
    language:      str = "en"
    processing_ms: int


# ── SCORING ────────────────────────────────────────────
class ScoreResult(BaseModel):
    accuracy:         int   # 0-100: key ideas conveyed correctly
    fluency:          int   # 0-100: natural and smooth delivery
    completeness:     int   # 0-100: all key points covered
    overall:          int   # 0-100: holistic score
    passed:           bool
    missing_concepts: list[str] = []
    extra_concepts:   list[str] = []
    feedback_brief:   str   # one-sentence summary
    processing_ms:    int


# ── COACHING ───────────────────────────────────────────
class CoachResult(BaseModel):
    strategy:         str   # replay | hint | full | skip
    tts_text:         str   # text for the earpiece TTS
    display_text:     str   # text shown in the UI
    missed_concepts:  list[str] = []
    encouragement:    str = ""
    auto_skip:        bool = False
    processing_ms:    int


# ── SESSION MEMORY ─────────────────────────────────────
class ChunkRecord(BaseModel):
    chunk_index: int
    expected:    str
    attempts:    int = 0
    scores:      list[int] = []
    transcripts: list[str] = []
    passed:      bool = False
    skipped:     bool = False
    time_ms:     int = 0


class SessionStats(BaseModel):
    total_chunks:      int = 0
    chunks_done:       int = 0
    chunks_skipped:    int = 0
    total_corrections: int = 0
    avg_accuracy:      float = 0.0
    avg_fluency:       float = 0.0
    avg_wpm:           float = 0.0
    duration_seconds:  int = 0
    weak_words:        list[str] = []


# ── SESSION INSIGHTS (from CoachingAgent) ─────────────
class SessionInsights(BaseModel):
    overall_assessment: str
    strengths:          list[str]
    improvements:       list[str]
    focus_words:        list[str]   # words to practice before next session
    recommended_mode:   str         # suggested mode for next session
    encouragement:      str
