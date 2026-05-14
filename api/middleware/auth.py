"""
API authentication middleware.
Supports API key header, JWT bearer tokens, and role-based access control.
"""

import os
import time
from typing import Optional
from datetime import datetime, timedelta

import jwt
from fastapi import HTTPException, Security, Depends
from fastapi.security import APIKeyHeader, HTTPBearer
from config.settings import settings
from dataclasses import dataclass

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET", "rasospeak-dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


# Roles
class Role:
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


@dataclass
class User:
    user_id: str
    role: str = Role.USER
    email: Optional[str] = None


async def verify_api_key(api_key: str = Security(_api_key_header)):
    """Verify API key from X-API-Key header. Allows requests if no key is configured."""
    if not settings.api_key:
        return None  # Auth disabled when no key is set
    if api_key == settings.api_key:
        return api_key
    raise HTTPException(status_code=401, detail="Invalid API key")


async def optional_api_key(api_key: str = Security(_api_key_header)):
    """Optional API key — allows unauthenticated requests but validates if key is present."""
    if api_key and settings.api_key and api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


def get_agent(agents: dict, name: str):
    """Get an agent by name, raising 503 if unavailable."""
    agent = agents.get(name)
    if agent is None:
        raise HTTPException(status_code=503, detail=f"Agent '{name}' is not available")
    return agent


# ──────────────────────────────────────────────────────────────────────────────
# JWT Authentication
# ──────────────────────────────────────────────────────────────────────────────

async def get_current_user(credentials = Security(_bearer)) -> User:
    """Get current user from JWT token or return guest."""
    if not credentials:
        return User(user_id="guest", role=Role.GUEST)

    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return User(
            user_id=payload.get("user_id", "unknown"),
            role=payload.get("role", Role.USER)
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def create_token(user_id: str, role: str = Role.USER) -> str:
    """Create JWT access token."""
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": int(expire.timestamp())
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def require_role(required_role: str):
    """Dependency that requires a specific role."""
    async def role_checker(user: User = Depends(get_current_user)):
        role_hierarchy = {Role.ADMIN: 3, Role.USER: 2, Role.GUEST: 1}
        if role_hierarchy.get(user.role, 0) < role_hierarchy.get(required_role, 0):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return role_checker


# Rate limiting
_user_requests: dict[str, list] = {}


def check_rate_limit(user_id: str, max_requests: int = 100, window_seconds: int = 60) -> bool:
    """Check if user has exceeded rate limit."""
    now = time.time()
    if user_id not in _user_requests:
        _user_requests[user_id] = []
    _user_requests[user_id] = [t for t in _user_requests[user_id] if now - t < window_seconds]
    if len(_user_requests[user_id]) >= max_requests:
        return False
    _user_requests[user_id].append(now)
    return True
