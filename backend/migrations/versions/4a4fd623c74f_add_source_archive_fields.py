"""add source archive fields

Revision ID: 4a4fd623c74f
Revises: cf3a9a83f4e2
Create Date: 2026-06-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4a4fd623c74f"
down_revision: str | None = "cf3a9a83f4e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("source_raw_sources") as batch:
        batch.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("archived_by", sa.Uuid(), nullable=True))
        batch.create_index(
            op.f("ix_source_raw_sources_archived_at"),
            ["archived_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("source_raw_sources") as batch:
        batch.drop_index(op.f("ix_source_raw_sources_archived_at"))
        batch.drop_column("archived_by")
        batch.drop_column("archived_at")
