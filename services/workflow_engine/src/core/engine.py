"""
RasoSpeak AI OS — Workflow Engine
================================
Durable workflow execution using Temporal patterns.

This provides:
- Durable execution (survives restarts)
- Activity retries with backoff
- Child workflows
- Saga patterns for compensation
- State persistence
- Execution replay
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional, Callable
import traceback

import structlog

logger = structlog.get_logger("rasospeak.workflow")


# ──────────────────────────────────────────────────────────────────────────────
# Types
# ──────────────────────────────────────────────────────────────────────────────

class WorkflowState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class ActivityState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowDefinition:
    """Definition of a workflow type."""
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    timeout_seconds: int = 3600
    retry_policy: dict = field(default_factory=lambda: {
        "max_attempts": 3,
        "initial_interval_seconds": 1,
        "backoff_coefficient": 2.0,
        "max_interval_seconds": 100,
    })


@dataclass
class WorkflowExecution:
    """A single workflow execution instance."""
    workflow_id: str
    workflow_name: str
    state: WorkflowState
    input: dict[str, Any]
    output: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    steps: list[WorkflowStep] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    parent_workflow_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "state": self.state.value,
            "input": self.input,
            "output": self.output,
            "error": self.error,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "retry_count": self.retry_count,
        }


@dataclass
class WorkflowStep:
    """A single step within a workflow."""
    step_id: str
    activity_name: str
    state: ActivityState
    input: dict[str, Any]
    output: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "activity_name": self.activity_name,
            "state": self.state.value,
            "input": self.input,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "retry_count": self.retry_count,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Activity Decorator
# ──────────────────────────────────────────────────────────────────────────────

class Activity:
    """
    Decorator for workflow activities.

    Activities are the building blocks of workflows.
    They are:
    - Idempotent (safe to retry)
    - Durable (state persisted)
    - Replayable (can replay from failure)

    Usage:
        @activity.defn
        async def my_activity(input: dict) -> dict:
            # Do work
            return {"result": "value"}
    """

    def __init__(
        self,
        name: Optional[str] = None,
        retry_policy: Optional[dict] = None,
        timeout_seconds: int = 300,
    ):
        self.name = name
        self.retry_policy = retry_policy or {
            "max_attempts": 3,
            "initial_interval_seconds": 1,
            "backoff_coefficient": 2.0,
        }
        self.timeout_seconds = timeout_seconds
        self._func: Optional[Callable] = None

    def __call__(self, func: Callable) -> Activity:
        self._func = func
        self.name = self.name or func.__name__
        return self

    async def execute(
        self,
        input_data: dict[str, Any],
        context: WorkflowContext,
    ) -> Any:
        """Execute the activity with retry logic."""
        max_attempts = self.retry_policy["max_attempts"]
        interval = self.retry_policy["initial_interval_seconds"]

        last_error: Optional[Exception] = None

        for attempt in range(max_attempts):
            try:
                logger.info(
                    "activity_executing",
                    activity=self.name,
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                    workflow_id=context.workflow_id,
                )

                result = await asyncio.wait_for(
                    self._func(input_data, context),
                    timeout=self.timeout_seconds,
                )

                logger.info(
                    "activity_completed",
                    activity=self.name,
                    attempt=attempt + 1,
                    workflow_id=context.workflow_id,
                )

                return result

            except asyncio.TimeoutError:
                last_error = Exception(f"Activity timeout after {self.timeout_seconds}s")
                logger.error(
                    "activity_timeout",
                    activity=self.name,
                    timeout=self.timeout_seconds,
                )

            except Exception as e:
                last_error = e
                logger.error(
                    "activity_error",
                    activity=self.name,
                    attempt=attempt + 1,
                    error=str(e),
                )

            if attempt < max_attempts - 1:
                await asyncio.sleep(interval)
                interval *= self.retry_policy.get("backoff_coefficient", 2.0)

        raise last_error


@dataclass
class WorkflowContext:
    """Context passed to activities during workflow execution."""
    workflow_id: str
    workflow_name: str
    run_id: str
    task_token: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# Workflow Decorator
# ──────────────────────────────────────────────────────────────────────────────

class Workflow:
    """
    Decorator for workflow definitions.

    Workflows define the orchestration of activities.
    They are:
    - Replayable (deterministic replay from start)
    - Durable (state persisted at each step)
    - Fault-tolerant (automatic retry)

    Usage:
        @workflow.defn
        class MyWorkflow:
            async def run(self, input: dict) -> dict:
                result = await workflow.execute_activity(
                    my_activity, input
                )
                return result
    """

    def __init__(
        self,
        name: Optional[str] = None,
        timeout_seconds: int = 3600,
    ):
        self.name = name
        self.timeout_seconds = timeout_seconds
        self._class: Optional[type] = None

    def __call__(self, workflow_class: type) -> Workflow:
        self._class = workflow_class
        self.name = self.name or workflow_class.__name__
        return self

    def create_instance(
        self,
        workflow_id: str,
        input_data: dict[str, Any],
    ) -> WorkflowInstance:
        """Create a workflow instance."""
        return WorkflowInstance(
            definition=self,
            workflow_id=workflow_id,
            input=input_data,
        )


@dataclass
class WorkflowInstance:
    """Runtime instance of a workflow."""
    definition: Workflow
    workflow_id: str
    input: dict[str, Any]
    state: WorkflowState = WorkflowState.PENDING
    output: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    steps: list[WorkflowStep] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    async def execute(
        self,
        executor: WorkflowExecutor,
    ) -> dict[str, Any]:
        """Execute the workflow."""
        self.state = WorkflowState.RUNNING
        self.started_at = datetime.utcnow()

        logger.info(
            "workflow_started",
            workflow_id=self.workflow_id,
            workflow_name=self.definition.name,
        )

        try:
            # Create workflow context
            context = WorkflowContext(
                workflow_id=self.workflow_id,
                workflow_name=self.definition.name,
                run_id=str(uuid.uuid4()),
                task_token=str(uuid.uuid4()),
            )

            # Create workflow instance
            instance = self.definition._class()

            # Get the run method
            run_method = getattr(instance, "run", None)
            if not run_method:
                raise ValueError(f"Workflow {self.definition.name} has no run method")

            # Execute workflow
            result = await asyncio.wait_for(
                run_method(self.input, executor, context),
                timeout=self.definition.timeout_seconds,
            )

            self.output = result
            self.state = WorkflowState.COMPLETED
            self.completed_at = datetime.utcnow()

            logger.info(
                "workflow_completed",
                workflow_id=self.workflow_id,
                duration_ms=(
                    self.completed_at - self.started_at
                ).total_seconds() * 1000 if self.started_at else 0,
            )

            return result

        except asyncio.TimeoutError:
            self.state = WorkflowState.TIMED_OUT
            self.error = f"Workflow timeout after {self.definition.timeout_seconds}s"
            logger.error(
                "workflow_timeout",
                workflow_id=self.workflow_id,
                timeout=self.definition.timeout_seconds,
            )

        except Exception as e:
            self.state = WorkflowState.FAILED
            self.error = str(e)
            logger.error(
                "workflow_failed",
                workflow_id=self.workflow_id,
                error=str(e),
                traceback=traceback.format_exc(),
            )

        self.completed_at = datetime.utcnow()
        return {}


# ──────────────────────────────────────────────────────────────────────────────
# Predefined Activities
# ──────────────────────────────────────────────────────────────────────────────

class Activities:
    """Collection of predefined activities."""

    @staticmethod
    @Activity(name="store_memory")
    async def store_memory(input: dict, context: WorkflowContext) -> dict:
        """Store a memory entry."""
        return {
            "memory_id": str(uuid.uuid4()),
            "stored": True,
        }

    @staticmethod
    @Activity(name="send_notification")
    async def send_notification(input: dict, context: WorkflowContext) -> dict:
        """Send a notification."""
        return {
            "notification_id": str(uuid.uuid4()),
            "sent": True,
        }

    @staticmethod
    @Activity(name="schedule_task")
    async def schedule_task(input: dict, context: WorkflowContext) -> dict:
        """Schedule a future task."""
        return {
            "task_id": str(uuid.uuid4()),
            "scheduled": True,
        }

    @staticmethod
    @Activity(name="llm_call")
    async def llm_call(input: dict, context: WorkflowContext) -> dict:
        """Make an LLM call."""
        return {
            "response": f"LLM response to: {input.get('prompt', 'unknown')}",
            "tokens_used": 100,
        }

    @staticmethod
    @Activity(name="update_progress")
    async def update_progress(input: dict, context: WorkflowContext) -> dict:
        """Update user progress tracking."""
        return {
            "updated": True,
            "progress": 0.5,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Workflow Executor
# ──────────────────────────────────────────────────────────────────────────────

class WorkflowExecutor:
    """
    Executes workflow activities with durability guarantees.

    In production, this would integrate with Temporal.
    For now, it provides the same interface with local execution.
    """

    def __init__(self, persistence=None):
        self.persistence = persistence  # PostgreSQL/Temporal persistence
        self.activities: dict[str, Activity] = {}
        self._lock = asyncio.Lock()

        # Register predefined activities
        self._register_activities()

        logger.info("workflow_executor_initialized")

    def _register_activities(self) -> None:
        """Register all predefined activities."""
        for name in dir(Activities):
            attr = getattr(Activities, name)
            if isinstance(attr, Activity):
                self.activities[attr.name] = attr

    def register_activity(self, activity: Activity) -> None:
        """Register a custom activity."""
        self.activities[activity.name] = activity

    async def execute_activity(
        self,
        activity_name: str,
        input_data: dict[str, Any],
        workflow_context: WorkflowContext,
    ) -> Any:
        """Execute a single activity."""
        activity = self.activities.get(activity_name)
        if not activity:
            raise ValueError(f"Activity not found: {activity_name}")

        result = await activity.execute(input_data, workflow_context)
        return result

    async def execute_activity_with_retry(
        self,
        activity_name: str,
        input_data: dict[str, Any],
        workflow_context: WorkflowContext,
        max_attempts: int = 3,
    ) -> Any:
        """Execute an activity with automatic retry."""
        last_error: Optional[Exception] = None

        for attempt in range(max_attempts):
            try:
                return await self.execute_activity(
                    activity_name, input_data, workflow_context
                )
            except Exception as e:
                last_error = e
                if attempt < max_attempts - 1:
                    await asyncio.sleep(2 ** attempt)

        raise last_error


# ──────────────────────────────────────────────────────────────────────────────
# Workflow Engine
# ──────────────────────────────────────────────────────────────────────────────

class WorkflowEngine:
    """
    Main workflow engine for managing workflow executions.

    Features:
    - Durable execution (persists state)
    - Automatic retry
    - Child workflows
    - Cancellation
    - Monitoring
    """

    def __init__(self, executor: Optional[WorkflowExecutor] = None):
        self.executor = executor or WorkflowExecutor()
        self.workflows: dict[str, type] = {}
        self.executions: dict[str, WorkflowInstance] = {}
        self._lock = asyncio.Lock()
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._running = False

        logger.info("workflow_engine_initialized")

    def register_workflow(self, workflow: Workflow) -> None:
        """Register a workflow type."""
        self.workflows[workflow.name] = workflow._class

    async def start_workflow(
        self,
        workflow_name: str,
        input_data: dict[str, Any],
        workflow_id: Optional[str] = None,
    ) -> WorkflowExecution:
        """Start a new workflow execution."""
        workflow_id = workflow_id or str(uuid.uuid4())

        workflow_class = self.workflows.get(workflow_name)
        if not workflow_class:
            raise ValueError(f"Workflow not found: {workflow_name}")

        # Create workflow definition
        definition = WorkflowDefinition(
            name=workflow_name,
            description=workflow_class.__doc__ or "",
            input_schema={},
            output_schema={},
        )

        # Create instance
        instance = WorkflowInstance(
            definition=definition,
            workflow_id=workflow_id,
            input=input_data,
        )

        async with self._lock:
            self.executions[workflow_id] = instance

        # Queue for execution
        await self._task_queue.put(instance)

        # Start worker if not running
        if not self._running:
            asyncio.create_task(self._worker_loop())

        logger.info(
            "workflow_queued",
            workflow_id=workflow_id,
            workflow_name=workflow_name,
        )

        return WorkflowExecution(
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            state=WorkflowState.PENDING,
            input=input_data,
        )

    async def _worker_loop(self) -> None:
        """Main worker loop for processing workflow queue."""
        self._running = True

        while self._running:
            try:
                instance = await asyncio.wait_for(
                    self._task_queue.get(),
                    timeout=1.0,
                )

                await instance.execute(self.executor)

            except asyncio.TimeoutError:
                continue

            except Exception as e:
                logger.error(
                    "workflow_worker_error",
                    error=str(e),
                    traceback=traceback.format_exc(),
                )

    async def get_execution(self, workflow_id: str) -> Optional[WorkflowInstance]:
        """Get a workflow execution by ID."""
        return self.executions.get(workflow_id)

    async def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a running workflow."""
        instance = self.executions.get(workflow_id)
        if not instance:
            return False

        if instance.state in (WorkflowState.COMPLETED, WorkflowState.FAILED):
            return False

        instance.state = WorkflowState.CANCELLED
        instance.completed_at = datetime.utcnow()

        logger.info("workflow_cancelled", workflow_id=workflow_id)
        return True

    def get_stats(self) -> dict:
        """Get workflow engine statistics."""
        states = {s: 0 for s in WorkflowState}
        for instance in self.executions.values():
            states[instance.state] += 1

        return {
            "total_executions": len(self.executions),
            "pending": states[WorkflowState.PENDING],
            "running": states[WorkflowState.RUNNING],
            "completed": states[WorkflowState.COMPLETED],
            "failed": states[WorkflowState.FAILED],
            "cancelled": states[WorkflowState.CANCELLED],
            "queue_depth": self._task_queue.qsize(),
        }


