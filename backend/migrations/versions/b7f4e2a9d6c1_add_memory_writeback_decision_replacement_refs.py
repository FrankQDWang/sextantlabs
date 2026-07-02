"""add memory writeback decision replacement refs

Revision ID: b7f4e2a9d6c1
Revises: a2b7c6d8e9f0
Create Date: 2026-06-01 18:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7f4e2a9d6c1"
down_revision: str | None = "a2b7c6d8e9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memory_writeback_decisions",
        sa.Column(
            "replacement_refs",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("memory_writeback_decisions", "replacement_refs")
