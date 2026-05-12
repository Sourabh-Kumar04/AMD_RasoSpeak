"""
RasoSpeak v2 — Configuration

No GPU required - runs on 4GB RAM using external APIs.
Supports: Google Gemini, NVIDIA NIM, OpenAI, Anthropic,
HuggingFace, OpenRouter, OpenCode, xAI, DeepSeek.
"""

import os
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.

    All settings can be overridden via .env file or environment variables.
    Sensitive values (API keys) should be set via environment.

    Attributes:
        default_provider: Primary LLM provider to use.
        google_api_key: Google AI API key for Gemini.
        openai_api_key: OpenAI API key for GPT models.
        anthropic_api_key: Anthropic API key for Claude.
        etc.
    """

    # ── DEFAULT LLM PROVIDER ─────────────────────────────
    default_provider: str = os.getenv("DEFAULT_PROVIDER", "nvidia")

    # ── GOOGLE GEMINI ───────────────────────────────────
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    google_model: str = os.getenv("GOOGLE_MODEL", "gemini-2.0-flash")
    google_max_tokens: int = 8192
    google_temperature: float = 0.15

    # ── NVIDIA NIM ───────────────────────────────────────
    nvidia_api_key: str = os.getenv("NVIDIA_API_KEY", "").strip()
    nvidia_api_url: str = os.getenv(
        "NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1"
    )
    nvidia_model: str = os.getenv(
        "NVIDIA_MODEL", "meta/llama-3.1-70b-instruct"
    )
    nvidia_max_tokens: int = 4096
    nvidia_temperature: float = 0.15

    # ── OPENAI (ChatGPT) ─────────────────────────────────
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_api_url: str = os.getenv(
        "OPENAI_API_URL", "https://api.openai.com/v1"
    )
    openai_max_tokens: int = 4096
    openai_temperature: float = 0.15

    # ── ANTHROPIC (Claude) ───────────────────────────────
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv(
        "ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"
    )
    anthropic_max_tokens: int = 4096
    anthropic_temperature: float = 0.15

    # ── HUGGINGFACE ─────────────────────────────────────
    hf_api_key: str = os.getenv("HF_API_KEY", "")
    hf_model: str = os.getenv("HF_MODEL", "meta-llama/Llama-3.2-1B-Instruct")
    hf_max_tokens: int = 2048
    hf_temperature: float = 0.15

    # ── OPENROUTER (80+ models) ──────────────────────────
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv(
        "OPENROUTER_MODEL", "google/gemini-2.0-flash"
    )
    openrouter_max_tokens: int = 4096
    openrouter_temperature: float = 0.15

    # ── OPENCODE ─────────────────────────────────────────
    opencode_api_key: str = os.getenv("OPENCODE_API_KEY", "")
    opencode_model: str = os.getenv("OPENCODE_MODEL", "opencode")
    opencode_api_url: str = os.getenv(
        "OPENCODE_API_URL", "https://api.opencode.ai/v1"
    )
    opencode_max_tokens: int = 4096
    opencode_temperature: float = 0.15

    # ── XAI (Grok) ──────────────────────────────────────
    xai_api_key: str = os.getenv("XAI_API_KEY", "")
    xai_model: str = os.getenv("XAI_MODEL", "grok-2-1212")
    xai_max_tokens: int = 4096
    xai_temperature: float = 0.15

    # ── DEEPSEEK ─────────────────────────────────────────
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    deepseek_api_url: str = os.getenv(
        "DEEPSEEK_API_URL", "https://api.deepseek.com/v1"
    )
    deepseek_max_tokens: int = 4096
    deepseek_temperature: float = 0.15

    # ── TRANSCRIPTION ────────────────────────────────────
    transcription_provider: str = os.getenv(
        "TRANSCRIPTION_PROVIDER", "webspeech"
    )
    openai_whisper_api_key: str = os.getenv("OPENAI_WHISPER_API_KEY", "")

    # ── SEARCH ───────────────────────────────────────────
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    serp_api_key: str = os.getenv("SERP_API_KEY", "")
    brave_api_key: str = os.getenv("BRAVE_API_KEY", "")
    search_num_results: int = 5

    # ── NOTIFICATIONS ────────────────────────────────────
    notification_webhook_url: str = os.getenv("NOTIFICATION_WEBHOOK_URL", "")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    pushover_token: str = os.getenv("PUSHOVER_TOKEN", "")
    pushover_user_key: str = os.getenv("PUSHOVER_USER_KEY", "")
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = 587
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_phone_from: str = os.getenv("TWILIO_PHONE_FROM", "")

    # ── SERVER ────────────────────────────────────────────
    port: int = int(os.getenv("PORT", "7860"))
    log_level: str = "info"

    # ── SECURITY ──────────────────────────────────────────
    allowed_origins: str = os.getenv("ALLOWED_ORIGINS", "*")
    api_key: str = os.getenv("API_KEY", "")

    # ── SESSIONS ─────────────────────────────────────────
    max_sessions: int = 50
    session_ttl_seconds: int = 3600
    max_history_sessions: int = 20

    # ── REDIS (optional) ────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # ── LLM BACKEND (optional vLLM) ──────────────────────
    vllm_base_url: str = ""
    llm_timeout_seconds: int = 60

    # ── SEGMENTATION ─────────────────────────────────────
    segmentation_model: str = "Qwen/Qwen2.5-7B-Instruct"
    segmentation_max_tokens: int = 512

    # ── QA MODEL ──────────────────────────────────────────
    qa_model: str = "Qwen/Qwen2.5-7B-Instruct"

    # ── STORAGE ──────────────────────────────────────────
    shared_memory_path: str = "./memory"
    documents_path: str = "./memory/documents"
    recordings_path: str = "./recordings"

    # ── SCORING THRESHOLDS ───────────────────────────────
    pass_thresholds: dict = {2: 42, 3: 55, 4: 68}
    max_attempts_before_skip: int = 4

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def get_provider_config(self, provider: str) -> dict:
        """Get configuration dict for a specific provider, with sanitized API keys."""
        config = self._get_provider_config_raw(provider)
        if config and "api_key" in config and config["api_key"]:
            config["api_key"] = config["api_key"].strip()
        return config

    def _get_provider_config_raw(self, provider: str) -> dict:
        """Internal method - raw config without sanitization."""
        configs = {
            "google": {
                "api_key": self.google_api_key,
                "model": self.google_model,
                "max_tokens": self.google_max_tokens,
                "temperature": self.google_temperature,
            },
            "nvidia": {
                "api_key": self.nvidia_api_key,
                "base_url": self.nvidia_api_url,
                "model": self.nvidia_model,
                "max_tokens": self.nvidia_max_tokens,
                "temperature": self.nvidia_temperature,
            },
            "openai": {
                "api_key": self.openai_api_key,
                "base_url": self.openai_api_url,
                "model": self.openai_model,
                "max_tokens": self.openai_max_tokens,
                "temperature": self.openai_temperature,
            },
            "anthropic": {
                "api_key": self.anthropic_api_key,
                "model": self.anthropic_model,
                "max_tokens": self.anthropic_max_tokens,
                "temperature": self.anthropic_temperature,
            },
            "huggingface": {
                "api_key": self.hf_api_key,
                "model": self.hf_model,
                "max_tokens": self.hf_max_tokens,
                "temperature": self.hf_temperature,
            },
            "openrouter": {
                "api_key": self.openrouter_api_key,
                "model": self.openrouter_model,
                "max_tokens": self.openrouter_max_tokens,
                "temperature": self.openrouter_temperature,
            },
            "opencode": {
                "api_key": self.opencode_api_key,
                "base_url": self.opencode_api_url,
                "model": self.opencode_model,
                "max_tokens": self.opencode_max_tokens,
                "temperature": self.opencode_temperature,
            },
            "xai": {
                "api_key": self.xai_api_key,
                "model": self.xai_model,
                "max_tokens": self.xai_max_tokens,
                "temperature": self.xai_temperature,
            },
            "deepseek": {
                "api_key": self.deepseek_api_key,
                "base_url": self.deepseek_api_url,
                "model": self.deepseek_model,
                "max_tokens": self.deepseek_max_tokens,
                "temperature": self.deepseek_temperature,
            },
        }
        return configs.get(provider, {})


settings = Settings()