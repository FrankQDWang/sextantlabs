from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path("backend/scripts/hosted_worker_capacity_probe.py")


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("hosted_worker_capacity_probe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _probe_env(**overrides: str) -> dict[str, str]:
    env = {
        **os.environ,
        "SEXTANT_HOSTED_WORKER_METRICS_URL": "https://metrics.sextant.example/worker",
        "SEXTANT_WORKER_CAPACITY_MAX_QUEUE_AGE_SECONDS": "30",
        "SEXTANT_WORKER_CAPACITY_MIN_SUCCEEDED_JOBS": "1",
        "SEXTANT_WORKER_CAPACITY_TIMEOUT_SECONDS": "3",
    }
    env.update(overrides)
    return env


def test_hosted_worker_capacity_config_rejects_local_or_missing_metrics_url() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_HOSTED_WORKER_METRICS_URL"):
        probe.WorkerCapacityConfig.from_env({})

    with pytest.raises(probe.ConfigError, match="hosted HTTPS URL"):
        probe.WorkerCapacityConfig.from_env(
            _probe_env(SEXTANT_HOSTED_WORKER_METRICS_URL="https://localhost:9091/metrics")
        )

    with pytest.raises(probe.ConfigError, match="positive number"):
        probe.WorkerCapacityConfig.from_env(
            _probe_env(SEXTANT_WORKER_CAPACITY_MAX_QUEUE_AGE_SECONDS="0")
        )

    config = probe.WorkerCapacityConfig.from_env(_probe_env())

    assert config.metrics_url == "https://metrics.sextant.example/worker"
    assert config.max_queue_age_seconds == 30.0
    assert config.min_succeeded_jobs == 1


def test_hosted_worker_capacity_evaluates_prometheus_metrics() -> None:
    probe = _load_probe_module()
    config = probe.WorkerCapacityConfig.from_env(_probe_env())
    metrics = "\n".join(
        [
            'sextant_worker_jobs_total{job_type="run_memory_writeback",status="succeeded"} 3',
            'sextant_worker_jobs_total{job_type="run_memory_writeback",status="failed_terminal"} 0',
            'sextant_job_queue_age_seconds_count{job_type="run_memory_writeback"} 3',
            'sextant_job_queue_age_seconds_sum{job_type="run_memory_writeback"} 12',
        ]
    )

    result = probe.evaluate_worker_metrics(metrics, config)

    assert result["status"] == "pass"
    assert result["succeeded_jobs"] == 3
    assert result["max_average_queue_age_seconds"] == 4


def test_hosted_worker_capacity_fails_on_missing_success_or_stale_queue() -> None:
    probe = _load_probe_module()
    config = probe.WorkerCapacityConfig.from_env(_probe_env())
    no_success = (
        'sextant_worker_jobs_total{job_type="run_memory_writeback",status="failed_terminal"} 1'
    )
    stale_queue = "\n".join(
        [
            'sextant_worker_jobs_total{job_type="run_memory_writeback",status="succeeded"} 1',
            'sextant_job_queue_age_seconds_count{job_type="run_memory_writeback"} 1',
            'sextant_job_queue_age_seconds_sum{job_type="run_memory_writeback"} 31',
        ]
    )

    with pytest.raises(probe.CapacityError, match="succeeded jobs"):
        probe.evaluate_worker_metrics(no_success, config)
    with pytest.raises(probe.CapacityError, match="queue age"):
        probe.evaluate_worker_metrics(stale_queue, config)


def test_hosted_worker_capacity_check_config_cli() -> None:
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
        env=_probe_env(SEXTANT_HOSTED_WORKER_METRICS_URL="https://127.0.0.1:9091/metrics"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-worker-capacity-config-ok"
    assert invalid.returncode == 1
    assert "hosted HTTPS URL" in invalid.stderr
