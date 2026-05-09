# RasoSpeak v2 — Agentic Architecture on AMD Developer Cloud
## Technical Deep-Dive for AMD Developer Hackathon (lablab.ai)

---

## 1. Why We Upgraded: The AMD Requirement

The AMD Developer Hackathon specifically requires projects to:

- Run AI workloads on **AMD Instinct MI300X GPUs** via AMD Developer Cloud
- Use **ROCm** (Radeon Open Compute) as the software stack
- Build **AI Agents & Agentic Workflows** — not just rule-based apps
- Demonstrate real model inference, not just browser Web APIs

**RasoSpeak v1 problem:** 100% browser-based, used Web Speech API + simple Levenshtein NLP.
No AMD GPU. No LLM. No agents. Would not qualify.

**RasoSpeak v2 solution:** Multi-agent backend running on AMD Developer Cloud,
with the browser as a thin UI client only.

---

## 2. The Old vs. New Architecture

### v1 — Browser-Only (Does NOT qualify)

```
Browser
├── Web Speech API  →  TTS (earpiece delivery)
├── Web Speech API  →  STT (speech capture)
├── Levenshtein NLP →  Word matching (rule-based)
└── Vanilla JS      →  All logic, all UI
```

Problems:
- No AMD GPU usage
- NLP is rule-based, not AI
- No agents
- Would not pass hackathon criteria

---

### v2 — Agentic on AMD (QUALIFIES)

```
Browser (thin client)
    │  WebSocket (real-time)
    ▼
FastAPI Backend  ←─── AMD Developer Cloud (MI300X GPU + ROCm)
    │
    ├── Agent 1: TranscriptionAgent   (Whisper Large v3 on ROCm)
    ├── Agent 2: ScoringAgent         (Qwen2.5-7B-Instruct on vLLM)
    ├── Agent 3: CoachingAgent        (Qwen2.5-7B-Instruct on vLLM)
    ├── Agent 4: SegmentationAgent    (Qwen2.5-3B on vLLM)
    └── Agent 5: SessionMemoryAgent   (State + history management)
```

Every inference call touches AMD hardware. Every coaching decision is LLM-generated.

---

## 3. The Five Agents — Detailed

### Agent 1: TranscriptionAgent 🎙
**Model:** OpenAI Whisper Large v3
**Runtime:** faster-whisper on ROCm
**AMD Hardware:** MI300X GPU

**What it does:**
- Receives raw audio chunks streamed from the browser microphone
- Transcribes speech in real time with word-level timestamps
- Handles accents, filler words, and noisy environments far better than browser Web Speech API
- Returns: transcript text + confidence scores + word timestamps

**Why AMD matters here:**
- Whisper Large v3 is a 1.5B parameter model
- On CPU: ~8–12 seconds per chunk
- On AMD MI300X with ROCm: ~0.4–0.8 seconds per chunk
- Real-time coaching is impossible without GPU acceleration

**Input:** Raw audio bytes (streamed via WebSocket)
**Output:**
```json
{
  "transcript": "good morning everyone thank you for being here",
  "confidence": 0.94,
  "words": [
    {"word": "good", "start": 0.0, "end": 0.3, "confidence": 0.98},
    {"word": "morning", "start": 0.3, "end": 0.7, "confidence": 0.96}
  ],
  "language": "en",
  "processing_ms": 420
}
```

---

### Agent 2: ScoringAgent ⚖️
**Model:** Qwen2.5-7B-Instruct
**Runtime:** vLLM on ROCm
**AMD Hardware:** MI300X GPU

**What it does:**
- Takes the Whisper transcript + the expected chunk text
- Uses an LLM (not rule-based NLP) to evaluate delivery quality
- Scores on multiple dimensions: accuracy, fluency, completeness, naturalness
- Understands semantic equivalence ("gonna" = "going to", paraphrasing = still valid)
- Returns structured JSON scores

**Why LLM scoring beats Levenshtein:**

