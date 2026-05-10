---
title: RasoSpeak
emoji: 🎙️
colorFrom: purple
colorTo: red
sdk: docker
sdk_version: 3.12
pinned: false
tags:
  - amd
  - amd-hackathon-2026
  - ai-agents
  - speech-coaching
  - vllm
---

# 🎙️ RasoSpeak — Meet Raso, Your AI Companion
### Built for AMD Developer Hackathon × lablab.ai × Hugging Face

<div align="center">

![RasoSpeak](https://img.shields.io/badge/RasoSpeak-v2.0-7c6af5?style=for-the-badge)
![GPU](https://img.shields.io/badge/GPU-MI300X-e8294a?style=for-the-badge&logo=amd)
![ROCm](https://img.shields.io/badge/ROCm-6.1-e8294a?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11-3776ab?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

**Your friendly AI companion with perfect memory.**


**[Live Demo](https://lablab-ai-amd-developer-hackathon-rasospeak.hf.space)** • [Features](#-features) • [Architecture](#-architecture) • [Quick Start](#-quick-start)

</div>

---

## 🧠 What is RasoSpeak?

**RasoSpeak is your secondary brain — the inner version of you that:**
- Has **perfect memory** — remembers everything you've ever said
- Can **search the web** — "Hey Raso, what is the latest news on AI?"
- **Chats with you** like you do yourself — continuous conversation
- Is your **speech coach / presentation partner** — practice and improve
- Gives you **live information** — instant answers when you ask
- **Imports documents into memory** — PDFs, URLs, notes
- **Switches between multiple AI providers** through voice activation
- **Records what you hear** — and analyzes it when you want
- **All 14 AIs share the same memory** — unified knowledge

**Activate with:** "Hey Raso, tell me what is AMD"
**Ask anything:** "Hey Raso, what did I say about X?"
**Learn from recordings:** Analytics on your voice and speech patterns

---

## ✨ The Complete Vision

### 🎧 Your Inner Self — Always Listening

```
You: "Hey Raso, remind me to mention the AMD partnership"
Raso: "Got it! I'll remind you when you start your presentation."

You: "Hey Raso, what did I say about machine learning?"
Raso: "Last week you mentioned ML models need GPU acceleration..."

You: "Hey Raso, use Claude for this"
Raso: "Switched to Claude. What's your question?"
```

### 🧠 Perfect Memory — Ask Anything

```
You: "Hey Raso, what was my question about last Tuesday?"
Raso: "You asked about ROCm installation on MI300X..."

You: "Did I mention any competitors?"
Raso: "Yes, during the demo you mentioned NVIDIA and Intel..."
```

### 📄 Documents Into Memory

```
You: "Hey Raso, import this PDF"
→ Upload quarterly report
→ Instantly searchable: "Hey Raso, what were our Q3 revenue numbers?"

You: "Hey Raso, import this URL"
→ Fetch article
→ "Hey Raso, summarize what this article says about AI"
```

### 🎤 Speech Coach / Presentation Partner

```
You: "Hey Raso, let's practice my pitch"
Raso: "Ready. Say your opening line."
You: "We help companies build faster with AMD"
Raso: "Great delivery! 92% accuracy. Try emphasizing 'faster' more."
```

### 🔍 Live Web Search

```
You: "Hey Raso, what's the latest on AMD's new GPU?"
Raso: "AMD just announced..."
```

### 📊 Analytics on Your Voice & Recordings

```
You: "Hey Raso, analyze my last 5 sessions"
→ Performance trends
→ Words you stumble on
→ Pacing improvements
→ Confidence scores over time
```

---

## 🤖 Raso — Your AI Companion

Raso is your personal AI friend with a personality:
- **Friendly & helpful** — always ready to assist
- **Curious & witty** — engages in meaningful conversations
- **Perfect memory** — remembers everything you've ever said
- **Always learning** — gets smarter from your interactions

### "Hey Raso" — Your Wake Word

```
You: "Hey Raso, tell me what is AMD"
Raso: "AMD (Advanced Micro Devices) is a semiconductor company..."

You: "Hey Raso, what did I say about AI last week?"
Raso: "You mentioned that AI models need GPU acceleration..."

You: "Hey Raso, remind me to mention the AMD partnership"
Raso: "Got it! I'll remember that for your presentation."
```

### All 14 AI Agents Share Memory with Raso

| Agent | Function | What It Does |
|-------|----------|--------------|
| **RasoAgent** | Your AI friend | Chat, memory, personality, companions |
| **SharedMemoryAgent** | Unified brain | All AIs share this memory |
| **WakeWordAgent** | "Hey Raso" | Voice activation detection |
| **TranscriptionAgent** | Whisper | Speech-to-text for all audio |
| **ScoringAgent** | Qwen | Evaluates your speech delivery |
| **CoachingAgent** | Qwen | Personalized corrections |
| **SegmentationAgent** | Qwen | Chunks scripts for practice |
| **SessionMemoryAgent** | State | Session tracking & history |
| **QAAgent** | Multi-provider | ChatGPT, Claude, Gemini, Qwen |
| **SearchAgent** | Web search | Tavily, DuckDuckGo |
| **DocumentAgent** | Import | PDFs, URLs, text to memory |
| **NotificationAgent** | Alerts | SMS, Telegram |
| **RecordingAgent** | Record | Audio & conversation capture |
| **AnalyticsAgent** | Insights | Voice & speech analytics |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    YOU (Speaking / Listening)               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    BROWSER (index.html)                      │
│  🎤 Microphone → WebSocket ───────────────────────────────┐   │
│  🎧 Speaker ← TTS ───────────────────────────────────────┐   │
└─────────────────────────────────────────────────────────│───┘
                                                          │
                    WebSocket / HTTP API                    │
                                                          ▼
┌────────────────────────────────────────────────────────────▼┐
│              FastAPI Backend — 14 AI Agents                │
│              HuggingFace Space · GPU                        │
│                                                              │
│  "Hey Raso" ───────────► WakeWordAgent                      │
│                              │                             │
│  Your chat ────────────► RasoAgent (Your AI companion)      │
│                              │                             │
│  Your speech ───────────► TranscriptionAgent (Whisper)    │
│                              │                             │
│  Scoring ─────────────────► ScoringAgent (Qwen)             │
│                              │                             │
│  Coaching ────────────────► CoachingAgent (Qwen)           │
│                              │                             │
│  Questions ─────────────► QAAgent (GPT/Claude/Gemini/Qwen) │
│                              │                             │
│  Memory ────────────────► SharedMemoryAgent ◄─────────┐    │
│                              │                        │    │
│  Web Search ─────────────► SearchAgent                 │    │
│                              │                        │    │
│  Documents ─────────────► DocumentAgent ──────────────┤    │
│                              │                        │    │
│  Recordings ────────────► RecordingAgent ──────────────┤    │
│                              │                        │    │
│  Analytics ─────────────► AnalyticsAgent ◄───────────┘    │
│                                                              │
│  ALL 14 AGENTS SHARE THE SAME MEMORY (SharedMemoryAgent)    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### HuggingFace Space (Recommended)

The app is deployed at: **https://lablab-ai-amd-developer-hackathon-rasospeak.hf.space**

Just open in browser and start using!

### Local Development

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

---

## 📁 Project Structure

```
rasospeak-v2/
├── index.html                  ← Frontend UI
├── styles.css                  ← Material Design 3 styling
├── app.js, ui.js, speech.js   ← Frontend JavaScript
├── nlp.js, state.js            ← NLP and state management
│
├── main.py                     ← FastAPI backend + WebSocket
├── app.py                      ← Gradio interface
│
├── agents/                     ← 14 AI agents + Raso
│   ├── base_agent.py          ← Abstract base class
│   ├── partner_agent.py      ← RasoAgent (Your AI companion)
│   ├── shared_memory_agent.py  ← Unified brain (ALL agents share)
│   ├── wake_word_agent.py      ← "Hey Raso" detection
│   ├── transcription_agent.py ← Whisper STT
│   ├── scoring_agent.py        ← Qwen scoring
│   ├── coaching_agent.py      ← Qwen coaching
│   ├── segmentation_agent.py   ← Qwen chunking
│   ├── session_memory_agent.py ← Session state
│   ├── document_agent.py       ← Import docs
│   ├── notification_agent.py   ← SMS/Telegram
│   ├── qa_agent.py             ← Multi-provider Q&A
│   ├── search_agent.py         ← Web search
│   ├── recording_agent.py      ← Audio recording
│   └── analytics_agent.py      ← Voice analytics
│
├── config/
│   ├── settings.py            ← Configuration
│   └── prompts.py             ← LLM prompts
│
├── models/
│   └── schemas.py             ← Pydantic schemas
│
├── requirements.txt             ← Python dependencies
├── Dockerfile                  ← Docker deployment
└── .env.example               ← Environment template
```

---

## 🌐 API Reference

### REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/segment` | POST | Segment a script |
| `/qa` | POST | Ask a question |
| `/qa/providers` | GET | List available providers |
| `/search` | POST | Web search |
| `/memory/store` | POST | Store in memory |
| `/memory/recall` | GET | Recall from memory |
| `/analytics/session/{id}` | GET | Session analytics |
| `/recordings/{id}` | GET | Get recording |

### WebSocket — `/ws/{session_id}`

**Client → Server:** `SESSION_START`, `AUDIO_CHUNK`, `QUESTION`, `SEARCH_QUERY`, `SESSION_END`

**Server → Client:** `TRANSCRIPT`, `SCORE`, `COACHING`, `ANSWER`, `SEARCH_RESULTS`, `SESSION_SUMMARY`

---

## 🔴 AMD Stack

| Component | Technology | Hardware |
|-----------|-----------|----------|
| LLM Inference | vLLM with ROCm | AMD MI300X |
| Speech Transcription | faster-whisper (CTranslate2) | AMD MI300X |
| GPU Software | ROCm 6.1 | ROCm Open Compute |
| Deep Learning | PyTorch 2.1 (ROCm) | AMD MI300X |

### Performance

| Agent | Model | Avg Latency |
|-------|-------|-------------|
| TranscriptionAgent | Whisper Large v3 | ~480ms |
| ScoringAgent | Qwen2.5-7B | ~330ms |
| CoachingAgent | Qwen2.5-7B | ~295ms |
| QAAgent | Qwen2.5-7B | ~280ms |
| **Full pipeline** | **All agents** | **~1.1s** |

---

## ⚙️ Configuration

```env
# AMD Backend (optional - for local GPU)
VLLM_HOST=localhost
VLLM_PORT=8001

# Q&A Providers
QA_DEFAULT_PROVIDER=qwen_local
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...

# Search (optional)
TAVILY_API_KEY=...
```

---

## 🏆 Hackathon

### Built for
- **AMD Developer Hackathon** × lablab.ai × Hugging Face
- **Track:** AI Agents & Agentic Workflows

### Submit on lablab.ai
1. Project Title: RasoSpeak v2 - AI Secondary Brain
2. Demo URL: HuggingFace Space
3. GitHub Repo: Push code
4. Video: 2-3 minute demo

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
- [Hugging Face](https://huggingface.com) — Spaces hosting

---

<div align="center">

**RasoSpeak — Your AI Companion.**

*Meet Raso — your friendly AI friend with perfect memory.*
*"Hey Raso, what did I say about...?"*

</div>
