"""
RasoSpeak v2 — SessionMemoryAgent
In-memory + Redis session state management with cross-session learning.

Tracks per-chunk results, WPM, accuracy trends, and weak words.
Feeds user history context to ScoringAgent and CoachingAgent.
"""

import asyncio
import json
import logging
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from .base_agent import BaseAgent
from config.settings import settings
from models.schemas import SessionConfig

log = logging.getLogger("rasospeak.memory")


class SessionMemoryAgent(BaseAgent):
    """
    Agent 5: SessionMemoryAgent

    Manages all session state — no LLM required.
    Provides context to other agents:
      - User's historical weak words → ScoringAgent + CoachingAgent
      - Attempt counts per chunk → CoachingAgent (for auto-skip)
      - Progress tracking → frontend UI

    Also persists completed sessions for the stats dashboard.
    """

    name = "SessionMemoryAgent"

    def __init__(self):
        # In-memory store (Redis optional for production)
        self._sessions: dict[str, dict] = {}
        self._redis = None

    async def initialize(self):
        """Try to connect to Redis; fall back to in-memory if unavailable."""
        try:
            import redis.asyncio as aioredis
            self._redis = await aioredis.from_url(
                f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}",
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()
            log.info(f"✅ SessionMemoryAgent connected to Redis")
        except Exception as e:
            log.warning(f"Redis unavailable ({e}) — using in-memory store only")
            self._redis = None

        # Start background cleanup task for session TTL enforcement
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_sessions())

    async def create_session(self, session_id: str) -> dict:
        """Initialize a new coaching session."""
        session = {
            "session_id":    session_id,
            "created_at":    datetime.utcnow().isoformat(),
            "config":        {},
            "chunk_records": {},
            "weak_words":    await self._load_weak_words(session_id),
            "stats": {
                "total_chunks":      0,
                "chunks_done":       0,
                "chunks_skipped":    0,
                "total_corrections": 0,
                "avg_accuracy":      0.0,
                "avg_fluency":       0.0,
                "avg_wpm":           0.0,
                "duration_seconds":  0,
            },
            "_started_at": time.time(),
            "_wpm_samples": [],
            "_acc_samples": [],
            "_flu_samples": [],
        }
        self._sessions[session_id] = session
        log.info(f"📝 Session created: {session_id}")
        return session

    async def update_config(self, session_id: str, config: SessionConfig):
        s = self._sessions.get(session_id)
        if s:
            s["config"] = config.model_dump()
            s["stats"]["total_chunks"] = config.chunk_size  # updated when chunks loaded

    async def get_session(self, session_id: str) -> Optional[dict]:
        return self._sessions.get(session_id)

    async def get_weak_words(self, session_id: str) -> list[str]:
        s = self._sessions.get(session_id, {})
        return s.get("weak_words", [])

    async def get_attempts(self, session_id: str, chunk_index: int) -> int:
        s = self._sessions.get(session_id, {})
        record = s.get("chunk_records", {}).get(str(chunk_index), {})
        return record.get("attempts", 0)

    async def get_progress(self, session_id: str) -> dict:
        s     = self._sessions.get(session_id, {})
        stats = s.get("stats", {})
        total = stats.get("total_chunks", 1) or 1
        done  = stats.get("chunks_done", 0)
        return {
            "done":  done,
            "total": total,
            "pct":   min(100, round(done / total * 100)),
        }

    async def record_chunk_result(
        self,
        session_id:  str,
        chunk_index: int,
        score:       dict,
        transcript:  str,
        expected:    str,
    ):
        """Record the result of a chunk attempt."""
        s   = self._sessions.get(session_id)
        if not s: return

        key    = str(chunk_index)
        record = s["chunk_records"].setdefault(key, {
            "chunk_index":   chunk_index,
            "expected":      expected,
            "attempts":      0,
            "scores":        [],
            "score_details": [],
            "transcripts":   [],
            "passed":        False,
            "skipped":       False,
            "time_ms":       0,
        })

        record["attempts"]      += 1
        record["scores"].append(score.get("overall", 0))
        record["score_details"].append(score)
        record["transcripts"].append(transcript)

        stats = s["stats"]

        if score.get("passed"):
            record["passed"]     = True
            stats["chunks_done"] += 1
            self._update_acc(s, score)
        else:
            stats["total_corrections"] += 1
            # Track missed concepts as weak words
            for concept in score.get("missing_concepts", []):
                for word in concept.split():
                    if len(word) > 3:
                        s.setdefault("_weak_candidates", []).append(word.lower())

        log.debug(
            f"Chunk {chunk_index}: attempt {record['attempts']}, "
            f"score {score.get('overall')}%, passed={score.get('passed')}"
        )

    async def record_skip(self, session_id: str, chunk_index: int):
        s = self._sessions.get(session_id)
        if not s: return
        key    = str(chunk_index)
        record = s["chunk_records"].setdefault(key, {"skipped": False})
        record["skipped"] = True
        s["stats"]["chunks_skipped"] += 1

    async def close_session(self, session_id: str):
        """Finalize session stats when WebSocket disconnects."""
        s = self._sessions.get(session_id)
        if not s: return

        elapsed = int(time.time() - s.get("_started_at", time.time()))
        s["stats"]["duration_seconds"] = elapsed
        self._finalize_weak_words(s)
        log.info(f"Session {session_id} closed after {elapsed}s")

    async def persist_session(self, session_id: str):
        """Save completed session to Redis (or local file as fallback)."""
        s = self._sessions.get(session_id)
        if not s: return

        # Build a clean persistence record
        record = {
            "session_id":  session_id,
            "date":        datetime.utcnow().strftime("%Y-%m-%d"),
            "time":        datetime.utcnow().strftime("%H:%M"),
            "stats":       s["stats"],
            "weak_words":  s.get("weak_words", []),
            "config":      s.get("config", {}),
        }

        if self._redis:
            try:
                key     = f"rs:session:{session_id}"
                hist_key= f"rs:history:{session_id.split('-')[0]}"  # user prefix
                await self._redis.setex(key, settings.session_ttl_seconds, json.dumps(record))
                # Push to history list (keep last 20)
                await self._redis.lpush(hist_key, json.dumps(record))
                await self._redis.ltrim(hist_key, 0, settings.max_history_sessions - 1)
                log.info(f"✅ Session {session_id} persisted to Redis")
            except Exception as e:
                log.warning(f"Redis persist failed: {e}")
        else:
            # Fallback: store in memory only (browser will use localStorage)
            log.info(f"Session {session_id} stats available in memory")

    # ── INTERNAL HELPERS ──────────────────────────────

    def _update_acc(self, session: dict, score: dict):
        session["_acc_samples"].append(score.get("accuracy", 0))
        session["_flu_samples"].append(score.get("fluency", 0))
        stats = session["stats"]
        if session["_acc_samples"]:
            stats["avg_accuracy"] = round(
                sum(session["_acc_samples"]) / len(session["_acc_samples"]), 1
            )
        if session["_flu_samples"]:
            stats["avg_fluency"] = round(
                sum(session["_flu_samples"]) / len(session["_flu_samples"]), 1
            )

    def _finalize_weak_words(self, session: dict):
        """Compute final weak word list from all missed concepts this session."""
        candidates = session.get("_weak_candidates", [])
        if candidates:
            # Words missed 2+ times are "weak words"
            counter   = Counter(candidates)
            new_weak  = [w for w, cnt in counter.most_common(15) if cnt >= 2]
            # Merge with existing, deduplicate
            existing  = session.get("weak_words", [])
            merged    = list(dict.fromkeys(new_weak + existing))[:15]
            session["weak_words"] = merged

    async def _load_weak_words(self, session_id: str) -> list[str]:
        """Load historical weak words for this user from Redis."""
        if not self._redis:
            return []
        try:
            user_prefix = session_id.split("-")[0]
            hist_key    = f"rs:history:{user_prefix}"
            history_raw = await self._redis.lrange(hist_key, 0, 4)  # last 5 sessions
            all_weak    = []
            for raw in history_raw:
                sess = json.loads(raw)
                all_weak.extend(sess.get("weak_words", []))
            return list(dict.fromkeys(all_weak))[:15]
        except Exception:
            return []

    async def _cleanup_expired_sessions(self):
        """Background task: remove in-memory sessions older than session_ttl_seconds."""
        while True:
            await asyncio.sleep(300)  # Check every 5 minutes
            try:
                cutoff = datetime.utcnow() - timedelta(seconds=settings.session_ttl_seconds)
                cutoff_ts = cutoff.timestamp()
                removed = 0
                for session_id in list(self._sessions.keys()):
                    session = self._sessions[session_id]
                    started_at = session.get("_started_at", 0)
                    if started_at > 0 and started_at < cutoff_ts:
                        del self._sessions[session_id]
                        removed += 1
                if removed > 0:
                    log.info(f"🧹 TTL cleanup: removed {removed} expired sessions")
            except Exception as e:
                log.warning(f"TTL cleanup task error: {e}")

    async def cleanup_old_sessions(self, max_age_days: int = 30) -> int:
        """Remove sessions older than max_age_days to prevent memory leaks."""
        import time
        cutoff = time.time() - (max_age_days * 86400)
        removed = 0

        for session_id in list(self._sessions.keys()):
            session = self._sessions[session_id]
            started_at = session.get("_started_at", 0)
            if started_at > 0 and started_at < cutoff:
                del self._sessions[session_id]
                removed += 1

        if removed > 0:
            log.info(f"🧹 Cleaned up {removed} old sessions (> {max_age_days} days)")
        return removed

    async def get_session_count(self) -> int:
        """Get current session count for monitoring."""
        return len(self._sessions)

    async def shutdown(self):
        # Cancel the cleanup background task
        if hasattr(self, "_cleanup_task") and self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        if self._redis:
            await self._redis.aclose()
        log.info("SessionMemoryAgent shut down")
