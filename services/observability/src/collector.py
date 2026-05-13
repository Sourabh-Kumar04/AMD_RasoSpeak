"""
RasoSpeak AI OS — Observability Collector
==========================================
OpenTelemetry-based observability for AI systems.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum

import structlog

logger = structlog.get_logger("rasospeak.observability")


# ──────────────────────────────────────────────────────────────────────────────
# Types
# ──────────────────────────────────────────────────────────────────────────────

class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


@dataclass
class Metric:
    name: str
    value: float
    metric_type: MetricType
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Trace:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    operation_name: str
    service_name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[int] = None
    labels: dict[str, str] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    status: str = "ok"


@dataclass
class LLMCall:
    """AI-specific telemetry for LLM calls."""
    call_id: str
    trace_id: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int
    cost_usd: float
    finish_reason: str
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentExecution:
    """Telemetry for agent executions."""
    execution_id: str
    trace_id: str
    agent_id: str
    agent_type: str
    state: str
    cycle_count: int
    tool_call_count: int
    token_usage: int
    confidence: float
    duration_ms: int
    success: bool
    error: Optional[str] = None
    user_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


# ──────────────────────────────────────────────────────────────────────────────
# Metrics Collector
# ──────────────────────────────────────────────────────────────────────────────

class MetricsCollector:
    """
    Collects and exports metrics to Prometheus.
    """

    def __init__(self, export_interval: int = 15):
        self._metrics: list[Metric] = []
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._export_interval = export_interval

    def increment(self, name: str, value: float = 1, labels: dict = None) -> None:
        """Increment a counter metric."""
        key = self._metric_key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + value

        self._metrics.append(Metric(
            name=name,
            value=self._counters[key],
            metric_type=MetricType.COUNTER,
            labels=labels or {},
        ))

    def gauge(self, name: str, value: float, labels: dict = None) -> None:
        """Set a gauge metric."""
        key = self._metric_key(name, labels)
        self._gauges[key] = value

        self._metrics.append(Metric(
            name=name,
            value=value,
            metric_type=MetricType.GAUGE,
            labels=labels or {},
        ))

    def histogram(self, name: str, value: float, labels: dict = None) -> None:
        """Observe a histogram metric."""
        key = self._metric_key(name, labels)

        if key not in self._histograms:
            self._histograms[key] = []

        self._histograms[key].append(value)

        self._metrics.append(Metric(
            name=name,
            value=value,
            metric_type=MetricType.HISTOGRAM,
            labels=labels or {},
        ))

    def record_llm_call(self, call: LLMCall) -> None:
        """Record an LLM call with all metrics."""
        self.increment(
            "llm_requests_total",
            labels={
                "provider": call.provider,
                "model": call.model,
                "status": "error" if call.error else "success",
            }
        )

        self.histogram(
            "llm_latency_ms",
            call.latency_ms,
            labels={"provider": call.provider, "model": call.model}
        )

        self.histogram(
            "llm_tokens_total",
            call.total_tokens,
            labels={"provider": call.provider, "type": "total"}
        )

        self.histogram(
            "llm_cost_usd",
            call.cost_usd,
            labels={"provider": call.provider, "model": call.model}
        )

        if call.user_id:
            self.increment(
                "llm_requests_by_user",
                labels={"user_id": call.user_id[:8]}  # Anonymized
            )

        logger.info(
            "llm_call_recorded",
            call_id=call.call_id,
            provider=call.provider,
            model=call.model,
            tokens=call.total_tokens,
            latency_ms=call.latency_ms,
            cost_usd=call.cost_usd,
        )

    def record_agent_execution(self, exec: AgentExecution) -> None:
        """Record an agent execution with all metrics."""
        self.increment(
            "agent_executions_total",
            labels={
                "agent_type": exec.agent_type,
                "state": exec.state,
                "success": str(exec.success).lower(),
            }
        )

        self.histogram(
            "agent_duration_ms",
            exec.duration_ms,
            labels={"agent_type": exec.agent_type}
        )

        self.histogram(
            "agent_cycles",
            exec.cycle_count,
            labels={"agent_type": exec.agent_type}
        )

        self.histogram(
            "agent_token_usage",
            exec.token_usage,
            labels={"agent_type": exec.agent_type}
        )

        self.gauge(
            "agent_confidence",
            exec.confidence,
            labels={"agent_id": exec.agent_id, "agent_type": exec.agent_type}
        )

        if exec.success:
            self.histogram(
                "agent_success_latency",
                exec.duration_ms,
                labels={"agent_type": exec.agent_type}
            )
        else:
            self.histogram(
                "agent_failure_latency",
                exec.duration_ms,
                labels={"agent_type": exec.agent_type}
            )

        logger.info(
            "agent_execution_recorded",
            execution_id=exec.execution_id,
            agent_type=exec.agent_type,
            state=exec.state,
            cycles=exec.cycle_count,
            duration_ms=exec.duration_ms,
            success=exec.success,
        )

    def record_memory_access(
        self,
        memory_type: str,
        hit: bool,
        latency_ms: float,
    ) -> None:
        """Record memory access metrics."""
        self.increment(
            "memory_access_total",
            labels={
                "memory_type": memory_type,
                "result": "hit" if hit else "miss",
            }
        )

        self.histogram(
            "memory_latency_ms",
            latency_ms,
            labels={"memory_type": memory_type}
        )

    def record_tool_execution(
        self,
        tool_name: str,
        success: bool,
        latency_ms: int,
        error: Optional[str] = None,
    ) -> None:
        """Record tool execution metrics."""
        self.increment(
            "tool_executions_total",
            labels={
                "tool": tool_name,
                "status": "success" if success else "error",
            }
        )

        self.histogram(
            "tool_latency_ms",
            latency_ms,
            labels={"tool": tool_name}
        )

        if error:
            self.increment(
                "tool_errors_total",
                labels={"tool": tool_name, "error_type": type(error).__name__}
            )

    def export(self) -> list[dict]:
        """Export all metrics in Prometheus format."""
        exported = []

        # Export counters
        for key, value in self._counters.items():
            name, labels = self._parse_key(key)
            exported.append({
                "name": name,
                "type": "counter",
                "value": value,
                "labels": labels,
            })

        # Export gauges
        for key, value in self._gauges.items():
            name, labels = self._parse_key(key)
            exported.append({
                "name": name,
                "type": "gauge",
                "value": value,
                "labels": labels,
            })

        # Export histograms
        for key, values in self._histograms.items():
            name, labels = self._parse_key(key)
            if values:
                sorted_values = sorted(values)
                n = len(sorted_values)

                exported.append({
                    "name": f"{name}_count",
                    "type": "counter",
                    "value": n,
                    "labels": labels,
                })

                exported.append({
                    "name": f"{name}_sum",
                    "type": "counter",
                    "value": sum(values),
                    "labels": labels,
                })

                # Quantiles
                for quantile in [0.5, 0.9, 0.95, 0.99]:
                    idx = int(n * quantile)
                    exported.append({
                        "name": f"{name}_quantile",
                        "type": "gauge",
                        "value": sorted_values[min(idx, n - 1)],
                        "labels": {**labels, "quantile": str(quantile)},
                    })

        # Clear exported metrics
        self._metrics.clear()

        return exported

    @staticmethod
    def _metric_key(name: str, labels: dict = None) -> str:
        """Generate a unique key for a metric."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    @staticmethod
    def _parse_key(key: str) -> tuple[str, dict]:
        """Parse a metric key into name and labels."""
        if "{" not in key:
            return key, {}

        name, label_str = key.split("{", 1)
        label_str = label_str.rstrip("}")

        labels = {}
        for part in label_str.split(","):
            k, v = part.split("=")
            labels[k] = v

        return name, labels


