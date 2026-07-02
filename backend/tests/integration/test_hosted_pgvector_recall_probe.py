from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path("backend/scripts/hosted_pgvector_recall_probe.py")


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("hosted_pgvector_recall_probe", SCRIPT_PATH)
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
        "SEXTANT_VECTOR_INDEX_PROVIDER": "pgvector",
        "SEXTANT_EMBEDDING_PROVIDER": "openai",
        "SEXTANT_EMBEDDING_MODEL": "text-embedding-3-small",
        "SEXTANT_EMBEDDING_DIMENSIONS": "1536",
        "SEXTANT_PGVECTOR_RECALL_PROJECT_ID": "11111111-1111-4111-8111-111111111111",
        "SEXTANT_PGVECTOR_RECALL_LIMIT": "5",
    }
    env.update(overrides)
    return env


def test_hosted_pgvector_recall_config_rejects_non_production_or_local_runtime() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_RELEASE_ENVIRONMENT=production"):
        probe.PgvectorRecallConfig.from_env({})

    with pytest.raises(probe.ConfigError, match="SEXTANT_DATABASE_URL"):
        probe.PgvectorRecallConfig.from_env(_probe_env(SEXTANT_DATABASE_URL=""))

    with pytest.raises(probe.ConfigError, match="PostgreSQL"):
        probe.PgvectorRecallConfig.from_env(
            _probe_env(SEXTANT_DATABASE_URL="sqlite+pysqlite:///tmp/local.db")
        )

    with pytest.raises(probe.ConfigError, match="hosted database host"):
        probe.PgvectorRecallConfig.from_env(
            _probe_env(SEXTANT_DATABASE_URL="postgresql+psycopg://user:pass@localhost/db")
        )

    with pytest.raises(probe.ConfigError, match="SEXTANT_VECTOR_INDEX_PROVIDER"):
        probe.PgvectorRecallConfig.from_env(_probe_env(SEXTANT_VECTOR_INDEX_PROVIDER="json"))

    with pytest.raises(probe.ConfigError, match="SEXTANT_EMBEDDING_DIMENSIONS"):
        probe.PgvectorRecallConfig.from_env(_probe_env(SEXTANT_EMBEDDING_DIMENSIONS="0"))

    with pytest.raises(probe.ConfigError, match="SEXTANT_PGVECTOR_RECALL_PROJECT_ID"):
        probe.PgvectorRecallConfig.from_env(
            _probe_env(SEXTANT_PGVECTOR_RECALL_PROJECT_ID="not-a-uuid")
        )

    config = probe.PgvectorRecallConfig.from_env(_probe_env())

    assert config.database_url.host == "db.sextant.example"
    assert config.database_url.sanitized == (
        "postgresql+psycopg://sextant:***@db.sextant.example:5432/sextant"
    )
    assert config.embedding_provider == "openai"
    assert config.embedding_model == "text-embedding-3-small"
    assert config.embedding_dimensions == 1536
    assert config.recall_limit == 5


def test_hosted_pgvector_recall_evidence_is_sanitized_and_hashes_targets() -> None:
    probe = _load_probe_module()
    config = probe.PgvectorRecallConfig.from_env(_probe_env())
    checks = probe.PgvectorProbeChecks(
        vector_extension=True,
        embedding_vector_column=True,
        hnsw_index=True,
        vector_rows=12,
        probe_embedding_id="22222222-2222-4222-8222-222222222222",
        nearest_embedding_id="22222222-2222-4222-8222-222222222222",
        nearest_target_type="memory_page",
        nearest_distance=0.0,
    )

    evidence = probe.build_pgvector_evidence(config, checks)
    encoded = json.dumps(evidence, sort_keys=True)

    assert evidence["status"] == "pass"
    assert evidence["database_url"] == (
        "postgresql+psycopg://sextant:***@db.sextant.example:5432/sextant"
    )
    assert evidence["vector_extension"] is True
    assert evidence["embedding_vector_column"] is True
    assert evidence["hnsw_index"] == "ix_semantic_embeddings_embedding_vector_hnsw"
    assert evidence["vector_rows"] == 12
    assert evidence["nearest_distance"] == 0.0
    assert evidence["nearest_target_type"] == "memory_page"
    assert "secret" not in encoded
    assert "11111111-1111-4111-8111-111111111111" not in encoded
    assert "22222222-2222-4222-8222-222222222222" not in encoded
    assert "project_id_hash" in evidence
    assert "probe_embedding_id_hash" in evidence
    assert "nearest_embedding_id_hash" in evidence


def test_hosted_pgvector_recall_rejects_missing_index_or_bad_self_recall() -> None:
    probe = _load_probe_module()
    config = probe.PgvectorRecallConfig.from_env(_probe_env())
    good = {
        "vector_extension": True,
        "embedding_vector_column": True,
        "hnsw_index": True,
        "vector_rows": 1,
        "probe_embedding_id": "22222222-2222-4222-8222-222222222222",
        "nearest_embedding_id": "22222222-2222-4222-8222-222222222222",
        "nearest_target_type": "source_span",
        "nearest_distance": 0.0,
    }

    with pytest.raises(probe.PgvectorProbeError, match="vector extension"):
        probe.build_pgvector_evidence(
            config,
            probe.PgvectorProbeChecks(**{**good, "vector_extension": False}),
        )

    with pytest.raises(probe.PgvectorProbeError, match="HNSW index"):
        probe.build_pgvector_evidence(
            config, probe.PgvectorProbeChecks(**{**good, "hnsw_index": False})
        )

    with pytest.raises(probe.PgvectorProbeError, match="embedding vectors"):
        probe.build_pgvector_evidence(
            config, probe.PgvectorProbeChecks(**{**good, "vector_rows": 0})
        )

    with pytest.raises(probe.PgvectorProbeError, match="nearest neighbor"):
        probe.build_pgvector_evidence(
            config,
            probe.PgvectorProbeChecks(
                **{
                    **good,
                    "nearest_embedding_id": "33333333-3333-4333-8333-333333333333",
                }
            ),
        )

    with pytest.raises(probe.PgvectorProbeError, match="self-distance"):
        probe.build_pgvector_evidence(
            config,
            probe.PgvectorProbeChecks(**{**good, "nearest_distance": 0.25}),
        )


def test_hosted_pgvector_recall_check_config_cli() -> None:
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
        env=_probe_env(SEXTANT_DATABASE_URL="postgresql+psycopg://user:pass@127.0.0.1/db"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-pgvector-recall-config-ok"
    assert invalid.returncode == 1
    assert "hosted database host" in invalid.stderr
