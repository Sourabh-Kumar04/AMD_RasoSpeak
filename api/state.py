"""
Shared application state — the single source of truth for the global agents dict.
Avoids circular imports between main.py and router modules.
"""

import secrets
from typing import Any

from slowapi import Limiter

# Populated during app startup (lifespan)
agents: dict[str, Any] = {}

# Rate limiter — created here so routers can import it at module load time.
# main.py reuses this same instance (avoids duplicate limiters).
def _get_remote_ip(request):
    if request.client:
        forwarded = request.headers.get("X-Forwarded-For", "").split(",")
        if forwarded and forwarded[0].strip():
            return forwarded[0].strip()
        return request.client.host
    return "127.0.0.1"

limiter = Limiter(key_func=_get_remote_ip)

# WebSocket session token storage
_ws_session_tokens: dict[str, str] = {}


def generate_ws_token(session_id: str) -> str:
    """Generate and store an HMAC token for a session."""
    secret = secrets.token_hex(32)
    _ws_session_tokens[session_id] = secret
    return secret


def validate_ws_token(session_id: str, token: str) -> bool:
    """Validate a WebSocket connection token against stored session."""
    stored = _ws_session_tokens.get(session_id)
    if not stored or not token:
        return False
    return secrets.compare_digest(stored, token)
