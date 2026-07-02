from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path("backend/scripts/hosted_postgres_readiness_probe.py")


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("hosted_postgres_readiness_probe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _probe_env(**overrides: str) -> dict[str, str]:
    env = {
        **os.environ,
        "SEXTANT_RELEASE_ENVIRONMENT": "production",
        "SEXTANT_DATABASE_URL": (
            "postgresql+psycopg://sextant:secret@db.sextant.example:5432/sextant"
        ),
        "SEXTANT_MANAGED_POSTGRES_INSTANCE": "rds://prod/sextant",
        "SEXTANT_POSTGRES_READINESS_MIN_SOURCE_DELTAS": "1",
        "SEXTANT_POSTGRES_READINESS_MIN_SOURCE_SPANS": "1",
        "SEXTANT_POSTGRES_READINESS_MIN_MEMORY_PAGES": "1",
        "SEXTANT_POSTGRES_READINESS_MIN_SOURCE_SPANS_WITH_RAW": "1",
    }
    env.update(overrides)
    return env


def test_hosted_postgres_config_rejects_non_production_local_or_invalid_refs() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_RELEASE_ENVIRONMENT=production"):
        probe.PostgresReadinessConfig.from_env({})

    with pytest.raises(probe.ConfigError, match="PostgreSQL"):
        probe.PostgresReadinessConfig.from_env(
            _probe_env(SEXTANT_DATABASE_URL="sqlite+pysqlite:///tmp/local.db")
        )

    with pytest.raises(probe.ConfigError, match="hosted database host"):
        probe.PostgresReadinessConfig.from_env(
            _probe_env(SEXTANT_DATABASE_URL="postgresql+psycopg://user:pass@127.0.0.1/db")
        )

    with pytest.raises(probe.ConfigError, match="SEXTANT_MANAGED_POSTGRES_INSTANCE"):
        probe.PostgresReadinessConfig.from_env(
            _probe_env(SEXTANT_MANAGED_POSTGRES_INSTANCE="postgres-prod")
        )

    with pytest.raises(probe.ConfigError, match="positive integer"):
        probe.PostgresReadinessConfig.from_env(
            _probe_env(SEXTANT_POSTGRES_READINESS_MIN_SOURCE_DELTAS="0")
        )

    config = probe.PostgresReadinessConfig.from_env(_probe_env())

    assert config.database_url.host == "db.sextant.example"
    assert config.database_url.sanitized == (
        "postgresql+psycopg://sextant:***@db.sextant.example:5432/sextant"
    )
    assert config.managed_instance_scheme == "rds"
    assert config.min_source_deltas == 1


def test_hosted_postgres_probe_validates_schema_counts_and_redacts_evidence() -> None:
    probe = _load_probe_module()
    config = probe.PostgresReadinessConfig.from_env(_probe_env())
    expected_head = "9e0f1a2b3c4d"

    def query_runner(sql: str) -> object:
        if "SELECT 1" in sql:
            return 1
        if "current_database" in sql:
            return "sextant"
        if "current_user" in sql:
            return "sextant_app"
        if "server_version" in sql:
            return "16.3"
        if "alembic_version" in sql:
            return expected_head
        if "source_deltas" in sql:
            return 2
        if "source_spans restored_source_spans" in sql:
            return 3
        if "source_spans" in sql:
            return 4
        if "memory_pages" in sql:
            return 5
        raise AssertionError(f"unexpected SQL: {sql}")

    evidence = probe.run_postgres_readiness_probe(
        config,
        query_runner=query_runner,
        expected_alembic_head=expected_head,
    )
    encoded = json.dumps(evidence, sort_keys=True)

    assert evidence["status"] == "pass"
    assert evidence["database_host"] == "db.sextant.example"
    assert evidence["database_url"] == (
        "postgresql+psycopg://sextant:***@db.sextant.example:5432/sextant"
    )
    assert evidence["alembic_version"] == expected_head
    assert evidence["expected_alembic_head"] == expected_head
    assert evidence["source_delta_count"] == 2
    assert evidence["source_span_count"] == 4
    assert evidence["memory_page_count"] == 5
    assert evidence["source_span_raw_resolution_count"] == 3
    assert evidence["managed_instance_scheme"] == "rds"
    assert evidence["managed_instance_fingerprint"]
    assert "secret" not in encoded
    assert "prod/sextant" not in encoded


def test_hosted_postgres_probe_fails_on_migration_or_evidence_gap() -> None:
    probe = _load_probe_module()
    config = probe.PostgresReadinessConfig.from_env(_probe_env())

    def stale_migration_runner(sql: str) -> object:
        if "alembic_version" in sql:
            return "old-head"
        return 1

    with pytest.raises(probe.PostgresReadinessError, match="Alembic"):
        probe.run_postgres_readiness_probe(
            config,
            query_runner=stale_migration_runner,
            expected_alembic_head="9e0f1a2b3c4d",
        )

    def missing_raw_runner(sql: str) -> object:
        if "alembic_version" in sql:
            return "9e0f1a2b3c4d"
        if "source_spans restored_source_spans" in sql:
            return 0
        return 1

    with pytest.raises(probe.PostgresReadinessError, match="SourceSpan -> RawSource"):
        probe.run_postgres_readiness_probe(
            config,
            query_runner=missing_raw_runner,
            expected_alembic_head="9e0f1a2b3c4d",
        )


def test_hosted_postgres_check_config_cli() -> None:
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
        env=_probe_env(SEXTANT_MANAGED_POSTGRES_INSTANCE="local-postgres"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-postgres-readiness-config-ok"
    assert invalid.returncode == 1
    assert "SEXTANT_MANAGED_POSTGRES_INSTANCE" in invalid.stderr
