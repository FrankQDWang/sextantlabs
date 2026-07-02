"""add project invitation external proof

Revision ID: 9e0f1a2b3c4d
Revises: 8d9e0f1a2b3c
Create Date: 2026-06-19 18:15:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9e0f1a2b3c4d"
down_revision: str | None = "8d9e0f1a2b3c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("project_invitations") as batch_op:
        batch_op.add_column(sa.Column("delivery_proof_ref", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("token_proof_ref", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("token_issued_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.drop_constraint("ck_project_invitations_status", type_="check")
        batch_op.create_check_constraint(
            "ck_project_invitations_status",
            "status in ('pending_external_delivery', 'external_delivery_recorded', 'cancelled')",
        )


def downgrade() -> None:
    with op.batch_alter_table("project_invitations") as batch_op:
        batch_op.drop_constraint("ck_project_invitations_status", type_="check")
        batch_op.create_check_constraint(
            "ck_project_invitations_status",
            "status in ('pending_external_delivery', 'cancelled')",
        )
        batch_op.drop_column("token_issued_at")
        batch_op.drop_column("delivered_at")
        batch_op.drop_column("token_proof_ref")
        batch_op.drop_column("delivery_proof_ref")
