"""
RasoSpeak AI OS — Agent Runtime Service
Main entry point for the autonomous agent runtime.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from rasospeak_common import setup_logging, get_logger, Settings, get_settings
from .core.agent import AgentRuntime, AgentType, Goal, AgentFactory
from .core.gateway import create_gateway
from .core.memory import MemoryService
from .core.planner import Planner, PlanningContext
from .core.reflection import Reflector
from .core.embedder import create_embedder


# Setup logging
setup_logging()
logger = get_logger("agent_runtime")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    settings = get_settings()

    logger.info(
        "agent_runtime_starting",
        version=settings.app_version,
        environment=settings.environment,
    )

    # Initialize embedder (OpenAI with local fallback)
    embedder = create_embedder(
        provider="auto",
        openai_key=settings.llm.openai_api_key or None,
        local_model="all-MiniLM-L6-v2",
        cache_size=10000,
    )

    # Initialize memory service
    memory_service = MemoryService(embedder=embedder)

    # Initialize planner and reflector
    planner = Planner()
    reflector = Reflector()

    # Initialize LLM gateway
    llm_gateway = create_gateway(
        anthropic_key=settings.llm.anthropic_api_key or None,
        openai_key=settings.llm.openai_api_key or None,
        nvidia_key=settings.llm.nvidia_api_key or None,
    )

    # Initialize agent runtime with planner and reflector
    runtime = AgentRuntime(planner=planner, reflector=reflector)

    # Store in app state
    app.state.runtime = runtime
    app.state.memory_service = memory_service
    app.state.llm_gateway = llm_gateway
    app.state.planner = planner
    app.state.reflector = reflector

    logger.info("agent_runtime_ready")

    yield

    # Cleanup
    logger.info("agent_runtime_shutting_down")


# Create FastAPI app
app = FastAPI(
    title="RasoSpeak Agent Runtime",
    description="Autonomous Multi-Agent Cognitive Platform",
    version="3.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "agent-runtime",
        "version": "3.0.0",
    }


@app.get("/ready")
async def ready(app: FastAPI):
    """Readiness check."""
    runtime = app.state.runtime
    return {
        "ready": True,
        "stats": runtime.get_runtime_stats(),
    }


@app.post("/agents/execute")
async def execute_goal(
    goal_text: str,
    agent_type: str = "supervisor",
    user_id: str = "default",
    tenant_id: str = "default",
    app: FastAPI = None,
):
    """Execute a goal using an agent."""
    runtime = app.state.runtime

    goal = Goal.from_text(
        goal_text,
        user_id=user_id,
        tenant_id=tenant_id,
    )

    agent_type_enum = AgentType(agent_type.lower())

    response = await runtime.execute_goal_auto(
        goal=goal,
        tenant_id=tenant_id,
        user_id=user_id,
        agent_type=agent_type_enum,
    )

    return {
        "goal_id": goal.goal_id,
        "agent_id": response.agent_id,
        "state": response.state.value,
        "confidence": response.confidence,
        "reasoning": response.reasoning,
        "output": response.output,
        "actions_taken": len(response.actions_taken),
        "cycles": response.cycle_count,
        "duration_ms": response.duration_ms,
    }


@app.get("/agents")
async def list_agents(app: FastAPI):
    """List all registered agents."""
    runtime = app.state.runtime
    return {
        "agents": runtime.get_runtime_stats(),
        "tools": runtime.tool_registry.list_tools(),
    }


@app.get("/metrics")
async def metrics(app: FastAPI):
    """Get runtime metrics."""
    runtime = app.state.runtime
    llm_gateway = app.state.llm_gateway

    return {
        "agent_runtime": runtime.get_runtime_stats(),
        "llm_gateway": llm_gateway.get_metrics(),
    }


def main():
    """Main entry point."""
    uvicorn.run(
        "services.agent_runtime.src.main:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
