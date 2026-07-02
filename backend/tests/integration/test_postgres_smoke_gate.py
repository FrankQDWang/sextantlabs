import os
import subprocess
import sys
from pathlib import Path


def test_postgres_smoke_gate_runs_real_database_backup_and_restore() -> None:
    script = Path("scripts/postgres-smoke.sh")
    assert script.exists(), "expected a Postgres production smoke gate script"
    smoke = Path("backend/scripts/production_smoke.py")
    assert smoke.exists(), "expected a production smoke script"

    text = script.read_text(encoding="utf-8")
    required_wrapper_fragments = [
        "postgres:16",
        'DATABASE_URL="postgresql+psycopg://',
        "export SEXTANT_DATABASE_URL",
        "export SEXTANT_OBJECT_STORE_ROOT",
        "alembic upgrade head",
        "backend/scripts/production_smoke.py",
        "backend/scripts/worker_healthcheck.py",
        "pg_dump",
        "psql",
        "restore",
        "RESTORED_SOURCE_SPANS_WITH_RAW",
        "source_spans restored_source_spans",
        "source_raw_sources restored_raw_sources",
        "trap cleanup EXIT",
    ]
    for fragment in required_wrapper_fragments:
        assert fragment in text

    smoke_text = smoke.read_text(encoding="utf-8")
    required_smoke_fragments = [
        "/memory/answer",
        "/agent/check-risk",
        "memory_answer_type",
        "memory_answer_source_span_count",
        "review_finding_count",
    ]
    for fragment in required_smoke_fragments:
        assert fragment in smoke_text


def test_local_production_smoke_rejects_production_release_environment() -> None:
    env = os.environ.copy()
    env["SEXTANT_RELEASE_ENVIRONMENT"] = "production"
    result = subprocess.run(
        [sys.executable, "backend/scripts/production_smoke.py"],
        cwd=Path.cwd(),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "local production-path smoke" in result.stderr


def test_pgvector_smoke_gate_validates_real_indexed_semantic_retrieval() -> None:
    script = Path("scripts/pgvector-smoke.sh")
    assert script.exists(), "expected a pgvector production semantic retrieval smoke gate script"

    text = script.read_text(encoding="utf-8")
    required_fragments = [
        "pgvector/pgvector:pg17",
        "CREATE EXTENSION IF NOT EXISTS vector",
        "alembic upgrade head",
        "refresh_project_semantic_embeddings",
        "semantic_ref_keys_for_text",
        "ix_semantic_embeddings_embedding_vector_hnsw",
        "embedding_vector::vector(32) <=>",
        "pgvector_semantic_recall",
        "trap cleanup EXIT",
    ]
    for fragment in required_fragments:
        assert fragment in text
