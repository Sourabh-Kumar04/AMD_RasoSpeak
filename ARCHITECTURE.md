# RasoSpeak v2 — Agentic Architecture
## Your Secondary Brain — 14 AI Agents Sharing Memory

---

## The Vision: Your Inner Self

**RasoSpeak is your secondary brain — the inner version of you that:**

1. **Has perfect memory** — remembers everything you've ever said
2. **Searches the web** — "Hey Raso, what is the latest on AMD?"
3. **Chats with you** like you do yourself — continuous conversation
4. **Coaches your speeches** — practice and improve delivery
5. **Gives live information** — instant answers when you ask
6. **Imports documents into memory** — PDFs, URLs, notes
7. **Switches between multiple AIs** through voice activation
8. **Records what you hear** — and analyzes it when you want
9. **All 14 AIs share the same memory** — unified knowledge

### Activate with: "Hey Raso, tell me what is AMD"
### Ask anything: "Hey Raso, what did I say about X?"
### Learn from recordings: Analytics on your voice and speech patterns

---

## 1. The Problem

You use AI assistants but they don't remember:
- What you asked last week
- What you said about your project
- What documents you shared
- What questions you asked in past sessions

**Every conversation starts from scratch.**

### The Solution: RasoSpeak

Your secondary brain that:
- Listens to everything you say
- Remembers it all (shared memory across 14 agents)
- Answers questions about your own conversations
- Imports documents and makes them searchable
- Analyzes your voice and speech patterns

---

## 2. Architecture Overview

### The Complete System

```
┌─────────────────────────────────────────────────────────────┐
│                         YOU                                  │
│           (Speaking / Listening / Asking)                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   BROWSER / APP                             │
│   🎤 Mic → "Hey Raso..." ──────────────────────────────┐    │
│   🎧 Speaker ← AI response ───────────────────────────┐    │
└───────────────────────────────────────────────────────│────┘
                                                       │
                    Wake Word: "Hey Raso"               │
                                                       ▼
┌────────────────────────────────────────────────────────────▼┐
│              FastAPI Backend — 14 AI Agents                 │
│                                                             │
│   ┌────────────────────────────────────────────────────┐   │
│   │           SharedMemoryAgent (UNIFIED BRAIN)         │   │
│   │    All 14 agents read/write to the same memory      │   │
│   └────────────────────────────────────────────────────┘   │
│                          │                                 │
│   ┌──────────────┐  ┌────────────┐  ┌──────────────────┐   │
│   │ PartnerAgent │  │ QAAgent    │  │ DocumentAgent    │   │
│   │ Continuous  │  │ Multi-    │  │ Import PDFs/URLs │   │
│   │ Chat        │  │ provider  │  │ to memory        │   │
│   └──────────────┘  └────────────┘  └──────────────────┘   │
│                                                             │
│   ┌──────────────┐  ┌────────────┐  ┌──────────────────┐   │
│   │SearchAgent   │  │ Recording  │  │ AnalyticsAgent   │   │
│   │ Web Search   │  │ Agent      │  │ Voice & Speech   │   │
│   └──────────────┘  └────────────┘  └──────────────────┘   │
│                                                             │
│   ┌──────────────┐  ┌────────────┐  ┌──────────────────┐   │
│   │WakeWordAgent│  │Transcrip- │  │ ScoringAgent    │   │
│   │"Hey Raso"   │  │tionAgent  │  │ Evaluate speech  │   │
│   └──────────────┘  └───────────┘  └──────────────────┘   │
│                                                             │
│   ┌──────────────┐  ┌────────────┐  ┌──────────────────┐   │
│   │CoachingAgent│  │Segmenta-   │  │NotificationAgent│   │
│   │ Corrections │  │tionAgent   │  │ SMS/Telegram     │   │
│   └──────────────┘  └────────────┘  └──────────────────┘   │
│                                                             │
│   ┌────────────────────────────────────────────────────┐   │
│   │           SessionMemoryAgent                        │   │
│   │    Tracks session state and conversation history   │   │
│   └────────────────────────────────────────────────────┘   │
│                                                             │
│   💾 All agents share memory via SharedMemoryAgent          │
└─────────────────────────────────────────────────────────────┘
```

### Key Innovation: Shared Memory

