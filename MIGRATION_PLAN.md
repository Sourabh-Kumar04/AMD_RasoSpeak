# RasoSpeak v3 — Migration Plan

## Overview

Transform RasoSpeak from a hackathon prototype to a production-grade autonomous AI operating system using a 5-phase migration strategy.

---

## Phase 1: Stabilization (Weeks 1-4)

### Goal: Fix critical issues, establish foundations

### Tasks

#### 1.1 Remove Global Mutable State
```
BEFORE:
  # api/state.py
  agents: dict[str, Any] = {}  # Global mutable state

AFTER:
  # Dependency injection via FastAPI Depends()
  # Each request gets fresh agent instances
```

#### 1.2 Migrate JSON Persistence to PostgreSQL
```
BEFORE:
  memory/conversations.json
  memory/facts.json
  memory/profile.json

AFTER:
  PostgreSQL tables with:
  - Full-text search (pg_trgm)
  - Vector embeddings (pgvector)
  - Row-level security
  - Automated backups
```

#### 1.3 Add Circuit Breakers
```python
# Before: Direct LLM call, no error handling
response = await llm.complete(messages)

# After: Circuit breaker with retry
circuit_breaker = CircuitBreaker(
    name="llm_provider",
    failure_threshold=5,
    timeout_seconds=30,
)

result = await circuit_breaker.call(
    lambda: llm.complete(messages)
)
```

#### 1.4 Add Structured Logging
```python
# Before
logging.info("Request processed")

# After
structlog.get_logger().info(
    "request_processed",
    user_id="abc123",
    latency_ms=150,
    tokens=500,
)
```

### Deliverables
- [ ] PostgreSQL schema deployed
- [ ] Migration scripts for existing data
- [ ] Health and readiness endpoints
- [ ] Basic Prometheus metrics
- [ ] Alerting for critical errors

### Migration Risks
- **Data loss**: Back up JSON files before migration
- **Downtime**: Run migration during low-traffic window
- **Schema conflicts**: Run parallel schema validation

---

## Phase 2: Infrastructure (Weeks 5-8)

### Goal: Deploy production-grade infrastructure

### Tasks

#### 2.1 Deploy Kubernetes Cluster
- EKS/GKE cluster with autoscaling
- Node pools: general, memory-optimized, GPU
- Network policies for tenant isolation

#### 2.2 Deploy Temporal
```yaml
# temporal-cluster.yaml
apiVersion: temporal.io/v1beta1
kind: TemporalCluster
metadata:
  name: rasospeak-temporal
spec:
  version: 1.23.0
  numHistoryShards: 4
  ui:
    enabled: true
  cassandra:
    enabled: true
    storage: 200Gi
```

#### 2.3 Deploy NATS JetStream
```yaml
# nats-cluster.yaml
apiVersion: nats.io/v1alpha2
kind: NatsCluster
metadata:
  name: rasospeak-nats
spec:
  size: 3
  pod:
    enabled: true
  jetstream:
    enabled: true
    fileStorage:
      size: 50Gi
```

#### 2.4 Deploy Qdrant
```yaml
# qdrant-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: qdrant
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: qdrant
          image: qdrant/qdrant:v1.7.4
          resources:
            limits:
              memory: 8Gi
```

#### 2.5 CI/CD Pipeline
```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: pytest tests/ -v --cov

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Build Docker images
        run: |
          docker build -t $ECR_REGISTRY/agent-runtime:$GITHUB_SHA .
          docker push $ECR_REGISTRY/agent-runtime:$GITHUB_SHA

  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to EKS
        run: |
          kubectl set image deployment/agent-runtime \
            agent-runtime=$ECR_REGISTRY/agent-runtime:$GITHUB_SHA
```

### Deliverables
- [ ] Kubernetes cluster running
- [ ] All services containerized
- [ ] CI/CD pipeline configured
- [ ] Staging environment deployed

---

## Phase 3: Real Agent Runtime (Weeks 9-16)

### Goal: Implement true multi-agent cognition

### Tasks

