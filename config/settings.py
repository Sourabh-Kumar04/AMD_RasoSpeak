"""
RasoSpeak v2 — Configuration
AMD Developer Cloud endpoints, model names, ROCm settings.
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    # ── AMD HARDWARE ───────────────────────────────────
    AMD_DEVICE:    str = "cuda"   # ROCm exposes as "cuda" to PyTorch
    AMD_GPU_ID:    int = 0
    ROCM_VERSION:  str = "6.1"

    # ── vLLM SERVER (running on AMD MI300X) ───────────
    VLLM_HOST:     str = os.getenv("VLLM_HOST", "localhost")
    VLLM_PORT:     int = int(os.getenv("VLLM_PORT", "8001"))

    @property
    def VLLM_BASE_URL(self) -> str:
        return f"http://{self.VLLM_HOST}:{self.VLLM_PORT}/v1"

    # ── MODEL NAMES ────────────────────────────────────
    WHISPER_MODEL:      str = "large-v3"           # Whisper on ROCm
    SCORING_MODEL:      str = "Qwen/Qwen2.5-7B-Instruct"
    COACHING_MODEL:     str = "Qwen/Qwen2.5-7B-Instruct"
    SEGMENTATION_MODEL: str = "Qwen/Qwen2.5-3B-Instruct"   # smaller, faster

    # ── INFERENCE PARAMS ───────────────────────────────
    SCORING_MAX_TOKENS:      int   = 512
    COACHING_MAX_TOKENS:     int   = 768
    SEGMENTATION_MAX_TOKENS: int   = 2048
    LLM_TEMPERATURE:         float = 0.15   # low for deterministic scoring
    LLM_TIMEOUT_SECONDS:     int   = 15

    # ── WHISPER CONFIG ─────────────────────────────────
    WHISPER_DEVICE:        str   = "cuda"   # ROCm = cuda for PyTorch
    WHISPER_COMPUTE_TYPE:  str   = "float16"
    WHISPER_BEAM_SIZE:     int   = 5
    WHISPER_VAD_FILTER:    bool  = True     # voice activity detection

    # ── REDIS (for session state) ──────────────────────
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB:   int = 0

    # ── SERVER CONFIG ───────────────────────────────────
    port:       int = 8000
    log_level:  str = "info"

    # ── SESSION SETTINGS ───────────────────────────────
    MAX_SESSIONS:         int = 50
    SESSION_TTL_SECONDS:  int = 3600      # 1 hour
    MAX_HISTORY_SESSIONS: int = 20

    # ── SCORING THRESHOLDS ─────────────────────────────
    # Maps strict level (2/3/4) → minimum overall score to pass
    PASS_THRESHOLDS: dict = {
        2: 42,   # Lenient
        3: 55,   # Normal
        4: 68,   # Strict
    }

    # ── AUTO-SKIP ──────────────────────────────────────
    MAX_ATTEMPTS_BEFORE_SKIP: int = 4

    # ═══════════════════════════════════════════════════
    # Q&A AGENT - Multi-provider AI question answering
    # ═══════════════════════════════════════════════════
    QA_DEFAULT_PROVIDER: str = "qwen_local"  # openai | anthropic | google | xai | qwen_local

    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = "gpt-4o"

    # Anthropic
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # Google Gemini
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    GOOGLE_MODEL: str = "gemini-2.0-flash"

    # xAI Grok
    XAI_API_KEY: str = os.getenv("XAI_API_KEY", "")
    XAI_MODEL: str = "grok-2-1212"

    # Local Qwen (via vLLM)
    QA_MODEL: str = "Qwen/Qwen2.5-7B-Instruct"

    # ═══════════════════════════════════════════════════
    # SEARCH AGENT - Web search for real-time info
    # ═══════════════════════════════════════════════════
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    SERP_API_KEY: str = os.getenv("SERP_API_KEY", "")
    BRAVE_API_KEY: str = os.getenv("BRAVE_API_KEY", "")
    SEARCH_NUM_RESULTS: int = 5

    # ═══════════════════════════════════════════════════
    # RECORDING AGENT - Audio/conversation storage
    # ═══════════════════════════════════════════════════
    RECORDINGS_PATH: str = "./recordings"
    RECORD_AUDIO_ENABLED: bool = True
    RECORD_QA_ENABLED: bool = True
    RECORD_COACHING_ENABLED: bool = True

    # ═══════════════════════════════════════════════════
    # ANALYTICS AGENT - Session insights
    # ═══════════════════════════════════════════════════
    ANALYTICS_ENABLED: bool = True
    ANALYTICS_RETENTION_DAYS: int = 90

    # ═══════════════════════════════════════════════════
    # SHARED MEMORY AGENT - Unified brain for all AIs
    # ═══════════════════════════════════════════════════
    SHARED_MEMORY_PATH: str = "./memory"

    # ═══════════════════════════════════════════════════
    # DOCUMENT AGENT - Import documents to memory
    # ═══════════════════════════════════════════════════
    DOCUMENTS_PATH: str = "./memory/documents"

    # ═══════════════════════════════════════════════════
    # NOTIFICATION AGENT - Phone notifications
    # ═══════════════════════════════════════════════════
    NOTIFICATION_WEBHOOK_URL: str = os.getenv("NOTIFICATION_WEBHOOK_URL", "")

    # Twilio (SMS)
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_PHONE_FROM: str = os.getenv("TWILIO_PHONE_FROM", "")

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Pushover
    PUSHOVER_TOKEN: str = os.getenv("PUSHOVER_TOKEN", "")
    PUSHOVER_USER_KEY: str = os.getenv("PUSHOVER_USER_KEY", "")

    # Email (SMTP)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = 587
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
