from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path("backend/scripts/hosted_external_smoke.py")


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location("hosted_external_smoke", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _smoke_env(**overrides: str) -> dict[str, str]:
    env = {
        **os.environ,
        "SEXTANT_EXTERNAL_SMOKE_URL": "https://api.sextant.example/smoke",
        "SEXTANT_EXTERNAL_SMOKE_PROJECT_ID": "00000000-0000-4000-8000-0000000000aa",
        "SEXTANT_EXTERNAL_SMOKE_BEARER_TOKEN": "eyJhbGciOiJsmoke-token",
        "SEXTANT_EXTERNAL_SMOKE_TIMEOUT_SECONDS": "3",
        "SEXTANT_EXTERNAL_SMOKE_POLL_ATTEMPTS": "2",
        "SEXTANT_EXTERNAL_SMOKE_POLL_INTERVAL_SECONDS": "0.01",
    }
    env.update(overrides)
    return env


def test_hosted_external_smoke_config_rejects_local_or_missing_runtime() -> None:
    smoke = _load_smoke_module()

    with pytest.raises(smoke.ConfigError, match="SEXTANT_EXTERNAL_SMOKE_URL"):
        smoke.SmokeConfig.from_env({})

    with pytest.raises(smoke.ConfigError, match="hosted HTTPS URL"):
        smoke.SmokeConfig.from_env(
            _smoke_env(SEXTANT_EXTERNAL_SMOKE_URL="https://127.0.0.1:8443/smoke")
        )

    with pytest.raises(smoke.ConfigError, match="SEXTANT_EXTERNAL_SMOKE_BEARER_TOKEN"):
        smoke.SmokeConfig.from_env(_smoke_env(SEXTANT_EXTERNAL_SMOKE_BEARER_TOKEN=""))

    with pytest.raises(smoke.ConfigError, match="UUID"):
        smoke.SmokeConfig.from_env(_smoke_env(SEXTANT_EXTERNAL_SMOKE_PROJECT_ID="not-a-uuid"))

    config = smoke.SmokeConfig.from_env(_smoke_env())

    assert config.base_url == "https://api.sextant.example/smoke"
    assert str(config.project_id) == "00000000-0000-4000-8000-0000000000aa"
    assert config.timeout_seconds == 3.0
    assert config.poll_attempts == 2


def test_hosted_external_smoke_check_config_cli() -> None:
    valid = subprocess.run(
        ["uv", "run", "python", str(SCRIPT_PATH), "--check-config"],
        cwd=Path.cwd(),
        env=_smoke_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    invalid = subprocess.run(
        ["uv", "run", "python", str(SCRIPT_PATH), "--check-config"],
        cwd=Path.cwd(),
        env=_smoke_env(SEXTANT_EXTERNAL_SMOKE_URL="https://localhost:8443/smoke"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-external-smoke-config-ok"
    assert invalid.returncode == 1
    assert "hosted HTTPS URL" in invalid.stderr
