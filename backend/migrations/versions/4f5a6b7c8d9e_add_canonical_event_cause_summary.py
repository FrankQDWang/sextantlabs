"""add canonical event cause summary

Revision ID: 4f5a6b7c8d9e
Revises: 3e4f5a6b7c8d
Create Date: 2026-06-14 21:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4f5a6b7c8d9e"
down_revision: str | None = "3e4f5a6b7c8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("story_canonical_events") as batch_op:
        batch_op.add_column(sa.Column("cause_summary", sa.String(length=2000), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("story_canonical_events") as batch_op:
        batch_op.drop_column("cause_summary")
