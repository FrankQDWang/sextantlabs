from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path("backend/scripts/hosted_observability_pipeline_probe.py")


def _load_probe_module():
    spec = importlib.util.spec_from_file_location(
        "hosted_observability_pipeline_probe", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _probe_env(**overrides: str) -> dict[str, str]:
    env = {
        **os.environ,
        "SEXTANT_RELEASE_ENVIRONMENT": "production",
        "SEXTANT_HOSTED_METRICS_URL": "https://metrics.sextant.example/sextant",
        "SEXTANT_HOSTED_TRACES_URL": "https://traces.sextant.example/sextant",
        "SEXTANT_ALERTING_DASHBOARD_URL": "https://alerts.sextant.example/sextant",
        "SEXTANT_OBSERVABILITY_PIPELINE_BEARER_TOKEN": "token-secret",
        "SEXTANT_OBSERVABILITY_PROBE_TIMEOUT_SECONDS": "3",
        "SEXTANT_OBSERVABILITY_REQUIRED_METRICS": (
            "sextant_api_requests_total,sextant_worker_jobs_total"
        ),
        "SEXTANT_OBSERVABILITY_TRACES_EXPECT": "trace_id",
        "SEXTANT_OBSERVABILITY_ALERTS_EXPECT": "Sextant",
    }
    env.update(overrides)
    return env


def test_hosted_observability_config_rejects_non_production_or_local_urls() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_RELEASE_ENVIRONMENT"):
        probe.ObservabilityPipelineConfig.from_env(
            _probe_env(SEXTANT_RELEASE_ENVIRONMENT="development")
        )

    with pytest.raises(probe.ConfigError, match="SEXTANT_HOSTED_METRICS_URL"):
        probe.ObservabilityPipelineConfig.from_env(
            _probe_env(SEXTANT_HOSTED_METRICS_URL="https://localhost:9090/metrics")
        )

    with pytest.raises(probe.ConfigError, match="positive number"):
        probe.ObservabilityPipelineConfig.from_env(
            _probe_env(SEXTANT_OBSERVABILITY_PROBE_TIMEOUT_SECONDS="0")
        )

    config = probe.ObservabilityPipelineConfig.from_env(_probe_env())

    assert config.metrics_url == "https://metrics.sextant.example/sextant"
    assert config.required_metrics == (
        "sextant_api_requests_total",
        "sextant_worker_jobs_total",
    )
    assert config.bearer_token == "token-secret"


def test_hosted_observability_probe_fetches_pipeline_and_redacts_evidence() -> None:
    probe = _load_probe_module()
    config = probe.ObservabilityPipelineConfig.from_env(_probe_env())
    metrics_body = (
        b'sextant_api_requests_total{method="POST",path="/api/action-requests",status="200"} 4\n'
        b'sextant_worker_jobs_total{job_type="run_memory_writeback",status="succeeded"} 2\n'
    )
    traces_body = b'{"trace_id":"trace-raw-secret","service":"sextant-api"}'
    alerts_body = b"<html>Sextant alert route healthy</html>"

    def fetcher(url: str, config: object) -> object:
        assert config.bearer_token == "token-secret"
        if url == "https://metrics.sextant.example/sextant":
            return probe.EndpointResponse(status_code=200, body=metrics_body)
        if url == "https://traces.sextant.example/sextant":
            return probe.EndpointResponse(status_code=200, body=traces_body)
        if url == "https://alerts.sextant.example/sextant":
            return probe.EndpointResponse(status_code=200, body=alerts_body)
        raise AssertionError(f"unexpected url {url}")

    result = probe.run_observability_probe(config, fetcher=fetcher)
    rendered = json.dumps(result, ensure_ascii=False, sort_keys=True)

    assert result["status"] == "pass"
    assert result["metrics"]["required_found"] == [
        "sextant_api_requests_total",
        "sextant_worker_jobs_total",
    ]
    assert result["metrics"]["series_count"] == 2
    assert result["traces"]["body_sha256"] == hashlib.sha256(traces_body).hexdigest()
    assert result["alerts"]["body_sha256"] == hashlib.sha256(alerts_body).hexdigest()
    assert "trace-raw-secret" not in rendered
    assert "token-secret" not in rendered
    assert "Sextant alert route healthy" not in rendered


def test_hosted_observability_metrics_parser_accepts_route_template_labels() -> None:
    probe = _load_probe_module()
    config = probe.ObservabilityPipelineConfig.from_env(
        _probe_env(
            SEXTANT_OBSERVABILITY_REQUIRED_METRICS="sextant_api_requests_total",
            SEXTANT_OBSERVABILITY_TRACES_EXPECT="trace_sample_count",
            SEXTANT_OBSERVABILITY_ALERTS_EXPECT="active_alert_count",
        )
    )
    metrics_body = (
        b'sextant_api_requests_total{method="GET",'
        b'path="/api/projects/{project_id}/context-pack-readiness",status="200"} 1\n'
    )

    def fetcher(url: str, _config: object) -> object:
        if url == config.metrics_url:
            return probe.EndpointResponse(status_code=200, body=metrics_body)
        return probe.EndpointResponse(
            status_code=200,
            body=b'{"trace_sample_count":1,"active_alert_count":0}',
        )

    result = probe.run_observability_probe(config, fetcher=fetcher)

    assert result["status"] == "pass"
    assert result["metrics"]["required_found"] == ["sextant_api_requests_total"]


def test_hosted_observability_probe_fails_on_missing_signals() -> None:
    probe = _load_probe_module()
    config = probe.ObservabilityPipelineConfig.from_env(_probe_env())

    def missing_metric_fetcher(url: str, _config: object) -> object:
        if url == config.metrics_url:
            return probe.EndpointResponse(
                status_code=200,
                body=b'sextant_api_requests_total{status="200"} 1\n',
            )
        return probe.EndpointResponse(status_code=200, body=b"trace_id Sextant")

    with pytest.raises(probe.ObservabilityProbeError, match="missing required metrics"):
        probe.run_observability_probe(config, fetcher=missing_metric_fetcher)

    def missing_trace_fetcher(url: str, _config: object) -> object:
        if url == config.metrics_url:
            return probe.EndpointResponse(
                status_code=200,
                body=(
                    b'sextant_api_requests_total{status="200"} 1\n'
                    b'sextant_worker_jobs_total{status="succeeded"} 1\n'
                ),
            )
        if url == config.traces_url:
            return probe.EndpointResponse(status_code=200, body=b"no trace marker")
        return probe.EndpointResponse(status_code=200, body=b"Sextant")

    with pytest.raises(probe.ObservabilityProbeError, match="traces response"):
        probe.run_observability_probe(config, fetcher=missing_trace_fetcher)


def test_hosted_observability_check_config_cli() -> None:
    valid = subprocess.run(
        ["uv", "run", "python", str(SCRIPT_PATH), "--check-config"],
        cwd=Path.cwd(),
        env=_probe_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    invalid = subprocess.run(
        ["uv", "run", "python", str(SCRIPT_PATH), "--check-config"],
        cwd=Path.cwd(),
        env=_probe_env(SEXTANT_ALERTING_DASHBOARD_URL="https://127.0.0.1/alerts"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-observability-pipeline-config-ok"
    assert invalid.returncode == 1
    assert "hosted HTTPS URL" in invalid.stderr