# ──────────────────────────────────────────────────────────────────────────────
# Distributed Tracer
# ──────────────────────────────────────────────────────────────────────────────

class Tracer:
    """
    Distributed tracing with OpenTelemetry-compatible format.
    """

    def __init__(self, service_name: str):
        self.service_name = service_name
        self._active_spans: dict[str, Trace] = {}

    def start_span(
        self,
        operation_name: str,
        parent_span_id: Optional[str] = None,
        labels: dict = None,
    ) -> str:
        """Start a new span."""
        trace_id = str(uuid.uuid4())
        span_id = str(uuid.uuid4())[:16]

        span = Trace(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            service_name=self.service_name,
            start_time=datetime.utcnow(),
            labels=labels or {},
        )

        self._active_spans[span_id] = span
        return span_id

    def end_span(self, span_id: str, status: str = "ok") -> Optional[Trace]:
        """End a span and return the complete trace."""
        span = self._active_spans.pop(span_id, None)
        if not span:
            return None

        span.end_time = datetime.utcnow()
        span.duration_ms = int(
            (span.end_time - span.start_time).total_seconds() * 1000
        )
        span.status = status

        logger.info(
            "span_completed",
            trace_id=span.trace_id,
            span_id=span_id,
            operation=span.operation_name,
            duration_ms=span.duration_ms,
            status=status,
        )

        return span

    def add_span_event(
        self,
        span_id: str,
        name: str,
        attributes: dict = None,
    ) -> None:
        """Add an event to a span."""
        span = self._active_spans.get(span_id)
        if span:
            span.events.append({
                "name": name,
                "timestamp": datetime.utcnow().isoformat(),
                "attributes": attributes or {},
            })

    def get_trace(self, trace_id: str) -> list[Trace]:
        """Get all spans for a trace."""
        return [
            span for span in self._active_spans.values()
            if span.trace_id == trace_id
        ]


