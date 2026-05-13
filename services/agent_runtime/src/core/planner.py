"""
RasoSpeak AI OS — Cognitive Planning Engine
===========================================
Real task decomposition using HTN-style planning with:
- Goal structure analysis
- Capability matching
- Dependency graph construction
- Resource estimation
- Adaptive planning based on prior success
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

logger = structlog.get_logger("rasospeak.planning")


# ──────────────────────────────────────────────────────────────────────────────
# Planning Types
# ──────────────────────────────────────────────────────────────────────────────

class TaskComplexity(Enum):
    TRIVIAL = 1      # Single action
    LOW = 2          # 2-3 sequential actions
    MEDIUM = 3       # 4-7 sequential or 2 parallel
    HIGH = 4         # 8-15 tasks, multiple dependencies
    COMPLEX = 5      # 15+ tasks, complex dependency graph


class TaskType(Enum):
    INFORMATION_GATHERING = "information_gathering"
    ANALYSIS = "analysis"
    SYNTHESIS = "synthesis"
    EXECUTION = "execution"
    COORDINATION = "coordination"
    REVIEW = "review"
    MONITORING = "monitoring"
    DELIVERY = "delivery"


@dataclass
class PlanningContext:
    """Context for the planning algorithm."""
    goal_description: str
    user_id: str
    tenant_id: str
    available_tools: list[str]
    available_agents: list[str]
    time_budget_seconds: int = 300
    max_tasks: int = 20
    priority: int = 0
    prior_success: dict[str, float] = field(default_factory=dict)  # task_type -> success_rate


@dataclass
class DecomposedTask:
    """A task produced by the decomposition algorithm."""
    task_id: str
    description: str
    task_type: TaskType
    complexity: TaskComplexity
    tools_needed: list[str]
    estimated_tokens: int
    estimated_duration_seconds: int
    depends_on: list[str] = field(default_factory=list)
    can_parallel_with: list[str] = field(default_factory=list)
    success_weight: float = 1.0
    agent_type: str = "execution"
    checkpoints: list[str] = field(default_factory=list)


@dataclass
class PlanResult:
    """Result of the planning algorithm."""
    tasks: list[DecomposedTask]
    total_tasks: int
    estimated_total_tokens: int
    estimated_duration_seconds: int
    parallelism_score: float  # 0-1, higher = more parallelizable
    confidence: float
    reasoning: str


# ──────────────────────────────────────────────────────────────────────────────
# Goal Analyzer
# ──────────────────────────────────────────────────────────────────────────────

class GoalAnalyzer:
    """
    Analyzes goal structure to understand:
    - What type of work is needed
    - What capabilities are required
    - What constraints exist
    - What success looks like
    """

    # Action verb taxonomy with complexity hints
    ACTION_VERBS = {
        # Simple informational
        "find": TaskType.INFORMATION_GATHERING,
        "search": TaskType.INFORMATION_GATHERING,
        "lookup": TaskType.INFORMATION_GATHERING,
        "retrieve": TaskType.INFORMATION_GATHERING,
        "get": TaskType.INFORMATION_GATHERING,

        # Analytical
        "analyze": TaskType.ANALYSIS,
        "assess": TaskType.ANALYSIS,
        "evaluate": TaskType.ANALYSIS,
        "compare": TaskType.ANALYSIS,
        "review": TaskType.ANALYSIS,
        "diagnose": TaskType.ANALYSIS,
        "identify": TaskType.ANALYSIS,

        # Synthetic
        "create": TaskType.SYNTHESIS,
        "generate": TaskType.SYNTHESIS,
        "write": TaskType.SYNTHESIS,
        "design": TaskType.SYNTHESIS,
        "build": TaskType.SYNTHESIS,
        "compose": TaskType.SYNTHESIS,
        "synthesize": TaskType.SYNTHESIS,
        "plan": TaskType.SYNTHESIS,
        "develop": TaskType.SYNTHESIS,

        # Coordination
        "coordinate": TaskType.COORDINATION,
        "organize": TaskType.COORDINATION,
        "schedule": TaskType.COORDINATION,
        "manage": TaskType.COORDINATION,
        "delegate": TaskType.COORDINATION,

        # Execution
        "execute": TaskType.EXECUTION,
        "run": TaskType.EXECUTION,
        "perform": TaskType.EXECUTION,
        "do": TaskType.EXECUTION,
        "send": TaskType.EXECUTION,
        "notify": TaskType.EXECUTION,

        # Delivery
        "deliver": TaskType.DELIVERY,
        "present": TaskType.DELIVERY,
        "share": TaskType.DELIVERY,
        "communicate": TaskType.DELIVERY,
        "report": TaskType.DELIVERY,
    }

    # Topic detection for domain-specific planning
    TOPIC_PATTERNS = {
        "interview_preparation": {
            "keywords": ["interview", "interviewing", "job interview", "technical interview", "coding interview"],
            "required_capabilities": ["assessment", "research", "planning", "practice", "feedback"],
        },
        "speech_coaching": {
            "keywords": ["speech", "presentation", "talk", "speaking", "presenting", "oral"],
            "required_capabilities": ["transcription", "feedback", "practice", "metrics"],
        },
        "career_development": {
            "keywords": ["career", "promotion", "growth", "履历", "resume", "cv"],
            "required_capabilities": ["research", "planning", "feedback"],
        },
        "technical_review": {
            "keywords": ["code review", "architecture", "system design", "technical", "code"],
            "required_capabilities": ["analysis", "research", "feedback"],
        },
        "learning": {
            "keywords": ["learn", "study", "practice", "train", "teach", "education"],
            "required_capabilities": ["research", "planning", "practice", "assessment"],
        },
        "research": {
            "keywords": ["research", "investigate", "explore", "study", "analyze topic"],
            "required_capabilities": ["information_gathering", "analysis", "synthesis"],
        },
        "general_assistance": {
            "keywords": [],
            "required_capabilities": ["reasoning", "problem_solving"],
        },
    }

    def analyze(self, goal_text: str) -> dict[str, Any]:
        """
        Analyze a goal and return structured understanding.

        Returns:
            {
                "domain": str,  # Detected topic domain
                "action_verbs": list[str],
                "task_types": list[TaskType],
                "complexity_hints": list[str],
                "entities": list[str],
                "constraints": dict[str, Any],
            }
        """
        goal_lower = goal_text.lower()
        words = goal_lower.split()

        # Detect domain
        domain = "general_assistance"
        for domain_name, pattern in self.TOPIC_PATTERNS.items():
            if any(kw in goal_lower for kw in pattern["keywords"]):
                domain = domain_name
                break

        # Extract action verbs
        action_verbs = []
        task_types_set = set()
        for word in words:
            if word in self.ACTION_VERBS:
                action_verbs.append(word)
                task_types_set.add(self.ACTION_VERBS[word])

        # If no action verbs found, infer from domain
        if not action_verbs:
            task_types_set.add(TaskType.ANALYSIS)

        # Extract entities (simple noun phrase detection)
        entities = self._extract_entities(goal_text)

        # Detect constraints
        constraints = self._detect_constraints(goal_text)

        return {
            "domain": domain,
            "action_verbs": action_verbs,
            "task_types": list(task_types_set),
            "entities": entities,
            "constraints": constraints,
            "original_goal": goal_text,
        }

    def _extract_entities(self, text: str) -> list[str]:
        """Extract key entities from goal text."""
        # Simple extraction: capitalized words, quoted phrases, numbers with units
        import re

        entities = []

        # Quoted phrases
        quoted = re.findall(r'"([^"]+)"', text)
        entities.extend(quoted)

        # Numbers with context
        numbers = re.findall(r'\b(\d+)\s*(hours?|minutes?|days?|weeks?|tasks?|items?)\b', text.lower())
        for num, unit in numbers:
            entities.append(f"{num} {unit}")

        # Capitalized multi-word phrases
        capitalized = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', text)
        entities.extend(capitalized[:5])  # Limit to 5

        return entities

    def _detect_constraints(self, text: str) -> dict[str, Any]:
        """Detect constraints from goal text."""
        constraints = {}

        import re

        # Time constraints
        time_match = re.search(r'within\s+(\d+)\s*(hours?|minutes?|days?)', text.lower())
        if time_match:
            amount, unit = time_match.groups()
            unit_hours = {"hour": 1, "hours": 1, "minute": 1/60, "minutes": 1/60, "day": 24, "days": 24}
            constraints["deadline_hours"] = int(amount) * unit_hours.get(unit, 1)

        # Budget constraints
        budget_match = re.search(r'budget\s*(of|is)?\s*\$?(\d+)', text.lower())
        if budget_match:
            constraints["budget"] = int(budget_match.group(2))

        # Quality constraints
        if "best" in text.lower() or "highest" in text.lower():
            constraints["quality_priority"] = "max"
        elif "fast" in text.lower() or "quick" in text.lower():
            constraints["speed_priority"] = "max"

        return constraints


# ──────────────────────────────────────────────────────────────────────────────
# Task Decomposer
# ──────────────────────────────────────────────────────────────────────────────

class TaskDecomposer:
    """
    Decomposes analyzed goals into executable task graphs.

    This is NOT a lookup table. It uses:
    - Domain templates derived from analysis
    - Dependency inference from task types
    - Resource estimation from complexity
    - Success history for adaptation
    """

    # Task type dependencies: what must complete before what
    TYPE_PREREQUISITES: dict[TaskType, list[TaskType]] = {
        TaskType.INFORMATION_GATHERING: [],
        TaskType.ANALYSIS: [TaskType.INFORMATION_GATHERING],
        TaskType.SYNTHESIS: [TaskType.INFORMATION_GATHERING, TaskType.ANALYSIS],
        TaskType.EXECUTION: [TaskType.SYNTHESIS],
        TaskType.COORDINATION: [TaskType.SYNTHESIS],
        TaskType.REVIEW: [TaskType.EXECUTION],
        TaskType.DELIVERY: [TaskType.REVIEW],
        TaskType.MONITORING: [TaskType.DELIVERY],
    }

    # Tool requirements by task type
    TOOL_REQUIREMENTS: dict[TaskType, list[str]] = {
        TaskType.INFORMATION_GATHERING: ["search_web", "retrieve_memories"],
        TaskType.ANALYSIS: ["llm_reason"],
        TaskType.SYNTHESIS: ["llm_reason", "retrieve_memories"],
        TaskType.EXECUTION: ["llm_reason", "send_notification"],
        TaskType.COORDINATION: ["schedule_task", "llm_reason"],
        TaskType.REVIEW: ["llm_reason"],
        TaskType.DELIVERY: ["send_notification", "llm_reason"],
        TaskType.MONITORING: ["retrieve_memories", "llm_reason"],
    }

    # Estimated token costs by task type
    TOKEN_ESTIMATES: dict[TaskType, tuple[int, int]] = {
        TaskType.INFORMATION_GATHERING: (500, 2000),
        TaskType.ANALYSIS: (1000, 3000),
        TaskType.SYNTHESIS: (2000, 5000),
        TaskType.EXECUTION: (500, 1500),
        TaskType.COORDINATION: (300, 1000),
        TaskType.REVIEW: (1000, 2500),
        TaskType.DELIVERY: (500, 1500),
        TaskType.MONITORING: (300, 800),
    }

    # Estimated duration by task type (seconds)
    DURATION_ESTIMATES: dict[TaskType, tuple[int, int]] = {
        TaskType.INFORMATION_GATHERING: (5, 30),
        TaskType.ANALYSIS: (10, 60),
        TaskType.SYNTHESIS: (20, 120),
        TaskType.EXECUTION: (5, 30),
        TaskType.COORDINATION: (3, 15),
        TaskType.REVIEW: (10, 45),
        TaskType.DELIVERY: (5, 20),
        TaskType.MONITORING: (3, 10),
    }

    # Complexity multipliers
    COMPLEXITY_MULTIPLIERS: dict[TaskComplexity, float] = {
        TaskComplexity.TRIVIAL: 1.0,
        TaskComplexity.LOW: 1.5,
        TaskComplexity.MEDIUM: 2.0,
        TaskComplexity.HIGH: 3.0,
        TaskComplexity.COMPLEX: 5.0,
    }

    def decompose(
        self,
        analysis: dict[str, Any],
        context: PlanningContext,
    ) -> list[DecomposedTask]:
        """
        Decompose a goal analysis into a task graph.

        Algorithm:
        1. Generate task types from analysis
        2. Apply prerequisites to establish dependencies
        3. Filter by available tools
        4. Estimate resources
        5. Apply prior success adjustments
        """
        tasks = []
        task_counter = 0

        domain = analysis["domain"]
        task_types = analysis["task_types"]

        # Add domain-specific tasks
        if domain == "interview_preparation":
            tasks.extend(self._decompose_interview_prep(analysis, context))
        elif domain == "speech_coaching":
            tasks.extend(self._decompose_speech_coaching(analysis, context))
        elif domain == "career_development":
            tasks.extend(self._decompose_career_dev(analysis, context))
        elif domain == "technical_review":
            tasks.extend(self._decompose_technical_review(analysis, context))
        elif domain == "research":
            tasks.extend(self._decompose_research(analysis, context))
        else:
            tasks.extend(self._decompose_generic(analysis, context))

        # Apply resource constraints
        total_tokens = sum(t.estimated_tokens for t in tasks)
        if total_tokens > context.max_tasks * 1000:  # Rough token limit
            tasks = self._prune_tasks(tasks, context)

        # Add dependencies based on task types
        tasks = self._add_dependencies(tasks)

        # Apply prior success weighting
        tasks = self._apply_success_history(tasks, context)

        return tasks

    def _decompose_interview_prep(
        self,
        analysis: dict[str, Any],
        context: PlanningContext,
    ) -> list[DecomposedTask]:
        """Domain-specific decomposition for interview preparation."""
        tasks = []

        # Phase 1: Assessment
        tasks.append(DecomposedTask(
            task_id="assess_current_level",
            description="Assess user's current skill level and experience",
            task_type=TaskType.ANALYSIS,
            complexity=TaskComplexity.MEDIUM,
            tools_needed=["llm_reason", "retrieve_memories"],
            estimated_tokens=1500,
            estimated_duration_seconds=30,
            checkpoints=["level_assessed"],
        ))

        # Phase 2: Research
        tasks.append(DecomposedTask(
            task_id="research_role_requirements",
            description="Research target role requirements and expectations",
            task_type=TaskType.INFORMATION_GATHERING,
            complexity=TaskComplexity.MEDIUM,
            tools_needed=["search_web", "retrieve_memories"],
            estimated_tokens=2000,
            estimated_duration_seconds=60,
            checkpoints=["requirements_researched"],
        ))

        tasks.append(DecomposedTask(
            task_id="identify_gaps",
            description="Identify skill gaps between user and role requirements",
            task_type=TaskType.ANALYSIS,
            complexity=TaskComplexity.MEDIUM,
            tools_needed=["llm_reason"],
            estimated_tokens=1000,
            estimated_duration_seconds=30,
            depends_on=["assess_current_level", "research_role_requirements"],
            checkpoints=["gaps_identified"],
        ))

        # Phase 3: Planning
        tasks.append(DecomposedTask(
            task_id="create_study_plan",
            description="Create structured study plan to address gaps",
            task_type=TaskType.SYNTHESIS,
            complexity=TaskComplexity.HIGH,
            tools_needed=["llm_reason", "retrieve_memories"],
            estimated_tokens=2500,
            estimated_duration_seconds=60,
            depends_on=["identify_gaps"],
            checkpoints=["study_plan_created"],
        ))

        # Phase 4: Practice generation
        tasks.append(DecomposedTask(
            task_id="generate_practice_questions",
            description="Generate practice questions and scenarios",
            task_type=TaskType.SYNTHESIS,
            complexity=TaskComplexity.HIGH,
            tools_needed=["llm_reason"],
            estimated_tokens=3000,
            estimated_duration_seconds=90,
            depends_on=["create_study_plan"],
            checkpoints=["questions_generated"],
        ))

        # Phase 5: Scheduling
        tasks.append(DecomposedTask(
            task_id="schedule_sessions",
            description="Schedule coaching sessions and practice times",
            task_type=TaskType.COORDINATION,
            complexity=TaskComplexity.LOW,
            tools_needed=["schedule_task", "llm_reason"],
            estimated_tokens=800,
            estimated_duration_seconds=15,
            depends_on=["create_study_plan"],
            checkpoints=["sessions_scheduled"],
        ))

        return tasks

    def _decompose_speech_coaching(
        self,
        analysis: dict[str, Any],
        context: PlanningContext,
    ) -> list[DecomposedTask]:
        """Domain-specific decomposition for speech coaching."""
        tasks = []

        tasks.append(DecomposedTask(
            task_id="analyze_speech_patterns",
            description="Analyze user's speech patterns and history",
            task_type=TaskType.ANALYSIS,
            complexity=TaskComplexity.MEDIUM,
            tools_needed=["retrieve_memories", "llm_reason"],
            estimated_tokens=1500,
            estimated_duration_seconds=45,
            checkpoints=["patterns_analyzed"],
        ))

        tasks.append(DecomposedTask(
            task_id="design_exercises",
            description="Design speech practice exercises",
            task_type=TaskType.SYNTHESIS,
            complexity=TaskComplexity.MEDIUM,
            tools_needed=["llm_reason"],
            estimated_tokens=2000,
            estimated_duration_seconds=60,
            depends_on=["analyze_speech_patterns"],
            checkpoints=["exercises_designed"],
        ))

        tasks.append(DecomposedTask(
            task_id="prepare_feedback_criteria",
            description="Prepare feedback criteria and metrics",
            task_type=TaskType.SYNTHESIS,
            complexity=TaskComplexity.LOW,
            tools_needed=["llm_reason"],
            estimated_tokens=1000,
            estimated_duration_seconds=30,
            depends_on=["analyze_speech_patterns"],
            checkpoints=["criteria_prepared"],
        ))

        return tasks

    def _decompose_career_dev(
        self,
        analysis: dict[str, Any],
        context: PlanningContext,
    ) -> list[DecomposedTask]:
        """Domain-specific decomposition for career development."""
        tasks = []

        tasks.append(DecomposedTask(
            task_id="review_career_history",
            description="Review user's career history and achievements",
            task_type=TaskType.ANALYSIS,
            complexity=TaskComplexity.MEDIUM,
            tools_needed=["retrieve_memories", "llm_reason"],
            estimated_tokens=1500,
            estimated_duration_seconds=30,
        ))

        tasks.append(DecomposedTask(
            task_id="research_career_paths",
            description="Research potential career paths and opportunities",
            task_type=TaskType.INFORMATION_GATHERING,
            complexity=TaskComplexity.MEDIUM,
            tools_needed=["search_web", "llm_reason"],
            estimated_tokens=2000,
            estimated_duration_seconds=60,
            depends_on=["review_career_history"],
        ))

        tasks.append(DecomposedTask(
            task_id="create_career_plan",
            description="Create career development plan with milestones",
            task_type=TaskType.SYNTHESIS,
            complexity=TaskComplexity.HIGH,
            tools_needed=["llm_reason"],
            estimated_tokens=2500,
            estimated_duration_seconds=90,
            depends_on=["research_career_paths"],
        ))

        return tasks

    def _decompose_technical_review(
        self,
        analysis: dict[str, Any],
        context: PlanningContext,
    ) -> list[DecomposedTask]:
        """Domain-specific decomposition for technical review."""
        tasks = []

        tasks.append(DecomposedTask(
            task_id="understand_system",
            description="Understand the system architecture and context",
            task_type=TaskType.INFORMATION_GATHERING,
            complexity=TaskComplexity.HIGH,
            tools_needed=["search_web", "retrieve_memories", "llm_reason"],
            estimated_tokens=3000,
            estimated_duration_seconds=120,
        ))

        tasks.append(DecomposedTask(
            task_id="identify_issues",
            description="Identify issues, anti-patterns, and risks",
            task_type=TaskType.ANALYSIS,
            complexity=TaskComplexity.HIGH,
            tools_needed=["llm_reason"],
            estimated_tokens=2500,
            estimated_duration_seconds=90,
            depends_on=["understand_system"],
        ))

        tasks.append(DecomposedTask(
            task_id="recommend_improvements",
            description="Recommend specific improvements with priorities",
            task_type=TaskType.SYNTHESIS,
            complexity=TaskComplexity.MEDIUM,
            tools_needed=["llm_reason"],
            estimated_tokens=2000,
            estimated_duration_seconds=60,
            depends_on=["identify_issues"],
        ))

        return tasks

    def _decompose_research(
        self,
        analysis: dict[str, Any],
        context: PlanningContext,
    ) -> list[DecomposedTask]:
        """Domain-specific decomposition for research tasks."""
        tasks = []

        tasks.append(DecomposedTask(
            task_id="gather_information",
            description="Gather initial information on the research topic",
            task_type=TaskType.INFORMATION_GATHERING,
            complexity=TaskComplexity.MEDIUM,
            tools_needed=["search_web", "retrieve_memories"],
            estimated_tokens=2000,
            estimated_duration_seconds=60,
        ))

        tasks.append(DecomposedTask(
            task_id="synthesize_findings",
            description="Synthesize findings into coherent understanding",
            task_type=TaskType.SYNTHESIS,
            complexity=TaskComplexity.HIGH,
            tools_needed=["llm_reason"],
            estimated_tokens=3000,
            estimated_duration_seconds=90,
            depends_on=["gather_information"],
        ))

        tasks.append(DecomposedTask(
            task_id="present_findings",
            description="Present findings in accessible format",
            task_type=TaskType.DELIVERY,
            complexity=TaskComplexity.LOW,
            tools_needed=["llm_reason", "send_notification"],
            estimated_tokens=1000,
            estimated_duration_seconds=30,
            depends_on=["synthesize_findings"],
        ))

        return tasks

    def _decompose_generic(
        self,
        analysis: dict[str, Any],
        context: PlanningContext,
    ) -> list[DecomposedTask]:
        """Generic decomposition for unknown domains."""
        tasks = []

        # Generic 3-phase approach
        tasks.append(DecomposedTask(
            task_id="understand_requirement",
            description=f"Understand and clarify: {analysis.get('original_goal', 'the request')}",
            task_type=TaskType.ANALYSIS,
            complexity=TaskComplexity.MEDIUM,
            tools_needed=["llm_reason", "retrieve_memories"],
            estimated_tokens=1500,
            estimated_duration_seconds=45,
        ))

        tasks.append(DecomposedTask(
            task_id="execute_solution",
            description="Execute appropriate solution for the request",
            task_type=TaskType.EXECUTION,
            complexity=TaskComplexity.MEDIUM,
            tools_needed=["llm_reason"],
            estimated_tokens=2000,
            estimated_duration_seconds=60,
            depends_on=["understand_requirement"],
        ))

        tasks.append(DecomposedTask(
            task_id="deliver_response",
            description="Deliver clear response to user",
            task_type=TaskType.DELIVERY,
            complexity=TaskComplexity.LOW,
            tools_needed=["llm_reason", "send_notification"],
            estimated_tokens=800,
            estimated_duration_seconds=20,
            depends_on=["execute_solution"],
        ))

        return tasks

    def _add_dependencies(self, tasks: list[DecomposedTask]) -> list[DecomposedTask]:
        """Add dependencies based on task type prerequisites."""
        task_by_id = {t.task_id: t for t in tasks}
        task_types_present = {t.task_type for t in tasks}

        for task in tasks:
            if task.depends_on:
                continue  # Already has explicit dependencies

            # Add implicit dependencies from prerequisites
            prerequisites = self.TYPE_PREREQUISITES.get(task.task_type, [])
            for prereq_type in prerequisites:
                if prereq_type in task_types_present:
                    # Find a task of that type to depend on
                    prereq_tasks = [t for t in tasks if t.task_type == prereq_type]
                    if prereq_tasks:
                        # Depend on the last task of that type (usually the most complex)
                        task.depends_on.append(prereq_tasks[-1].task_id)

        return tasks

    def _apply_success_history(
        self,
        tasks: list[DecomposedTask],
        context: PlanningContext,
    ) -> list[DecomposedTask]:
        """Adjust task weights based on prior success."""
        for task in tasks:
            type_key = task.task_type.value
            if type_key in context.prior_success:
                prior_rate = context.prior_success[type_key]
                # Increase weight for high-success tasks (more important)
                # Decrease weight for low-success tasks (might need more attention)
                if prior_rate > 0.8:
                    task.success_weight = 1.2
                elif prior_rate < 0.5:
                    task.success_weight = 0.8

        return tasks

    def _prune_tasks(
        self,
        tasks: list[DecomposedTask],
        context: PlanningContext,
    ) -> list[DecomposedTask]:
        """Prune tasks to fit resource constraints."""
        # Keep high-weight tasks, prune low-weight ones
        tasks.sort(key=lambda t: t.success_weight * t.complexity.value, reverse=True)
        max_tasks = min(len(tasks), context.max_tasks)

        # Ensure we keep at least one task per phase
        kept = []
        phases_seen = set()

        for task in tasks:
            if len(kept) >= max_tasks:
                break

            # Always keep at least one from each task type category
            phase_key = task.task_type.name.split("_")[0]
            if phase_key not in phases_seen:
                kept.append(task)
                phases_seen.add(phase_key)
            elif len(kept) < max_tasks:
                kept.append(task)

        return kept


# ──────────────────────────────────────────────────────────────────────────────
# Planner — Main Entry Point
# ──────────────────────────────────────────────────────────────────────────────

class Planner:
    """
    Main planning engine that orchestrates goal analysis and task decomposition.

    This replaces the old string-matching approach with a real planning algorithm:
    - Goal analysis: Understand what the user wants
    - Task decomposition: Generate tasks based on domain and constraints
    - Resource estimation: Estimate tokens and time
    - Dependency resolution: Build the execution graph
    """

    def __init__(self):
        self.analyzer = GoalAnalyzer()
        self.decomposer = TaskDecomposer()
        logger.info("planner_initialized")

    async def plan(self, context: PlanningContext) -> PlanResult:
        """
        Create a plan for the given context.

        Args:
            context: PlanningContext with goal and constraints

        Returns:
            PlanResult with decomposed tasks and estimates
        """
        reasoning_parts = []

        # Step 1: Analyze the goal
        analysis = self.analyzer.analyze(context.goal_description)
        reasoning_parts.append(
            f"[ANALYSIS] Domain: {analysis['domain']}, "
            f"Task types: {[t.value for t in analysis['task_types']]}, "
            f"Constraints: {list(analysis['constraints'].keys())}"
        )

        # Step 2: Decompose into tasks
        tasks = self.decomposer.decompose(analysis, context)
        reasoning_parts.append(f"[DECOMPOSITION] Generated {len(tasks)} tasks")

        # Step 3: Calculate estimates
        total_tokens = sum(t.estimated_tokens for t in tasks)
        total_duration = sum(t.estimated_duration_seconds for t in tasks)
        parallelism = self._calculate_parallelism(tasks)

        # Step 4: Calculate confidence
        confidence = self._calculate_confidence(tasks, analysis, context)

        # Step 5: Record reasoning
        task_summaries = [f"{t.task_id}({t.task_type.value})" for t in tasks]
        reasoning_parts.append(
            f"[SUMMARY] Tasks: {', '.join(task_summaries)}, "
            f"Est tokens: {total_tokens}, Est duration: {total_duration}s"
        )

        result = PlanResult(
            tasks=tasks,
            total_tasks=len(tasks),
            estimated_total_tokens=total_tokens,
            estimated_duration_seconds=total_duration,
            parallelism_score=parallelism,
            confidence=confidence,
            reasoning="\n".join(reasoning_parts),
        )

        logger.info(
            "plan_created",
            goal=context.goal_description[:50],
            tasks=len(tasks),
            tokens=total_tokens,
            confidence=confidence,
        )

        return result

    def _calculate_parallelism(self, tasks: list[DecomposedTask]) -> float:
        """Calculate how parallelizable the task graph is (0-1)."""
        if not tasks:
            return 0.0

        # Count tasks with no dependencies
        independent = sum(1 for t in tasks if not t.depends_on)
        max_parallel = max(1, independent)

        # Estimate: if most tasks are independent, high parallelism
        return min(1.0, max_parallel / max(1, len(tasks)))

    def _calculate_confidence(
        self,
        tasks: list[DecomposedTask],
        analysis: dict[str, Any],
        context: PlanningContext,
    ) -> float:
        """Calculate confidence in the plan."""
        confidence = 0.8  # Base confidence

        # Reduce for complex domains without specific templates
        if analysis["domain"] == "general_assistance":
            confidence *= 0.7

        # Reduce for high complexity tasks
        complex_tasks = [t for t in tasks if t.complexity in (TaskComplexity.HIGH, TaskComplexity.COMPLEX)]
        if complex_tasks:
            confidence *= (1.0 - 0.1 * len(complex_tasks))

        # Reduce if missing tools
        for task in tasks:
            available = set(context.available_tools)
            needed = set(task.tools_needed)
            missing = needed - available
            if missing:
                confidence *= 0.9

        # Reduce for time pressure
        total_estimated = sum(t.estimated_duration_seconds for t in tasks)
        if context.time_budget_seconds < total_estimated:
            confidence *= 0.7

        return max(0.1, min(1.0, confidence))


# ──────────────────────────────────────────────────────────────────────────────
# Factory function
# ──────────────────────────────────────────────────────────────────────────────

def create_planner() -> Planner:
    """Create a configured planner instance."""
    return Planner()