| Scenario | Levenshtein v1 | LLM ScoringAgent v2 |
|---|---|---|
| "gonna" vs "going to" | ❌ Different words, penalized | ✅ Semantically equivalent |
| Paraphrase with same meaning | ❌ Low score | ✅ High score, understood |
| Wrong order but all words present | ⚠️ Partial credit | ✅ Intelligent assessment |
| Filler words added ("um", "uh") | ❌ Extra words penalized | ✅ Ignored intelligently |
| Key concept missed entirely | ✅ Caught | ✅ Caught + explained |

**System prompt used:**
```
You are an expert speech coach evaluating a presenter's delivery.
Given the EXPECTED chunk and the SPOKEN transcript, score the delivery on:
- accuracy (0-100): how well key ideas were conveyed
- fluency (0-100): how natural and smooth the delivery was  
- completeness (0-100): were all key points covered
- overall (0-100): holistic score

Be lenient with: filler words, minor word substitutions, natural paraphrasing.
Be strict with: missing key concepts, wrong facts, significant omissions.

Respond ONLY with valid JSON matching the schema provided.
```

**Output:**
```json
{
  "accuracy": 88,
  "fluency": 92,
  "completeness": 85,
  "overall": 88,
  "passed": true,
  "missing_concepts": [],
  "feedback_brief": "Strong delivery. Minor omission of 'real-time' qualifier.",
  "processing_ms": 310
}
```

---

### Agent 3: CoachingAgent 🎓
**Model:** Qwen2.5-7B-Instruct
**Runtime:** vLLM on ROCm
**AMD Hardware:** MI300X GPU

**What it does:**
- Only activates when ScoringAgent returns `passed: false`
- Analyzes what specifically went wrong
- Generates a personalized correction strategy based on:
  - The user's correction mode (silent / hint / full)
  - How many attempts they've had on this chunk
  - Their historical weak points (from SessionMemoryAgent)
  - The specific concepts that were missed
- Returns both a text correction AND a TTS-ready speech string

**Correction strategies by mode:**

**Silent mode:** Replays the original chunk via TTS only (no verbal coaching)

**Hint mode:** LLM generates a targeted hint
```
Input:  Expected "AI compares your delivery in real time"
        Spoken:  "AI checks what you said"
Hint:   "Remember: 'compares delivery in real time'"
```

**Full mode:** LLM generates a full coaching response
```
"You got the core idea but missed 'real time' — that's the key differentiator.
 Let's try again: 'AI compares your delivery in real time'"
```

**Progressive difficulty:** After 2 failed attempts, CoachingAgent adjusts its strategy.
After 4 attempts, it generates an encouraging skip message.

**Output:**
```json
{
  "strategy": "hint",
  "tts_text": "Key phrase: 'compares delivery in real time'",
  "display_text": "You were close! Missing: 'compares' and 'real time'",
  "missed_concepts": ["real-time comparison"],
  "encouragement": "You're getting the structure right — just add the time qualifier.",
  "processing_ms": 280
}
```

---

### Agent 4: SegmentationAgent ✂️
**Model:** Qwen2.5-3B (smaller, faster)
**Runtime:** vLLM on ROCm
**AMD Hardware:** MI300X GPU

**What it does:**
- Takes the raw script pasted by the user
- Uses an LLM to intelligently segment it — not just by word count
- Understands: natural breathing pauses, rhetorical structure, emphasis points
- Respects: sentence boundaries, paragraph breaks, speaker intent
- Labels each chunk with: type (statement/question/list item), emphasis words, suggested pace

**Why LLM segmentation is better than word-count chunking:**

Old v1 approach: Split every N words mechanically
```
"Today I am introducing a solution it is called" ← cuts mid-thought
```

New v2 LLM approach:
```
"Today I am introducing a solution." ← natural pause
"It is called RasoSpeak."            ← clean emphasis
```

**System prompt:**
```
You are an expert presentation coach segmenting a script for earpiece delivery.
Break the script into chunks of 5-12 words each.
Rules:
- Never break mid-sentence unless unavoidable
- Prefer breaking at commas, periods, conjunctions
- Each chunk should feel like a natural breath unit
- Label emphasis words in each chunk
- Suggest pace: slow/normal/fast for each chunk
Return ONLY valid JSON.
```

