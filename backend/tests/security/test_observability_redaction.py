from __future__ import annotations

from urllib.request import urlopen
from uuid import uuid4

from sextant.common.observability import (
    MetricsRegistry,
    render_prometheus_metrics,
    safe_log_event,
    trace_context_from_traceparent,
    traceparent_header,
)
from sextant.infra.worker_metrics import start_worker_metrics_server


def test_safe_log_event_redacts_manuscript_text() -> None:
    project_id = uuid4()
    actor_id = uuid4()
    manuscript = "Mira 把钥匙放在两人之间。钥匙是冷的。"

    encoded = safe_log_event(
        event_type="candidate.accepted",
        project_id=project_id,
        request_id="req-redaction",
        actor_id=actor_id,
        payload={
            "accepted_text": manuscript,
            "nested": {"current_text_window": manuscript},
            "source_delta_id": "delta-1",
        },
    )

    assert manuscript not in encoded
    assert '"redacted":true' in encoded
    assert "delta-1" in encoded


def test_metrics_registry_counts_labeled_events() -> None:
    metrics = MetricsRegistry()

    metrics.increment("sextant_jobs_total", labels={"status": "succeeded"})
    metrics.increment("sextant_jobs_total", labels={"status": "succeeded"})

    [counter] = metrics.snapshot()
    assert counter.name == "sextant_jobs_total"
    assert counter.value == 2
    assert counter.labels == {"status": "succeeded"}


def test_metrics_registry_observes_latency_count_and_sum() -> None:
    metrics = MetricsRegistry()

    metrics.observe_ms(
        "sextant_action_request_latency_ms",
        42.5,
        labels={"action_type": "ask_memory", "status": "success"},
    )

    counters = {
        (counter.name, tuple(sorted(counter.labels.items()))): counter.value
        for counter in metrics.snapshot()
    }
    labels = (("action_type", "ask_memory"), ("status", "success"))
    assert counters[("sextant_action_request_latency_ms_count", labels)] == 1
    assert counters[("sextant_action_request_latency_ms_sum", labels)] == 42.5


def test_prometheus_metrics_export_renders_labeled_counters_without_payloads() -> None:
    metrics = MetricsRegistry()
    metrics.increment(
        "sextant_api_requests_total",
        labels={
            "method": "POST",
            "path": "/api/projects/{project_id}/sources",
            "status": "201",
        },
    )

    exported = render_prometheus_metrics(metrics.snapshot())

    request_counter = (
        'sextant_api_requests_total{method="POST",'
        'path="/api/projects/{project_id}/sources",status="201"} 1'
    )
    assert request_counter in exported
    assert "Mira 把钥匙放在两人之间" not in exported


def test_worker_metrics_server_exports_prometheus_without_payloads() -> None:
    metrics = MetricsRegistry()
    manuscript = "Mira 把钥匙放在两人之间。"
    metrics.increment(
        "sextant_worker_jobs_total",
        labels={"job_type": "run_memory_writeback", "status": "succeeded"},
    )

    server = start_worker_metrics_server(metrics, host="127.0.0.1", port=0)
    try:
        host, port = server.server_address
        with urlopen(f"http://{host}:{port}/metrics", timeout=5) as response:
            body = response.read().decode("utf-8")
            content_type = response.headers.get("content-type", "")
    finally:
        server.shutdown()
        server.server_close()

    assert (
        'sextant_worker_jobs_total{job_type="run_memory_writeback",status="succeeded"} 1'
    ) in body
    assert "text/plain" in content_type
    assert manuscript not in body


def test_trace_context_preserves_valid_w3c_trace_id_and_replaces_span_id() -> None:
    incoming = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

    context = trace_context_from_traceparent(incoming)

    assert context.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert context.span_id != "00f067aa0ba902b7"
    assert len(context.span_id) == 16
    assert context.sampled is True
    assert traceparent_header(context).startswith("00-4bf92f3577b34da6a3ce929d0e0e4736-")
    assert traceparent_header(context).endswith("-01")


def test_trace_context_rejects_invalid_traceparent_without_echoing_payload() -> None:
    invalid = "00-zzzz<script>-00f067aa0ba902b7-01"

    context = trace_context_from_traceparent(invalid)

    rendered = traceparent_header(context)
    assert invalid not in rendered
    assert rendered.startswith("00-")
    assert len(context.trace_id) == 32
    assert len(context.span_id) == 16
