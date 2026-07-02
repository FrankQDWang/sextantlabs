from __future__ import annotations

import json
import re
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from secrets import token_hex
from threading import Lock
from uuid import UUID

SENSITIVE_KEYS = {
    "text",
    "submitted_text",
    "accepted_text",
    "revised_text",
    "current_text_window",
    "raw_text",
    "candidate_text",
}

_TRACEPARENT_RE = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})(?:-[0-9a-f]+)?$")


@dataclass(slots=True)
class MetricCounter:
    name: str
    value: float = 0
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TraceContext:
    trace_id: str
    span_id: str
    sampled: bool


@dataclass(frozen=True, slots=True)
class TraceSample:
    recorded_at: str
    method: str
    path: str
    status: int
    duration_ms: int
    trace_id_sha256: str
    span_id_sha256: str


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], MetricCounter] = {}
        self._lock = Lock()

    def increment(
        self,
        name: str,
        *,
        labels: dict[str, str] | None = None,
        amount: float = 1,
    ) -> None:
        labels = labels or {}
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            counter = self._counters.setdefault(key, MetricCounter(name=name, labels=labels))
            counter.value += amount

    def observe_ms(
        self,
        name: str,
        value: float,
        *,
        labels: dict[str, str] | None = None,
    ) -> None:
        self.increment(f"{name}_count", labels=labels)
        self.increment(f"{name}_sum", labels=labels, amount=value)

    def observe_seconds(
        self,
        name: str,
        value: float,
        *,
        labels: dict[str, str] | None = None,
    ) -> None:
        self.increment(f"{name}_count", labels=labels)
        self.increment(f"{name}_sum", labels=labels, amount=value)

    def snapshot(self) -> list[MetricCounter]:
        with self._lock:
            return [
                MetricCounter(name=counter.name, value=counter.value, labels=dict(counter.labels))
                for counter in self._counters.values()
            ]


class ObservabilityState:
    def __init__(self, *, max_trace_samples: int = 200) -> None:
        if max_trace_samples <= 0:
            raise ValueError("max_trace_samples must be positive.")
        self._trace_samples: deque[TraceSample] = deque(maxlen=max_trace_samples)
        self._lock = Lock()

    def record_api_request(
        self,
        *,
        method: str,
        path: str,
        status: int,
        duration_ms: int,
        trace_context: TraceContext,
    ) -> None:
        sample = TraceSample(
            recorded_at=datetime.now(UTC).isoformat(),
            method=method,
            path=path,
            status=status,
            duration_ms=duration_ms,
            trace_id_sha256=_fingerprint_text(trace_context.trace_id),
            span_id_sha256=_fingerprint_text(trace_context.span_id),
        )
        with self._lock:
            self._trace_samples.append(sample)

    def trace_report(self) -> dict[str, object]:
        with self._lock:
            samples = list(self._trace_samples)
        return {
            "status": "ready" if samples else "empty",
            "service": "sextant-api",
            "trace_sample_count": len(samples),
            "samples": [
                {
                    "recorded_at": sample.recorded_at,
                    "method": sample.method,
                    "path": sample.path,
                    "status": sample.status,
                    "duration_ms": sample.duration_ms,
                    "trace_id_sha256": sample.trace_id_sha256,
                    "span_id_sha256": sample.span_id_sha256,
                }
                for sample in samples[-20:]
            ],
        }

    def alert_report(self, metrics: MetricsRegistry | None) -> dict[str, object]:
        counters = metrics.snapshot() if metrics is not None else []
        api_error_count = _metric_total(counters, "sextant_api_errors_total")
        application_error_count = _metric_total(counters, "sextant_application_errors_total")
        failed_worker_jobs = _metric_total(counters, "sextant_worker_jobs_total", status="failed")
        active_alerts = []
        if api_error_count > 0 or application_error_count > 0:
            active_alerts.append(
                {
                    "name": "api_error_rate",
                    "status": "firing",
                    "observed_error_count": api_error_count,
                    "observed_application_error_count": application_error_count,
                }
            )
        else:
            active_alerts.append(
                {
                    "name": "api_error_rate",
                    "status": "ok",
                    "observed_error_count": 0,
                    "observed_application_error_count": 0,
                }
            )
        if failed_worker_jobs > 0:
            active_alerts.append(
                {
                    "name": "worker_job_failures",
                    "status": "firing",
                    "observed_failure_count": failed_worker_jobs,
                }
            )
        else:
            active_alerts.append(
                {
                    "name": "worker_job_failures",
                    "status": "ok",
                    "observed_failure_count": 0,
                }
            )

        firing = [alert for alert in active_alerts if alert["status"] == "firing"]
        return {
            "status": "degraded" if firing else "ok",
            "service": "sextant-api",
            "active_alert_count": len(firing),
            "checks": active_alerts,
        }


