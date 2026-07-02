"""add pgvector semantic index

Revision ID: 7c8d9e0f1a2b
Revises: 6b7c8d9e0f1a
Create Date: 2026-06-16 14:20:00.000000
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c8d9e0f1a2b"
down_revision: str | None = "6b7c8d9e0f1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    context = op.get_context()
    if context.dialect.name != "postgresql":
        return

    bind = op.get_bind()
    pgvector_available = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector')")
    ).scalar()
    if not pgvector_available:
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE semantic_embeddings ADD COLUMN IF NOT EXISTS embedding_vector vector")
    op.execute(
        """
        UPDATE semantic_embeddings
        SET embedding_vector = (
          '[' || (
            SELECT string_agg(value, ',')
            FROM jsonb_array_elements_text(vector::jsonb) AS value
          ) || ']'
        )::vector
        WHERE embedding_vector IS NULL
        """
    )
    embedding_dimensions = _configured_embedding_dimensions()
    if embedding_dimensions is not None:
        op.execute(
            f"""
            CREATE INDEX IF NOT EXISTS ix_semantic_embeddings_embedding_vector_hnsw
            ON semantic_embeddings
            USING hnsw ((embedding_vector::vector({embedding_dimensions})) vector_cosine_ops)
            WHERE dimensions = {embedding_dimensions}
              AND embedding_vector IS NOT NULL
            """
        )


def downgrade() -> None:
    context = op.get_context()
    if context.dialect.name != "postgresql":
        return

    op.execute("DROP INDEX IF EXISTS ix_semantic_embeddings_embedding_vector_hnsw")
    op.execute("ALTER TABLE semantic_embeddings DROP COLUMN IF EXISTS embedding_vector")


def _configured_embedding_dimensions() -> int | None:
    value = os.environ.get("SEXTANT_EMBEDDING_DIMENSIONS", "").strip()
    if not value:
        return None
    dimensions = int(value)
    if dimensions <= 0:
        raise ValueError("SEXTANT_EMBEDDING_DIMENSIONS must be a positive integer.")
    return dimensions
