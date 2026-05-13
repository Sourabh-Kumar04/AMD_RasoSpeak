# RasoSpeak AI OS — Complete Example Execution Flow

## User Request

**"Hey Raso, help me prepare for my ML interview next month."**

---

## Step-by-Step Execution

### 1. Wake Word Detection

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Audio Stream → WakeWordAgent → "Hey Raso" Detected                    │
└─────────────────────────────────────────────────────────────────────────┘

Event:
{
  "type": "wake_word",
  "agent": "wake_word",
  "timestamp": "2026-05-12T10:00:00.000Z",
  "confidence": 0.97,
  "user_id": "user_abc123"
}

System:
- Wake word detected via Web Speech API / Silero VAD
- Audio chunk sent to STT service
- Text extracted: "help me prepare for my ML interview next month"
- Request routed to API Gateway
```

---

### 2. API Gateway Reception

```
┌─────────────────────────────────────────────────────────────────────────┐
│  API Gateway                                                            │
│  ├── JWT Authentication (verify token)                                  │
│  ├── Rate Limiting (check user quota)                                  │
│  ├── Prompt Injection Detection                                         │
│  └── Route to Agent Runtime                                            │
└─────────────────────────────────────────────────────────────────────────┘

Processing:
1. Extract user_id from JWT: "user_abc123"
2. Extract tenant_id from JWT: "tenant_xyz"
3. Check rate limit: 60 req/min (current: 12) ✓
4. Scan for prompt injection: "help me prepare" → Clean ✓
5. Store user message in Working Memory (Redis)
6. Emit event to NATS: user.message.received
```

---

### 3. Supervisor Agent Activation

```
┌─────────────────────────────────────────────────────────────────────────┐
│  SupervisorAgent activated                                              │
│                                                                          │
│  State: IDLE → PLANNING                                                 │
│                                                                          │
│  Input: {                                                               │
│    "goal": "Help me prepare for my ML interview next month",            │
│    "user_id": "user_abc123",                                           │
│    "tenant_id": "tenant_xyz"                                           │
│  }                                                                      │
└─────────────────────────────────────────────────────────────────────────┘

Supervisor thinks:
┌─────────────────────────────────────────────────────────────────────────┐
│  CHAIN OF THOUGHT:                                                       │
│                                                                          │
│  Goal: ML interview preparation (complex, multi-step)                     │
│                                                                          │
│  Required capabilities:                                                  │
│  1. Memory retrieval (assess current level)                              │
│  2. Research (find ML interview patterns)                                │
│  3. Planning (create study schedule)                                     │
│  4. Coaching (schedule practice sessions)                                │
│  5. Notifications (follow-up reminders)                                 │
│                                                                          │
│  Delegation strategy:                                                    │
│  → Parallel: MemoryAgent + ResearcherAgent                              │
│  → Sequential: PlannerAgent (after memory + research)                    │
│  → Parallel: CoachingAgent + NotificationAgent                          │
│                                                                          │
│  Estimated duration: 30 days                                             │
│  Priority: HIGH                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 4. Parallel Agent Delegation

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    PARALLEL DELEGATION                                   │
│                                                                          │
│  ┌─────────────────────┐  ┌─────────────────────┐                       │
│  │   MemoryAgent       │  │  ResearcherAgent    │                       │
│  │                     │  │                     │                       │
│  │ Query: "ML skills, │  │ Query: "ML engineer  │                       │
│  │  interview history, │  │  interview topics,   │                       │
│  │  weak areas"        │  │  common questions"   │                       │
│  │                     │  │                     │                       │
│  │ State: EXECUTING    │  │  State: EXECUTING    │                       │
│  └──────────┬──────────┘  └──────────┬──────────┘                       │
│             │                        │                                   │
│             ▼                        ▼                                   │
│  ┌─────────────────────────────────────────────────────┐               │
│  │                  MEMORY RETRIEVAL                    │               │
│  │                                                       │               │
│  │  Working Memory (Redis):                              │               │
│  │  - Last interview: 6 months ago                      │               │
│  │  - Topics studied: CNNs, RNNs, Transformers          │               │
│  │  - Weak areas: System Design, MLOps                  │               │
│  │                                                       │               │
│  │  Episodic Memory (PostgreSQL):                        │               │
│  │  - Past interview #1: Failed (system design)        │               │
│  │  - Past interview #2: Passed (coding)               │               │
│  │  - Learning style: hands-on practice                  │               │
│  │                                                       │               │
│  │  Semantic Memory (pgvector):                          │               │
│  │  - "ML engineer at tech company" (importance: 0.9)  │               │
│  │  - "Specializes in NLP" (importance: 0.7)           │               │
│  │                                                       │               │
│  │  Procedural Memory:                                   │               │
│  │  - "Interview prep strategy" (success_rate: 0.85)    │               │
│  │                                                       │               │
│  └─────────────────────────────────────────────────────┘               │
│             │                        │                                   │
│             ▼                        ▼                                   │
│  ┌─────────────────────┐  ┌─────────────────────┐                       │
│  │   RESULT:           │  │   RESULT:           │                       │
│  │   - Current level:  │  │   - 50 ML topics    │                       │
│  │     intermediate    │  │   - Top 10 questions│                       │
│  │   - Weak areas:     │  │   - Resources list │                       │
│  │     MLOps, System   │  │                     │                       │
│  │     Design          │  │                     │                       │
│  │   - Time: 10h/week  │  │                     │                       │
│  └──────────┬──────────┘  └──────────┬──────────┘                       │
└─────────────┼─────────────────────────┼─────────────────────────────────┘
              │                         │
              └───────────┬─────────────┘
                          ▼
