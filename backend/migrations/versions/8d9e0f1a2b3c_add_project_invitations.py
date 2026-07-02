"""add project invitations

Revision ID: 8d9e0f1a2b3c
Revises: 7c8d9e0f1a2b
Create Date: 2026-06-19 17:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8d9e0f1a2b3c"
down_revision: str | None = "7c8d9e0f1a2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("member_actor_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("delivery_provider_ref", sa.String(length=300), nullable=False),
        sa.Column("delivery_target_ref", sa.String(length=300), nullable=False),
        sa.Column("token_issuer_ref", sa.String(length=300), nullable=True),
        sa.Column("status", sa.String(length=60), nullable=False),
        sa.Column("delivery_status", sa.String(length=40), nullable=False),
        sa.Column("token_status", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role in ('owner', 'editor', 'viewer')",
            name="ck_project_invitations_role",
        ),
        sa.CheckConstraint(
            "status in ('pending_external_delivery', 'cancelled')",
            name="ck_project_invitations_status",
        ),
        sa.CheckConstraint(
            "delivery_status in ('not_sent', 'sent', 'failed')",
            name="ck_project_invitations_delivery_status",
        ),
        sa.CheckConstraint(
            "token_status in ('not_issued', 'issued', 'failed')",
            name="ck_project_invitations_token_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "member_actor_id",
            "status",
            name="uq_project_invitations_active_actor",
        ),
    )
    op.create_index(
        op.f("ix_project_invitations_member_actor_id"),
        "project_invitations",
        ["member_actor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_invitations_project_id"),
        "project_invitations",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_project_invitations_project_id"), table_name="project_invitations")
    op.drop_index(
        op.f("ix_project_invitations_member_actor_id"),
        table_name="project_invitations",
    )
    op.drop_table("project_invitations")
