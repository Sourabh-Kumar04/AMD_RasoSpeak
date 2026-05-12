"""
RasoSpeak v2 — Analytics Agent
Analyzes recorded sessions, conversations, and speech patterns.

Generates insights on:
- Speech improvement over time
- Common questions asked
- Q&A patterns
- Coaching effectiveness
- Pronunciation weak points
- Pace and fluency trends
"""

import json
import logging
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx

from .base_agent import BaseAgent
from config.settings import settings

log = logging.getLogger("rasospeak.analytics")


class AnalyticsAgent(BaseAgent):
    """
    Agent for analyzing recorded sessions and generating insights.

    Provides:
    - Personal speech analytics (accuracy trends, weak words)
    - Q&A history analysis (common topics, providers used)
    - Session comparisons (improvement over time)
    - Coaching effectiveness metrics
    """

    name = "AnalyticsAgent"

    def __init__(self):
        self._storage_path = Path(settings.recordings_path or "./recordings")
        self._client: Optional[httpx.AsyncClient] = None

    async def initialize(self):
        """Initialize analytics system."""
        if settings.vllm_base_url:
            self._client = httpx.AsyncClient(
                base_url=settings.vllm_base_url,
                timeout=30.0,
            )
        log.info("✅ AnalyticsAgent initialized")
        self._shared_memory = None
        self._second_brain = None  # Second Brain for enhanced memory analytics

    def set_second_brain(self, second_brain):
        """Connect to Second Brain for enhanced memory analytics."""
        self._second_brain = second_brain
        log.info("AnalyticsAgent connected to SecondBrainAgent")

    def set_shared_memory(self, shared_memory):
        """Connect to shared memory."""
        self._shared_memory = shared_memory

    async def generate_session_analytics(self, session_id: str) -> dict:
        """
        Generate comprehensive analytics for a session.

        Returns:
            SessionAnalytics with charts data, trends, insights
        """
        log.info(f"Generating analytics for session: {session_id}")

        # Load session data
        session_data = await self._load_session(session_id)
        if not session_data:
            return {"error": "Session not found"}

        # Calculate metrics
        analytics = {
            "session_id": session_id,
            "generated_at": datetime.utcnow().isoformat(),

            # Basic stats
            "duration_seconds": session_data.get("duration_seconds", 0),
            "total_chunks": len(session_data.get("transcripts", [])),
            "total_qa": len(session_data.get("qa_interactions", [])),
            "total_audio_recordings": len(session_data.get("audio_files", [])),

            # Transcript analytics
            "transcript_stats": self._analyze_transcripts(session_data),

            # Q&A analytics
            "qa_stats": self._analyze_qa(session_data),

            # Coaching analytics
            "coaching_stats": self._analyze_coaching(session_data),

            # Provider usage
            "provider_usage": self._analyze_providers(session_data),
        }

        # Generate AI insights if LLM available
        if self._client:
            insights = await self._generate_ai_insights(session_data)
            analytics["ai_insights"] = insights

        log.info(f"Analytics generated for {session_id}")
        return analytics

    async def generate_user_analytics(self, user_id: str, days: int = 30) -> dict:
        """
        Generate analytics across multiple sessions for a user.

        Args:
            user_id: User identifier (prefix of session_id)
            days: Number of days to analyze

        Returns:
            UserAnalytics with trends, comparisons, recommendations
        """
        log.info(f"Generating user analytics for: {user_id}, days={days}")

        sessions = await self._load_user_sessions(user_id, days)
        if not sessions:
            return {"error": "No sessions found for user"}

        # Aggregate metrics
        total_sessions = len(sessions)
        total_duration = sum(s.get("duration_seconds", 0) for s in sessions)
        total_questions = sum(len(s.get("qa_interactions", [])) for s in sessions)

        # Calculate trends
        accuracy_trend = self._calculate_accuracy_trend(sessions)
        qa_trend = self._calculate_qa_trend(sessions)

        # Find common patterns
        common_questions = self._find_common_questions(sessions)
        weak_words = self._find_weak_words(sessions)

        return {
            "user_id": user_id,
            "period_days": days,
            "generated_at": datetime.utcnow().isoformat(),

            "summary": {
                "total_sessions": total_sessions,
                "total_duration_minutes": round(total_duration / 60, 1),
                "total_questions_asked": total_questions,
                "avg_session_duration": round(total_duration / total_sessions / 60, 1) if total_sessions else 0,
            },

            "trends": {
                "accuracy_trend": accuracy_trend,
                "qa_frequency_trend": qa_trend,
            },

            "patterns": {
                "common_questions": common_questions[:10],
                "identified_weak_words": weak_words[:15],
            },

            "recommendations": self._generate_recommendations(sessions),
        }

    async def get_speech_improvement_report(self, user_id: str) -> dict:
        """Generate a report showing speech improvement over time."""
        sessions = await self._load_user_sessions(user_id, days=90)

        if len(sessions) < 2:
            return {
                "status": "insufficient_data",
                "message": "Need at least 2 sessions to show improvement",
                "sessions_count": len(sessions),
            }

        # Calculate improvement metrics
        first_session = sessions[-1]
        last_session = sessions[0]

        first_accuracy = self._get_avg_accuracy(first_session)
        last_accuracy = self._get_avg_accuracy(last_session)

        improvement = last_accuracy - first_accuracy

        return {
            "user_id": user_id,
            "report_date": datetime.utcnow().isoformat(),
            "sessions_analyzed": len(sessions),

            "improvement": {
                "accuracy_delta": improvement,
                "first_session_accuracy": first_accuracy,
                "latest_session_accuracy": last_accuracy,
                "trend": "improving" if improvement > 5 else "stable" if improvement > -5 else "declining",
            },

            "milestones": self._calculate_milestones(sessions),

            "encouragement": self._generate_encouragement(improvement),
        }

    async def get_qa_topics_analysis(self, user_id: str) -> dict:
        """Analyze what topics the user asks about most."""
        sessions = await self._load_user_sessions(user_id, days=30)

        all_questions = []
        for session in sessions:
            all_questions.extend(session.get("questions_asked", []))

        # Categorize questions
        categories = {
            "factual": [],
            "how_to": [],
            "why": [],
            "definition": [],
            "opinion": [],
            "other": [],
        }

        question_lower = [q.lower() for q in all_questions]
        for q in question_lower:
            if any(w in q for w in ["what is", "who is", "when", "where"]):
                categories["factual"].append(q)
            elif "how" in q:
                categories["how_to"].append(q)
            elif "why" in q:
                categories["why"].append(q)
            elif "mean" in q or "definition" in q:
                categories["definition"].append(q)
            elif any(w in q for w in ["should", "think", "opinion", "best"]):
                categories["opinion"].append(q)
            else:
                categories["other"].append(q)

        return {
            "total_questions": len(all_questions),
            "categories": {k: len(v) for k, v in categories.items()},
            "sample_questions": all_questions[:20],
        }

    # ── Internal helpers ────────────────────────────────────

    def _analyze_transcripts(self, session_data: dict) -> dict:
        """Analyze transcript data from a session."""
        transcripts = session_data.get("transcripts", [])
        if not transcripts:
            return {"total": 0}

        scores = [t.get("score", {}).get("overall", 0) for t in transcripts if t.get("score")]
        accuracies = [t.get("score", {}).get("accuracy", 0) for t in transcripts if t.get("score")]
        fluencies = [t.get("score", {}).get("fluency", 0) for t in transcripts if t.get("score")]

        return {
            "total": len(transcripts),
            "avg_overall": round(sum(scores) / len(scores), 1) if scores else 0,
            "avg_accuracy": round(sum(accuracies) / len(accuracies), 1) if accuracies else 0,
            "avg_fluency": round(sum(fluencies) / len(fluencies), 1) if fluencies else 0,
            "passed_chunks": sum(1 for s in scores if s >= 55),
            "failed_chunks": sum(1 for s in scores if s < 55),
        }

    def _analyze_qa(self, session_data: dict) -> dict:
        """Analyze Q&A interactions."""
        qa_list = session_data.get("qa_interactions", [])
        if not qa_list:
            return {"total": 0}

        providers = [qa.get("provider") for qa in qa_list]
        provider_counts = Counter(providers)

        return {
            "total": len(qa_list),
            "providers_used": dict(provider_counts),
            "most_used_provider": provider_counts.most_common(1)[0][0] if provider_counts else None,
        }

    def _analyze_coaching(self, session_data: dict) -> dict:
        """Analyze coaching events."""
        events = session_data.get("coaching_events", [])
        if not events:
            return {"total": 0}

        strategies = [e.get("strategy") for e in events]
        strategy_counts = Counter(strategies)

        return {
            "total": len(events),
            "strategies_used": dict(strategy_counts),
            "most_used_strategy": strategy_counts.most_common(1)[0][0] if strategy_counts else None,
        }

    def _analyze_providers(self, session_data: dict) -> dict:
        """Analyze AI provider usage."""
        providers = set()
        for qa in session_data.get("qa_interactions", []):
            if qa.get("provider"):
                providers.add(qa["provider"])

        return {
            "providers_used": list(providers),
            "total_providers": len(providers),
        }

    async def _load_session(self, session_id: str) -> dict:
        """Load session data from storage."""
        filepath = self._storage_path / "conversations" / f"{session_id}.json"
        if filepath.exists():
            return json.loads(filepath.read_text())
        return None

    async def _load_user_sessions(self, user_id: str, days: int) -> list:
        """Load all sessions for a user within a time period."""
        sessions = []
        conv_path = self._storage_path / "conversations"

        cutoff = datetime.utcnow() - timedelta(days=days)

        for filepath in conv_path.glob(f"{user_id}-*.json"):
            try:
                data = json.loads(filepath.read_text())
                started = datetime.fromisoformat(data.get("started_at", ""))
                if started >= cutoff:
                    sessions.append(data)
            except Exception:
                continue

        return sorted(sessions, key=lambda x: x.get("started_at", ""), reverse=True)

    def _calculate_accuracy_trend(self, sessions: list) -> dict:
        """Calculate accuracy trend across sessions."""
        accuracies = []
        for session in sessions:
            transcripts = session.get("transcripts", [])
            if transcripts:
                scores = [t.get("score", {}).get("overall", 0) for t in transcripts if t.get("score")]
                if scores:
                    accuracies.append(sum(scores) / len(scores))

        if len(accuracies) < 2:
            return {"trend": "insufficient_data", "delta": 0}

        return {
            "trend": "improving" if accuracies[-1] > accuracies[0] else "declining",
            "delta": round(accuracies[-1] - accuracies[0], 1),
            "sessions": len(accuracies),
        }

    def _calculate_qa_trend(self, sessions: list) -> dict:
        """Calculate Q&A frequency trend."""
        qa_counts = [len(s.get("qa_interactions", [])) for s in sessions]

        if len(qa_counts) < 2:
            return {"trend": "stable"}

        return {
            "trend": "increasing" if qa_counts[0] > qa_counts[-1] else "decreasing",
            "first_session": qa_counts[-1] if qa_counts else 0,
            "latest_session": qa_counts[0] if qa_counts else 0,
        }

    def _find_common_questions(self, sessions: list) -> list:
        """Find most commonly asked questions."""
        all_questions = []
        for session in sessions:
            all_questions.extend(session.get("questions_asked", []))

        # Simple keyword-based clustering
        return [q for q, _ in Counter(all_questions).most_common(20)]

    def _find_weak_words(self, sessions: list) -> list:
        """Find words user struggles with across sessions."""
        all_missing = []
        for session in sessions:
            for transcript in session.get("transcripts", []):
                score = transcript.get("score", {})
                all_missing.extend(score.get("missing_concepts", []))

        return [w for w, _ in Counter(all_missing).most_common(15)]

    def _get_avg_accuracy(self, session: dict) -> float:
        """Get average accuracy from a session."""
        transcripts = session.get("transcripts", [])
        if not transcripts:
            return 0

        accuracies = [t.get("score", {}).get("accuracy", 0) for t in transcripts if t.get("score")]
        return sum(accuracies) / len(accuracies) if accuracies else 0

    def _calculate_milestones(self, sessions: list) -> list:
        """Calculate improvement milestones."""
        milestones = []
        accuracies = []

        for session in sessions:
            acc = self._get_avg_accuracy(session)
            if acc > 0:
                accuracies.append((session.get("started_at"), acc))

        if len(accuracies) >= 3:
            # Find first time hitting 80%
            for date, acc in accuracies:
                if acc >= 80:
                    milestones.append({"type": "accuracy_80", "date": date})
                    break

        return milestones

    def _generate_recommendations(self, sessions: list) -> list:
        """Generate personalized recommendations."""
        recommendations = []

        if len(sessions) < 3:
            recommendations.append("Practice more sessions to get personalized recommendations")
            return recommendations

        recent = sessions[0]
        avg_acc = self._get_avg_accuracy(recent)

        if avg_acc < 60:
            recommendations.append("Focus on speaking slower and clearer")
            recommendations.append("Review the coaching feedback for each chunk")
        elif avg_acc < 80:
            recommendations.append("Great progress! Focus on pronunciation of technical terms")
        else:
            recommendations.append("Excellent performance! Practice maintaining consistency")

        return recommendations

    def _generate_encouragement(self, improvement: float) -> str:
        """Generate encouraging message based on improvement."""
        if improvement > 15:
            return "Amazing progress! You've improved significantly."
        elif improvement > 5:
            return "Great job! You're consistently improving."
        elif improvement > -5:
            return "Keep practicing! Consistency is key to improvement."
        else:
            return "Don't worry - every session helps. Focus on one chunk at a time."

    async def _generate_ai_insights(self, session_data: dict) -> dict:
        """Generate AI-powered insights using LLM."""
        if not self._client:
            return {"error": "LLM not available"}

        try:
            prompt = f"""Analyze this speech coaching session and provide insights:

Session Stats:
- Duration: {session_data.get('duration_seconds', 0)} seconds
- Chunks completed: {len(session_data.get('transcripts', []))}
- Q&A interactions: {len(session_data.get('qa_interactions', []))}

Provide a brief assessment in JSON:
{{
  "highlights": ["key strength observed"],
  "areas_for_improvement": ["specific suggestion"],
  "next_practice_focus": "what to focus on"
}}"""

            resp = await self._client.post(
                "/chat/completions",
                json={
                    "model": settings.qa_model or "Qwen/Qwen2.5-7B-Instruct",
                    "messages": [
                        {"role": "system", "content": "You are a speech coaching analytics expert."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 256,
                    "temperature": 0.3,
                }
            )
            resp.raise_for_status()
            data = resp.json()
            return json.loads(data["choices"][0]["message"]["content"])

        except Exception as e:
            log.warning(f"AI insights generation failed: {e}")
            return {"error": str(e)}

    async def shutdown(self):
        if self._client:
            await self._client.aclose()
        log.info("AnalyticsAgent shut down")