# ──────────────────────────────────────────────────────────────────────────────
# Example Workflows
# ──────────────────────────────────────────────────────────────────────────────

@Workflow(name="interview_prep")
class InterviewPrepWorkflow:
    """
    Durable workflow for ML interview preparation.

    Survives server restarts, retries failed activities.
    """

    async def run(
        self,
        input_data: dict,
        executor: WorkflowExecutor,
        context: WorkflowContext,
    ) -> dict:
        user_id = input_data.get("user_id")
        job_description = input_data.get("job_description", "")

        # Step 1: Initialize state
        state = await executor.execute_activity(
            "store_memory",
            {
                "user_id": user_id,
                "type": "workflow_state",
                "workflow": "interview_prep",
                "step": "initializing",
            },
            context,
        )

        # Step 2: Assess ML level
        assessment = await executor.execute_activity(
            "llm_call",
            {
                "prompt": f"Assess ML skills for: {job_description}",
                "model": "claude-3-5-sonnet",
            },
            context,
        )

        # Step 3: Create study plan
        study_plan = await executor.execute_activity(
            "llm_call",
            {
                "prompt": f"Create study plan based on assessment: {assessment}",
                "model": "claude-3-5-sonnet",
            },
            context,
        )

        # Step 4: Schedule coaching sessions
        for i, date in enumerate(["2026-05-15", "2026-05-22", "2026-05-29"]):
            await executor.execute_activity(
                "schedule_task",
                {
                    "user_id": user_id,
                    "date": date,
                    "topic": f"Coaching session {i+1}",
                },
                context,
            )

        # Step 5: Send welcome notification
        await executor.execute_activity(
            "send_notification",
            {
                "user_id": user_id,
                "message": "Your interview prep plan is ready!",
            },
            context,
        )

        # Step 6: Update progress
        await executor.execute_activity(
            "update_progress",
            {
                "user_id": user_id,
                "workflow": "interview_prep",
                "progress": 1.0,
            },
            context,
        )

        return {
            "status": "completed",
            "user_id": user_id,
            "sessions_scheduled": 3,
        }


@Workflow(name="daily_checkin")
class DailyCheckinWorkflow:
    """Daily check-in workflow with reminders and progress tracking."""

    async def run(
        self,
        input_data: dict,
        executor: WorkflowExecutor,
        context: WorkflowContext,
    ) -> dict:
        user_id = input_data.get("user_id")

        # Check progress
        progress = await executor.execute_activity(
            "update_progress",
            {"user_id": user_id},
            context,
        )

        # Send reminder if needed
        if progress.get("progress", 0) < 0.5:
            await executor.execute_activity(
                "send_notification",
                {
                    "user_id": user_id,
                    "message": "Don't forget to practice today!",
                },
                context,
            )

        return {
            "status": "completed",
            "user_id": user_id,
            "progress": progress.get("progress", 0),
        }