#### 3.1 Implement Base Agent Class
```python
# BEFORE: Prompt wrapper
class CoachingAgent:
    async def generate_feedback(self, transcript):
        messages = [{"role": "user", "content": f"Feedback: {transcript}"}]
        return await llm.complete(messages)

# AFTER: Real autonomous agent
class BaseAgent:
    async def plan(self, context: ExecutionContext) -> list[TaskNode]:
        # Real task decomposition
        pass

    async def execute_task(self, task: TaskNode, context) -> Any:
        # Tool execution with retry
        pass

    async def verify(self, output: Any, goal: Goal) -> tuple[bool, str]:
        # Output verification
        pass

    async def reflect(self, context, output) -> dict:
        # Self-evaluation
        pass
```

#### 3.2 Implement Cognition Loop
```python
async def run_cognition_loop(self, goal: Goal) -> AgentResponse:
    for cycle in range(max_retries):
        # 1. Plan
        tasks = await self.plan(context)

        # 2. Execute
        for task in tasks:
            await self.execute_task(task, context)

        # 3. Verify
        verified, msg = await self.verify(output, goal)
        if verified:
            break

        # 4. Reflect
        reflection = await self.reflect(context, output)
        context.confidence *= reflection.get("confidence_multiplier", 0.9)
```

#### 3.3 Implement Tool Registry
```python
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    async def execute(self, tool_name, params, context) -> ToolCall:
        tool = self._tools.get(tool_name)
        return await tool.execute(params, context)

# Register built-in tools
registry.register(SearchTool())
registry.register(MemoryRetrieveTool())
registry.register(ScheduleTaskTool())
registry.register(NotificationTool())
```

#### 3.4 Implement Memory Hierarchy
```python
class MemoryService:
    def __init__(self):
        self.working = WorkingMemory(redis)    # Redis
        self.episodic = EpisodicMemory(db)     # PostgreSQL
        self.semantic = SemanticMemory(db)    # PostgreSQL + pgvector
        self.procedural = ProceduralMemory(db) # PostgreSQL
        self.knowledge = KnowledgeGraph(db)   # PostgreSQL
```

#### 3.5 Implement Durable Workflows
```python
@workflow.defn
class InterviewPrepWorkflow:
    @workflow.run
    async def run(self, user_id, job_description):
        # All steps are durable
        assessment = await workflow.execute_activity(
            AssessMLLevel,
            user_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3)
        )

        plan = await workflow.execute_activity(
            CreateStudyPlan,
            PlanInput(user_id=user_id, assessment=assessment)
        )

        # Schedule coaching sessions
        for date, topics in plan.sessions:
            await workflow.execute_activity(
                ScheduleCoachingSession,
                ScheduleInput(user_id=user_id, date=date, topics=topics)
            )

        return PrepResult(plan_id=plan.id, sessions=len(plan.sessions))
```

### Deliverables
- [ ] Working agents: Supervisor, Planner, Researcher, Coach, Critic
- [ ] Durable workflows execute correctly
- [ ] Memory retrieval < 100ms
- [ ] Tool execution with retry

---

## Phase 4: Distributed Cognition (Weeks 17-24)

### Goal: Scale to multi-agent, multi-user

### Tasks

#### 4.1 Multi-Agent Coordination
```python
class SupervisorAgent(BaseAgent):
    async def plan(self, context):
        # Analyze goal and delegate to sub-agents
        if "interview" in goal:
            return [
                TaskNode(agent_type=AgentType.RESEARCHER, ...),
                TaskNode(agent_type=AgentType.PLANNER, depends_on=["researcher"]),
                TaskNode(agent_type=AgentType.COACH, depends_on=["planner"]),
            ]

    async def execute_task(self, task, context):
        # Create sub-agent and delegate
        agent = await agent_factory.create(task.agent_type, ...)
        return await agent.run(task.to_goal())
```

#### 4.2 Tenant Isolation
```sql
-- Row-level security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON users
    USING (tenant_id = current_setting('app.tenant_id')::UUID);
```

#### 4.3 AI Safety Layer
```python
class PromptInjectionDetector:
    PATTERNS = [
        r"ignore\s+(previous|all)\s+instructions",
        r"forget\s+everything",
        r"<\|system\|>|<\|user\|>",
    ]

    async def detect(self, text) -> tuple[bool, list]:
        # Multi-pattern detection
        matches = []
        for pattern in self.PATTERNS:
            found = re.findall(pattern, text)
            if found:
                matches.append({"pattern": pattern, "match": found[0]})

        return len(matches) > 0, matches
```

