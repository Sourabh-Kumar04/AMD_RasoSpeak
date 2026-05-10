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

# 🎙️ RasoSpeak — Your Secondary Brain & AI Partner
### Built for AMD Developer Hackathon × lablab.ai × Hugging Face

<div align="center">

![RasoSpeak](https://img.shields.io/badge/RasoSpeak-v2.0-7c6af5?style=for-the-badge)
![AMD MI300X](https://img.shields.io/badge/AMD-MI300X%20GPU-e8294a?style=for-the-badge&logo=amd)
![ROCm](https://img.shields.io/badge/ROCm-6.1-e8294a?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11-3776ab?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

**An invisible AI speech coach that whispers your script through your earpiece,
listens to your delivery, evaluates it with LLMs on AMD GPUs, and corrects you in real time.**

**[Live Demo](https://lablab-ai-amd-developer-hackathon-rasospeak.hf.space)** • [Features](#-features) • [Architecture](#-architecture) • [Quick Start](#-quick-start)

</div>

---

## 🧠 What is RasoSpeak?

RasoSpeak is your **AI Partner / Secondary Brain** — an intelligent system that:

1. **Listens 24/7** and remembers everything you say
2. **Whispers your script** through your earpiece during presentations
3. **Evaluates your delivery** in real-time with LLM-powered analysis
4. **Corrects you silently** without the audience knowing
5. **Answers questions** on the fly (GPT/Claude/Gemini/Qwen)

### Use Cases
- 🎤 **Presentation Practice** — Practice speeches with real-time AI coaching
- ❓ **Instant Q&A** — Ask questions during practice (like ChatGPT in your ear)
- 🔍 **Live Information** — Search for facts, news, or definitions
- 📊 **Progress Tracking** — Analytics on your speech improvement
- 📝 **Document Memory** — Import PDFs, web pages, notes to your memory

---

## ✨ Features

### 🤖 14 Specialized AI Agents

| Agent | Function |
|-------|----------|
| **PartnerAgent** | Your AI partner — continuous listening, memory, reminders |
| **SharedMemoryAgent** | Unified brain — all AIs share this memory |
| **WakeWordAgent** | "Hey Raso" — voice wake word detection |
| **DocumentAgent** | Import docs — PDFs, URLs, text to memory |
| **NotificationAgent** | Phone notifications — SMS, Telegram, Push |
| **TranscriptionAgent** | Speech-to-text (Whisper Large v3) |
| **ScoringAgent** | Semantic speech evaluation (Qwen2.5-7B) |
| **CoachingAgent** | Personalized corrections (Qwen2.5-7B) |
| **SegmentationAgent** | Script chunking (Qwen2.5-3B) |
| **SessionMemoryAgent** | Session state & history |
| **QAAgent** | Real-time Q&A (GPT/Claude/Gemini/Qwen) |
| **SearchAgent** | Web search (Tavily/DuckDuckGo) |
| **RecordingAgent** | Audio & conversation recording |
| **AnalyticsAgent** | Session & user insights |

### 🎙️ Speech Coaching Loop
- Real-time audio streaming via WebSocket
- Three correction modes: **Silent** · **Hint** · **Full**
- Three strictness levels: **Lenient** · **Normal** · **Strict**
- Auto-skip after 4 failed attempts
- Early advance at 82% coverage

### ❓ Real-time Q&A
- Connect to **5 AI providers**: OpenAI GPT, Anthropic Claude, Google Gemini, Local Qwen
- Context-aware (uses your script as context)
- Multi-turn conversation support

### 🔍 Web Search
- Real-time information lookup via Tavily or DuckDuckGo
- Results + AI summary

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    BROWSER (index.html)                     │
│  js/app.js ──── WebSocket ──────────────────────────────┐   │
└─────────────────────────────────────────────────────────│───┘
                                                         │
                    WebSocket / HTTP API                   │
                                                         │
┌────────────────────────────────────────────────────────▼───┐
│              FastAPI Backend  (main.py)                    │
│         Hugging Face Space · AMD MI300X GPU                │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              AGENT PIPELINE (14 Agents)             │   │
│  │   PartnerAgent ← WakeWordAgent ← DocumentAgent       │   │
│  │   TranscriptionAgent ← ScoringAgent ← CoachingAgent   │   │
│  │   QAAgent ← SearchAgent ← SharedMemoryAgent           │   │
│  │   RecordingAgent ← AnalyticsAgent                    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Hugging Face Space (Recommended)

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
├── index.html                  ← Frontend entry point
├── styles.css                  ← Styling
├── app.js, ui.js, speech.js    ← Frontend JavaScript
├── nlp.js, state.js            ← NLP and state management
│
├── main.py                     ← FastAPI backend + WebSocket
├── app.py                      ← Gradio interface
│
├── agents/                     ← 14 AI agents
│   ├── base_agent.py
│   ├── partner_agent.py        ← Your AI partner
│   ├── shared_memory_agent.py  ← Unified brain
│   ├── wake_word_agent.py      ← "Hey Raso" detection
│   ├── transcription_agent.py ← Whisper
│   ├── scoring_agent.py        ← Qwen scoring
│   ├── coaching_agent.py       ← Qwen coaching
│   ├── segmentation_agent.py   ← Qwen chunking
│   ├── session_memory_agent.py
│   ├── document_agent.py       ← Import docs
│   ├── notification_agent.py   ← SMS/Telegram
│   ├── qa_agent.py             ← Multi-provider Q&A
│   ├── search_agent.py         ← Web search
│   ├── recording_agent.py      ← Audio recording
│   └── analytics_agent.py     ← Insights
│
├── config/
│   ├── settings.py             ← Configuration
│   └── prompts.py             ← LLM prompts
│
├── models/
│   └── schemas.py              ← Pydantic schemas
│
├── requirements.txt            ← Python dependencies
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
1. Project Title: RasoSpeak v2 - AI Speech Coach
2. Demo URL: Hugging Face Space
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
- [Hugging Face](https://huggingface.co) — Spaces hosting

---

<div align="center">

**RasoSpeak v2 — Your Secondary Brain & AI Partner.**

*Every great speaker deserves an invisible coach.*

</div>