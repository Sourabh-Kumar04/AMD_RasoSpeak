"""
RasoSpeak OS — Security Layer
Prompt injection protection, memory sanitization, input validation
"""

import re
import logging
from typing import Optional
from dataclasses import dataclass

log = logging.getLogger("rasospeak.security")


@dataclass
class SecurityResult:
    """Result of security check."""
    allowed: bool
    sanitized: str
    reason: Optional[str] = None
    blocked: bool = False


class SecurityLayer:
    """
    Security layer for:
    - Prompt injection detection
    - Memory sanitization
    - Input validation
    - Output filtering
    """

    # Patterns that indicate prompt injection attempts
    INJECTION_PATTERNS = [
        # Classic jailbreak patterns
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|rules?|commands?)",
        r"forget\s+(everything|all)\s+(you|I)\s+(told|said|know)",
        r"(you\s+are|act\s+as|pretend\s+to\s+be)\s+(a\s+)?different",
        r"system\s*:\s*",
        r"assistant\s*:\s*",
        # Role playing jailbreaks
        r"roleplay\s+as\s+",
        r"play\s+the\s+role\s+of",
        # Instruction override
        r"new\s+instructions?",
        r"override\s+(your\s+)?",
        r"(do|perform)\s+anything",
        # DAN-style (Do Anything Now)
        r"\bDAN\b",
        r"developer\s+mode",
        r"jailbreak",
        # Unicode obfuscation attempts
        r"[​‌‍]",  # Zero-width characters
        # Base64 encoded attempts
        r"(?:base64|b64)[:=]",
    ]

    # Compiled patterns for performance
    _injection_regex = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)

    # Dangerous output patterns to filter
    DANGEROUS_OUTPUT_PATTERNS = [
        r"(?:api_key|apikey|secret)[_\s]*[:=]\s*[\w-]{20,}",
        r"password[:=]\s*\S+",
        r"eval\s*\(",
        r"exec\s*\(",
        r"__import__\s*\(",
        r"<script[^>]*>",
        r"javascript:",
    ]

    _dangerous_regex = re.compile("|".join(DANGEROUS_OUTPUT_PATTERNS), re.IGNORECASE)

    def __init__(self):
        self._blocked_count = 0
        self._sanitized_count = 0

    def check_input(self, text: str, user_context: str = "") -> SecurityResult:
        """
        Check user input for injection attempts.
        Returns sanitized version with blocking if needed.
        """
        if not text:
            return SecurityResult(allowed=True, sanitized="", reason="empty")

        # Check for injection patterns
        matches = self._injection_regex.findall(text)
        if matches:
            # Found potential injection - sanitize but don't block completely
            # Instead, escape the dangerous parts
            sanitized = self._sanitize_injection(text)
            self._blocked_count += 1

            log.warning(f"Prompt injection detected and sanitized: {text[:50]}...")

            return SecurityResult(
                allowed=True,
                sanitized=sanitized,
                reason="injection_detected_sanitized",
                blocked=False,
            )

        # Additional context-aware checks
        if user_context:
            # Check if input tries to override system context
            if "system:" in text.lower() and "i am" in text.lower():
                sanitized = text.replace("system:", "user notes:")
                return SecurityResult(
                    allowed=True,
                    sanitized=sanitized,
                    reason="system_override_sanitized",
                )

        self._sanitized_count += 1
        return SecurityResult(allowed=True, sanitized=text)

    def _sanitize_injection(self, text: str) -> str:
        """Sanitize injection attempts by escaping dangerous patterns."""
        # Replace potential injection markers
        sanitized = text

        # Replace "ignore all" type patterns
        sanitized = re.sub(
            r"ignore\s+(all\s+)?(previous|prior|above)",
            "[NOTE: This instruction was ignored]",
            sanitized,
            flags=re.IGNORECASE,
        )

        # Replace "forget everything" patterns
        sanitized = re.sub(
            r"forget\s+(everything|all\s+you\s+know)",
            "[NOTE: Cannot forget learned knowledge]",
            sanitized,
            flags=re.IGNORECASE,
        )

        # Replace roleplay attempts
        sanitized = re.sub(
            r"(roleplay|act\s+as|pretend)\s+(as\s+)?",
            "[NOTE: Function: ",
            sanitized,
            flags=re.IGNORECASE,
        )

        # Remove zero-width characters
        sanitized = sanitized.replace("​", "").replace("‌", "").replace("‍", "")

        return sanitized

    def check_memory_input(self, memory_content: str) -> SecurityResult:
        """
        Check memory content before storing.
        Prevents memory poisoning attacks.
        """
        if not memory_content:
            return SecurityResult(allowed=True, sanitized="")

        # Check for injection patterns
        result = self.check_input(memory_content)
        if not result.allowed:
            return result

        # Additional checks for memory-specific threats

        # Check for encoded commands that might execute later
        if re.search(r"(?:base64|b64|encode)[:=][A-Za-z0-9+/=]{20,}", memory_content):
            log.warning("Potential encoded content in memory - allowing but flagging")

        # Check for suspicious patterns that could manipulate future behavior
        if "always" in memory_content.lower() and "never" in memory_content.lower():
            # Could be an attempt to set absolute rules
            log.warning("Absolute rule attempt in memory - allowing but flagging")

        return result

    def filter_output(self, text: str) -> str:
        """
        Filter dangerous content from LLM output.
        """
        if not text:
            return text

        # Check for dangerous patterns
        matches = self._dangerous_regex.findall(text)
        if matches:
            log.warning(f"Dangerous output detected: {matches}")
            # Mask sensitive information
            text = re.sub(
                r"(api_key|apikey|secret)[_\s]*[:=]\s*[\w-]{20,}",
                r"\1: [REDACTED]",
                text,
                flags=re.IGNORECASE,
            )

            text = re.sub(
                r"password[:=]\s*\S+",
                "password: [REDACTED]",
                text,
                flags=re.IGNORECASE,
            )

            # Remove script tags
            text = re.sub(r"<script[^>]*>", "[script removed]", text, flags=re.IGNORECASE)
            text = re.sub(r"javascript:", "[javascript removed]", text, flags=re.IGNORECASE)

        return text

    def validate_user_id(self, user_id: str) -> bool:
        """Validate user ID format."""
        if not user_id:
            return False

        # Must be alphanumeric with limited special chars
        return bool(re.match(r"^[a-zA-Z0-9_-]{1,64}$", user_id))

    def get_stats(self) -> dict:
        """Get security stats."""
        return {
            "blocked_count": self._blocked_count,
            "sanitized_count": self._sanitized_count,
            "total_processed": self._blocked_count + self._sanitized_count,
        }


# Singleton
security_layer = SecurityLayer()


# ── DECORATOR FOR ROUTE PROTECTION ─────────────────────

def sanitize_input(func):
    """Decorator to sanitize input to route handlers."""
    import functools

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Get the request/input
        for key, value in kwargs.items():
            if isinstance(value, str) and len(value) > 0:
                result = security_layer.check_input(value)
                kwargs[key] = result.sanitized

        return await func(*args, **kwargs)

    return wrapper