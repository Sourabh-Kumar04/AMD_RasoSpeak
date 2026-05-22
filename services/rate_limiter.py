"""
RasoSpeak OS — Rate Limiting with Redis Support
Production-grade rate limiting that works across multiple instances
"""

import time
import logging
from typing import Optional
from dataclasses import dataclass

import redis.asyncio as redis
from config.settings import settings

log = logging.getLogger("rasospeak.ratelimit")


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests: int       # Max requests per window
    window_seconds: int # Window size in seconds
    burst: int          # Additional burst allowance


# Default limits
DEFAULT_LIMITS = {
    "default": RateLimitConfig(requests=100, window_seconds=60, burst=20),
    "voice": RateLimitConfig(requests=50, window_seconds=60, burst=10),
    "llm": RateLimitConfig(requests=30, window_seconds=60, burst=5),
    "auth": RateLimitConfig(requests=5, window_seconds=60, burst=2),
}


class RedisRateLimiter:
    """
    Redis-backed rate limiter for distributed deployments.
    Uses sliding window algorithm.
    """

    def __init__(self, redis_url: str = None):
        self._redis: Optional[redis.Redis] = None
        self._redis_url = redis_url or f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
        self._enabled = False

    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            self._redis = redis.from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
            self._enabled = True
            log.info("✅ Redis rate limiter connected")
        except Exception as e:
            log.warning(f"Redis not available, falling back to in-memory: {e}")
            self._enabled = False

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._redis:
            await self._redis.close()

    async def check_rate_limit(
        self,
        key: str,
        limit: RateLimitConfig = None,
    ) -> tuple[bool, dict]:
        """
        Check if request is within rate limit.
        Returns (allowed, info_dict)
        """
        limit = limit or DEFAULT_LIMITS["default"]

        if not self._enabled:
            # Fallback to in-memory (single instance only)
            return self._check_memory(key, limit)

        # Redis sliding window
        now = time.time()
        window_key = f"ratelimit:{key}"
        window_start = now - limit.window_seconds

        pipe = self._redis.pipeline()
        # Remove old entries
        pipe.zremrangebyscore(window_key, 0, window_start)
        # Count current requests
        pipe.zcard(window_key)
        # Add current request
        pipe.zadd(window_key, {str(now): now})
        # Set expiry
        pipe.expire(window_key, limit.window_seconds)

        results = await pipe.execute()
        request_count = results[1]

        allowed = request_count < limit.requests
        remaining = max(0, limit.requests - request_count - 1)
        reset_time = int(now + limit.window_seconds)

        return allowed, {
            "allowed": allowed,
            "limit": limit.requests,
            "remaining": remaining,
            "reset": reset_time,
        }

    def _check_memory(self, key: str, limit: RateLimitConfig) -> tuple[bool, dict]:
        """In-memory fallback (single instance only)."""
        now = time.time()

        if not hasattr(self, "_memory"):
            self._memory = {}

        if key not in self._memory:
            self._memory[key] = []

        # Clean old entries
        self._memory[key] = [t for t in self._memory[key] if now - t < limit.window_seconds]

        request_count = len(self._memory[key])
        allowed = request_count < limit.requests

        if allowed:
            self._memory[key].append(now)

        return allowed, {
            "allowed": allowed,
            "limit": limit.requests,
            "remaining": max(0, limit.requests - request_count - 1),
            "reset": int(now + limit.window_seconds),
        }


# Singleton
rate_limiter = RedisRateLimiter()


# ── MIDDLEWARE ─────────────────────────────────────────

async def rate_limit_middleware(request, call_next):
    """FastAPI middleware for rate limiting."""
    from fastapi import HTTPException

    # Get user identifier
    user_id = "anonymous"
    if request.headers.get("authorization"):
        # Extract from JWT if present
        try:
            import jwt
            token = request.headers["authorization"].replace("Bearer ", "")
            payload = jwt.decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
            user_id = payload.get("user_id", "anonymous")
        except:
            pass

    # Determine limit type
    path = request.url.path
    if "/voice/" in path:
        limit_type = "voice"
    elif "/llm/" in path or "/raso/ask" in path:
        limit_type = "llm"
    elif "/auth/" in path:
        limit_type = "auth"
    else:
        limit_type = "default"

    limit = DEFAULT_LIMITS.get(limit_type, DEFAULT_LIMITS["default"])
    allowed, info = await rate_limiter.check_rate_limit(f"{user_id}:{limit_type}", limit)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {info['reset'] - int(time.time())} seconds."
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(info["limit"])
    response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
    response.headers["X-RateLimit-Reset"] = str(info["reset"])

    return response