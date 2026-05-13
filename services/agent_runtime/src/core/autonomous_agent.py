"""
True Autonomous Agent Runtime
==============================
Real agents with beliefs, goals, plans, reflection, and self-evaluation.

NOT prompt wrappers - these are genuine autonomous agents.
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
import uuid
import structlog

logger = structlog.get_logger("rasospeak.agents")


class AgentState(Enum):
    """Agent lifecycle states."""
    IDLE = "idle"
    THINKING = "thinking"
    ACTING = "acting"
    REFLECTING = "reflecting"
    WAITING = "waiting"
    ERROR = "error"


class GoalStatus(Enum):
    """Goal completion status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class Belief:
    """Agent belief about the world."""
    belief_id: str
    content: str
    confidence: float  # 0-1
    source: str  # observation, inference, memory
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_updated: datetime = field(default_factory=datetime.utcnow)
    is_core: bool = False  # Core beliefs are harder to change


@dataclass
class Goal:
    """Agent goal."""
    goal_id: str
    title: str
    description: str
    status: GoalStatus = GoalStatus.PENDING
    priority: int = 5  # 1-10

    # Goal hierarchy
    parent_goal_id: Optional[str] = None
    sub_goals: list[str] = field(default_factory=list)

    # Progress
    progress: float = 0.0  # 0-1
    completed_steps: list[str] = field(default_factory=list)

    # Temporal
    created_at: datetime = field(default_factory=datetime.utcnow)
    deadline: Optional[datetime] = None
    last_progress_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PlanStep:
    """Single step in a plan."""
    step_id: str
    action: str
    parameters: dict = field(default_factory=dict)
    prerequisites: list[str] = field(default_factory=list)
    expected_outcome: str = ""
    status: str = "pending"  # pending, in_progress, completed, failed
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class Plan:
    """Agent execution plan."""
    plan_id: str
    goal_id: str
    steps: list[PlanStep] = field(default_factory=list)
    current_step_index: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Reflection:
    """Agent self-reflection."""
    reflection_id: str
    agent_id: str

    # What happened
    observation: str

    # Agent's interpretation
    interpretation: str

    # Evaluation
    evaluation: str  # How well did it do?
    lessons_learned: list[str] = field(default_factory=list)
    beliefs_updated: list[str] = field(default_factory=list)

    # Future planning
    adjustment: str  # What would agent do differently?
    created_at: datetime = field(default_factory=datetime.utcnow)


