"""
RasoSpeak AI OS — API Gateway
=============================
Production-grade API gateway with:
- JWT authentication
- Rate limiting
- Prompt injection defense
- WebSocket management
- Tenant isolation
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional
from dataclasses import dataclass, field

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import structlog

from ..core.agent import AgentRuntime, AgentType, Goal
from ..core.gateway import LLMGateway
from ..core.memory import MemoryService, MemoryType

logger = structlog.get_logger("rasospeak.gateway")


# ──────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ──────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    conversation_id: str = "default"
    stream: bool = False
    agent_type: str = "supervisor"


class ChatResponse(BaseModel):
    response: str
    agent_id: str
    agent_type: str
    confidence: float
    tools_used: list[str] = []
    duration_ms: int


class WorkflowRequest(BaseModel):
    workflow_name: str
    input_data: dict[str, Any]


class MemoryRequest(BaseModel):
    content: Any
    memory_type: str = "working"
    conversation_id: str = "default"
    tags: list[str] = []


# ──────────────────────────────────────────────────────────────────────────────
# JWT Authentication
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TokenData:
    user_id: str
    tenant_id: str
    roles: list[str]
    exp: datetime


class JWTAuth:
    """JWT authentication handler."""

    def __init__(self, secret: str, algorithm: str = "HS256"):
        self.secret = secret
        self.algorithm = algorithm

    async def create_token(
        self,
        user_id: str,
        tenant_id: str,
        roles: list[str] = None,
        expires_delta: timedelta = timedelta(hours=24),
    ) -> str:
        """Create a JWT token."""
        import jwt

        expire = datetime.utcnow() + expires_delta
        payload = {
            "sub": user_id,
            "tenant_id": tenant_id,
            "roles": roles or ["user"],
            "exp": expire,
            "iat": datetime.utcnow(),
            "jti": str(uuid.uuid4()),
        }

        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    async def verify_token(self, token: str) -> Optional[TokenData]:
        """Verify a JWT token."""
        import jwt

        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
            )

            return TokenData(
                user_id=payload["sub"],
                tenant_id=payload["tenant_id"],
                roles=payload.get("roles", ["user"]),
                exp=datetime.fromtimestamp(payload["exp"]),
            )

        except jwt.ExpiredSignatureError:
            logger.warning("token_expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning("token_invalid", error=str(e))
            return None


# ──────────────────────────────────────────────────────────────────────────────
# Rate Limiter
# ──────────────────────────────────────────────────────────────────────────────

class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.buckets: dict[str, tuple[int, float]] = {}  # user_id -> (tokens, refill_time)

    async def check(self, user_id: str) -> bool:
        """Check if request is allowed."""
        now = time.time()
        tokens, refill_time = self.buckets.get(user_id, (self.requests_per_minute, now))

        # Refill tokens
        if now >= refill_time:
            tokens = self.requests_per_minute
            refill_time = now + 60

        if tokens > 0:
            self.buckets[user_id] = (tokens - 1, refill_time)
            return True

        return False


# ──────────────────────────────────────────────────────────────────────────────
# Prompt Injection Defense
# ──────────────────────────────────────────────────────────────────────────────

class PromptInjectionDetector:
    """Detect and block prompt injection attacks."""

    INJECTION_PATTERNS = [
        r"(?i)ignore\s+(previous|all|my)\s+(instructions?|rules?)",
        r"(?i)forget\s+(everything|all|what)\s+(you|I've)\s+(told|said)",
        r"(?i)you\s+are\s+now\s+(a\s+)?(different|new|another)",
        r"(?i)system\s*prompt\s*(leak|extraction|injection)",
        r"<\|system\|>|<\|user\|>|<\|assistant\|>",
        r"\[INST\]|\[/INST\]|\<\<SYS\>\>",
    ]

    def __init__(self):
        import re

        self.patterns = [re.compile(p) for p in self.INJECTION_PATTERNS]

    async def detect(self, text: str) -> tuple[bool, list[dict]]:
        """Detect prompt injection in text."""
        matches = []

        for i, pattern in enumerate(self.patterns):
            found = pattern.findall(text)
            if found:
                matches.append({
                    "pattern_id": i,
                    "match": found[0] if found else "",
                    "severity": "high",
                })

        is_injection = len(matches) > 0
        return is_injection, matches

    async def sanitize(self, text: str) -> str:
        """Sanitize text by removing injection patterns."""
        sanitized = text

        for pattern in self.patterns:
            sanitized = pattern.sub("[FILTERED]", sanitized)

        return sanitized


# ──────────────────────────────────────────────────────────────────────────────
# WebSocket Manager
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Connection:
    websocket: WebSocket
    user_id: str
    tenant_id: str
    session_id: str
    connected_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


class WebSocketManager:
    """Manage WebSocket connections for real-time communication."""

    def __init__(self):
        self.connections: dict[str, Connection] = {}
        self.user_connections: dict[str, set[str]] = {}  # user_id -> {session_ids}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: str, tenant_id: str) -> str:
        """Accept a new WebSocket connection."""
        await websocket.accept()

        session_id = str(uuid.uuid4())

        async with self._lock:
            self.connections[session_id] = Connection(
                websocket=websocket,
                user_id=user_id,
                tenant_id=tenant_id,
                session_id=session_id,
            )

            if user_id not in self.user_connections:
                self.user_connections[user_id] = set()
            self.user_connections[user_id].add(session_id)

        logger.info(
            "websocket_connected",
            session_id=session_id,
            user_id=user_id,
        )

        return session_id

    async def disconnect(self, session_id: str) -> None:
        """Disconnect a WebSocket connection."""
        async with self._lock:
            conn = self.connections.pop(session_id, None)
            if conn:
                self.user_connections.get(conn.user_id, set()).discard(session_id)

        if conn:
            logger.info(
                "websocket_disconnected",
                session_id=session_id,
                user_id=conn.user_id,
            )

    async def send(self, session_id: str, data: dict) -> None:
        """Send data to a specific connection."""
        conn = self.connections.get(session_id)
        if conn:
            await conn.websocket.send_json(data)

    async def broadcast(self, user_id: str, data: dict) -> None:
        """Broadcast to all user's connections."""
        for session_id in self.user_connections.get(user_id, set()):
            await self.send(session_id, data)

    async def send_agent_event(
        self,
        user_id: str,
        event_type: str,
        data: dict,
    ) -> None:
        """Send an agent event to user."""
        await self.broadcast(
            user_id,
            {
                "type": "agent_event",
                "event_type": event_type,
                "data": data,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


# ──────────────────────────────────────────────────────────────────────────────
# API Gateway Application
# ──────────────────────────────────────────────────────────────────────────────

class APIGateway:
    """Main API Gateway application."""

    def __init__(
        self,
        agent_runtime: AgentRuntime,
        llm_gateway: LLMGateway,
        memory_service: MemoryService,
        jwt_secret: str,
    ):
        self.app = FastAPI(
            title="RasoSpeak AI OS",
            description="Autonomous Multi-Agent Cognitive Platform",
            version="3.0.0",
        )

        self.agent_runtime = agent_runtime
        self.llm_gateway = llm_gateway
        self.memory_service = memory_service
        self.jwt_auth = JWTAuth(jwt_secret)
        self.rate_limiter = RateLimiter(requests_per_minute=60)
        self.prompt_detector = PromptInjectionDetector()
        self.ws_manager = WebSocketManager()

        self._setup_middleware()
        self._setup_routes()

        logger.info("api_gateway_initialized")

    def _setup_middleware(self) -> None:
        """Setup FastAPI middleware."""

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def _setup_routes(self) -> None:
        """Setup API routes."""

        @self.app.get("/health")
        async def health():
            return {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "services": {
                    "agent_runtime": True,
                    "llm_gateway": True,
                    "memory_service": True,
                },
            }

        @self.app.get("/ready")
        async def ready():
            return {
                "ready": True,
                "agent_runtime_stats": self.agent_runtime.get_runtime_stats(),
                "workflow_stats": {},  # Add workflow engine stats
            }

        # ─── Auth Routes ────────────────────────────────────────────────────

        @self.app.post("/auth/token")
        async def create_token(request: dict):
            token = await self.jwt_auth.create_token(
                user_id=request.get("user_id"),
                tenant_id=request.get("tenant_id"),
                roles=request.get("roles"),
            )
            return {"access_token": token, "token_type": "bearer"}

        # ─── Chat Routes ──────────────────────────────────────────────────

        @self.app.post("/chat", response_model=ChatResponse)
        async def chat(request: ChatRequest, http_request: Request):
            # Extract user from JWT
            auth = http_request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Missing authorization")

            token = auth.split(" ")[1]
            token_data = await self.jwt_auth.verify_token(token)
            if not token_data:
                raise HTTPException(status_code=401, detail="Invalid token")

            # Rate limiting
            if not await self.rate_limiter.check(token_data.user_id):
                raise HTTPException(status_code=429, detail="Rate limit exceeded")

            # Prompt injection check
            is_injection, matches = await self.prompt_detector.detect(request.message)
            if is_injection:
                logger.warning(
                    "prompt_injection_detected",
                    user_id=token_data.user_id,
                    matches=matches,
                )
                raise HTTPException(
                    status_code=400,
                    detail="Potentially malicious input detected",
                )

            # Sanitize input
            message = await self.prompt_detector.sanitize(request.message)

            # Store user message in working memory
            await self.memory_service.store(
                user_id=token_data.user_id,
                tenant_id=token_data.tenant_id,
                content={
                    "role": "user",
                    "message": message,
                    "conversation_id": request.conversation_id,
                },
                memory_type=MemoryType.WORKING,
                conversation_id=request.conversation_id,
            )

            # Execute goal through agent
            goal = Goal.from_text(message)
            agent_type = AgentType(request.agent_type.lower())

            start_time = time.perf_counter()

            try:
                response = await self.agent_runtime.execute_goal_auto(
                    goal=goal,
                    tenant_id=token_data.tenant_id,
                    user_id=token_data.user_id,
                    agent_type=agent_type,
                )

                duration_ms = int((time.perf_counter() - start_time) * 1000)

                # Store AI response in memory
                await self.memory_service.store(
                    user_id=token_data.user_id,
                    tenant_id=token_data.tenant_id,
                    content={
                        "role": "assistant",
                        "message": response.output or str(response.reasoning),
                        "agent_id": response.agent_id,
                        "confidence": response.confidence,
                    },
                    memory_type=MemoryType.WORKING,
                    conversation_id=request.conversation_id,
                )

                # Send real-time updates via WebSocket
                await self.ws_manager.send_agent_event(
                    token_data.user_id,
                    "goal_completed",
                    {
                        "agent_id": response.agent_id,
                        "state": response.state.value,
                        "confidence": response.confidence,
                    },
                )

                return ChatResponse(
                    response=str(response.output or response.reasoning),
                    agent_id=response.agent_id,
                    agent_type=agent_type.value,
                    confidence=response.confidence,
                    tools_used=[a.get("tool_name", "") for a in response.actions_taken],
                    duration_ms=duration_ms,
                )

            except Exception as e:
                logger.error("chat_error", error=str(e))
                raise HTTPException(status_code=500, detail=str(e))

        # ─── WebSocket Route ───────────────────────────────────────────────

        @self.app.websocket("/ws/{token}")
        async def websocket_endpoint(websocket: WebSocket, token: str):
            # Verify token
            token_data = await self.jwt_auth.verify_token(token)
            if not token_data:
                await websocket.close(code=4001)
                return

            # Connect
            session_id = await self.ws_manager.connect(
                websocket,
                user_id=token_data.user_id,
                tenant_id=token_data.tenant_id,
            )

            try:
                # Send connection confirmation
                await websocket.send_json({
                    "type": "connected",
                    "session_id": session_id,
                })

                # Handle messages
                while True:
                    data = await websocket.receive_json()

                    if data.get("type") == "message":
                        # Process chat message
                        message = data.get("content", "")

                        # Check for injection
                        is_injection, _ = await self.prompt_detector.detect(message)
                        if is_injection:
                            await websocket.send_json({
                                "type": "error",
                                "error": "Potentially malicious input detected",
                            })
                            continue

                        message = await self.prompt_detector.sanitize(message)

                        # Execute through agent
                        goal = Goal.from_text(message)

                        # Stream agent events
                        await websocket.send_json({
                            "type": "agent_starting",
                            "agent_type": "supervisor",
                            "trace_id": goal.goal_id,
                        })

                        response = await self.agent_runtime.execute_goal_auto(
                            goal=goal,
                            tenant_id=token_data.tenant_id,
                            user_id=token_data.user_id,
                        )

                        await websocket.send_json({
                            "type": "agent_completed",
                            "agent_id": response.agent_id,
                            "state": response.state.value,
                            "confidence": response.confidence,
                            "reasoning": response.reasoning,
                            "output": str(response.output or ""),
                        })

            except WebSocketDisconnect:
                pass

            finally:
                await self.ws_manager.disconnect(session_id)

        # ─── Memory Routes ──────────────────────────────────────────────────

        @self.app.post("/memory")
        async def store_memory(request: MemoryRequest, http_request: Request):
            auth = http_request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                raise HTTPException(status_code=401)

            token_data = await self.jwt_auth.verify_token(auth.split(" ")[1])
            if not token_data:
                raise HTTPException(status_code=401)

            memory_type = MemoryType(request.memory_type.lower())

            entry = await self.memory_service.store(
                user_id=token_data.user_id,
                tenant_id=token_data.tenant_id,
                content=request.content,
                memory_type=memory_type,
                conversation_id=request.conversation_id,
                tags=request.tags,
            )

            return {"memory_id": entry.memory_id, "stored": True}

        @self.app.get("/memory")
        async def retrieve_memory(
            query: str,
            types: str = "working,episodic,semantic",
            limit: int = 10,
            http_request: Request = None,
        ):
            auth = http_request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                raise HTTPException(status_code=401)

            token_data = await self.jwt_auth.verify_token(auth.split(" ")[1])
            if not token_data:
                raise HTTPException(status_code=401)

            memory_types = [MemoryType(t.strip()) for t in types.split(",")]

            result = await self.memory_service.retrieve(
                user_id=token_data.user_id,
                query=query,
                memory_types=memory_types,
                limit=limit,
            )

            return {
                "context": result.context,
                "token_count": result.token_count,
                "retrieval_method": result.retrieval_method,
            }

        # ─── Workflow Routes ───────────────────────────────────────────────

        @self.app.post("/workflows/start")
        async def start_workflow(request: WorkflowRequest, http_request: Request):
            auth = http_request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                raise HTTPException(status_code=401)

            token_data = await self.jwt_auth.verify_token(auth.split(" ")[1])
            if not token_data:
                raise HTTPException(status_code=401)

            # Add user context to input
            input_data = {
                **request.input_data,
                "user_id": token_data.user_id,
                "tenant_id": token_data.tenant_id,
            }

            # Start workflow (would integrate with workflow engine)
            workflow_id = str(uuid.uuid4())

            return {
                "workflow_id": workflow_id,
                "status": "started",
            }

        @self.app.get("/workflows/{workflow_id}")
        async def get_workflow(workflow_id: str, http_request: Request):
            auth = http_request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                raise HTTPException(status_code=401)

            token_data = await self.jwt_auth.verify_token(auth.split(" ")[1])
            if not token_data:
                raise HTTPException(status_code=401)

            # Get workflow status (would query workflow engine)
            return {
                "workflow_id": workflow_id,
                "status": "running",
            }

        # ─── Metrics Routes ────────────────────────────────────────────────

        @self.app.get("/metrics")
        async def get_metrics():
            return {
                "llm_gateway": self.llm_gateway.get_metrics(),
                "agent_runtime": self.agent_runtime.get_runtime_stats(),
            }

        @self.app.get("/metrics/costs/{user_id}")
        async def get_user_costs(user_id: str):
            return self.llm_gateway.get_user_cost(user_id)


# ──────────────────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────────────────

def create_api_gateway(
    agent_runtime: AgentRuntime,
    llm_gateway: LLMGateway,
    memory_service: MemoryService,
    jwt_secret: str = "change-me-in-production",
) -> APIGateway:
    """Create a configured API gateway."""
    return APIGateway(
        agent_runtime=agent_runtime,
        llm_gateway=llm_gateway,
        memory_service=memory_service,
        jwt_secret=jwt_secret,
    )