def render_prometheus_metrics(counters: list[MetricCounter]) -> str:
    lines: list[str] = []
    for counter in sorted(counters, key=lambda item: (item.name, sorted(item.labels.items()))):
        label_text = _prometheus_labels(counter.labels)
        lines.append(
            f"{_prometheus_name(counter.name)}{label_text} {_prometheus_value(counter.value)}"
        )
    return "\n".join(lines) + ("\n" if lines else "")


def safe_log_event(
    *,
    event_type: str,
    project_id: UUID | None,
    request_id: str | None,
    actor_id: UUID | None,
    payload: dict[str, object],
) -> str:
    event = {
        "ts": datetime.now(UTC).isoformat(),
        "event_type": event_type,
        "project_id": str(project_id) if project_id else None,
        "request_id": request_id,
        "actor_id": str(actor_id) if actor_id else None,
        "payload": _redact(payload),
    }
    return json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def trace_context_from_traceparent(traceparent: str | None) -> TraceContext:
    match = _TRACEPARENT_RE.match((traceparent or "").strip())
    if match is None:
        return TraceContext(trace_id=_new_trace_id(), span_id=_new_span_id(), sampled=False)

    trace_id, parent_id, flags = match.groups()
    if trace_id == "0" * 32 or parent_id == "0" * 16:
        return TraceContext(trace_id=_new_trace_id(), span_id=_new_span_id(), sampled=False)

    return TraceContext(
        trace_id=trace_id,
        span_id=_new_span_id(),
        sampled=bool(int(flags, 16) & 1),
    )


def traceparent_header(context: TraceContext) -> str:
    flags = "01" if context.sampled else "00"
    return f"00-{context.trace_id}-{context.span_id}-{flags}"


def _redact(value: object) -> object:
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for raw_key, nested in value.items():
            key = str(raw_key)
            if key in SENSITIVE_KEYS:
                redacted[key] = _fingerprint(nested)
            else:
                redacted[key] = _redact(nested)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _fingerprint(value: object) -> dict[str, object]:
    text = str(value)
    return {
        "redacted": True,
        "sha256": _fingerprint_text(text),
        "length": len(text),
    }


def _fingerprint_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _metric_total(counters: Iterable[MetricCounter], name: str, **labels: str) -> float:
    total = 0.0
    for counter in counters:
        if counter.name != name:
            continue
        if any(
            counter.labels.get(label_name) != label_value
            for label_name, label_value in labels.items()
        ):
            continue
        total += counter.value
    return total


def _new_trace_id() -> str:
    trace_id = token_hex(16)
    while trace_id == "0" * 32:
        trace_id = token_hex(16)
    return trace_id


def _new_span_id() -> str:
    span_id = token_hex(8)
    while span_id == "0" * 16:
        span_id = token_hex(8)
    return span_id


def _prometheus_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "_:" else "_" for char in value)


def _prometheus_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    rendered = ",".join(
        f'{_prometheus_name(key)}="{_prometheus_label_value(value)}"'
        for key, value in sorted(labels.items())
    )
    return f"{{{rendered}}}"


def _prometheus_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _prometheus_value(value: float) -> str:
    return f"{value:g}"
