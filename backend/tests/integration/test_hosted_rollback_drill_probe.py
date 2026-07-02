from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path("backend/scripts/hosted_rollback_drill_probe.py")


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("hosted_rollback_drill_probe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _probe_env(**overrides: str) -> dict[str, str]:
    env = {
        **os.environ,
        "SEXTANT_RELEASE_ENVIRONMENT": "production",
        "SEXTANT_DEPLOYMENT_VERSION": "2026.06.19+current",
        "SEXTANT_ROLLBACK_TARGET_VERSION": "2026.06.18+previous",
        "SEXTANT_ROLLBACK_STATUS_URL": "https://deploy.sextant.example/status",
        "SEXTANT_ROLLBACK_RUNBOOK_REF": "runbook://release/rollback/2026-06-19",
        "SEXTANT_ROLLBACK_COMMAND": (
            "sextant-release rollback --target-version 2026.06.18+previous"
        ),
        "SEXTANT_ROLLBACK_TIMEOUT_SECONDS": "30",
        "SEXTANT_ROLLBACK_POLL_ATTEMPTS": "2",
        "SEXTANT_ROLLBACK_POLL_INTERVAL_SECONDS": "0.01",
    }
    env.update(overrides)
    return env


def test_hosted_rollback_config_rejects_non_production_local_or_noop_runtime() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_RELEASE_ENVIRONMENT=production"):
        probe.RollbackDrillConfig.from_env({})

    with pytest.raises(probe.ConfigError, match="hosted HTTPS URL"):
        probe.RollbackDrillConfig.from_env(
            _probe_env(SEXTANT_ROLLBACK_STATUS_URL="https://127.0.0.1/status")
        )

    with pytest.raises(probe.ConfigError, match="target version"):
        probe.RollbackDrillConfig.from_env(
            _probe_env(SEXTANT_ROLLBACK_TARGET_VERSION="2026.06.19+current")
        )

    with pytest.raises(probe.ConfigError, match="auditable"):
        probe.RollbackDrillConfig.from_env(_probe_env(SEXTANT_ROLLBACK_RUNBOOK_REF="rollback-ok"))

    with pytest.raises(probe.ConfigError, match="cannot be a no-op"):
        probe.RollbackDrillConfig.from_env(_probe_env(SEXTANT_ROLLBACK_COMMAND="echo ok"))

    with pytest.raises(probe.ConfigError, match="target version"):
        probe.RollbackDrillConfig.from_env(
            _probe_env(SEXTANT_ROLLBACK_COMMAND="sextant-release rollback")
        )

    config = probe.RollbackDrillConfig.from_env(_probe_env())

    assert config.status_url == "https://deploy.sextant.example/status"
    assert config.current_version == "2026.06.19+current"
    assert config.target_version == "2026.06.18+previous"
    assert config.runbook_ref_scheme == "runbook"
    assert config.command_args == (
        "sextant-release",
        "rollback",
        "--target-version",
        "2026.06.18+previous",
    )


def test_hosted_rollback_runs_command_polls_status_and_redacts_evidence() -> None:
    probe = _load_probe_module()
    config = probe.RollbackDrillConfig.from_env(
        _probe_env(SEXTANT_ROLLBACK_STATUS_BEARER_TOKEN="secret-status-token")
    )
    statuses = [
        {"version": "2026.06.19+current", "status": "ok", "secret": "before-body-secret"},
        {"version": "2026.06.18+previous", "status": "ok", "secret": "after-body-secret"},
    ]
    commands: list[tuple[str, ...]] = []

    def fetcher(_config: object) -> dict[str, object]:
        return statuses.pop(0)

    def runner(args: tuple[str, ...]) -> object:
        commands.append(args)
        return probe.CommandResult(stdout="rolled back secret", stderr="token=secret", returncode=0)

    evidence = probe.run_rollback_drill_probe(
        config,
        status_fetcher=fetcher,
        command_runner=runner,
    )
    rendered = json.dumps(evidence, sort_keys=True)

    assert evidence["status"] == "pass"
    assert evidence["status_url_host"] == "deploy.sextant.example"
    assert evidence["pre_rollback_version"] == "2026.06.19+current"
    assert evidence["post_rollback_version"] == "2026.06.18+previous"
    assert evidence["post_rollback_health"] == "ok"
    assert evidence["command_exit_code"] == 0
    assert evidence["runbook_ref_scheme"] == "runbook"
    assert commands == [config.command_args]
    assert "secret-status-token" not in rendered
    assert "rolled back secret" not in rendered
    assert "token=secret" not in rendered
    assert "before-body-secret" not in rendered
    assert "after-body-secret" not in rendered
    assert config.raw_runbook_ref not in rendered


def test_hosted_rollback_fails_when_status_never_reaches_target_version() -> None:
    probe = _load_probe_module()
    config = probe.RollbackDrillConfig.from_env(_probe_env())

    def fetcher(_config: object) -> dict[str, object]:
        return {"version": "2026.06.19+current", "status": "ok"}

    def runner(_args: tuple[str, ...]) -> object:
        return probe.CommandResult(stdout="", stderr="", returncode=0)

    with pytest.raises(probe.RollbackDrillError, match="target rollback version"):
        probe.run_rollback_drill_probe(
            config,
            status_fetcher=fetcher,
            command_runner=runner,
        )


def test_hosted_rollback_check_config_cli() -> None:
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
        env=_probe_env(SEXTANT_ROLLBACK_STATUS_URL="https://localhost/status"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-rollback-drill-config-ok"
    assert invalid.returncode == 1
    assert "hosted HTTPS URL" in invalid.stderr
