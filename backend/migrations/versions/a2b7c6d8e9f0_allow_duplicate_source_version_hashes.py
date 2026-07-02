"""allow duplicate source version hashes

Revision ID: a2b7c6d8e9f0
Revises: 9f0b7c1a2d3e
Create Date: 2026-06-01 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a2b7c6d8e9f0"
down_revision: str | None = "9f0b7c1a2d3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("source_versions") as batch:
        batch.drop_constraint("uq_source_versions_hash", type_="unique")


def downgrade() -> None:
    with op.batch_alter_table("source_versions") as batch:
        batch.create_unique_constraint(
            "uq_source_versions_hash",
            ["source_id", "raw_hash"],
        )
