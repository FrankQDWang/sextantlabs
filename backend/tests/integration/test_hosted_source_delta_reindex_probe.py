from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path("backend/scripts/hosted_source_delta_reindex_probe.py")


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("hosted_source_delta_reindex_probe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _probe_env(**overrides: str) -> dict[str, str]:
    env = {
        **os.environ,
        "SEXTANT_RELEASE_ENVIRONMENT": "production",
        "SEXTANT_DATABASE_URL": "postgresql+psycopg://sextant:secret@db.sextant.example:5432/sextant",
        "SEXTANT_OBJECT_STORE_ROOT": "s3://sextant-prod/objects",
    }
    env.update(overrides)
    return env


def test_hosted_source_delta_reindex_config_rejects_non_production_or_local_runtime() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_RELEASE_ENVIRONMENT=production"):
        probe.ReindexProbeConfig.from_env({})

    with pytest.raises(probe.ConfigError, match="SEXTANT_DATABASE_URL"):
        probe.ReindexProbeConfig.from_env(_probe_env(SEXTANT_DATABASE_URL=""))

    with pytest.raises(probe.ConfigError, match="PostgreSQL"):
        probe.ReindexProbeConfig.from_env(
            _probe_env(SEXTANT_DATABASE_URL="sqlite+pysqlite:///tmp/local.db")
        )

    with pytest.raises(probe.ConfigError, match="hosted database host"):
        probe.ReindexProbeConfig.from_env(
            _probe_env(SEXTANT_DATABASE_URL="postgresql+psycopg://user:pass@localhost/db")
        )

    with pytest.raises(probe.ConfigError, match="s3://"):
        probe.ReindexProbeConfig.from_env(
            _probe_env(SEXTANT_OBJECT_STORE_ROOT="/tmp/sextant-objects")
        )

    with pytest.raises(probe.ConfigError, match="batch-size"):
        probe.ReindexProbeConfig.from_env(_probe_env(), batch_size=0)

    config = probe.ReindexProbeConfig.from_env(_probe_env(), batch_size=25, rebuild_all=True)

    assert config.database_url.host == "db.sextant.example"
    assert config.database_url.sanitized == (
        "postgresql+psycopg://sextant:***@db.sextant.example:5432/sextant"
    )
    assert config.object_store_root == "s3://sextant-prod/objects"
    assert config.batch_size == 25
    assert config.rebuild_all is True


def test_hosted_source_delta_reindex_evidence_is_json_and_sanitizes_database_url() -> None:
    probe = _load_probe_module()
    config = probe.ReindexProbeConfig.from_env(_probe_env(), batch_size=10)

    evidence = probe.build_reindex_evidence(config, reindexed_rows=3)
    encoded = json.dumps(evidence, sort_keys=True)

    assert evidence == {
        "status": "pass",
        "database_host": "db.sextant.example",
        "database_scheme": "postgresql+psycopg",
        "database_url": "postgresql+psycopg://sextant:***@db.sextant.example:5432/sextant",
        "object_store_root": "s3://sextant-prod/objects",
        "batch_size": 10,
        "rebuild_all": False,
        "reindexed_rows": 3,
    }
    assert "secret" not in encoded


def test_hosted_source_delta_reindex_check_config_cli() -> None:
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
        env=_probe_env(SEXTANT_OBJECT_STORE_ROOT="./.sextant/objects"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-source-delta-reindex-config-ok"
    assert invalid.returncode == 1
    assert "s3://" in invalid.stderr