```

---

### 5. Planner Agent — Task Decomposition

```
┌─────────────────────────────────────────────────────────────────────────┐
│  PlannerAgent                                                            │
│                                                                          │
│  State: PLANNING → EXECUTING                                             │
│                                                                          │
│  Input received:                                                         │
│  - Memory context (weak areas, learning style)                           │
│  - Research data (topics, questions)                                      │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  TASK DECOMPOSITION                                               │   │
│  │                                                                   │   │
│  │  ROOT GOAL: "ML Interview Prep (30 days)"                       │   │
│  │                                                                   │   │
│  │  ├── WEEK 1: Fundamentals Deep Dive                             │   │
│  │  │   ├── Day 1-2: Transformers & Attention (weak)              │   │
│  │  │   │       → Self-attention mechanism                        │   │
│  │  │   │       → Multi-head attention                             │   │
│  │  │   │       → BERT, GPT architectures                         │   │
│  │  │   ├── Day 3-4: CNNs & Computer Vision                        │   │
│  │  │   └── Day 5-7: Practice + Week 1 Review                      │   │
│  │  │                                                              │   │
│  │  ├── WEEK 2: ML Systems & MLOps (weak)                        │   │
│  │  │   ├── Day 8-10: Training Pipelines, MLflow                  │   │
│  │  │   ├── Day 11-12: System Design                              │   │
│  │  │   └── Day 13-14: Week 2 Review + Mock Interview #0          │   │
│  │  │                                                              │   │
│  │  ├── WEEK 3: Advanced + Coding                                 │   │
│  │  │   ├── Day 15-18: Advanced Architectures                    │   │
│  │  │   └── Day 19-21: LeetCode + Pair Coding                      │   │
│  │  │                                                              │   │
│  │  └── WEEK 4: Mock Interviews + Company Prep                     │   │
│  │      ├── Day 22-25: 3 Mock Interviews                          │   │
│  │      └── Day 26-30: Company-Specific + Final Review             │   │
│  │                                                                   │   │
│  │  METRICS:                                                         │   │
│  │  - Total tasks: 47                                               │   │
│  │  - Total hours: 40 (10h/week budget)                           │   │
│  │  - Critical path: Day 1 → Day 30                                 │   │
│  │  - Dependencies: Sequential within weeks, parallel across      │   │
│  │                                                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 6. Temporal Workflow — Durable Execution

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Temporal Workflow Engine                                                │
│                                                                          │
│  Workflow: interview_prep_v1                                              │
│  WorkflowID: wf_user123_interview_20260512                               │
│  RunID: 7a8b9c0d-e1f2-3456-7890-abcd12345678                             │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  STEP 1: InitializeState                                         │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │ Activity: store_memory                                     │  │   │
│  │  │ Input: {user_id, workflow: "interview_prep", step: 0}    │  │   │
│  │  │ Result: {checkpoint_id: "ckpt_001"}                       │  │   │
│  │  │ Retry: Attempt 1/3 ✓                                     │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  │                                                               │   │
│  │  STEP 2: AssessMLLevel                                         │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │ Activity: llm_call                                         │  │   │
│  │  │ Input: {prompt: "Assess ML skills for: tech company...",   │  │   │
│  │  │         model: "claude-3-5-sonnet"}                       │  │   │
│  │  │ Result: {level: "intermediate", weak_areas: [...]}       │  │   │
│  │  │ Tokens: 1200 | Latency: 1.2s | Cost: $0.02              │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  │                                                               │   │
│  │  STEP 3: CreateStudyPlan (PARALLEL with Step 4)              │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │ Activity: llm_call                                         │  │   │
│  │  │ Input: {prompt: "Create study plan...", assessment}        │  │   │
│  │  │ Result: {plan_id: "plan_xyz789", sessions: [...]}          │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  │                                                               │   │
│  │  STEP 4: ResearchMLTopics                                     │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │ Activity: search_web (parallel)                            │  │   │
│  │  │ Input: {queries: ["ML interview topics", ...]}            │  │   │
│  │  │ Result: {topics: [...], questions: [...]}                  │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  │                                                               │   │
│  │  STEP 5: ScheduleCoachingSessions (PARALLEL)                 │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │ Activity: schedule_task (6x)                              │  │   │
│  │  │                                                           │  │   │
│  │  │ Session 1: Day 2 @ 9:00 AM - Transformers Deep Dive     │  │   │
│  │  │ Session 2: Day 7 @ 2:00 PM - Week 1 Review               │  │   │
│  │  │ Session 3: Day 14 @ 10:00 AM - MLOps Practice            │  │   │
│  │  │ Session 4: Day 21 @ 3:00 PM - Mock Interview #1         │  │   │
│  │  │ Session 5: Day 25 @ 11:00 AM - Mock Interview #2         │  │   │
│  │  │ Session 6: Day 28 @ 9:00 AM - Final Review               │  │   │
│  │  │                                                           │  │   │
│  │  │ Result: {scheduled: 6, failed: 0}                        │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  │                                                               │   │
│  │  STEP 6: SetupProgressTracking                                 │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │ Activity: setup_monitoring                               │  │   │
│  │  │ Input: {plan_id, metrics: [daily_study_time, ...]}       │  │   │
│  │  │ Result: {monitor_id: "mon_123"}                           │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  │                                                               │   │
│  │  STEP 7: SendWelcomeNotification                              │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │ Activity: send_notification                              │  │   │
│  │  │ Input: {user_id, channel: "push", message: "..."}         │  │   │
│  │  │ Result: {notification_id: "notif_456"}                   │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  │                                                               │   │
│  │  STEP 8: StartBackgroundMonitoring (Child Workflow)           │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │ WorkflowID: monitor_user123_planxyz                      │  │   │
│  │  │ Runs: Daily check-in loop (30 days)                      │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  DURABILITY:                                                             │
│  - All state persisted to Cassandra                                      │
│  - If server crashes, workflow resumes from last checkpoint               │
│  - Activities retry automatically on failure                              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 7. Memory Consolidation

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Memory Service — Consolidation Pipeline                                   │
│                                                                          │
│  1. WORKING → EPISODIC                                                   │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ Episode: "ML Interview Prep Initiation"                          │  │
│  │ {                                                                 │  │
│  │   type: "goal_creation",                                         │  │
│  │   goal: "Prepare for ML interview",                              │  │
│  │   timeline: "30 days",                                           │  │
│  │   sessions_scheduled: 6,                                        │  │
│  │   plan_id: "plan_xyz789",                                        │  │
│  │   created_at: "2026-05-12T10:00:30Z"                            │  │
│  │ }                                                                 │  │
│  │ Importance: 0.9 (high priority goal)                             │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  2. EPISODIC → SEMANTIC (fact extraction)                                │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ Facts Extracted:                                                  │  │
│  │ - "User is preparing for ML engineer interview" (conf: 0.95)    │  │
│  │ - "Weak in: Transformers, MLOps" (conf: 0.90)                   │  │
│  │ - "Prefers hands-on learning" (conf: 0.85)                     │  │
│  │ - "Has 10 hours per week" (conf: 0.95)                          │  │
│  │ - "Past 3 interviews, 1 offer" (conf: 0.90)                    │  │
│  │                                                                   │  │
│  │ Knowledge Graph Updates:                                           │  │
│  │ - Node: "ML Interview Prep" (type: goal, importance: 0.9)      │  │
│  │ - Node: "Transformers" (type: topic, importance: 0.8)           │  │
│  │ - Node: "MLOps" (type: topic, importance: 0.8)                 │  │
│  │ - Edge: "USER → studies → ML Interview Prep"                   │  │
│  │ - Edge: "ML Interview Prep → includes → Transformers"          │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  3. PROCEDURAL UPDATE                                                     │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ Procedure: "ML Interview Prep Strategy"                         │  │
│  │ {                                                                 │  │
│  │   trigger: {goal_type: "interview_prep"},                       │  │
│  │   steps: [assess, research, plan, schedule, track],             │  │
│  │   success_rate: 1.0,  // First execution                         │  │
│  │   usage_count: 1                                                 │  │
│  │ }                                                                 │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 8. Background Monitoring (Child Workflow)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  MonitorProgressWorkflow — Running in Background                         │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Day 2 @ 8:30 AM                                                 │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │ NOTIFICATION: "Your Transformers session starts in 30 min!" │  │   │
│  │  │                                                             │  │   │
│  │  │ Topics covered:                                             │  │   │
│  │  │ • Attention mechanism                                       │  │   │
│  │  │ • Self-attention vs multi-head attention                    │  │   │
│  │  │ • Transformer architecture                                  │  │   │
│  │  │                                                             │  │   │
│  │  │ Prerequisites: Bring questions about BERT/GPT!             │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Day 2 @ 11:00 AM (After Session)                                │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │ MEMORY UPDATE:                                            │  │   │
│  │  │                                                           │  │   │
│  │  │ Episodic: Session "Transformers Deep Dive" completed     │  │   │
│  │  │ - Duration: 90 minutes                                   │  │   │
│  │  │ - Score: 8/10                                           │  │   │
│  │  │ - Notes: "Good understanding of attention, need more    │  │   │
│  │  │   practice with scaled dot-product"                      │  │   │
│  │  │                                                           │  │   │
│  │  │ Semantic Update:                                          │  │   │
│  │  │ - Confidence in Transformers: 0.65 → 0.78                │  │   │
│  │  │                                                           │  │   │
│  │  │ Analytics:                                                │  │   │
│  │  │ - Progress: 5% (1/20 days)                              │  │   │
│  │  │ - Status: ON TRACK                                        │  │   │
│  │  │ - Next: CNNs on Day 3                                    │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Day 3 @ 9:00 AM                                                 │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │ PROACTIVE SUGGESTION:                                    │  │   │
│  │  │                                                           │  │   │
│  │  │ "I noticed you studied CNNs yesterday. Based on your    │  │   │
│  │  │  weak areas, I recommend adding an extra session on     │  │   │
│  │  │  Object Detection before the interview. Want me to        │  │   │
│  │  │  schedule it?"                                           │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 9. Agent Reflection

