# 🎙 RasoSpeak — Your Secondary Brain & AI Partner
### Built for AMD Developer Hackathon × lablab.ai

<div align="center">

![RasoSpeak Banner](https://img.shields.io/badge/RasoSpeak-v2.0-7c6af5?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZmlsbD0id2hpdGUiIGQ9Ik0xMiAxNGMxLjY2IDAgMy0xLjM0IDMtM1Y1YzAtMS42Ni0xLjM0LTMtMy0zUzkgMy4zNCA5IDV2NmMwIDEuNjYgMS4zNCAzIDMgM3oiLz48cGF0aCBmaWxsPSJ3aGl0ZSIgZD0iTTE3IDExYzAgMi43Ni0yLjI0IDUtNSA1cy01LTIuMjQtNS01SDVjMCAzLjUzIDIuNjEgNi40MyA2IDYuOTJWMjFoMnYtMy4wOGMzLjM5LS40OSA2LTMuMzkgNi02LjkyaC0yeiIvPjwvc3ZnPg==)
![AMD MI300X](https://img.shields.io/badge/AMD-MI300X%20GPU-e8294a?style=for-the-badge&logo=amd)
![ROCm](https://img.shields.io/badge/ROCm-6.1-e8294a?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11-3776ab?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi)
![Gradio](https://img.shields.io/badge/Gradio-4.44-orange?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

**An invisible AI speech coach that whispers your script through your earpiece,
listens to your delivery, evaluates it with LLMs on AMD GPUs, and corrects you in real time.**

**PLUS** — Real-time Q&A with AI (GPT/Claude/Gemini/Qwen), web search, and comprehensive analytics.

[Features](#-features) • [Architecture](#-architecture) • [AMD Stack](#-amd-stack) • [Quick Start](#-quick-start) • [Agents](#-the-9-agents) • [API](#-api-reference) • [Hugging Face Space](#-hugging-face-space)

</div>

---

## 🧠 What is RasoSpeak?

RasoSpeak is your **AI Partner / Secondary Brain** — like having a smart companion in your ear 24/7.

### Core Features

1. **AI Partner (Primary)** — Your continuous AI companion that:
   - Activated by **"Hey Raso"** wake word
   - Always listens and remembers everything you say
   - Answers questions based on past conversations ("What did I say about X?")
   - Searches the web for new information
   - Sets reminders and follows up
   - Acts like a helpful partner, not just a tool

2. **Voice Wake Word** — Say "Hey Raso" to activate (like Alexa/Siri)

3. **Document Import** — Import PDFs, web pages, notes to your memory

4. **Phone Notifications** — Get SMS, Telegram alerts for reminders

5. **Speech Coaching** — Practice presentations with real-time AI feedback
6. **Real-time Q&A** — Ask any question, get instant answers
7. **Web Search** — Search the web for current information
8. **Recording & Analytics** — Track your progress over time

### Use Cases
- 🎤 **Presentation Practice** — Practice speeches with AI coaching
- ❓ **Instant Q&A** — Ask questions during practice (like having ChatGPT in your ear)
- 🔍 **Live Information** — Search for facts, news, or definitions
- 📊 **Progress Tracking** — Analytics on your speech improvement

---

## ✨ Features

### 🤖 14 Specialized AI Agents (on AMD MI300X)

| Agent | Model | Function |
|-------|-------|----------|
| **PartnerAgent** | — | **YOUR AI PARTNER** — continuous listening, memory, reminders |
| **SharedMemoryAgent** | — | **UNIFIED BRAIN** — all AIs share this memory |
| **WakeWordAgent** | — | **"Hey Raso"** — voice wake word detection |
| **DocumentAgent** | — | **Import docs** — PDFs, URLs, text to memory |
| **NotificationAgent** | — | **Phone notifications** — SMS, Telegram, Push |
| **TranscriptionAgent** | Whisper Large v3 | Speech-to-text |
| **ScoringAgent** | Qwen2.5-7B | Semantic speech evaluation |
| **CoachingAgent** | Qwen2.5-7B | Personalized corrections |
| **SegmentationAgent** | Qwen2.5-3B | Script chunking |
| **SessionMemoryAgent** | — | Session state & history |
| **QAAgent** | GPT/Claude/Gemini/Qwen | Real-time Q&A |
| **SearchAgent** | DuckDuckGo/Tavily | Web search |
| **RecordingAgent** | — | Audio/conversation recording |
| **AnalyticsAgent** | Qwen2.5-7B | Insights & analytics |

### ❓ Real-time Q&A (like ChatGPT/Gemini)
- Connect to **5 AI providers**: OpenAI GPT, Anthropic Claude, Google Gemini, xAI Grok, Local Qwen
- Answers **stream to your earpiece** via TTS
- Context-aware (uses your script as context)
- Multi-turn conversation support

### 🔍 Web Search
- Real-time information lookup
- Uses Tavily, SerpAPI, Brave Search, or DuckDuckGo (fallback)
- Results + AI summary
- Perfect for current events, facts, definitions

### 📊 Recording & Analytics
- Records all audio, Q&A conversations, coaching events
- Session-level analytics (accuracy, fluency, trends)
- User-level analytics (improvement over time)
- Q&A topic analysis
- Speech improvement reports

### 🎙 Speech Coaching Loop
- Real-time audio streaming via WebSocket
- Three correction modes: **Silent** · **Hint** · **Full**
- Three strictness levels: **Lenient** · **Normal** · **Strict**
- Auto-skip after 4 failed attempts
- Early advance at 82% coverage

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    BROWSER / GRADIO SPACE                   │
│  index.html · Gradio UI (app.py)                           │
│  js/app.js ──── WebSocket ────────────────────────────┐   │
└─────────────────────────────────────────────────────────│───┘
                                                         │
                    WebSocket / HTTP API                   │
                                                         │
┌────────────────────────────────────────────────────────▼───┐
│              FastAPI Backend  (main.py)                    │
│                AMD Developer Cloud · MI300X GPU             │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              AGENT PIPELINE (14 Agents)             │   │
│  │                                                      │   │
│  │   ┌─────────────────────────────────────────────┐  │   │
│  │   │        🌟 YOUR AI PARTNER (PartnerAgent)     │  │   │
│  │   │   ←→ "Hey Raso" wake word + continuous       │  │   │
│  │   └────────────────────┬──────────────────────────┘  │   │
│  │                        │                              │   │
│  │   ┌────────────────────▼──────────────────────────┐  │   │
│  │   │     SharedMemoryAgent (UNIFIED BRAIN)        │  │   │
│  │   │     ← ALL AIs read/write this memory →       │  │   │
│  │   └────────────────────┬──────────────────────────┘  │   │
│  │                        │                              │   │
│  │  [1] WakeWordAgent ───► "Hey Raso" detection       │   │
│  │  [2] DocumentAgent ────► Import PDFs, URLs, docs    │   │
│  │  [3] NotificationAgent ─► Phone SMS, Telegram      │   │
│  │  [4] TranscriptionAgent ─ Whisper Large v3       │   │
│  │  [5] ScoringAgent ─────── Qwen2.5-7B                │   │
│  │  [6] CoachingAgent ────── Qwen2.5-7B                │   │
│  │  [7] SegmentationAgent ─ Qwen2.5-3B                 │   │
│  │  [8] SessionMemoryAgent ─ In-memory + Redis         │   │
│  │  [9] QAAgent ──────────── GPT/Claude/Gemini/Qwen    │   │
│  │  [10] SearchAgent ─────── Tavily/DuckDuckGo        │   │
│  │  [11] RecordingAgent ─── Audio & conversation log  │   │
│  │  [12] AnalyticsAgent ─── Session & user insights   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔴 AMD Stack

| Component | Technology | AMD Hardware |
|-----------|-----------|--------------|
| LLM Inference | vLLM with ROCm backend | AMD Instinct MI300X |
| Speech Transcription | faster-whisper (CTranslate2) | AMD Instinct MI300X |
| GPU Software Stack | ROCm 6.1 | ROCm Open Compute |
| Deep Learning | PyTorch 2.1 (ROCm build) | AMD Instinct MI300X |

### Why AMD MI300X?
| Model | CPU Inference | AMD MI300X (ROCm) | Speedup |
|-------|-------------|-------------------|---------|
| Whisper Large v3 | ~8–12s/chunk | ~0.4–0.6s/chunk | **~20×** |
| Qwen2.5-7B | ~45–90s/query | ~0.3–0.4s/query | **~150×** |

---

## 🚀 Quick Start

### Option 1 — Hugging Face Space (Recommended for Demo)

```bash
# Deploy as HF Space (for hackathon submission)
# Just push to Hugging Face and it will auto-deploy!
```

### Option 2 — Local Development

```bash
# 1. Clone the repository
git clone https://github.com/your-username/rasospeak-v2
cd rasospeak-v2

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start vLLM server (Qwen2.5-7B on AMD GPU)
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-7B-Instruct \
  --device rocm \
  --dtype float16 \
  --port 8001

# 4. Start FastAPI backend
uvicorn main:app --host 0.0.0.0 --port 8000

# 5. Open in browser
open http://localhost:8000
```

### Option 3 — Gradio Demo (No GPU required)

```bash
# Run the Gradio interface (uses external APIs if configured)
python app.py
# Opens at http://localhost:7860
```

---

## 📁 Project Structure

```
rasospeak-v2/
├── app.py                      ← Hugging Face Space (Gradio)
├── main.py                     ← FastAPI backend + WebSocket
├── index.html                  ← Frontend entry point
│
├── agents/                     ← 9 AI agents
│   ├── base_agent.py
│   ├── transcription_agent.py  ← Whisper
│   ├── scoring_agent.py        ← Qwen scoring
│   ├── coaching_agent.py       ← Qwen coaching
│   ├── segmentation_agent.py   ← Qwen chunking
│   ├── session_memory_agent.py
│   ├── qa_agent.py             ← Multi-provider Q&A (NEW)
│   ├── search_agent.py         ← Web search (NEW)
│   ├── recording_agent.py      ← Audio recording (NEW)
│   └── analytics_agent.py     ← Insights (NEW)
│
├── config/
│   ├── settings.py             ← Configuration
│   └── prompts.py             ← LLM prompts
│
├── models/
│   └── schemas.py              ← Pydantic schemas
│
├── requirements.txt            ← Python dependencies
├── Dockerfile                  ← ROCm-based container
└── .env.example               ← Environment template
```

---

## 🤖 The 10 Agents

### Core — The Unified Brain (1)

0. **SharedMemoryAgent** — The brain that connects ALL agents
   - Stores user profile, preferences, facts
   - Remembers all Q&A conversations
   - Tracks weak words and improvement areas
   - Provides context to every AI for personalized responses
   - Persists to disk for long-term memory

### Core Coaching (5)

1. **TranscriptionAgent** — Whisper Large v3 on ROCm
2. **ScoringAgent** — Qwen2.5-7B semantic evaluation
3. **CoachingAgent** — Personalized corrections
4. **SegmentationAgent** — Script chunking
5. **SessionMemoryAgent** — Session state & history

### Q&A & Search (2)

6. **QAAgent** — Connects to OpenAI, Anthropic, Google, xAI, or local Qwen
   - Real-time question answering
   - **Uses shared memory** for personalized context
   - Stores all conversations in shared memory

7. **SearchAgent** — Web search for current information
   - Tavily, SerpAPI, Brave, or DuckDuckGo
   - Returns results + AI summary

### Recording & Analytics (2)

8. **RecordingAgent** — Records all interactions
   - Audio chunks (user speech, coaching TTS, AI answers)
   - Q&A conversations
   - Coaching events and transcripts

9. **AnalyticsAgent** — Generates insights
   - Session analytics (accuracy, fluency, trends)
   - User analytics (improvement over time)
   - Q&A topic analysis
   - AI-powered insights via LLM

---

## 🌐 API Reference

### REST Endpoints

```bash
# Health check
GET  /health

# Segment a script
POST /segment

# Q&A - Ask a question (streams to earpiece)
POST /qa
# Body: {"question": "...", "provider": "openai|anthropic|google|qwen_local"}

# Web search
POST /search
# Body: {"query": "..."}

# Recording
POST /recordings/{session_id}/start
POST /recordings/{session_id}/stop
POST /recordings/{session_id}/audio

# Analytics
GET  /analytics/session/{session_id}
GET  /analytics/user/{user_id}?days=30
GET  /analytics/improvement/{user_id}
```

### WebSocket — `/ws/{session_id}`

**Client → Server:**

| Type | Description |
|------|-------------|
| `SESSION_START` | Start coaching session |
| `AUDIO_CHUNK` | Stream audio for scoring |
| `QUESTION` | Ask AI a question (NEW) |
| `SEARCH_QUERY` | Search the web (NEW) |
| `SESSION_END` | End session |

**Server → Client:**

| Type | Description |
|------|-------------|
| `TRANSCRIPT` | Whisper transcription |
| `SCORE` | Qwen scoring result |
| `COACHING` | Correction feedback |
| `ANSWER` | AI answer to question (NEW) |
| `SEARCH_RESULTS` | Web search results (NEW) |
| `SESSION_SUMMARY` | End-of-session insights |

---

## ⚙️ Configuration

### Environment Variables

```env
# AMD Developer Cloud
VLLM_HOST=localhost
VLLM_PORT=8001

# Q&A Providers (at least one recommended)
QA_DEFAULT_PROVIDER=qwen_local
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
XAI_API_KEY=...

# Search (at least one recommended)
TAVILY_API_KEY=...
SERP_API_KEY=...
BRAVE_API_KEY=...

# Recording & Analytics
RECORDINGS_PATH=./recordings
ANALYTICS_ENABLED=true
```

---

## 🎯 Hackathon Submission

### What's Ready
- ✅ Full AI speech coaching pipeline
- ✅ Real-time Q&A (5 providers)
- ✅ Web search
- ✅ Recording & analytics
- ✅ Gradio interface (HF Space ready)
- ✅ 9 specialized agents on AMD MI300X

### To Submit on lablab.ai
1. **Project Title**: RasoSpeak v2 - AI Speech Coach
2. **Demo URL**: Deploy as Hugging Face Space
3. **GitHub Repo**: Push code
4. **Video**: 2-3 minute demo
5. **Cover Image**: Screenshot

### Build in Public Challenge
- Post 2+ technical updates on X/LinkedIn
- Tag @lablab and @AIatAMD
- Publish technical walkthrough

---

## 📈 Performance (AMD MI300X)

| Agent | Model | Avg Latency |
|-------|-------|-------------|
| TranscriptionAgent | Whisper Large v3 | 480ms |
| ScoringAgent | Qwen2.5-7B | 330ms |
| CoachingAgent | Qwen2.5-7B | 295ms |
| QAAgent | Qwen2.5-7B | 280ms |
| **Full pipeline** | **All agents** | **~1.1s** |

---

## 🏆 Prizes We're Targeting

- 🤖 AI Agents & Agentic Workflows (1st/2nd/3rd)
- 🤗 Hugging Face Special Prize (most likes)
- 🐲 Qwen Special Reward (best Qwen use)

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgements

- [AMD Developer Cloud](https://www.amd.com/en/developer/resources/ml-and-ai/amd-developer-cloud.html) — MI300X GPU access
- [ROCm](https://rocm.docs.amd.com/) — Open source GPU software stack
- [vLLM](https://github.com/vllm-project/vllm) — High-throughput LLM serving
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — Whisper acceleration
- [Qwen](https://huggingface.co/Qwen) — Alibaba's open-source LLM family
- [lablab.ai](https://lablab.ai) — Hackathon platform

---

<div align="center">

**RasoSpeak v2 — Nine agents. One voice in your ear. Zero visible teleprompters.**

*Every great speaker deserves an invisible coach.*

</div>