"""
RasoSpeak AI OS — Shared Python Package
======================================
Common utilities shared across all services.
"""

__version__ = "3.0.0"

from .config import Settings, get_settings
from .logging import setup_logging, get_logger
from .errors import (
    RasoSpeakError,
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    RateLimitError,
    ProviderError,
    CircuitBreakerOpenError,
)
from .types import *
from .utils import *

__all__ = [
    "__version__",
    "Settings",
    "get_settings",
    "setup_logging",
    "get_logger",
    "RasoSpeakError",
    "AuthenticationError",
    "AuthorizationError",
    "NotFoundError",
    "RateLimitError",
    "ProviderError",
    "CircuitBreakerOpenError",
]
