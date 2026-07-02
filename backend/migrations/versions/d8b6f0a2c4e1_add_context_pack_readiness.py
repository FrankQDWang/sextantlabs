"""add context pack readiness

Revision ID: d8b6f0a2c4e1
Revises: c6e4b2d1a9f0
Create Date: 2026-06-03 15:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d8b6f0a2c4e1"
down_revision: str | None = "c6e4b2d1a9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def json_type() -> sa.types.TypeEngine:
    if op.get_context().dialect.name == "postgresql":
        return postgresql.JSONB()
    return sa.JSON()


def upgrade() -> None:
    op.create_table(
        "context_pack_readiness",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_span_id", sa.Uuid(), nullable=False),
        sa.Column("source_delta_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.String(length=80), nullable=False),
        sa.Column("affected_refs", json_type(), nullable=False),
        sa.Column("evidence_refs", json_type(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reason in ('memory_dependency_changed', 'review_dependency_changed')",
            name="ck_context_pack_readiness_reason",
        ),
        sa.CheckConstraint(
            "status in ('pending', 'stale', 'consumed')",
            name="ck_context_pack_readiness_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["source_delta_id"], ["source_deltas.id"]),
        sa.ForeignKeyConstraint(["source_span_id"], ["source_spans.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "source_span_id",
            "reason",
            name="uq_context_pack_readiness_span_reason",
        ),
    )
    op.create_index(
        op.f("ix_context_pack_readiness_project_id"),
        "context_pack_readiness",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_context_pack_readiness_source_delta_id"),
        "context_pack_readiness",
        ["source_delta_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_context_pack_readiness_source_span_id"),
        "context_pack_readiness",
        ["source_span_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_context_pack_readiness_source_span_id"),
        table_name="context_pack_readiness",
    )
    op.drop_index(
        op.f("ix_context_pack_readiness_source_delta_id"),
        table_name="context_pack_readiness",
    )
    op.drop_index(
        op.f("ix_context_pack_readiness_project_id"),
        table_name="context_pack_readiness",
    )
    op.drop_table("context_pack_readiness")
