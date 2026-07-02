"""add scene pov confidence evidence

Revision ID: e9c1a0d7b2f3
Revises: d8b6f0a2c4e1
Create Date: 2026-06-04 11:20:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e9c1a0d7b2f3"
down_revision: str | None = "d8b6f0a2c4e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def json_type() -> sa.types.TypeEngine:
    if op.get_context().dialect.name == "postgresql":
        return postgresql.JSONB()
    return sa.JSON()


def json_empty_array_default() -> sa.TextClause:
    if op.get_context().dialect.name == "postgresql":
        return sa.text("'[]'::jsonb")
    return sa.text("'[]'")


def upgrade() -> None:
    with op.batch_alter_table("story_scenes") as batch_op:
        batch_op.add_column(sa.Column("pov_confidence", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "pov_evidence_span_ids",
                json_type(),
                server_default=json_empty_array_default(),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("pov_uncertainty_reason", sa.String(length=500), nullable=True)
        )
        batch_op.create_check_constraint(
            "ck_story_scenes_pov_confidence_range",
            "pov_confidence is null or (pov_confidence >= 0 and pov_confidence <= 1)",
        )


def downgrade() -> None:
    with op.batch_alter_table("story_scenes") as batch_op:
        batch_op.drop_constraint("ck_story_scenes_pov_confidence_range", type_="check")
        batch_op.drop_column("pov_uncertainty_reason")
        batch_op.drop_column("pov_evidence_span_ids")
        batch_op.drop_column("pov_confidence")
