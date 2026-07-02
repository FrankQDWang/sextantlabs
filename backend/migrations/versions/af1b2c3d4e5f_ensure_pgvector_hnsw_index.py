"""ensure pgvector hnsw semantic index

Revision ID: af1b2c3d4e5f
Revises: 9e0f1a2b3c4d
Create Date: 2026-07-01 15:45:00.000000
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from alembic import op

revision: str = "af1b2c3d4e5f"
down_revision: str | None = "9e0f1a2b3c4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    context = op.get_context()
    if context.dialect.name != "postgresql":
        return
    embedding_dimensions = _configured_embedding_dimensions()
    if embedding_dimensions is None:
        return
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


def _configured_embedding_dimensions() -> int | None:
    value = os.environ.get("SEXTANT_EMBEDDING_DIMENSIONS", "").strip()
    if not value:
        return None
    dimensions = int(value)
    if dimensions <= 0:
        raise ValueError("SEXTANT_EMBEDDING_DIMENSIONS must be a positive integer.")
    return dimensions
