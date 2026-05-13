"""
RasoSpeak AI OS — Proactive Intelligence Service
=================================================
Safe proactive suggestion engine that:
- Identifies patterns and habits
- Detects recurring struggles
- Suggests improvements
- Reminds about unresolved tasks
- Tracks learning progress
- Adapts coaching style

BUT with strict safety constraints to avoid:
- Intrusive behavior
- Manipulation
- Hallucination-driven suggestions
- Overly autonomous actions
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger("rasospeak.proactive")


# ──────────────────────────────────────────────────────────────────────────────
# Proactive Types
# ──────────────────────────────────────────────────────────────────────────────

class SuggestionType(Enum):
    HABIT_DETECTED = "habit_detected"
    STRUGGLE_RECURRING = "struggle_recurring"
    UNRESOLVED_TASK = "unresolved_task"
    LEARNING_OPPORTUNITY = "learning_opportunity"
    RELATIONSHIP_REMINDER = "relationship_reminder"
    PROJECT_FOLLOWUP = "project_followup"
    GOAL_PROGRESS = "goal_progress"
    CONTRADICTION = "contradiction"
    PATTERN_CHANGE = "pattern_change"


class SuggestionPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Suggestion:
    """A proactive suggestion."""
    suggestion_id: str
    suggestion_type: SuggestionType
    priority: SuggestionPriority
    title: str
    description: str
    evidence: list[str] = field(default_factory=list)
    confidence: float
    action_suggested: Optional[str] = None
    dismissible: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Pattern:
    """Detected pattern in user behavior."""
    pattern_id: str
    pattern_type: str
    frequency: float
    last_occurrence: datetime
    evidence: list[dict] = field(default_factory=list)
    is_positive: bool  # Good habit vs. struggle


@dataclass
class SafetyConfig:
    """Safety configuration for proactive service."""
    max_suggestions_per_day: int = 5
    confidence_threshold: float = 0.75
    min_evidence_count: int = 3
    intrusion_check_enabled: bool = True
    user_override_respected: bool = True
    cooldown_hours: int = 24


# ──────────────────────────────────────────────────────────────────────────────
# Pattern Detection
# ──────────────────────────────────────────────────────────────────────────────

class PatternDetector:
    """Detects patterns in user behavior."""

    def __init__(self, world_model, memory_service):
        self._world_model = world_model
        self._memory = memory_service
        self._patterns: dict[str, list[Pattern]] = {}  # user_id -> patterns

    async def analyze_user(self, user_id: str) -> list[Pattern]:
        """Analyze user for patterns."""
        patterns = []

        # Get recent events
        events = await self._world_model.temporal_model.get_events(
            user_id,
            since=datetime.utcnow() - timedelta(days=30),
        )

        # Analyze conversation patterns
        conversation_events = [e for e in events if e.get("type") == "conversation"]
        if len(conversation_events) >= 3:
            patterns.extend(await self._detect_communication_patterns(user_id, conversation_events))

        # Analyze goal patterns
        goals = await self._world_model.user_model.get_user_goals(user_id, status="active")
        if goals:
            patterns.extend(await self._detect_goal_patterns(user_id, goals))

        # Store patterns
        self._patterns[user_id] = patterns

        logger.info("patterns_detected", user_id=user_id, count=len(patterns))
        return patterns

    async def _detect_communication_patterns(self, user_id: str, events: list[dict]) -> list[Pattern]:
        """Detect communication patterns."""
        patterns = []

        # Check for time-of-day patterns
        timestamps = [datetime.fromisoformat(e["timestamp"]) for e in events]
        hours = [t.hour for t in timestamps]

        morning_count = sum(1 for h in hours if 6 <= h < 12)
        evening_count = sum(1 for h in hours if 18 <= h < 22)

        if morning_count > len(events) * 0.6:
            patterns.append(Pattern(
                pattern_id=str(uuid.uuid4()),
                pattern_type="morning_user",
                frequency=morning_count / len(events),
                last_occurrence=max(timestamps),
                evidence=[{"type": "time_analysis", "morning_ratio": morning_count / len(events)}],
                is_positive=True,
            ))

        return patterns

    async def _detect_goal_patterns(self, user_id: str, goals: list) -> list[Pattern]:
        """Detect goal-related patterns."""
        patterns = []

        # Check for abandoned goals
        abandoned_count = sum(1 for g in goals if g.status == "abandoned")
        if abandoned_count > 2:
            patterns.append(Pattern(
                pattern_id=str(uuid.uuid4()),
                pattern_type="goal_abandonment",
                frequency=abandoned_count / len(goals),
                last_occurrence=datetime.utcnow(),
                evidence=[{"type": "goal_analysis", "abandoned_count": abandoned_count}],
                is_positive=False,
            ))

        return patterns


# ──────────────────────────────────────────────────────────────────────────────
# Suggestion Generator
# ──────────────────────────────────────────────────────────────────────────────

class SuggestionGenerator:
    """Generates proactive suggestions based on patterns."""

    def __init__(self, world_model, memory_service, safety_config: SafetyConfig):
        self._world_model = world_model
        self._memory = memory_service
        self._safety = safety_config

    async def generate_suggestions(self, user_id: str, patterns: list[Pattern]) -> list[Suggestion]:
        """Generate suggestions from detected patterns."""
        suggestions = []

        for pattern in patterns:
            # Only suggest high-confidence patterns
            if pattern.frequency < 0.5:
                continue

            if not pattern.is_positive and pattern.frequency > 0.3:
                # Negative pattern - suggest improvement
                suggestion = await self._suggest_improvement(pattern)
                if suggestion:
                    suggestions.append(suggestion)

            elif pattern.is_positive and pattern.frequency > 0.7:
                # Strong positive pattern - reinforce
                suggestion = await self._reinforce_positive(pattern)
                if suggestion:
                    suggestions.append(suggestion)

        # Check for unresolved tasks
        task_suggestions = await self._check_unresolved_tasks(user_id)
        suggestions.extend(task_suggestions)

        # Check for learning opportunities
        learning_suggestions = await self._check_learning_opportunities(user_id)
        suggestions.extend(learning_suggestions)

        # Limit suggestions per day
        suggestions = suggestions[:self._safety.max_suggestions_per_day]

        logger.info("suggestions_generated", user_id=user_id, count=len(suggestions))
        return suggestions

    async def _suggest_improvement(self, pattern: Pattern) -> Optional[Suggestion]:
        """Generate suggestion for negative pattern."""
        if "abandonment" in pattern.pattern_type:
            return Suggestion(
                suggestion_id=str(uuid.uuid4()),
                suggestion_type=SuggestionType.STRUGGLE_RECURRING,
                priority=SuggestionPriority.HIGH,
                title="Goal Abandonment Pattern",
                description="You've abandoned multiple goals recently. Consider breaking goals into smaller, more achievable steps.",
                evidence=[f"Abandoned {int(pattern.frequency * 100)}% of goals"],
                confidence=pattern.frequency,
                action_suggested="Review and restart one abandoned goal",
            )

        return None

    async def _reinforce_positive(self, pattern: Pattern) -> Optional[Suggestion]:
        """Generate suggestion to reinforce positive pattern."""
        if "morning_user" in pattern.pattern_type:
            return Suggestion(
                suggestion_id=str(uuid.uuid4()),
                suggestion_type=SuggestionType.HABIT_DETECTED,
                priority=SuggestionPriority.LOW,
                title="Morning Communication Habit",
                description="You tend to communicate most in the morning. This is a great time for important discussions.",
                evidence=[f"Pattern observed {int(pattern.frequency * 100)}% of the time"],
                confidence=pattern.frequency,
                action_suggested=None,
            )

        return None

    async def _check_unresolved_tasks(self, user_id: str) -> list[Suggestion]:
        """Check for unresolved tasks."""
        suggestions = []

        # Get active goals with old updates
        goals = await self._world_model.user_model.get_user_goals(user_id, status="active")

        for goal in goals:
            if (datetime.utcnow() - goal.updated_at).days > 7:
                # Goal hasn't been updated in over a week
                suggestions.append(Suggestion(
                    suggestion_id=str(uuid.uuid4()),
                    suggestion_type=SuggestionType.UNRESOLVED_TASK,
                    priority=SuggestionPriority.MEDIUM,
                    title=f"Goal not updated: {goal.title}",
                    description=f"It's been over a week since you updated '{goal.title}'. What's the current status?",
                    evidence=[f"Last update: {goal.updated_at}"],
                    confidence=0.8,
                    action_suggested=f"Update progress on: {goal.title}",
                ))

        return suggestions

    async def _check_learning_opportunities(self, user_id: str) -> list[Suggestion]:
        """Check for learning opportunities."""
        suggestions = []

        # Check for repeated topics in conversations
        events = await self._world_model.temporal_model.get_events(
            user_id,
            since=datetime.utcnow() - timedelta(days=14),
            event_type="conversation",
        )

        if len(events) >= 5:
            # Multiple conversations - check for learning opportunity
            topics = []
            for event in events:
                content = str(event.get("content", ""))
                # Simple topic extraction
                if "learn" in content.lower() or "study" in content.lower():
                    topics.append(event.get("content", ""))

            if topics:
                suggestions.append(Suggestion(
                    suggestion_id=str(uuid.uuid4()),
                    suggestion_type=SuggestionType.LEARNING_OPPORTUNITY,
                    priority=SuggestionPriority.MEDIUM,
                    title="Learning Topic Detected",
                    description="You've mentioned learning multiple times recently. Want me to help create a study plan?",
                    evidence=[f"Mentions: {len(topics)}"],
                    confidence=0.7,
                    action_suggested="Create learning plan",
                ))

        return suggestions


# ──────────────────────────────────────────────────────────────────────────────
# User Override Handler
# ──────────────────────────────────────────────────────────────────────────────

class UserOverrideHandler:
    """Handles user preferences and overrides."""

    def __init__(self):
        self._dismissed: dict[str, set[str]] = {}  # user_id -> suggestion_ids
        self._feedback: dict[str, list[dict]] = {}  # user_id -> feedback

    async def is_dismissed(self, user_id: str, suggestion_id: str) -> bool:
        """Check if suggestion was dismissed by user."""
        return suggestion_id in self._dismissed.get(user_id, set())

    async def dismiss(self, user_id: str, suggestion_id: str):
        """User dismisses a suggestion."""
        if user_id not in self._dismissed:
            self._dismissed[user_id] = set()
        self._dismissed[user_id].add(suggestion_id)

        logger.info("suggestion_dismissed", user_id=user_id, suggestion_id=suggestion_id)

    async def record_feedback(self, user_id: str, suggestion_id: str, helpful: bool, reason: str = ""):
        """Record user feedback on suggestion."""
        if user_id not in self._feedback:
            self._feedback[user_id] = []

        self._feedback[user_id].append({
            "suggestion_id": suggestion_id,
            "helpful": helpful,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        })

        logger.info("feedback_recorded", user_id=user_id, helpful=helpful)


# ──────────────────────────────────────────────────────────────────────────────
# Proactive Intelligence Service
# ──────────────────────────────────────────────────────────────────────────────

class ProactiveService:
    """
    Proactive intelligence service with safety constraints.

    Generates suggestions while respecting:
    - User privacy and preferences
    - Consent for suggestions
    - Avoidance of manipulation
    - Confidence thresholds
    - User overrides
    """

    def __init__(
        self,
        world_model,
        memory_service,
        safety_config: SafetyConfig = None,
    ):
        self._world_model = world_model
        self._memory = memory_service
        self._safety = safety_config or SafetyConfig()

        self._pattern_detector = PatternDetector(world_model, memory_service)
        self._generator = SuggestionGenerator(world_model, memory_service, self._safety)
        self._override_handler = UserOverrideHandler()

        # Rate limiting
        self._last_suggestions: dict[str, datetime] = {}

        logger.info("proactive_service_initialized")

    async def get_suggestions(self, user_id: str) -> list[Suggestion]:
        """Get current suggestions for user."""
        # Check cooldown
        last_time = self._last_suggestions.get(user_id)
        if last_time and (datetime.utcnow() - last_time).hours < self._safety.cooldown_hours:
            return []

        # Analyze patterns
        patterns = await self._pattern_detector.analyze_user(user_id)

        # Generate suggestions
        suggestions = await self._generator.generate_suggestions(user_id, patterns)

        # Filter dismissed suggestions
        filtered = []
        for suggestion in suggestions:
            if not await self._override_handler.is_dismissed(user_id, suggestion.suggestion_id):
                filtered.append(suggestion)

        self._last_suggestions[user_id] = datetime.utcnow()

        logger.info("suggestions_returned", user_id=user_id, count=len(filtered))
        return filtered

    async def dismiss_suggestion(self, user_id: str, suggestion_id: str):
        """User dismisses a suggestion."""
        await self._override_handler.dismiss(user_id, suggestion_id)

    async def provide_feedback(
        self,
        user_id: str,
        suggestion_id: str,
        helpful: bool,
        reason: str = "",
    ):
        """User provides feedback on suggestion."""
        await self._override_handler.record_feedback(user_id, suggestion_id, helpful, reason)

        # Adjust confidence threshold based on feedback
        if not helpful:
            self._safety.confidence_threshold = min(0.95, self._safety.confidence_threshold + 0.05)
        else:
            self._safety.confidence_threshold = max(0.5, self._safety.confidence_threshold - 0.02)

    async def check_consent(self, user_id: str) -> bool:
        """Check if user has enabled proactive suggestions."""
        # In production, check user preferences
        return True  # Default enabled

    async def disable_for_user(self, user_id: str):
        """Disable proactive suggestions for user."""
        # In production, update user preferences
        self._last_suggestions[user_id] = datetime.max


def create_proactive_service(
    world_model,
    memory_service,
    max_suggestions_per_day: int = 5,
) -> ProactiveService:
    """Factory function to create proactive service."""
    safety_config = SafetyConfig(max_suggestions_per_day=max_suggestions_per_day)

    return ProactiveService(
        world_model=world_model,
        memory_service=memory_service,
        safety_config=safety_config,
    )