"""add source delta new version

Revision ID: cf3a9a83f4e2
Revises: ef9b4a3f2d1c
Create Date: 2026-06-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cf3a9a83f4e2"
down_revision: str | None = "ef9b4a3f2d1c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("source_deltas") as batch:
        batch.add_column(sa.Column("new_version_id", sa.Uuid(), nullable=True))
        batch.create_index(
            op.f("ix_source_deltas_new_version_id"),
            ["new_version_id"],
            unique=False,
        )
        batch.create_foreign_key(
            op.f("fk_source_deltas_new_version_id_source_versions"),
            "source_versions",
            ["new_version_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("source_deltas") as batch:
        batch.drop_constraint(
            op.f("fk_source_deltas_new_version_id_source_versions"),
            type_="foreignkey",
        )
        batch.drop_index(op.f("ix_source_deltas_new_version_id"))
        batch.drop_column("new_version_id")
