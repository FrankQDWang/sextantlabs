"""add alias scene boundaries

Revision ID: 3e4f5a6b7c8d
Revises: 2d3e4f5a6b7c
Create Date: 2026-06-12 16:52:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3e4f5a6b7c8d"
down_revision: str | None = "2d3e4f5a6b7c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("story_alias_records") as batch_op:
        batch_op.add_column(sa.Column("valid_from_scene_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("valid_until_scene_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("story_alias_records") as batch_op:
        batch_op.drop_column("valid_until_scene_id")
        batch_op.drop_column("valid_from_scene_id")