```
Traditional AI:
  User → ChatGPT → "What did I ask yesterday?" → "I don't know"

RasoSpeak:
  User → "Hey Raso, what did I ask yesterday?"
         │
         ▼
    WakeWordAgent detects "Hey Raso"
         │
         ▼
    SharedMemoryAgent searches memory
         │
         ▼
    "You asked about ROCm installation on Tuesday"
```

---

## 3. The 14 Agents — Detailed

### Agent 1: PartnerAgent 🤝
**Model:** Qwen2.5-7B-Instruct via vLLM on ROCm
**AMD Hardware:** MI300X GPU

**What it does:**
- Your AI partner — continuous listening and memory
- Maintains conversation context across the session
- Answers follow-up questions based on previous exchanges
- Provides reminders and contextual suggestions
- Acts as the central coordinator for user interactions

**Input:** User messages, session context, memory context
**Output:** Natural language response, action suggestions

---

### Agent 2: SharedMemoryAgent 🧠
**Model:** Qwen2.5-7B-Instruct via vLLM on ROCm
**AMD Hardware:** MI300X GPU

**What it does:**
- Unified brain — all 14 agents share this memory
- Stores facts, preferences, context across sessions
- Enables cross-agent context sharing
- Maintains persistent user profiles
- Acts as the central knowledge store

**Input:** Facts, user preferences, session data
**Output:** Retrieved memories, context summaries

---

### Agent 3: WakeWordAgent 🎙️
**Model:** Qwen2.5-7B-Instruct via vLLM on ROCm
**AMD Hardware:** MI300X GPU

**What it does:**
- Listens for "Hey Raso" wake word
- Activates on voice command
- Handles natural language activation phrases
- Integrates with real-time audio stream

**Input:** Audio stream (continuous)
**Output:** Wake confirmation, intent parsing

---

### Agent 4: DocumentAgent 📄
**Model:** Qwen2.5-7B-Instruct via vLLM on ROCm
**AMD Hardware:** MI300X GPU

**What it does:**
- Import documents — PDFs, URLs, text to memory
- Parses and indexes uploaded content
- Extracts key information and facts
- Makes document content available to all agents

**Input:** PDF files, URLs, raw text
**Output:** Parsed content, indexed facts, summaries

---

### Agent 5: NotificationAgent 📱
**Model:** Qwen2.5-7B-Instruct via vLLM on ROCm
**AMD Hardware:** MI300X GPU

**What it does:**
- Send phone notifications — SMS, Telegram, Push
- Alert user about session events
- Deliver reminders and follow-ups
- Broadcast coaching feedback to multiple channels

**Input:** Notification request, channel selection
**Output:** Notification sent confirmation

---

### Agent 6: TranscriptionAgent 🎙️
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

### Agent 7: ScoringAgent ⚖️
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

### Agent 8: CoachingAgent 🎓
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

### Agent 9: SegmentationAgent ✂️
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

### Agent 10: SessionMemoryAgent 🧠
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

### Agent 11: QAAgent ❓
**Model:** GPT/Claude/Gemini/Qwen (multi-provider)
**Runtime:** OpenAI API / Anthropic API / Google API / vLLM
**AMD Hardware:** MI300X GPU (for Qwen local)

**What it does:**
- Real-time Q&A during practice sessions
- Connect to 5 AI providers: OpenAI GPT, Anthropic Claude, Google Gemini, Local Qwen
- Context-aware (uses your script as context)
- Multi-turn conversation support
- Answers questions on the fly like ChatGPT in your ear

**Input:** User question + script context
**Output:** AI-generated answer with sources

---

### Agent 12: SearchAgent 🔍
**Model:** Tavily AI / DuckDuckGo
**Runtime:** HTTP API calls
**AMD Hardware:** None (API-based)

**What it does:**
- Real-time web search for live information
- Searches for facts, news, or definitions during sessions
- Returns results with AI summaries
- Supports Tavily for AI-optimized search or DuckDuckGo fallback

**Input:** Search query
**Output:** Search results + AI summary

---

### Agent 13: RecordingAgent 🎥
**Model:** No LLM (pure audio processing)
**Runtime:** Python + FFmpeg
**AMD Hardware:** None (CPU audio processing)

**What it does:**
- Records full audio sessions
- Stores conversation history
- Enables playback and review
- Exports recordings for review

**Input:** Audio stream
**Output:** Stored recording + metadata

---

### Agent 14: AnalyticsAgent 📊
**Model:** Qwen2.5-7B-Instruct via vLLM on ROCm
**Runtime:** vLLM on ROCm
**AMD Hardware:** MI300X GPU

