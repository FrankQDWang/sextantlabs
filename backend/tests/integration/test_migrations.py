from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_head_creates_production_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "sextant.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{db_path}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "source_raw_sources",
        "source_versions",
        "source_processed_views",
        "source_spans",
        "source_deltas",
        "memory_writeback_decisions",
        "review_items",
        "agent_draft_candidates",
        "agent_review_findings",
        "story_fact_assertions",
        "memory_evidence_log_entries",
        "memory_graph_projection_edges",
        "story_schema_packs",
        "project_story_schema_bindings",
        "job_records",
        "audit_events",
        "semantic_embeddings",
    }.issubset(tables)

    view_indexes = inspector.get_indexes("source_processed_views")
    assert any(
        index["name"] == "uq_source_processed_views_current_version" and index["unique"]
        for index in view_indexes
    )
    decision_columns = {
        column["name"] for column in inspector.get_columns("memory_writeback_decisions")
    }
    assert "replacement_refs" in decision_columns
    alias_columns = {column["name"] for column in inspector.get_columns("story_alias_records")}
    assert {"valid_from_scene_id", "valid_until_scene_id"}.issubset(alias_columns)
    event_columns = {column["name"] for column in inspector.get_columns("story_canonical_events")}
    assert "cause_summary" in event_columns
    scene_columns = {column["name"] for column in inspector.get_columns("story_scenes")}
    assert {
        "pov_confidence",
        "pov_evidence_span_ids",
        "pov_uncertainty_reason",
    }.issubset(scene_columns)
    schema_pack_columns = {column["name"] for column in inspector.get_columns("story_schema_packs")}
    assert {
        "pack_type",
        "pack_name",
        "version",
        "entity_types",
        "event_types",
        "relations",
    }.issubset(schema_pack_columns)
    binding_indexes = inspector.get_indexes("project_story_schema_bindings")
    assert any(
        index["name"] == "uq_project_story_schema_bindings_active" and index["unique"]
        for index in binding_indexes
    )
    semantic_embedding_columns = {
        column["name"] for column in inspector.get_columns("semantic_embeddings")
    }
    assert {
        "project_id",
        "target_type",
        "target_id",
        "target_ref",
        "provider",
        "model_name",
        "dimensions",
        "vector",
        "evidence_refs",
    }.issubset(semantic_embedding_columns)


def test_alembic_env_accepts_percent_encoded_database_url(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "sextant%25encoded.db"
    monkeypatch.setenv("SEXTANT_DATABASE_URL", f"sqlite+pysqlite:///{db_path}")

    command.upgrade(Config("alembic.ini"), "head")

    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    inspector = inspect(engine)
    assert "alembic_version" in set(inspector.get_table_names())


def test_pgvector_migration_creates_configured_dimension_hnsw_index() -> None:
    migration = Path(
        "backend/migrations/versions/7c8d9e0f1a2b_add_pgvector_semantic_index.py"
    ).read_text(encoding="utf-8")

    assert "SEXTANT_EMBEDDING_DIMENSIONS" in migration
    assert "ix_semantic_embeddings_embedding_vector_hnsw" in migration
    assert "USING hnsw" in migration
    assert "embedding_vector::vector(" in migration
    assert "vector_cosine_ops" in migration
    assert "WHERE dimensions =" in migration
