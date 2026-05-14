"""
RasoSpeak Observability Middleware
==================================
OpenTelemetry tracing and metrics for production monitoring.
"""

import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

logger = structlog.get_logger("rasospeak.observability")

# Simple tracing implementation (OpenTelemetry wrapper would go here in production)
_traces = []


class TracingMiddleware(BaseHTTPMiddleware):
    """Middleware that traces all requests."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate trace ID
        trace_id = str(uuid.uuid4())[:8]

        # Start timer
        start_time = time.time()

        # Log request
        logger.debug(
            "request_started",
            trace_id=trace_id,
            method=request.method,
            path=request.url.path
        )

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log response
            logger.info(
                "request_completed",
                trace_id=trace_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2)
            )

            # Add trace headers
            response.headers["X-Trace-ID"] = trace_id

            return response

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "request_failed",
                trace_id=trace_id,
                method=request.method,
                path=request.url.path,
                error=str(e),
                duration_ms=round(duration_ms, 2)
            )
            raise


def trace_cognition(cognitive_layers: list, user_id: str):
    """Trace cognitive pipeline execution."""
    trace = {
        "trace_id": str(uuid.uuid4())[:8],
        "user_id": user_id,
        "layers": cognitive_layers,
        "timestamp": time.time()
    }
    _traces.append(trace)
    logger.info("cognition_trace", trace=trace)
    return trace


def get_traces(limit: int = 100) -> list:
    """Get recent traces."""
    return _traces[-limit:]


# Metrics (simple in-memory implementation)
_metrics = {
    "requests_total": 0,
    "requests_by_endpoint": {},
    "requests_by_status": {},
    "latency_sum": 0,
    "latency_count": 0,
}


def record_metric(endpoint: str, status_code: int, latency_ms: float):
    """Record request metrics."""
    _metrics["requests_total"] += 1
    _metrics["requests_by_endpoint"][endpoint] = _metrics["requests_by_endpoint"].get(endpoint, 0) + 1
    _metrics["requests_by_status"][status_code] = _metrics["requests_by_status"].get(status_code, 0) + 1
    _metrics["latency_sum"] += latency_ms
    _metrics["latency_count"] += 1


def get_metrics() -> dict:
    """Get current metrics."""
    avg_latency = (
        round(_metrics["latency_sum"] / _metrics["latency_count"], 2)
        if _metrics["latency_count"] > 0
        else 0
    )

    return {
        "requests_total": _metrics["requests_total"],
        "requests_per_endpoint": _metrics["requests_by_endpoint"],
        "requests_per_status": _metrics["requests_by_status"],
        "avg_latency_ms": avg_latency,
    }


# Langfuse-style LLM tracking (simplified)
_llm_calls = []


def track_llm_call(provider: str, model: str, prompt_tokens: int, completion_tokens: int, latency_ms: float):
    """Track LLM API calls."""
    call = {
        "timestamp": time.time(),
        "provider": provider,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "latency_ms": latency_ms
    }
    _llm_calls.append(call)

    logger.info(
        "llm_call",
        provider=provider,
        model=model,
        tokens=call["total_tokens"],
        latency_ms=latency_ms
    )


def get_llm_stats() -> dict:
    """Get LLM usage statistics."""
    if not _llm_calls:
        return {"total_calls": 0}

    total_tokens = sum(c["total_tokens"] for c in _llm_calls)
    return {
        "total_calls": len(_llm_calls),
        "total_tokens": total_tokens,
        "by_provider": {
            p: len([c for c in _llm_calls if c["provider"] == p])
            for p in set(c["provider"] for c in _llm_calls)
        }
    }