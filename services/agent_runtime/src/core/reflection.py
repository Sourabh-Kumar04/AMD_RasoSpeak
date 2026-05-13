"""
RasoSpeak AI OS — Reflection Engine
====================================
Genuine self-evaluation with:
- Performance analysis
- Error categorization
- Insight extraction
- Behavioral adaptation
- Learning updates
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger("rasospeak.reflection")


# ──────────────────────────────────────────────────────────────────────────────
# Reflection Types
# ──────────────────────────────────────────────────────────────────────────────

class ErrorCategory(Enum):
    """Categories for classifying execution errors."""
    PLANNING_FAILURE = "planning_failure"       # Task decomposition was wrong
    TOOL_FAILURE = "tool_failure"               # Tool execution failed
    VERIFICATION_FAILURE = "verification_failure"  # Output didn't meet criteria
    RESOURCE_EXHAUSTION = "resource_exhaustion"  # Ran out of time/tokens
    CONTEXT_OVERFLOW = "context_overflow"        # Context too large
    COORDINATION_FAILURE = "coordination_failure"  # Cross-agent issues
    UNKNOWN = "unknown"


class PerformanceLevel(Enum):
    """How well the agent performed."""
    EXCELLENT = "excellent"
    GOOD = "good"
    ADEQUATE = "adequate"
    POOR = "poor"
    FAILED = "failed"


@dataclass
class ExecutionTrace:
    """A single action in the execution history."""
    action_type: str
    timestamp: datetime
    details: dict[str, Any]
    success: bool
    duration_ms: int
    tokens_used: int


@dataclass
class ReflectionResult:
    """Result of self-reflection."""
    confidence_multiplier: float          # 0.0 - 1.5, how much to adjust confidence
    performance_level: PerformanceLevel
    error_categories: list[ErrorCategory]
    insights: list[str]
    suggestions: list[str]
    learning_updates: list[dict[str, Any]]
    next_strategy: str
    reasoning: str
    metrics: dict[str, float]


@dataclass
class LearningRecord:
    """Record of what was learned from an execution."""
    record_id: str
    timestamp: datetime
    goal_type: str
    strategy_used: str
    success: bool
    performance_level: PerformanceLevel
    error_categories: list[ErrorCategory]
    tokens_used: int
    cycles_used: int
    lessons_learned: list[str]


# ──────────────────────────────────────────────────────────────────────────────
# Performance Analyzer
# ──────────────────────────────────────────────────────────────────────────────

class PerformanceAnalyzer:
    """
    Analyzes execution trace to determine how well the agent performed.

    Metrics considered:
    - Success rate of tool calls
    - Token efficiency
    - Cycle efficiency (did it need multiple attempts?)
    - Verification success
    - Time efficiency
    """

    # Thresholds for performance classification
    TOKEN_EFFICIENCY_THRESHOLD = 0.7   # Tokens used vs estimated
    CYCLE_EFFICIENCY_THRESHOLD = 1.5  # Cycles used vs optimal
    TOOL_SUCCESS_THRESHOLD = 0.8       # Fraction of successful tool calls
    VERIFICATION_THRESHOLD = 0.8      # Fraction of successful verifications

    def analyze(
        self,
        actions: list[dict],
        estimated_tokens: int,
        actual_tokens: int,
        cycles: int,
        verified: bool,
    ) -> tuple[PerformanceLevel, dict[str, float]]:
        """
        Analyze performance and return level with detailed metrics.

        Returns:
            (PerformanceLevel, metrics_dict)
        """
        metrics = {}

        # Token efficiency
        if estimated_tokens > 0:
            metrics["token_efficiency"] = min(1.0, estimated_tokens / max(1, actual_tokens))
        else:
            metrics["token_efficiency"] = 1.0

        # Cycle efficiency
        metrics["cycle_efficiency"] = min(1.0, 1.0 / max(1, cycles))

        # Tool success rate
        tool_calls = [a for a in actions if a.get("tool_name")]
        if tool_calls:
            successful = sum(1 for t in tool_calls if not t.get("error"))
            metrics["tool_success_rate"] = successful / len(tool_calls)
        else:
            metrics["tool_success_rate"] = 1.0

        # Verification rate
        metrics["verification_success"] = 1.0 if verified else 0.0

        # Calculate overall score
        scores = []
        weights = []

        scores.append(metrics["token_efficiency"])
        weights.append(0.25)

        scores.append(metrics["cycle_efficiency"])
        weights.append(0.25)

        scores.append(metrics.get("tool_success_rate", 1.0))
        weights.append(0.25)

        scores.append(metrics["verification_success"])
        weights.append(0.25)

        total_weight = sum(weights)
        overall_score = sum(s * w for s, w in zip(scores, weights)) / total_weight

        # Classify performance
        if overall_score >= 0.9 and verified:
            level = PerformanceLevel.EXCELLENT
        elif overall_score >= 0.75 and verified:
            level = PerformanceLevel.GOOD
        elif overall_score >= 0.5:
            level = PerformanceLevel.ADEQUATE
        elif overall_score >= 0.3:
            level = PerformanceLevel.POOR
        else:
            level = PerformanceLevel.FAILED

        metrics["overall_score"] = overall_score

        return level, metrics


# ──────────────────────────────────────────────────────────────────────────────
# Error Classifier
# ──────────────────────────────────────────────────────────────────────────────

class ErrorClassifier:
    """
    Classifies errors from execution trace into actionable categories.

    This enables targeted improvement instead of blanket retry strategies.
    """

    # Error pattern matchers
    ERROR_PATTERNS: dict[ErrorCategory, list[tuple[str, str]]] = {
        ErrorCategory.PLANNING_FAILURE: [
            ("error", "no.*task.*generat"),
            ("error", "plan.*empty"),
            ("error", "decomp.*fail"),
        ],
        ErrorCategory.TOOL_FAILURE: [
            ("error", "timeout"),
            ("error", "connection.*fail"),
            ("error", "tool.*not.*found"),
            ("error", "invalid.*param"),
        ],
        ErrorCategory.VERIFICATION_FAILURE: [
            ("error", "verif.*fail"),
            ("error", "output.*invalid"),
            ("error", "criteria.*not.*met"),
        ],
        ErrorCategory.RESOURCE_EXHAUSTION: [
            ("error", "token.*limit"),
            ("error", "budget.*exceed"),
            ("error", "timeout.*exceed"),
        ],
        ErrorCategory.CONTEXT_OVERFLOW: [
            ("error", "context.*overflow"),
            ("error", "context.*window"),
            ("error", "too.*long"),
        ],
    }

    def classify(self, actions: list[dict]) -> list[ErrorCategory]:
        """Classify errors found in execution trace."""
        import re

        categories = set()

        for action in actions:
            error_text = str(action.get("error", "")).lower()
            if not error_text or error_text == "none":
                continue

            for category, patterns in self.ERROR_PATTERNS.items():
                for field_name, pattern in patterns:
                    if re.search(pattern, error_text, re.IGNORECASE):
                        categories.add(category)

        return list(categories) if categories else [ErrorCategory.UNKNOWN]


# ──────────────────────────────────────────────────────────────────────────────
# Insight Extractor
# ──────────────────────────────────────────────────────────────────────────────

class InsightExtractor:
    """
    Extracts actionable insights from execution performance.

    This is not just "what went wrong" but "what should change":
    - Planning strategy adjustments
    - Tool selection changes
    - Context management improvements
    - Resource allocation changes
    """

    def extract(
        self,
        level: PerformanceLevel,
        metrics: dict[str, float],
        errors: list[ErrorCategory],
        actions: list[dict],
    ) -> tuple[list[str], list[str]]:
        """
        Extract insights and suggestions.

        Returns:
            (insights, suggestions)
        """
        insights = []
        suggestions = []

        # Performance-based insights
        if level == PerformanceLevel.EXCELLENT:
            insights.append("Agent performed optimally - strategies should be preserved")
            suggestions.append("Record this execution pattern for future reference")
        elif level == PerformanceLevel.POOR:
            insights.append("Agent underperformed - needs strategy adjustment")
        elif level == PerformanceLevel.FAILED:
            insights.append("Agent failed - fundamental approach needs revision")

        # Metric-based insights
        if metrics.get("token_efficiency", 1.0) < 0.5:
            insights.append("High token usage - consider context compression")
            suggestions.append("Use summarization more aggressively")

        if metrics.get("cycle_efficiency", 1.0) < 0.5:
            insights.append("Multiple retries needed - planning should be more accurate")
            suggestions.append("Review and improve task decomposition")

        if metrics.get("tool_success_rate", 1.0) < 0.8:
            insights.append("Tool failures detected - review tool selection")
            suggestions.append("Ensure tools are available before selecting them")

        # Error-based insights
        if ErrorCategory.PLANNING_FAILURE in errors:
            insights.append("Planning failed to produce valid task graph")
            suggestions.append("Review domain-specific planning templates")

        if ErrorCategory.TOOL_FAILURE in errors:
            insights.append("Tool execution had failures - timeout or connection issues")
            suggestions.append("Review tool timeouts and retry policies")

        if ErrorCategory.VERIFICATION_FAILURE in errors:
            insights.append("Output did not meet success criteria")
            suggestions.append("Review verification criteria or improve output quality")

        if ErrorCategory.RESOURCE_EXHAUSTION in errors:
            insights.append("Resources (time/tokens) were exhausted")
            suggestions.append("Increase budget or reduce scope")

        if ErrorCategory.CONTEXT_OVERFLOW in errors:
            insights.append("Context became too large for effective reasoning")
            suggestions.append("Implement aggressive context pruning")

        # Action-based insights
        tool_names = [a.get("tool_name") for a in actions if a.get("tool_name")]
        if tool_names:
            most_used = max(set(tool_names), key=tool_names.count)
            insights.append(f"Most used tool: {most_used}")

        return insights, suggestions


# ──────────────────────────────────────────────────────────────────────────────
# Behavioral Adapter
# ──────────────────────────────────────────────────────────────────────────────

class BehavioralAdapter:
    """
    Adapts agent behavior based on reflection results.

    This actually CHANGES agent behavior, not just logs results.
    """

    def __init__(self):
        self._success_history: dict[str, list[bool]] = {}  # goal_type -> [success]
        self._strategy_preferences: dict[str, str] = {}    # goal_type -> preferred_strategy
        self._tool_success_rates: dict[str, float] = {}   # tool_name -> success_rate

    async def update(
        self,
        goal_type: str,
        strategy: str,
        success: bool,
        actions: list[dict],
    ) -> dict[str, Any]:
        """
        Update behavioral model based on execution result.

        Returns learning updates to apply to agent.
        """
        # Update success history
        if goal_type not in self._success_history:
            self._success_history[goal_type] = []

        self._success_history[goal_type].append(success)
        if len(self._success_history[goal_type]) > 100:
            self._success_history[goal_type] = self._success_history[goal_type][-100:]

        # Update strategy preference
        recent_successes = self._success_history[goal_type][-10:]
        success_rate = sum(1 for s in recent_successes) / len(recent_successes)

        if success_rate > 0.7:
            self._strategy_preferences[goal_type] = strategy

        # Update tool success rates
        for action in actions:
            tool_name = action.get("tool_name")
            if tool_name:
                if tool_name not in self._tool_success_rates:
                    self._tool_success_rates[tool_name] = 1.0

                # Exponential moving average
                alpha = 0.1
                tool_success = 0.0 if action.get("error") else 1.0
                self._tool_success_rates[tool_name] = (
                    alpha * tool_success +
                    (1 - alpha) * self._tool_success_rates[tool_name]
                )

        # Generate learning updates
        updates = []

        # Update 1: Strategy effectiveness
        updates.append({
            "type": "strategy_update",
            "goal_type": goal_type,
            "strategy": strategy,
            "new_success_rate": success_rate,
        })

        # Update 2: Tool reliability
        for tool_name, rate in self._tool_success_rates.items():
            if rate < 0.7:
                updates.append({
                    "type": "tool_warning",
                    "tool_name": tool_name,
                    "reliability": rate,
                    "suggestion": f"Consider alternative to {tool_name} (reliability: {rate:.0%})",
                })

        # Update 3: Strategy recommendation
        preferred = self._strategy_preferences.get(goal_type)
        if preferred and preferred != strategy:
            updates.append({
                "type": "strategy_recommendation",
                "goal_type": goal_type,
                "recommended_strategy": preferred,
                "reason": f"Historical success rate with this strategy: {success_rate:.0%}",
            })

        return {"updates": updates}

    def get_success_rate(self, goal_type: str) -> float:
        """Get success rate for a goal type."""
        history = self._success_history.get(goal_type, [])
        if not history:
            return 0.5  # Neutral if no history

        return sum(1 for s in history if s) / len(history)

    def get_tool_reliability(self, tool_name: str) -> float:
        """Get reliability score for a tool."""
        return self._tool_success_rates.get(tool_name, 0.8)  # Default 80% if unknown

    def get_recommended_strategy(self, goal_type: str) -> Optional[str]:
        """Get recommended strategy for a goal type based on history."""
        return self._strategy_preferences.get(goal_type)


# ──────────────────────────────────────────────────────────────────────────────
# Reflector — Main Entry Point
# ──────────────────────────────────────────────────────────────────────────────

class Reflector:
    """
    Main reflection engine that orchestrates self-evaluation.

    This replaces the old hardcoded `return {"confidence_multiplier": 0.92}`
    with genuine self-evaluation:
    1. Analyze performance metrics
    2. Classify errors
    3. Extract insights
    4. Adapt behavior
    5. Generate learning updates
    """

    def __init__(self):
        self.analyzer = PerformanceAnalyzer()
        self.classifier = ErrorClassifier()
        self.extractor = InsightExtractor()
        self.adapter = BehavioralAdapter()

        logger.info("reflector_initialized")

    async def reflect(
        self,
        actions: list[dict],
        goal_type: str,
        strategy: str,
        estimated_tokens: int,
        actual_tokens: int,
        cycles: int,
        verified: bool,
        context_summary: str = "",
    ) -> ReflectionResult:
        """
        Perform self-reflection on execution.

        Args:
            actions: List of action dicts from execution
            goal_type: Type/category of goal executed
            strategy: Strategy used in execution
            estimated_tokens: Estimated token budget
            actual_tokens: Actual tokens consumed
            cycles: Number of cognition cycles used
            verified: Whether goal was verified as successful
            context_summary: Summary of execution context

        Returns:
            ReflectionResult with evaluation, insights, and adaptations
        """
        reasoning_parts = []

        # Step 1: Performance Analysis
        reasoning_parts.append("[ANALYSIS] Analyzing execution performance...")
        level, metrics = self.analyzer.analyze(
            actions=actions,
            estimated_tokens=estimated_tokens,
            actual_tokens=actual_tokens,
            cycles=cycles,
            verified=verified,
        )
        reasoning_parts.append(
            f"[ANALYSIS] Performance: {level.value}, "
            f"Score: {metrics['overall_score']:.2f}, "
            f"Token efficiency: {metrics['token_efficiency']:.2f}"
        )

        # Step 2: Error Classification
        reasoning_parts.append("[CLASSIFY] Classifying errors...")
        errors = self.classifier.classify(actions)
        reasoning_parts.append(f"[CLASSIFY] Error categories: {[e.value for e in errors]}")

        # Step 3: Insight Extraction
        reasoning_parts.append("[EXTRACT] Extracting insights...")
        insights, suggestions = self.extractor.extract(level, metrics, errors, actions)
        reasoning_parts.append(f"[EXTRACT] Insights: {insights}")

        # Step 4: Behavioral Adaptation
        reasoning_parts.append("[ADAPT] Updating behavioral model...")
        learning = await self.adapter.update(goal_type, strategy, verified, actions)
        reasoning_parts.append(f"[ADAPT] Updates: {len(learning['updates'])} behavioral changes")

        # Step 5: Calculate confidence multiplier
        # Start with base multiplier from performance
        if level == PerformanceLevel.EXCELLENT:
            base_multiplier = 1.1
        elif level == PerformanceLevel.GOOD:
            base_multiplier = 1.0
        elif level == PerformanceLevel.ADEQUATE:
            base_multiplier = 0.9
        elif level == PerformanceLevel.POOR:
            base_multiplier = 0.8
        else:
            base_multiplier = 0.5

        # Adjust for error categories
        if ErrorCategory.PLANNING_FAILURE in errors:
            base_multiplier *= 0.9
        if ErrorCategory.CONTEXT_OVERFLOW in errors:
            base_multiplier *= 0.85

        # Adjust for success rate history
        prior_success = self.adapter.get_success_rate(goal_type)
        if prior_success > 0.8:
            base_multiplier *= 1.1
        elif prior_success < 0.5:
            base_multiplier *= 0.85

        # Cap the multiplier
        confidence_multiplier = max(0.3, min(1.3, base_multiplier))

        # Step 6: Determine next strategy
        recommended = self.adapter.get_recommended_strategy(goal_type)
        next_strategy = recommended if recommended else strategy

        reasoning_parts.append(
            f"[RESULT] Confidence multiplier: {confidence_multiplier:.2f}, "
            f"Next strategy: {next_strategy}"
        )

        result = ReflectionResult(
            confidence_multiplier=confidence_multiplier,
            performance_level=level,
            error_categories=errors,
            insights=insights,
            suggestions=suggestions,
            learning_updates=learning["updates"],
            next_strategy=next_strategy,
            reasoning="\n".join(reasoning_parts),
            metrics=metrics,
        )

        logger.info(
            "reflection_completed",
            goal_type=goal_type,
            performance=level.value,
            confidence=confidence_multiplier,
            errors=len(errors),
            insights=len(insights),
        )

        return result

    async def get_learning_context(self, goal_type: str) -> dict[str, Any]:
        """Get learning context for a goal type."""
        return {
            "success_rate": self.adapter.get_success_rate(goal_type),
            "recommended_strategy": self.adapter.get_recommended_strategy(goal_type),
            "tool_reliabilities": self.adapter._tool_success_rates,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Factory function
# ──────────────────────────────────────────────────────────────────────────────

def create_reflector() -> Reflector:
    """Create a configured reflector instance."""
    return Reflector()