```
┌─────────────────────────────────────────────────────────────────────────┐
│  CriticAgent — Post-Execution Reflection                                 │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  EVALUATION:                                                     │   │
│  │                                                                   │   │
│  │  Strengths:                                                       │   │
│  │  ✓ Correctly identified weak areas from assessment               │   │
│  │  ✓ Balanced schedule within 10h/week budget                      │   │
│  │  ✓ Scheduled realistic number of coaching sessions                │   │
│  │  ✓ Used past interview data to personalize plan                   │   │
│  │                                                                   │   │
│  │  Improvements for Next Time:                                       │   │
│  │  - Could have asked about specific companies sooner              │   │
│  │  - Should include resume/CV review in plan                       │   │
│  │  - Consider adding behavioral prep earlier                        │   │
│  │                                                                   │   │
│  │  Confidence Score: 0.92 (high)                                   │   │
│  │                                                                   │   │
│  │  Learning:                                                        │   │
│  │  - Update "interview prep" procedure success rate: 0.85 → 0.92   │   │
│  │  - Add trigger condition: "company_type: tech" → extra research │   │
│  │                                                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 10. Final Response to User

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│  "Got it! I've created a 30-day ML Interview Prep plan for you.        │
│                                                                          │
│   🎯 Your Focus Areas:
│   • Transformers & Attention (your weak area)
│   • MLOps & System Design
│   • Coding Practice
│                                                                          │
│   📅 6 Coaching Sessions Scheduled:
│   • Day 2: Transformers Deep Dive ← Starting soon!
│   • Day 7: Week 1 Review
│   • Day 14: MLOps Practice
│   • Day 21: Mock Interview #1
│   • Day 25: Mock Interview #2
│   • Day 28: Mock Interview #3 + Final Review
│                                                                          │
│   ⏱️ 47 Topics · 40 Hours Total · 10h/week
│                                                                          │
│   I'll send you daily reminders and track your progress!
│                                                                          │
│   Confidence: 92%
│   Plan ID: plan_xyz789
│   Status: ACTIVE"                                                        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 11. Observability Output

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Metrics Captured:                                                      │
│                                                                          │
│  LLM Calls:                                                             │
│  - AssessMLLevel: 1200 tokens, 1.2s, $0.02                            │
│  - CreateStudyPlan: 800 tokens, 0.9s, $0.015                          │
│                                                                          │
│  Agent Execution:                                                        │
│  - SupervisorAgent: 3 cycles, 4.5s total                               │
│  - PlannerAgent: 1 cycle, 2.1s                                         │
│  - MemoryAgent: 1 cycle, 0.8s                                          │
│  - ResearcherAgent: 1 cycle, 1.2s                                     │
│                                                                          │
│  Tool Executions:                                                       │
│  - llm_call: 2 (100% success)                                          │
│  - schedule_task: 6 (100% success)                                     │
│  - send_notification: 1 (100% success)                                 │
│                                                                          │
│  Memory Operations:                                                      │
│  - Working memory writes: 3                                             │
│  - Episodic memory writes: 1                                            │
│  - Semantic memory writes: 5 facts extracted                            │
│  - Knowledge graph updates: 5 nodes, 2 edges                             │
│                                                                          │
│  Workflow:                                                               │
│  - interview_prep_v1: COMPLETED                                         │
│  - monitor_user123_planxyz: RUNNING                                     │
│                                                                          │
│  Total Cost: $0.035                                                     │
│  Total Latency: 6.8s                                                    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Summary

This execution demonstrates the full power of a true agentic AI system:

1. **Wake word detection** → Triggers entire system
2. **Supervisor orchestration** → Decomposes goal, delegates
3. **Parallel execution** → Memory + Research run simultaneously
4. **Durable workflows** → Temporal ensures completion even on failure
5. **Hierarchical memory** → Working → Episodic → Semantic → Procedural
6. **Background monitoring** → Child workflow runs daily check-ins
7. **Proactive suggestions** → Agent identifies opportunities
8. **Self-improvement** → Reflection updates procedures
9. **Full observability** → Every step tracked and measured

**This is NOT a prompt wrapper. This is an autonomous AI operating system.**