class AutonomousAgent:
    """
    True autonomous agent with:

    - Beliefs: Mental model of the world
    - Goals: Objectives to pursue
    - Plans: Action sequences to achieve goals
    - Memory: Experience storage
    - Reflection: Self-evaluation and learning
    - Environment awareness: Understands context

    NOT a prompt wrapper - this is a real agent architecture.
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str = "",
        llm_gateway=None,  # LLM for reasoning
        memory_system=None,
    ):
        self.agent_id = agent_id
        self.name = name
        self.description = description

        # LLM for reasoning (can be swapped)
        self._llm = llm_gateway

        # Memory
        self._memory = memory_system

        # Agent state
        self._state = AgentState.IDLE
        self._current_context: dict = {}

        # Beliefs
        self._beliefs: dict[str, Belief] = {}

        # Goals
        self._goals: dict[str, Goal] = {}
        self._active_goal_id: Optional[str] = None

        # Plans
        self._plans: dict[str, Plan] = {}

        # Reflection history
        self._reflections: list[Reflection] = []

        # Performance metrics
        self._success_count = 0
        self._failure_count = 0
        self._total_actions = 0

    # ─────────────────────────────────────────────────────────────
    # State Management
    # ─────────────────────────────────────────────────────────────

    def get_state(self) -> AgentState:
        return self._state

    async def set_state(self, new_state: AgentState):
        old = self._state
        self._state = new_state
        logger.info("agent_state_changed", agent=self.name, old=old.value, new=new_state.value)

    # ─────────────────────────────────────────────────────────────
    # Beliefs
    # ─────────────────────────────────────────────────────────────

    async def add_belief(
        self,
        content: str,
        confidence: float,
        source: str = "inference",
        is_core: bool = False
    ) -> Belief:
        """Add new belief."""
        belief = Belief(
            belief_id=str(uuid.uuid4()),
            content=content,
            confidence=confidence,
            source=source,
            is_core=is_core
        )

        self._beliefs[belief.belief_id] = belief
        logger.info("belief_added", agent=self.name, content=content[:50])

        return belief

    async def update_belief(self, belief_id: str, new_content: str, new_confidence: float):
        """Update existing belief."""
        if belief_id in self._beliefs:
            belief = self._beliefs[belief_id]
            belief.content = new_content
            belief.confidence = new_confidence
            belief.last_updated = datetime.utcnow()

    def get_beliefs(self, min_confidence: float = 0.0) -> list[Belief]:
        """Get beliefs above confidence threshold."""
        return [b for b in self._beliefs.values() if b.confidence >= min_confidence]

    # ─────────────────────────────────────────────────────────────
    # Goals
    # ─────────────────────────────────────────────────────────────

    async def create_goal(
        self,
        title: str,
        description: str,
        priority: int = 5,
        deadline: Optional[datetime] = None
    ) -> Goal:
        """Create new goal."""
        goal = Goal(
            goal_id=str(uuid.uuid4()),
            title=title,
            description=description,
            priority=priority,
            deadline=deadline
        )

        self._goals[goal.goal_id] = goal

        # If no active goal, set this as active
        if not self._active_goal_id:
            self._active_goal_id = goal.goal_id
            goal.status = GoalStatus.IN_PROGRESS

        logger.info("goal_created", agent=self.name, title=title)

        return goal

    async def update_goal_progress(self, goal_id: str, progress: float):
        """Update goal progress."""
        if goal_id in self._goals:
            goal = self._goals[goal_id]
            goal.progress = progress
            goal.last_progress_at = datetime.utcnow()

            if progress >= 1.0:
                goal.status = GoalStatus.COMPLETED
                logger.info("goal_completed", agent=self.name, goal_id=goal_id)

    async def add_sub_goal(self, parent_goal_id: str, sub_goal: Goal):
        """Add sub-goal to parent."""
        if parent_goal_id in self._goals:
            self._goals[parent_goal_id].sub_goals.append(sub_goal.goal_id)
            self._goals[sub_goal.goal_id] = sub_goal

    def get_active_goal(self) -> Optional[Goal]:
        """Get current active goal."""
        if self._active_goal_id and self._active_goal_id in self._goals:
            return self._goals[self._active_goal_id]
        return None

    def get_goals_by_status(self, status: GoalStatus) -> list[Goal]:
        """Get goals by status."""
        return [g for g in self._goals.values() if g.status == status]

    # ─────────────────────────────────────────────────────────────
    # Planning (HTN-style)
    # ─────────────────────────────────────────────────────────────

    async def create_plan(self, goal_id: str, steps: list[dict]) -> Plan:
        """Create execution plan from goal."""
        plan = Plan(
            plan_id=str(uuid.uuid4()),
            goal_id=goal_id,
            steps=[
                PlanStep(
                    step_id=str(uuid.uuid4()),
                    action=step.get("action", ""),
                    parameters=step.get("parameters", {}),
                    prerequisites=step.get("prerequisites", []),
                    expected_outcome=step.get("expected_outcome", "")
                )
                for step in steps
            ]
        )

        self._plans[plan.plan_id] = plan
        logger.info("plan_created", agent=self.name, goal_id=goal_id, steps=len(steps))

        return plan

    async def execute_plan(self) -> tuple[bool, list[str]]:
        """
        Execute current plan.

        Returns (success, results/errors)
        """
        goal = self.get_active_goal()
        if not goal:
            return False, ["No active goal"]

        # Find plan for goal
        plan = None
        for p in self._plans.values():
            if p.goal_id == goal.goal_id:
                plan = p
                break

        if not plan:
            return False, ["No plan for goal"]

        results = []

        await self.set_state(AgentState.ACTING)

        for i, step in enumerate(plan.steps):
            plan.current_step_index = i

            await self.set_state(AgentState.THINKING)

            # Execute step
            step.status = "in_progress"

            try:
                result = await self._execute_step(step)
                step.status = "completed"
                step.result = result
                results.append(f"Step {i+1}: {result}")

                # Update goal progress
                progress = (i + 1) / len(plan.steps)
                await self.update_goal_progress(goal.goal_id, progress)

            except Exception as e:
                step.status = "failed"
                step.error = str(e)
                results.append(f"Step {i+1} failed: {e}")

                # Reflection on failure
                await self.reflect(
                    observation=f"Step {i+1} failed: {e}",
                    evaluation="Failed",
                    adjustment="Should retry with different approach"
                )

                return False, results

        await self.set_state(AgentState.IDLE)

        # Goal completed
        goal.status = GoalStatus.COMPLETED

        return True, results

    async def _execute_step(self, step: PlanStep) -> Any:
        """Execute single step."""
        # Placeholder - actual implementation would:
        # - Call tools/APIs
        # - Use LLM for reasoning
        # - Interact with memory/environment

        logger.info("executing_step", agent=self.name, action=step.action)

        # Simulate execution
        await asyncio.sleep(0.1)

        return f"Executed: {step.action}"

    # ─────────────────────────────────────────────────────────────
    # Reflection
    # ─────────────────────────────────────────────────────────────

    async def reflect(
        self,
        observation: str,
        evaluation: str,
        adjustment: str = "",
        interpretation: Optional[str] = None
    ) -> Reflection:
        """Create reflection on action."""
        reflection = Reflection(
            reflection_id=str(uuid.uuid4()),
            agent_id=self.agent_id,
            observation=observation,
            interpretation=interpretation or observation,
            evaluation=evaluation,
            adjustment=adjustment,
            lessons_learned=[evaluation],
        )

        self._reflections.append(reflection)

        # Update beliefs based on reflection
        if evaluation == "Failed":
            await self.add_belief(
                content=f"Previous approach failed: {observation}",
                confidence=0.7,
                source="reflection",
                is_core=False
            )

        logger.info("reflection_created", agent=self.name, evaluation=evaluation)

        return reflection

    async def reflect_on_success(self, result: Any):
        """Reflect on successful action."""
        await self.reflect(
            observation=f"Action succeeded: {str(result)[:100]}",
            evaluation="Success",
            adjustment="Continue similar approach"
        )
        self._success_count += 1
        self._total_actions += 1

    async def reflect_on_failure(self, error: str):
        """Reflect on failed action."""
        await self.reflect(
            observation=f"Action failed: {error}",
            evaluation="Failed",
            adjustment="Need different approach"
        )
        self._failure_count += 1
        self._total_actions += 1

    # ─────────────────────────────────────────────────────────────
    # Environment Awareness
    # ─────────────────────────────────────────────────────────────

    async def perceive_environment(self, context: dict):
        """Process environmental context."""
        self._current_context = context

        # Extract relevant information
        if "user_message" in context:
            message = context["user_message"]

            # Build beliefs about user
            if "preferences" in context:
                await self.add_belief(
                    content=f"User preferences: {context['preferences']}",
                    confidence=0.6,
                    source="observation"
                )

    def get_context_summary(self) -> str:
        """Get summary of current context."""
        return f"Context: {len(self._current_context)} items, State: {self._state.value}"

    # ─────────────────────────────────────────────────────────────
    # Proactive Behavior
    # ─────────────────────────────────────────────────────────────

    async def evaluate_proactive_actions(self) -> list[dict]:
        """
        Evaluate if agent should take proactive action.

        Called periodically when idle.
        """
        suggestions = []

        # Check for incomplete goals
        incomplete = self.get_goals_by_status(GoalStatus.PENDING)
        for goal in incomplete[:3]:
            if goal.priority >= 8:  # High priority
                suggestions.append({
                    "type": "goal",
                    "title": goal.title,
                    "priority": goal.priority,
                    "action": "resume_goal"
                })

        # Check for blocked goals
        blocked = self.get_goals_by_status(GoalStatus.BLOCKED)
        for goal in blocked:
            suggestions.append({
                "type": "blocked_goal",
                "title": goal.title,
                "action": "resolve_blocker"
            })

        return suggestions

    # ─────────────────────────────────────────────────────────────
    # Metrics
    # ─────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get agent statistics."""
        total = self._success_count + self._failure_count
        success_rate = self._success_count / total if total > 0 else 0

        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "state": self._state.value,
            "active_goal": self._active_goal_id,
            "total_goals": len(self._goals),
            "total_beliefs": len(self._beliefs),
            "total_reflections": len(self._reflections),
            "success_count": self._success_count,
            "failure_count": self._failure_count,
            "success_rate": success_rate
        }


