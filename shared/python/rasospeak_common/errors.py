"""RasoSpeak AI OS — Error Types"""

from __future__ import annotations


class RasoSpeakError(Exception):
    """Base exception for all RasoSpeak errors."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR", details: dict = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)


class AuthenticationError(RasoSpeakError):
    """Authentication failed."""

    def __init__(self, message: str = "Authentication failed", details: dict = None):
        super().__init__(message, code="AUTH_FAILED", details=details)


class AuthorizationError(RasoSpeakError):
    """Authorization denied."""

    def __init__(self, message: str = "Access denied", details: dict = None):
        super().__init__(message, code="AUTHZ_DENIED", details=details)


class NotFoundError(RasoSpeakError):
    """Resource not found."""

    def __init__(self, resource: str, identifier: str):
        super().__init__(
            message=f"{resource} not found: {identifier}",
            code="NOT_FOUND",
            details={"resource": resource, "identifier": identifier},
        )


class RateLimitError(RasoSpeakError):
    """Rate limit exceeded."""

    def __init__(self, retry_after: int = 60):
        super().__init__(
            message=f"Rate limit exceeded. Retry after {retry_after} seconds.",
            code="RATE_LIMITED",
            details={"retry_after": retry_after},
        )


class ProviderError(RasoSpeakError):
    """LLM provider error."""

    def __init__(self, provider: str, message: str, details: dict = None):
        super().__init__(
            message=f"{provider} error: {message}",
            code="PROVIDER_ERROR",
            details={**({"provider": provider}, **(details or {}))},
        )


class CircuitBreakerOpenError(ProviderError):
    """Circuit breaker is open."""

    def __init__(self, provider: str):
        super().__init__(
            provider=provider,
            message="Circuit breaker is open",
            details={"circuit": "open"},
        )


class ValidationError(RasoSpeakError):
    """Input validation error."""

    def __init__(self, field: str, message: str):
        super().__init__(
            message=f"Validation error on {field}: {message}",
            code="VALIDATION_ERROR",
            details={"field": field},
        )


class MemoryError(RasoSpeakError):
    """Memory operation error."""

    def __init__(self, operation: str, message: str):
        super().__init__(
            message=f"Memory error during {operation}: {message}",
            code="MEMORY_ERROR",
            details={"operation": operation},
        )


class WorkflowError(RasoSpeakError):
    """Workflow execution error."""

    def __init__(self, workflow: str, message: str, details: dict = None):
        super().__init__(
            message=f"Workflow {workflow} error: {message}",
            code="WORKFLOW_ERROR",
            details={**({"workflow": workflow}, **(details or {}))},
        )


class ToolExecutionError(RasoSpeakError):
    """Tool execution error."""

    def __init__(self, tool: str, message: str, details: dict = None):
        super().__init__(
            message=f"Tool {tool} error: {message}",
            code="TOOL_ERROR",
            details={**({"tool": tool}, **(details or {}))},
        )


class TokenBudgetExceededError(RasoSpeakError):
    """Token budget exceeded."""

    def __init__(self, user_id: str, limit: int):
        super().__init__(
            message=f"Token budget exceeded for user {user_id}",
            code="BUDGET_EXCEEDED",
            details={"user_id": user_id, "limit": limit},
        )