**Output per chunk:**
```json
{
  "chunks": [
    {
      "id": 1,
      "text": "Good morning everyone.",
      "word_count": 3,
      "type": "greeting",
      "emphasis_words": ["morning"],
      "suggested_pace": "slow",
      "breathing_pause_after": true
    },
    {
      "id": 2, 
      "text": "Thank you so much for being here today.",
      "word_count": 8,
      "type": "courtesy",
      "emphasis_words": ["thank", "today"],
      "suggested_pace": "normal",
      "breathing_pause_after": true
    }
  ],
  "total_chunks": 24,
  "estimated_duration_minutes": 3.2
}
```

---

### Agent 5: SessionMemoryAgent 🧠
**Model:** No LLM (pure logic + data)
**Runtime:** Python + Redis on AMD Developer Cloud
**AMD Hardware:** CPU (data management, no GPU needed)

**What it does:**
- Maintains full session state across all agents
- Tracks per-chunk performance history
- Identifies patterns: which words/phrases a user consistently misses
- Builds a user profile: weak spots, average WPM, accuracy trends
- Feeds this context to CoachingAgent for personalized feedback
- Persists sessions to disk for cross-session learning

**Data it tracks:**
```python
session = {
  "user_id": "uuid",
  "session_id": "uuid",
  "started_at": "2026-05-07T10:30:00Z",
  "chunks": {
    0: {
      "attempts": 2,
      "scores": [0.61, 0.89],
      "transcripts": ["...", "..."],
      "time_spent_ms": 14200,
      "final_passed": True
    }
  },
  "weak_words": ["real-time", "autonomous", "infrastructure"],
  "avg_wpm": 142,
  "avg_accuracy": 0.81,
  "correction_count": 3,
  "skip_count": 0
}
```

**Cross-session learning:**
After 3+ sessions, CoachingAgent is given the user's historical weak words
and proactively emphasizes them during hint mode.

---

## 4. Data Flow — End to End

```
USER ACTION: Speaks to audience after hearing earpiece chunk

     │
     ▼
[Browser] captures audio via MediaRecorder API
     │   streams 1-second audio chunks via WebSocket
     ▼
[FastAPI WebSocket Handler]
     │   passes audio bytes to Agent 1
     ▼
[Agent 1: TranscriptionAgent]
     │   Whisper Large v3 on AMD MI300X
     │   returns transcript + word timestamps
     ▼
[Agent 5: SessionMemoryAgent]
     │   stores transcript, retrieves user history
     │   passes context to Agent 2
     ▼
[Agent 2: ScoringAgent]
     │   Qwen2.5-7B on vLLM/ROCm
     │   LLM evaluates transcript vs expected chunk
     │   returns multi-dimensional score
     ▼
[Decision Router]
     │   score >= threshold? → ADVANCE (no Agent 3 needed)
     │   score < threshold?  → CORRECT (call Agent 3)
     ▼
[Agent 3: CoachingAgent]  ← only if correction needed
     │   Qwen2.5-7B on vLLM/ROCm
     │   generates personalized correction
     │   returns TTS text + display text
     ▼
[Agent 5: SessionMemoryAgent]
     │   records result, updates user profile
     ▼
[FastAPI WebSocket Handler]
     │   sends structured response to browser
     ▼
[Browser]
     ├── displays score + feedback in UI
     ├── speaks correction via Web TTS (if needed)
     └── advances to next chunk (if passed)
```

**Total round-trip latency target:** < 2 seconds
- Whisper transcription:    ~500ms  (AMD GPU)
- ScoringAgent LLM:         ~350ms  (vLLM batching)
- CoachingAgent LLM:        ~300ms  (only when needed)
- Network + overhead:       ~150ms
- **Total:**                ~1.3s average

---

## 5. AMD Stack — Exactly What We Use

