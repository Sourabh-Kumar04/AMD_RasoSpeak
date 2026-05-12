"""
API authentication middleware.
Supports API key header and optional JWT bearer tokens.
"""

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPBearer
from config.settings import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)


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
