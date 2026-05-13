"""RasoSpeak AI OS — Configuration"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    host: str = Field(default="localhost")
    port: int = Field(default=5432)
    name: str = Field(default="rasospeak")
    user: str = Field(default="rasospeak")
    password: str = Field(default="")
    pool_size: int = 10
    max_overflow: int = 20

    @property
    def url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class RedisSettings(BaseSettings):
    """Redis configuration."""

    host: str = Field(default="localhost")
    port: int = Field(default=6379)
    db: int = Field(default=0)
    password: Optional[str] = Field(default=None)
    ssl: bool = Field(default=False)

    @property
    def url(self) -> str:
        auth = f":{self.password}@" if self.password else ""
        ssl = "ssl" if self.ssl else "redis"
        return f"{ssl}://{auth}{self.host}:{self.port}/{self.db}"


class LLMSettings(BaseSettings):
    """LLM provider configuration."""

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    nvidia_api_key: str = ""
    google_api_key: str = ""
    deepseek_api_key: str = ""

    default_provider: str = "anthropic"
    default_model: str = "claude-3-5-sonnet-20241022"

    request_timeout: int = 60
    max_retries: int = 3


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # Application
    app_name: str = "RasoSpeak AI OS"
    app_version: str = "3.0.0"
    debug: bool = False
    environment: str = "production"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4

    # Security
    secret_key: str = Field(default="change-me-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    allowed_origins: str = "*"

    # Database
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)

    # Redis
    redis: RedisSettings = Field(default_factory=RedisSettings)

    # LLM
    llm: LLMSettings = Field(default_factory=LLMSettings)

    # Vector DB
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    embedding_model: str = "text-embedding-3-large"
    embedding_dimension: int = 1536

    # Temporal
    temporal_host: str = "localhost"
    temporal_port: int = 7233
    temporal_namespace: str = "rasospeak"

    # NATS
    nats_url: str = "nats://localhost:4222"

    # Observability
    otel_endpoint: str = "http://localhost:4317"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"

    # Rate limits
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000

    # Memory
    working_memory_ttl_seconds: int = 3600
    max_token_budget: int = 128_000


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