| Layer | Technology | AMD Component |
|---|---|---|
| GPU Hardware | AMD Instinct MI300X | AMD Developer Cloud |
| GPU Software | ROCm 6.x | ROCm Open Source Stack |
| LLM Inference | vLLM with ROCm backend | Runs on MI300X |
| STT Model | faster-whisper (CTranslate2) | ROCm GPU acceleration |
| Python Runtime | Python 3.11 | Standard |
| API Server | FastAPI + uvicorn | Standard |
| Real-time comm | WebSockets | Standard |
| State/cache | Redis | Standard |
| Container | Docker + ROCm base image | AMD ROCm Docker |

**AMD Developer Cloud setup:**
```bash
# 1. Provision MI300X instance on AMD Developer Cloud
# 2. Pull ROCm base image
docker pull rocm/pytorch:rocm6.1_ubuntu22.04_py3.11_pytorch_2.1

# 3. Install vLLM with ROCm support
pip install vllm --extra-index-url https://download.pytorch.org/whl/rocm6.1

# 4. Launch Qwen2.5-7B on vLLM
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-7B-Instruct \
  --device rocm \
  --port 8001

# 5. Install faster-whisper with ROCm
pip install faster-whisper
# CTranslate2 detects ROCm automatically
```

---

## 6. Backend File Structure

```
rasospeak-v2/
├── index.html                    ← Browser UI (thin client)
├── css/styles.css                ← Design system
├── js/
│   ├── state.js                  ← Client state
│   ├── ui.js                     ← UI rendering
│   ├── app.js                    ← Entry point + WebSocket client
│   └── speech.js                 ← TTS (earpiece) + audio capture
│
└── backend/
    ├── main.py                   ← FastAPI app + WebSocket handler
    ├── requirements.txt          ← Python dependencies
    ├── Dockerfile                ← ROCm-based container
    │
    ├── agents/
    │   ├── __init__.py
    │   ├── base_agent.py         ← Abstract base class
    │   ├── transcription_agent.py ← Whisper on ROCm
    │   ├── scoring_agent.py      ← Qwen2.5 scoring via vLLM
    │   ├── coaching_agent.py     ← Qwen2.5 coaching via vLLM
    │   ├── segmentation_agent.py ← Qwen2.5 script segmentation
    │   └── session_memory_agent.py ← State + history
    │
    ├── models/
    │   ├── schemas.py            ← Pydantic request/response models
    │   └── session.py            ← Session data models
    │
    └── config/
        ├── settings.py           ← AMD cloud endpoints, model names
        └── prompts.py            ← All LLM system prompts
```

---

## 7. Why This Wins the Hackathon

### Judges look for:

**✅ AMD GPU usage:** Every AI inference call (Whisper + Qwen × 3 agents) runs on MI300X via ROCm.

**✅ Agentic architecture:** 5 specialized agents with clear separation of concerns, passing structured data between each other, with a decision router controlling flow.

**✅ Real-world impact:** Solves a genuine human problem — presentation anxiety affects millions of professionals globally. Doctors, lawyers, executives, students.

**✅ Technical depth:** Multi-model pipeline, real-time WebSocket streaming, LLM prompt engineering, GPU-accelerated STT, vLLM inference optimization.

**✅ Novelty:** No existing tool does closed-loop earpiece coaching with LLM evaluation. This is genuinely new.

**✅ Working demo:** Fully functional end-to-end system that judges can actually try.

---

## 8. Hackathon Submission Answers

**Track:** AI Agents & Agentic Workflows

**Technologies:**
- AMD Instinct MI300X GPU
- ROCm 6.x
- vLLM (ROCm backend)
- Qwen2.5-7B-Instruct
- Whisper Large v3 (faster-whisper)
- FastAPI + WebSockets
- Python 3.11
- Redis
- Docker

**AMD Developer Cloud used:** Yes — MI300X instance for all model inference

**Open source:** Yes — full repo with backend + frontend

---

*RasoSpeak v2 — Five agents. One voice in your ear. Zero visible teleprompters.*
