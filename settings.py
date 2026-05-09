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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