# ──────────────────────────────────────────────────────────────────────────────
# AI Evaluator
# ──────────────────────────────────────────────────────────────────────────────

class AIEvaluator:
    """
    Evaluates AI outputs for quality and safety.
    """

    def __init__(self):
        self._hallucination_threshold = 0.7
        self._evaluations: list[dict] = []

    async def evaluate_response(
        self,
        response: str,
        context: list[str],
        user_id: str,
    ) -> dict[str, Any]:
        """
        Evaluate an AI response for quality and potential issues.

        Checks:
        - Hallucination indicators
        - Consistency with context
        - Safety concerns
        - Confidence scoring
        """
        score = 1.0
        issues = []

        # Check consistency with context
        if context:
            context_text = " ".join(context)
            # Simple check: response should contain some context keywords
            common_words = set(response.lower().split()) & set(context_text.lower().split())
            if len(common_words) < 3:
                issues.append({
                    "type": "low_context_alignment",
                    "severity": "warning",
                    "detail": "Response has low alignment with retrieved context",
                })
                score *= 0.8

        # Check for hallucination indicators
        hallucination_indicators = [
            "i'm not sure if this is accurate",
            "as far as i know",
            "it is possible that",
            "i may be wrong",
        ]

        uncertainty_count = sum(
            1 for ind in hallucination_indicators
            if ind in response.lower()
        )

        if uncertainty_count > 2:
            issues.append({
                "type": "high_uncertainty",
                "severity": "info",
                "detail": "Response contains multiple uncertainty markers",
            })
            score *= 0.9

        # Length-based quality check
        if len(response) < 50:
            issues.append({
                "type": "too_short",
                "severity": "warning",
                "detail": "Response is unusually short",
            })
            score *= 0.7

        if len(response) > 10000:
            issues.append({
                "type": "too_long",
                "severity": "info",
                "detail": "Response is unusually long",
            })
            score *= 0.95

        evaluation = {
            "evaluation_id": str(uuid.uuid4()),
            "response_length": len(response),
            "score": max(0, min(1, score)),
            "issues": issues,
            "flags": {
                "needs_review": score < self._hallucination_threshold,
                "has_uncertainty": uncertainty_count > 0,
            },
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

        self._evaluations.append(evaluation)

        return evaluation

    def get_quality_stats(self, time_window: timedelta = timedelta(hours=1)) -> dict:
        """Get quality statistics over a time window."""
        cutoff = datetime.utcnow() - time_window
        recent = [e for e in self._evaluations if datetime.fromisoformat(e["timestamp"]) > cutoff]

        if not recent:
            return {"count": 0, "avg_score": 0, "flagged_count": 0}

        scores = [e["score"] for e in recent]
        flagged = sum(1 for e in recent if e["flags"]["needs_review"])

        return {
            "count": len(recent),
            "avg_score": sum(scores) / len(scores),
            "min_score": min(scores),
            "max_score": max(scores),
            "flagged_count": flagged,
            "flagged_rate": flagged / len(recent),
            "issue_counts": self._count_issues(recent),
        }

    @staticmethod
    def _count_issues(evaluations: list[dict]) -> dict:
        """Count issue types across evaluations."""
        counts = {}
        for eval in evaluations:
            for issue in eval.get("issues", []):
                issue_type = issue["type"]
                counts[issue_type] = counts.get(issue_type, 0) + 1
        return counts


# ──────────────────────────────────────────────────────────────────────────────
# Global Observability Instance
# ──────────────────────────────────────────────────────────────────────────────

# Create global instances
metrics = MetricsCollector()
tracer = Tracer(service_name="rasospeak")
evaluator = AIEvaluator()

# Convenience functions
def record_llm_call(**kwargs) -> None:
    """Record an LLM call."""
    metrics.record_llm_call(LLMCall(call_id=str(uuid.uuid4()), **kwargs))


def record_agent_execution(**kwargs) -> None:
    """Record an agent execution."""
    metrics.record_agent_execution(AgentExecution(execution_id=str(uuid.uuid4()), **kwargs))


def get_metrics() -> list[dict]:
    """Get current metrics for Prometheus scraping."""
    return metrics.export()


def get_prometheus_metrics() -> str:
    """Format metrics for Prometheus text format."""
    exported = get_metrics()
    lines = []

    for metric in exported:
        labels = ",".join(f'{k}="{v}"' for k, v in metric["labels"].items())
        label_str = f"{{{labels}}}" if labels else ""

        if metric["type"] == "counter":
            lines.append(f"# TYPE {metric['name']} counter")
        elif metric["type"] == "gauge":
            lines.append(f"# TYPE {metric['name']} gauge")
        elif metric["type"] == "histogram":
            lines.append(f"# TYPE {metric['name']} histogram")

        lines.append(f"{metric['name']}{label_str} {metric['value']}")

    return "\n".join(lines)
