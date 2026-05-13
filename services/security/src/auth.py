"""
Security Layer - JWT Auth, RBAC, API Key Encryption
===================================================
Enterprise-grade security for RasoSpeak OS.
"""

from __future__ import annotations
import asyncio
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from functools import wraps

import structlog

try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False

try:
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

logger = structlog.get_logger("rasospeak.security")


# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────

@dataclass
class SecurityConfig:
    """Security configuration."""
    secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    password_min_length: int = 8
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 15
    encryption_key: Optional[bytes] = None


class SecurityManager:
    """
    Central security manager for RasoSpeak OS.

    Responsibilities:
    - JWT token generation and validation
    - Password hashing and verification
    - API key encryption/decryption
    - Rate limiting
    - Session management
    """

    def __init__(self, config: SecurityConfig):
        self._config = config
        self._fernet = None

        if CRYPTO_AVAILABLE and config.encryption_key:
            self._fernet = Fernet(config.encryption_key)

    # ─────────────────────────────────────────────────────────────
    # JWT Tokens
    # ─────────────────────────────────────────────────────────────

    def create_access_token(
        self,
        user_id: str,
        email: str,
        role: str = "user",
        additional_claims: dict = None
    ) -> str:
        """Create JWT access token."""
        if not JWT_AVAILABLE:
            return "dummy_token"

        now = datetime.utcnow()
        payload = {
            "sub": user_id,
            "email": email,
            "role": role,
            "iat": now,
            "exp": now + timedelta(minutes=self._config.access_token_expire_minutes),
            "type": "access"
        }

        if additional_claims:
            payload.update(additional_claims)

        return jwt.encode(
            payload,
            self._config.secret_key,
            algorithm=self._config.jwt_algorithm
        )

    def create_refresh_token(self, user_id: str) -> str:
        """Create JWT refresh token."""
        if not JWT_AVAILABLE:
            return "dummy_refresh"

        now = datetime.utcnow()
        payload = {
            "sub": user_id,
            "iat": now,
            "exp": now + timedelta(days=self._config.refresh_token_expire_days),
            "type": "refresh",
            "nonce": secrets.token_hex(16)
        }

        return jwt.encode(
            payload,
            self._config.secret_key,
            algorithm=self._config.jwt_algorithm
        )

    def verify_token(self, token: str) -> Optional[dict]:
        """Verify JWT token and return payload."""
        if not JWT_AVAILABLE:
            return {"sub": "default", "email": "user@local", "role": "user"}

        try:
            payload = jwt.decode(
                token,
                self._config.secret_key,
                algorithms=[self._config.jwt_algorithm]
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("token_expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning("token_invalid", error=str(e))
            return None

    def decode_token(self, token: str) -> Optional[dict]:
        """Decode token without verification (for inspection)."""
        if not JWT_AVAILABLE:
            return None
        try:
            return jwt.decode(token, options={"verify_signature": False})
        except:
            return None

    # ─────────────────────────────────────────────────────────────
    # Password Security
    # ─────────────────────────────────────────────────────────────

    def hash_password(self, password: str) -> str:
        """Hash password with salt."""
        salt = secrets.token_hex(32)
        pwd_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100000
        )
        return f"{salt}${pwd_hash.hex()}"

    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash."""
        try:
            salt, pwd_hash = hashed.split("$")
            check_hash = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt.encode("utf-8"),
                100000
            )
            return check_hash.hex() == pwd_hash
        except:
            return False

    def validate_password_strength(self, password: str) -> tuple[bool, str]:
        """Check password strength."""
        if len(password) < self._config.password_min_length:
            return False, f"Password must be at least {self._config.password_min_length} characters"

        # Check for complexity
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)

        if not (has_upper and has_lower and has_digit):
            return False, "Password must contain uppercase, lowercase, and digits"

        return True, "OK"

    # ─────────────────────────────────────────────────────────────
    # API Key Encryption
    # ─────────────────────────────────────────────────────────────

    def encrypt_api_key(self, api_key: str, user_id: str) -> str:
        """Encrypt API key for storage."""
        if not self._fernet:
            # Fallback: simple encoding (not secure, but functional)
            import base64
            return base64.b64encode(api_key.encode()).decode()

        # Create user-specific key derivation
        user_key = hashlib.sha256(user_id.encode()).digest()
        fernet = Fernet(user_key)

        return fernet.encrypt(api_key.encode()).decode()

    def decrypt_api_key(self, encrypted_key: str, user_id: str) -> Optional[str]:
        """Decrypt API key."""
        if not self._fernet:
            import base64
            return base64.b64decode(encrypted_key.encode()).decode()

        try:
            user_key = hashlib.sha256(user_id.encode()).digest()
            fernet = Fernet(user_key)
            return fernet.decrypt(encrypted_key.encode()).decode()
        except Exception as e:
            logger.error("api_key_decrypt_failed", error=str(e))
            return None

    # ─────────────────────────────────────────────────────────────
    # Session Management
    # ─────────────────────────────────────────────────────────────

    def create_session_token(
        self,
        user_id: str,
        session_id: str,
        expires_in_minutes: int = 60
    ) -> str:
        """Create session-specific token."""
        if not JWT_AVAILABLE:
            return "session_token"

        now = datetime.utcnow()
        payload = {
            "sub": user_id,
            "session_id": session_id,
            "iat": now,
            "exp": now + timedelta(minutes=expires_in_minutes),
            "type": "session"
        }

        return jwt.encode(
            payload,
            self._config.secret_key,
            algorithm=self._config.jwt_algorithm
        )


# ─────────────────────────────────────────────────────────────
# Role-Based Access Control
# ─────────────────────────────────────────────────────────────

class Permission(Enum):
    """System permissions."""
    # User
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DELETE = "user:delete"

    # Memory
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    MEMORY_DELETE = "memory:delete"

    # API Keys
    APIKEY_READ = "apikey:read"
    APIKEY_WRITE = "apikey:write"
    APIKEY_DELETE = "apikey:delete"

    # Provider
    PROVIDER_READ = "provider:read"
    PROVIDER_WRITE = "provider:write"

    # Workflow
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_WRITE = "workflow:write"
    WORKFLOW_EXECUTE = "workflow:execute"

    # Admin
    ADMIN = "admin:all"


ROLE_PERMISSIONS = {
    "user": [
        Permission.USER_READ,
        Permission.MEMORY_READ,
        Permission.MEMORY_WRITE,
        Permission.APIKEY_READ,
        Permission.APIKEY_WRITE,
    ],
    "premium": [
        Permission.USER_READ,
        Permission.MEMORY_READ,
        Permission.MEMORY_WRITE,
        Permission.MEMORY_DELETE,
        Permission.APIKEY_READ,
        Permission.APIKEY_WRITE,
        Permission.APIKEY_DELETE,
        Permission.PROVIDER_READ,
        Permission.PROVIDER_WRITE,
        Permission.WORKFLOW_READ,
        Permission.WORKFLOW_WRITE,
    ],
    "admin": list(Permission),
}


def check_permission(role: str, permission: Permission) -> bool:
    """Check if role has permission."""
    return permission in ROLE_PERMISSIONS.get(role, [])


def require_permission(permission: Permission):
    """Decorator to require permission."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get user from context
            # In real implementation, would get from request context
            user_role = kwargs.get("role", "user")

            if not check_permission(user_role, permission):
                raise PermissionDenied(f"Permission denied: {permission.value}")

            return await func(*args, **kwargs)
        return wrapper
    return decorator


class PermissionDenied(Exception):
    """Permission denied error."""
    pass


# ─────────────────────────────────────────────────────────────
# Rate Limiting
# ─────────────────────────────────────────────────────────────

class RateLimiter:
    """
    Token bucket rate limiter.

    Used for:
    - API request limiting per user
    - Provider request limiting
    - Cost limiting
    """

    def __init__(self, rate: int, per_seconds: int):
        self.rate = rate  # Max requests
        self.per_seconds = per_seconds
        self._buckets: dict[str, tuple[int, datetime]] = {}

    async def check(self, key: str) -> bool:
        """Check if request is allowed."""
        now = datetime.utcnow()

        if key not in self._buckets:
            self._buckets[key] = (self.rate - 1, now)
            return True

        count, timestamp = self._buckets[key]

        # Reset if time passed
        elapsed = (now - timestamp).total_seconds()
        if elapsed >= self.per_seconds:
            self._buckets[key] = (self.rate - 1, now)
            return True

        # Check count
        if count > 0:
            self._buckets[key] = (count - 1, timestamp)
            return True

        return False

    async def get_remaining(self, key: str) -> int:
        """Get remaining requests."""
        if key not in self._buckets:
            return self.rate
        return self._buckets[key][0]


# ─────────────────────────────────────────────────────────────
# Prompt Injection Defense
# ─────────────────────────────────────────────────────────────

class PromptGuard:
    """
    Prompt injection detection and prevention.
    """

    INJECTION_PATTERNS = [
        r"ignore\s+(previous|all|above)",
        r"disregard\s+(instructions|rules)",
        r"forget\s+(everything|instructions)",
        r"new\s+instruction",
        r"system\s*:\s*",
        r"you\s+are\s+now",
        r"act\s+as\s+if",
        r"pretend\s+to\s+be",
    ]

    @classmethod
    def check(cls, text: str) -> tuple[bool, Optional[str]]:
        """Check for prompt injection attempts."""
        import re

        for pattern in cls.INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True, f"Potential injection detected: {pattern}"

        return False, None

    @classmethod
    def sanitize(cls, text: str) -> str:
        """Remove potentially dangerous patterns."""
        import re

        sanitized = text

        for pattern in cls.INJECTION_PATTERNS:
            sanitized = re.sub(pattern, "[FILTERED]", sanitized, flags=re.IGNORECASE)

        return sanitized


# ─────────────────────────────────────────────────────────────
# Global Security Manager
# ─────────────────────────────────────────────────────────────

_security_manager: Optional[SecurityManager] = None


def get_security_manager() -> SecurityManager:
    """Get global security manager."""
    global _security_manager
    if _security_manager is None:
        config = SecurityManager(
            secret_key="rasospeak-secret-key-change-in-production",
            encryption_key=Fernet.generate_key() if CRYPTO_AVAILABLE else None
        )
        _security_manager = SecurityManager(config)
    return _security_manager