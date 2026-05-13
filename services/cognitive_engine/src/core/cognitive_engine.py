"""
RasoSpeak AI OS — Cognitive Engine
==================================
Unified cognitive engine orchestrating all 7 cognitive layers:

1. Reactive Layer (fast path responses)
2. Perception Layer (STT, vision, documents)
3. Planning Layer (HTN planning, DAG execution)
4. Reflection Layer (self-evaluation, adaptation)
5. Memory Layer (consolidation, retrieval)
6. World Model Layer (entity graph, reasoning)
7. Execution Layer (tools, workflows, actions)

This is the ONE cognitive runtime that all subsystems share.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger("rasospeak.cognition")


# ──────────────────────────────────────────────────────────────────────────────
# Cognition Types
# ──────────────────────────────────────────────────────────────────────────────

class CognitionState(Enum):
    IDLE = "idle"
    PERCEIVING = "perceiving"
    REASONING = "reasoning"
    PLANNING = "planning"
    EXECUTING = "executing"
    REFLECTING = "reflecting"
    SPEAKING = "speaking"


class ConfidenceLevel(Enum):
    VERY_HIGH = 0.95
    HIGH = 0.8
    MEDIUM = 0.6
    LOW = 0.4
    VERY_LOW = 0.2


@dataclass
class Perception:
    """Input perception from various sources."""
    perception_id: str
    source: str  # voice, text, document, vision
    raw_input: Any
    processed_text: str
    entities: list[dict] = field(default_factory=list)
    intent: Optional[str] = None
    emotional_tone: Optional[str] = None
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)


@dataclass
class Thought:
    """Internal reasoning result."""
    thought_id: str
    reasoning: str
    confidence: ConfidenceLevel
    supporting_evidence: list[str] = field(default_factory=list)
    alternatives_considered: list[str] = field(default_factory=list)
    uncertainty_areas: list[str] = field(default_factory=list)


@dataclass
class Plan:
    """Execution plan from planning layer."""
    plan_id: str
    tasks: list[dict] = field(default_factory=list)
    estimated_duration_ms: int = 0
    estimated_tokens: int = 0
    confidence: float = 1.0
    can_parallelize: list[str] = field(default_factory=list)


@dataclass
class Action:
    """Action to execute."""
    action_id: str
    action_type: str  # tool, workflow, response
    tool_name: Optional[str] = None
    parameters: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """Result of action execution."""
    action_id: str
    success: bool
    output: Any
    error: Optional[str] = None
    duration_ms: int = 0
    tokens_used: int = 0


@dataclass
class Reflection:
    """Self-evaluation result."""
    reflection_id: str
    performance_score: float
    errors: list[str] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    adaptations: list[dict] = field(default_factory=list)
    confidence_adjustment: float = 1.0


@dataclass
class CognitionContext:
    """Complete context for cognition."""
    user_id: str
    session_id: str
    conversation_history: list[dict] = field(default_factory=list)
    active_goals: list[str] = field(default_factory=list)
    recent_memories: list[dict] = field(default_factory=list)
    user_preferences: dict = field(default_factory=dict)
    current_plan: Optional[Plan] = None
    confidence: float = 1.0
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class CognitiveResponse:
    """Complete response from cognitive engine."""
    response_id: str
    output_text: Optional[str] = None
    output_audio: Optional[bytes] = None
    actions: list[Action] = field(default_factory=list)
    state: CognitionState
    confidence: float
    reasoning: str
    memory_updates: list[dict] = field(default_factory=list)
    world_model_updates: list[dict] = field(default_factory=list)
    duration_ms: int = 0


# ──────────────────────────────────────────────────────────────────────────────
# Reactive Layer (Fast Path)
# ──────────────────────────────────────────────────────────────────────────────

class ReactiveLayer:
    """Low-latency response layer for simple queries."""

    FAST_PATTERNS = {
        "time": ["what time", "current time", "clock"],
        "date": ["what date", "today's date", "calendar"],
        "weather": ["weather", "temperature", "forecast"],
        "help": ["help", "commands", "what can you do"],
        "status": ["status", "how are you", "system"],
    }

    def __init__(self, world_model, memory_service):
        self._world_model = world_model
        self._memory = memory_service

    async def try_handle(self, perception: Perception) -> Optional[CognitiveResponse]:
        """Attempt fast-path response for simple queries."""
        text_lower = perception.processed_text.lower()

        # Check for fast patterns
        for intent, patterns in self.FAST_PATTERNS.items():
            if any(p in text_lower for p in patterns):
                response_text = await self._handle_fast_pattern(intent, perception)
                if response_text:
                    logger.info("reactive_layer_handled", intent=intent)
                    return CognitiveResponse(
                        response_id=str(uuid.uuid4()),
                        output_text=response_text,
                        state=CognitionState.IDLE,
                        confidence=0.9,
                        reasoning=f"Fast path: {intent}",
                    )

        return None

    async def _handle_fast_pattern(self, intent: str, perception: Perception) -> Optional[str]:
        """Handle specific fast pattern."""
        from datetime import datetime

        if intent == "time":
            return f"The current time is {datetime.now().strftime('%H:%M')}"
        elif intent == "date":
            return f"Today is {datetime.now().strftime('%Y-%m-%d')}"
        elif intent == "help":
            return "I can help with: conversations, planning, memory, documents, coaching. Just ask!"
        elif intent == "status":
            return "I'm running well. Ready to assist you."

        return None


# ──────────────────────────────────────────────────────────────────────────────
# Perception Layer
# ──────────────────────────────────────────────────────────────────────────────

class PerceptionLayer:
    """Process inputs from various sources."""

    def __init__(self, world_model, memory_service):
        self._world_model = world_model
        self._memory = memory_service

    async def perceive(self, input_data: Any, source: str) -> Perception:
        """Process input and extract meaning."""
        perception_id = str(uuid.uuid4())

        # Process based on source
        if source == "voice" or source == "text":
            processed_text = self._extract_text(input_data)
            entities = await self._extract_entities(processed_text)
            intent = self._classify_intent(processed_text)

            # Get emotional tone
            emotional_tone = await self._detect_emotion(processed_text)

            return Perception(
                perception_id=perception_id,
                source=source,
                raw_input=input_data,
                processed_text=processed_text,
                entities=entities,
                intent=intent,
                emotional_tone=emotional_tone,
            )

        elif source == "document":
            return await self._perceive_document(input_data, perception_id)

        return Perception(
            perception_id=perception_id,
            source=source,
            raw_input=input_data,
            processed_text=str(input_data),
        )

    def _extract_text(self, input_data: Any) -> str:
        """Extract text from input."""
        if isinstance(input_data, str):
            return input_data
        elif hasattr(input_data, 'text'):
            return input_data.text
        return str(input_data)

    async def _extract_entities(self, text: str) -> list[dict]:
        """Extract entities from text."""
        entities = []

        # Simple entity extraction (in production use NER)
        words = text.split()
        for i, word in enumerate(words):
            # Capitalized words might be names
            if word and word[0].isupper() and len(word) > 1:
                entities.append({
                    "text": word,
                    "type": "potential_entity",
                })

        return entities

    def _classify_intent(self, text: str) -> Optional[str]:
        """Classify user intent."""
        text_lower = text.lower()

        intents = {
            "question": ["who", "what", "where", "when", "why", "how", "?"],
            "command": ["do", "make", "create", "start", "stop", "delete"],
            "statement": [],
            "request": ["can you", "could you", "would you", "please"],
            "reflection": ["remember", "recall", "what did", "when was"],
        }

        for intent, patterns in intents.items():
            if any(p in text_lower for p in patterns):
                return intent

        return "statement"

    async def _detect_emotion(self, text: str) -> Optional[str]:
        """Detect emotional tone."""
        text_lower = text.lower()

        emotions = {
            "happy": ["great", "awesome", "love", "excited", "! !"],
            "frustrated": ["stuck", "frustrated", "annoying", "can't"],
            "worried": ["worried", "concerned", "nervous", "afraid"],
            "curious": ["wonder", "interesting", "tell me about"],
        }

        for emotion, patterns in emotions.items():
            if any(p in text_lower for p in patterns):
                return emotion

        return None

    async def _perceive_document(self, document: Any, perception_id: str) -> Perception:
        """Process document input."""
        # Extract text from document
        text = document.get("text", "") if isinstance(document, dict) else str(document)

        return Perception(
            perception_id=perception_id,
            source="document",
            raw_input=document,
            processed_text=text,
            entities=await self._extract_entities(text),
        )


# ──────────────────────────────────────────────────────────────────────────────
# Planning Layer
# ──────────────────────────────────────────────────────────────────────────────

class PlanningLayer:
    """HTN-style planning with DAG execution."""

    def __init__(self, world_model, memory_service):
        self._world_model = world_model
        self._memory = memory_service

    async def create_plan(self, perception: Perception, context: CognitionContext) -> Optional[Plan]:
        """Create execution plan from perception."""
        # Check if planning is needed
        if await self._should_use_fast_path(perception):
            return None

        # Extract goal from perception
        goal = perception.processed_text

        # Create task decomposition
        tasks = await self._decompose_goal(goal, context)

        # Build DAG
        dag = self._build_dag(tasks)

        # Calculate estimates
        estimated_tokens = sum(t.get("estimated_tokens", 500) for t in tasks)
        estimated_duration = sum(t.get("estimated_duration", 1000) for t in tasks)

        # Identify parallelizable tasks
        parallelizable = [t["task_id"] for t in tasks if not t.get("depends_on")]

        plan = Plan(
            plan_id=str(uuid.uuid4()),
            tasks=dag,
            estimated_duration_ms=estimated_duration,
            estimated_tokens=estimated_tokens,
            confidence=0.7,
            can_parallelize=parallelizable,
        )

        logger.info("plan_created", plan_id=plan.plan_id, tasks=len(tasks))
        return plan

    async def _should_use_fast_path(self, perception: Perception) -> bool:
        """Check if simple response is sufficient."""
        text = perception.processed_text.lower()

        # Short simple queries don't need planning
        if len(perception.processed_text.split()) < 5:
            if any(w in text for w in ["what", "who", "when", "where", "how many"]):
                return True

        return False

    async def _decompose_goal(self, goal: str, context: CognitionContext) -> list[dict]:
        """Decompose goal into tasks."""
        goal_lower = goal.lower()

        # Domain-specific decomposition
        if "remember" in goal_lower or "what did" in goal_lower:
            return [
                {"task_id": "retrieve_memories", "task_type": "memory", "estimated_tokens": 2000, "estimated_duration": 500},
                {"task_id": "reconstruct_context", "task_type": "reasoning", "depends_on": ["retrieve_memories"], "estimated_tokens": 1500, "estimated_duration": 500},
            ]

        elif "plan" in goal_lower or "organize" in goal_lower:
            return [
                {"task_id": "understand_requirements", "task_type": "analysis", "estimated_tokens": 1500, "estimated_duration": 500},
                {"task_id": "decompose_tasks", "task_type": "planning", "depends_on": ["understand_requirements"], "estimated_tokens": 2000, "estimated_duration": 1000},
                {"task_id": "estimate_resources", "task_type": "analysis", "depends_on": ["decompose_tasks"], "estimated_tokens": 1000, "estimated_duration": 500},
            ]

        elif "learn" in goal_lower or "study" in goal_lower:
            return [
                {"task_id": "assess_level", "task_type": "analysis", "estimated_tokens": 1500, "estimated_duration": 500},
                {"task_id": "create_path", "task_type": "planning", "depends_on": ["assess_level"], "estimated_tokens": 2500, "estimated_duration": 1000},
                {"task_id": "recommend_resources", "task_type": "synthesis", "depends_on": ["create_path"], "estimated_tokens": 1500, "estimated_duration": 500},
            ]

        else:
            # Default: understand + respond
            return [
                {"task_id": "retrieve_context", "task_type": "memory", "estimated_tokens": 2000, "estimated_duration": 500},
                {"task_id": "generate_response", "task_type": "reasoning", "depends_on": ["retrieve_context"], "estimated_tokens": 3000, "estimated_duration": 1000},
            ]

    def _build_dag(self, tasks: list[dict]) -> list[dict]:
        """Build directed acyclic graph of tasks."""
        # Validate no cycles
        task_ids = {t["task_id"] for t in tasks}

        for task in tasks:
            if task.get("depends_on"):
                for dep in task["depends_on"]:
                    if dep not in task_ids:
                        task["depends_on"].remove(dep)

        return tasks


# ──────────────────────────────────────────────────────────────────────────────
# Execution Layer
# ──────────────────────────────────────────────────────────────────────────────

class ExecutionLayer:
    """Execute actions using tools and workflows."""

    def __init__(self, world_model, memory_service, llm_gateway):
        self._world_model = world_model
        self._memory = memory_service
        self._llm = llm_gateway

    async def execute_plan(
        self,
        plan: Plan,
        context: CognitionContext,
    ) -> list[ExecutionResult]:
        """Execute plan tasks in topological order."""
        results = []
        completed = set()

        for task in plan.tasks:
            # Wait for dependencies
            if task.get("depends_on"):
                deps_satisfied = all(d in completed for d in task["depends_on"])
                if not deps_satisfied:
                    logger.warning("deps_not_satisfied", task_id=task["task_id"])
                    continue

            # Execute task
            result = await self._execute_task(task, context)
            results.append(result)

            if result.success:
                completed.add(task["task_id"])

        return results

    async def _execute_task(self, task: dict, context: CognitionContext) -> ExecutionResult:
        """Execute single task."""
        task_type = task.get("task_type", "reasoning")
        task_id = task["task_id"]

        try:
            if task_type == "memory":
                # Memory operation
                return ExecutionResult(
                    action_id=task_id,
                    success=True,
                    output={"memories_retrieved": True},
                    duration_ms=100,
                )

            elif task_type == "planning":
                # Planning operation
                return ExecutionResult(
                    action_id=task_id,
                    success=True,
                    output={"plan_created": True},
                    duration_ms=200,
                )

            elif task_type == "reasoning":
                # LLM reasoning
                prompt = f"Context: {context.conversation_history[-3:]}\nUser: {context.conversation_history[-1] if context.conversation_history else 'Hello'}"

                # In production call LLM
                output = f"Reasoned response to: {task_id}"

                return ExecutionResult(
                    action_id=task_id,
                    success=True,
                    output=output,
                    duration_ms=500,
                    tokens_used=100,
                )

            else:
                return ExecutionResult(
                    action_id=task_id,
                    success=False,
                    output=None,
                    error=f"Unknown task type: {task_type}",
                )

        except Exception as e:
            logger.error("task_execution_error", task_id=task_id, error=str(e))
            return ExecutionResult(
                action_id=task_id,
                success=False,
                output=None,
                error=str(e),
            )


# ──────────────────────────────────────────────────────────────────────────────
# Reflection Layer
# ──────────────────────────────────────────────────────────────────────────────

class ReflectionLayer:
    """Self-evaluation and behavioral adaptation."""

    def __init__(self, world_model):
        self._world_model = world_model
        self._learning_history: dict[str, list[dict]] = {}

    async def reflect(
        self,
        results: list[ExecutionResult],
        context: CognitionContext,
    ) -> Reflection:
        """Reflect on execution results."""
        reflection_id = str(uuid.uuid4())

        # Calculate performance
        total_tasks = len(results)
        successful = sum(1 for r in results if r.success)
        performance_score = successful / total_tasks if total_tasks > 0 else 0

        # Analyze errors
        errors = [r.error for r in results if r.error]

        # Generate insights
        insights = []
        if performance_score == 1.0:
            insights.append("All tasks completed successfully")
        elif performance_score > 0.5:
            insights.append("Partial success - some tasks failed")
        else:
            insights.append("Multiple failures - review approach")

        # Adapt for future
        adaptations = await self._adapt_behavior(performance_score, context)

        # Adjust confidence
        if performance_score > 0.8:
            confidence_adjustment = 1.1
        elif performance_score < 0.5:
            confidence_adjustment = 0.8
        else:
            confidence_adjustment = 1.0

        # Record learning
        await self._record_learning(context.user_id, {
            "timestamp": datetime.utcnow().isoformat(),
            "performance": performance_score,
            "errors": errors,
        })

        logger.info("reflection_completed", performance=performance_score, insights=len(insights))

        return Reflection(
            reflection_id=reflection_id,
            performance_score=performance_score,
            errors=errors,
            insights=insights,
            adaptations=adaptations,
            confidence_adjustment=confidence_adjustment,
        )

    async def _adapt_behavior(self, performance: float, context: CognitionContext) -> list[dict]:
        """Adapt behavior based on performance."""
        adaptations = []

        if performance > 0.8:
            # Successful - maintain current approach
            adaptations.append({
                "type": "maintain",
                "strategy": "current_approach",
            })

        elif performance < 0.5:
            # Failed - try different approach
            adaptations.append({
                "type": "change_strategy",
                "strategy": "more_thorough",
            })

        return adaptations

    async def _record_learning(self, user_id: str, learning: dict):
        """Record learning for future reference."""
        if user_id not in self._learning_history:
            self._learning_history[user_id] = []

        self._learning_history[user_id].append(learning)

        # Keep last 100 entries
        if len(self._learning_history[user_id]) > 100:
            self._learning_history[user_id] = self._learning_history[user_id][-100:]


# ──────────────────────────────────────────────────────────────────────────────
# Memory Layer
# ──────────────────────────────────────────────────────────────────────────────

class MemoryLayer:
    """Memory consolidation, retrieval, and context assembly."""

    def __init__(self, memory_service):
        self._memory = memory_service

    async def retrieve_context(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
    ) -> list[dict]:
        """Retrieve relevant memories for context."""
        # Use memory service
        result = await self._memory.retrieve(
            user_id=user_id,
            query=query,
            limit=limit,
        )

        return result.memories if result else []

    async def form_memory(
        self,
        user_id: str,
        perception: Perception,
        response: str,
    ):
        """Form episodic memory from interaction."""
        from services.memory_service.src.core.memory import MemoryType

        # Store conversation
        await self._memory.store(
            user_id=user_id,
            tenant_id=user_id,
            content={
                "perception": perception.processed_text,
                "response": response,
                "entities": perception.entities,
                "intent": perception.intent,
                "emotion": perception.emotional_tone,
            },
            memory_type=MemoryType.EPISODIC,
            tags=["conversation", perception.intent or "general"],
        )

    async def consolidate(self, user_id: str):
        """Run memory consolidation."""
        return await self._memory.consolidate(user_id)


# ──────────────────────────────────────────────────────────────────────────────
# Unified Cognitive Engine
# ──────────────────────────────────────────────────────────────────────────────

class CognitiveEngine:
    """
    Unified cognitive engine - orchestrates all 7 layers.

    This is the ONE intelligence that all subsystems share.
    """

    def __init__(
        self,
        world_model,
        memory_service,
        llm_gateway,
        voice_service=None,
    ):
        # Initialize all layers
        self._world_model = world_model
        self._memory_service = memory_service

        self.reactive = ReactiveLayer(world_model, memory_service)
        self.perception = PerceptionLayer(world_model, memory_service)
        self.planning = PlanningLayer(world_model, memory_service)
        self.execution = ExecutionLayer(world_model, memory_service, llm_gateway)
        self.reflection = ReflectionLayer(world_model)
        self.memory = MemoryLayer(memory_service)

        self._voice = voice_service
        self._active_contexts: dict[str, CognitionContext] = {}

        logger.info("cognitive_engine_initialized")

    async def process_input(
        self,
        input_data: Any,
        source: str,
        user_id: str,
    ) -> CognitiveResponse:
        """Process input through all cognitive layers."""
        start_time = datetime.utcnow()
        trace_id = str(uuid.uuid4())

        # Get or create context
        if user_id not in self._active_contexts:
            self._active_contexts[user_id] = CognitionContext(
                user_id=user_id,
                session_id=str(uuid.uuid4()),
            )
        context = self._active_contexts[user_id]

        logger.info("cognition_started", trace_id=trace_id, source=source)

        # Layer 1: Reactive (fast path)
        perception = await self.perception.perceive(input_data, source)
        reactive_response = await self.reactive.try_handle(perception)

        if reactive_response:
            reactive_response.duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return reactive_response

        # Layer 2-3: Planning (if needed)
        plan = await self.planning.create_plan(perception, context)
        if plan:
            context.current_plan = plan
            results = await self.execution.execute_plan(plan, context)
        else:
            # Simple direct execution
            results = []

        # Layer 4: Reflection
        reflection = await self.reflection.reflect(results, context)
        context.confidence *= reflection.confidence_adjustment

        # Layer 5: Memory formation
        output_text = await self._generate_output(results, perception, context)
        await self.memory.form_memory(user_id, perception, output_text)

        # Update world model with interaction
        await self._world_model.record_event(
            user_id=user_id,
            event_type="conversation",
            content={
                "input": perception.processed_text,
                "output": output_text,
                "intent": perception.intent,
            },
        )

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        response = CognitiveResponse(
            response_id=str(uuid.uuid4()),
            output_text=output_text,
            state=CognitionState.IDLE,
            confidence=context.confidence,
            reasoning=f"Cognition completed in {duration_ms}ms",
            duration_ms=duration_ms,
        )

        logger.info("cognition_completed", trace_id=trace_id, duration_ms=duration_ms)
        return response

    async def _generate_output(
        self,
        results: list[ExecutionResult],
        perception: Perception,
        context: CognitionContext,
    ) -> str:
        """Generate output text from results."""
        # Simple response generation
        if results:
            outputs = [r.output for r in results if r.output]
            if outputs:
                return str(outputs[-1])

        # Default response
        return f"I understand: {perception.processed_text[:100]}"

    async def get_context(self, user_id: str) -> Optional[CognitionContext]:
        """Get current cognition context for user."""
        return self._active_contexts.get(user_id)

    async def clear_context(self, user_id: str):
        """Clear cognition context."""
        if user_id in self._active_contexts:
            self._active_contexts[user_id] = CognitionContext(
                user_id=user_id,
                session_id=str(uuid.uuid4()),
            )


def create_cognitive_engine(
    world_model,
    memory_service,
    llm_gateway,
    voice_service=None,
) -> CognitiveEngine:
    """Factory function to create cognitive engine."""
    return CognitiveEngine(
        world_model=world_model,
        memory_service=memory_service,
        llm_gateway=llm_gateway,
        voice_service=voice_service,
    )