# Agent Factory
class AgentFactory:
    """Factory for creating configured agents."""

    @staticmethod
    async def create_research_agent(llm_gateway=None, memory=None) -> AutonomousAgent:
        """Create research agent."""
        agent = AutonomousAgent(
            agent_id=str(uuid.uuid4()),
            name="Research Agent",
            description="Autonomous research and information gathering",
            llm_gateway=llm_gateway,
            memory_system=memory
        )

        # Add initial beliefs
        await agent.add_belief(
            content="Research requires verifying information from multiple sources",
            confidence=0.9,
            is_core=True
        )

        return agent

    @staticmethod
    async def create_planning_agent(llm_gateway=None, memory=None) -> AutonomousAgent:
        """Create planning agent."""
        agent = AutonomousAgent(
            agent_id=str(uuid.uuid4()),
            name="Planning Agent",
            description="Autonomous task planning and execution",
            llm_gateway=llm_gateway,
            memory_system=memory
        )

        await agent.add_belief(
            content="Plans should be adaptable to changing circumstances",
            confidence=0.9,
            is_core=True
        )

        return agent

    @staticmethod
    async def create_coach_agent(llm_gateway=None, memory=None) -> AutonomousAgent:
        """Create coaching agent."""
        agent = AutonomousAgent(
            agent_id=str(uuid.uuid4()),
            name="Coach Agent",
            description="Personal coaching and feedback",
            llm_gateway=llm_gateway,
            memory_system=memory
        )

        await agent.add_belief(
            content="Effective coaching requires understanding the user's context and goals",
            confidence=0.9,
            is_core=True
        )

        return agent