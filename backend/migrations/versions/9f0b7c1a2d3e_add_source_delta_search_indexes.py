"""add source delta search indexes

Revision ID: 9f0b7c1a2d3e
Revises: 4a4fd623c74f
Create Date: 2026-06-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9f0b7c1a2d3e"
down_revision: str | None = "4a4fd623c74f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    dialect_name = op.get_bind().dialect.name
    with op.batch_alter_table("source_deltas") as batch:
        batch.add_column(
            sa.Column("submitted_text_search", sa.Text(), server_default="", nullable=False)
        )
        batch.create_index(
            op.f("ix_source_deltas_project_created_id"),
            ["project_id", "created_at", "id"],
            unique=False,
        )
        batch.create_index(
            op.f("ix_source_deltas_project_status_created"),
            ["project_id", "status", "created_at"],
            unique=False,
        )

    if dialect_name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.create_index(
            op.f("ix_source_deltas_search_trgm"),
            "source_deltas",
            ["submitted_text_search"],
            unique=False,
            postgresql_using="gin",
            postgresql_ops={"submitted_text_search": "gin_trgm_ops"},
        )
    else:
        op.create_index(
            op.f("ix_source_deltas_search_trgm"),
            "source_deltas",
            ["submitted_text_search"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("source_deltas") as batch:
        batch.drop_index(op.f("ix_source_deltas_search_trgm"))
        batch.drop_index(op.f("ix_source_deltas_project_status_created"))
        batch.drop_index(op.f("ix_source_deltas_project_created_id"))
        batch.drop_column("submitted_text_search")