**What it does:**
- Session & user insights
- Analyzes speech improvement over time
- Generates analytics reports
- Tracks performance metrics across sessions
- Identifies patterns and trends in user performance

**Input:** Session data, historical performance
**Output:** Analytics report, improvement suggestions

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
     │   passes audio bytes to Agent 6
     ▼
[Agent 6: TranscriptionAgent]
     │   Whisper Large v3 on AMD MI300X
     │   returns transcript + word timestamps
     ▼
[Agent 10: SessionMemoryAgent]
     │   stores transcript, retrieves user history
     │   passes context to Agent 7
     ▼
[Agent 7: ScoringAgent]
     │   Qwen2.5-7B on vLLM/ROCm
     │   LLM evaluates transcript vs expected chunk
     │   returns multi-dimensional score
     ▼
[Decision Router]
     │   score >= threshold? → ADVANCE (no Agent 8 needed)
     │   score < threshold?  → CORRECT (call Agent 8)
     ▼
[Agent 8: CoachingAgent]  ← only if correction needed
     │   Qwen2.5-7B on vLLM/ROCm
     │   generates personalized correction
     │   returns TTS text + display text
     ▼
[Agent 10: SessionMemoryAgent]
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

**Total round-trip latency target:** < 1.5 seconds
- Whisper transcription:    ~480ms  (AMD GPU)
- ScoringAgent LLM:         ~330ms  (vLLM batching)
- CoachingAgent LLM:        ~295ms  (only when needed)
- Network + overhead:       ~150ms
- **Total:**                ~1.1s average

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
| Container | Docker | HF Spaces |

**HuggingFace Space / AMD Developer Cloud setup:**
```bash
# 1. Clone the repository
git clone https://github.com/Sourabh-Kumar04/AMD_RasoSpeak
cd AMD_RasoSpeak

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start FastAPI backend
uvicorn main:app --host 0.0.0.0 --port 7860

# 4. Open in browser
open http://localhost:7860
```

For AMD Developer Cloud (MI300X GPU):
```bash
# Install vLLM with ROCm support
pip install vllm --extra-index-url https://download.pytorch.org/whl/rocm6.1

# Launch Qwen2.5-7B on vLLM
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-7B-Instruct \
  --device rocm \
  --port 8001

# Install faster-whisper with ROCm
pip install faster-whisper
# CTranslate2 detects ROCm automatically
```

---

## 6. Backend File Structure

```
rasospeak-v2/
├── index.html                  ← Browser UI (thin client)
├── styles.css                  ← Design system (Material Design 3)
├── app.js, ui.js, speech.js   ← Frontend JavaScript
├── nlp.js, state.js            ← NLP and state management
│
├── main.py                     ← FastAPI backend + WebSocket
├── app.py                      ← Gradio interface
│
├── agents/                     ← 14 AI agents
│   ├── base_agent.py          ← Abstract base class
│   ├── partner_agent.py       ← AI partner
│   ├── shared_memory_agent.py ← Unified brain
│   ├── wake_word_agent.py     ← Wake word detection
│   ├── transcription_agent.py ← Whisper on ROCm
│   ├── scoring_agent.py       ← Qwen scoring
│   ├── coaching_agent.py      ← Qwen coaching
│   ├── segmentation_agent.py  ← Qwen chunking
│   ├── session_memory_agent.py ← Session state
│   ├── document_agent.py      ← PDF/URL import
│   ├── notification_agent.py  ← SMS/Telegram
│   ├── qa_agent.py            ← Multi-provider Q&A
│   ├── search_agent.py        ← Web search
│   ├── recording_agent.py     ← Audio recording
│   └── analytics_agent.py     ← Insights
│
├── config/
│   ├── settings.py            ← Configuration
│   └── prompts.py             ← LLM prompts
│
├── models/
│   └── schemas.py             ← Pydantic schemas
│
├── requirements.txt            ← Python dependencies
├── Dockerfile                 ← Docker deployment
└── .env.example               ← Environment template
```

---

## 7. Why This Wins the Hackathon

### Judges look for:

**✅ AMD GPU usage:** Every AI inference call (Whisper + Qwen × multiple agents) runs on MI300X via ROCm.

**✅ Agentic architecture:** 14 specialized agents with clear separation of concerns, passing structured data between each other, with a decision router controlling flow.

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

*RasoSpeak v2 — 14 agents. One voice in your ear. Zero visible teleprompters.*