#### 4.4 AI Observability (Langfuse)
```python
from langfuse import Langfuse

langfuse = Langfuse()

@observe(asr="llm_call")
async def llm_call(messages, user_id):
    trace = langfuse.trace(
        name="llm_completion",
        user_id=user_id,
        input=messages[-1]["content"]
    )

    result = await llm.complete(messages)

    trace.log(
        output=result.content,
        metadata={
            "model": result.model,
            "tokens": result.usage.total_tokens,
            "latency_ms": result.latency_ms,
        }
    )

    return result
```

### Deliverables
- [ ] Multi-tenant deployment
- [ ] Comprehensive AI telemetry
- [ ] Security hardening
- [ ] Performance optimization

---

## Phase 5: Autonomous Intelligence (Weeks 25-32)

### Goal: Full autonomous operation

### Tasks

#### 5.1 Self-Improvement Loop
```python
class SelfImprovementAgent(BaseAgent):
    async def reflect(self, context, output):
        # Learn from outcomes
        if output.get("success"):
            # Update success rate
            await procedural_memory.update_stats(
                procedure_id=context.goal.goal_id,
                success=True
            )

        # Extract new patterns
        patterns = await self._extract_patterns(output)
        for pattern in patterns:
            await procedural_memory.store(pattern)

        return {
            "confidence_multiplier": 0.95,
            "learning": patterns
        }
```

#### 5.2 Proactive Behavior
```python
@workflow.defn
class ProactiveMonitoringWorkflow:
    @workflow.run
    async def run(self, user_id):
        while True:
            # Check user state
            progress = await workflow.execute_activity(
                CheckProgress,
                user_id,
                start_to_close_timeout=timedelta(minutes=1)
            )

            # If behind schedule, send reminder
            if progress.days_behind > 1:
                await workflow.execute_activity(
                    SendReminder,
                    ReminderInput(user_id=user_id, urgency="high")
                )

            # If on track, send encouragement
            elif progress.days_ahead > 2:
                await workflow.execute_activity(
                    SendEncouragement,
                    EncouragementInput(user_id=user_id)
                )

            # Wait until next check
            await asyncio.sleep(86400)  # Daily
```

#### 5.3 Advanced RAG
```python
class HybridRAG:
    async def retrieve(self, query, user_id):
        # Dense vector search
        dense_results = await self.vector_db.search(
            embedding=query,
            limit=20,
        )

        # Sparse BM25 search
        sparse_results = await self.bm25.search(
            query=query,
            limit=20,
        )

        # Rerank with cross-encoder
        combined = self.reranker.combine(dense_results, sparse_results)
        reranked = await self.reranker.rerank(query, combined, limit=10)

        return reranked
```

### Deliverables
- [ ] Truly autonomous agent behavior
- [ ] Self-improving system
- [ ] Production-ready at scale

---

## Migration Rollback Strategy

```yaml
# rollback.yml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-runtime
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    spec:
      containers:
        - name: agent-runtime
          image: $OLD_IMAGE_TAG  # Previous known good
```

### Rollback Triggers
- Error rate > 5% increase
- Latency > 2x baseline
- Critical user-facing bugs

---

## Success Metrics

| Phase | Metric | Target |
|-------|--------|--------|
| 1 | JSON migration complete | 100% |
| 1 | Error rate | < 1% |
| 2 | Deployment success rate | > 99% |
| 2 | Infrastructure costs | Within budget |
| 3 | Agent execution time | < 5s (P95) |
| 3 | Tool retry success | > 90% |
| 4 | Multi-tenant isolation | 100% |
| 4 | AI telemetry coverage | > 95% |
| 5 | Autonomous task completion | > 80% |
| 5 | Self-improvement rate | Measurable |

---

## Resource Requirements

| Phase | Engineers | Timeline | Infrastructure |
|-------|-----------|----------|----------------|
| 1 | 2 | 4 weeks | $10K/month |
| 2 | 3 | 4 weeks | $30K/month |
| 3 | 4 | 8 weeks | $50K/month |
| 4 | 3 | 8 weeks | $80K/month |
| 5 | 2 | 8 weeks | $100K/month |

**Total**: 14 engineers, 32 weeks, ~$2M infrastructure
