"""add memory writeback decisions

Revision ID: ef9b4a3f2d1c
Revises: 84dcaa7be84a
Create Date: 2026-06-01 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ef9b4a3f2d1c"
down_revision: str | None = "84dcaa7be84a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_writeback_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_delta_id", sa.Uuid(), nullable=False),
        sa.Column("item_ref", sa.JSON(), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("correction", sa.JSON(), nullable=False),
        sa.Column("author_note", sa.String(length=2000), nullable=True),
        sa.Column("side_effects", sa.JSON(), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "decision in ('accept','reject','correct')",
            name="ck_memory_writeback_decisions_decision",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["source_delta_id"], ["source_deltas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_memory_writeback_decisions_project_id"),
        "memory_writeback_decisions",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_writeback_decisions_source_delta_id"),
        "memory_writeback_decisions",
        ["source_delta_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_memory_writeback_decisions_source_delta_id"),
        table_name="memory_writeback_decisions",
    )
    op.drop_index(
        op.f("ix_memory_writeback_decisions_project_id"),
        table_name="memory_writeback_decisions",
    )
    op.drop_table("memory_writeback_decisions")
