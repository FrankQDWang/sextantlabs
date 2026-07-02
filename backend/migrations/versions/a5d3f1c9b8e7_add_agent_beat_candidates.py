"""add agent beat candidates

Revision ID: a5d3f1c9b8e7
Revises: f4c2b9a8d7e1
Create Date: 2026-06-03 10:35:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a5d3f1c9b8e7"
down_revision: str | None = "f4c2b9a8d7e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_beat_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("action_request_id", sa.Uuid(), nullable=False),
        sa.Column("context_pack_id", sa.Uuid(), nullable=True),
        sa.Column("target_source_id", sa.Uuid(), nullable=True),
        sa.Column("target_version_id", sa.Uuid(), nullable=True),
        sa.Column("target_scene_id", sa.Uuid(), nullable=True),
        sa.Column("affected_range", sa.JSON(), nullable=True),
        sa.Column("base_hash", sa.String(length=128), nullable=True),
        sa.Column("summary", sa.String(length=2000), nullable=False),
        sa.Column("driver_character", sa.String(length=400), nullable=False),
        sa.Column("agency_rationale", sa.String(length=2000), nullable=False),
        sa.Column("storytelling_rationale", sa.String(length=2000), nullable=False),
        sa.Column("cast_decision", sa.JSON(), nullable=False),
        sa.Column("tension", sa.String(length=1000), nullable=False),
        sa.Column("memory_refs", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status in ('suggested', 'selected', 'dismissed', 'archived')",
            name="ck_agent_beat_candidates_status",
        ),
        sa.ForeignKeyConstraint(["action_request_id"], ["agent_action_requests.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["target_scene_id"], ["story_scenes.id"]),
        sa.ForeignKeyConstraint(["target_source_id"], ["source_raw_sources.id"]),
        sa.ForeignKeyConstraint(["target_version_id"], ["source_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_beat_candidates_action_request_id"),
        "agent_beat_candidates",
        ["action_request_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_beat_candidates_project_id"),
        "agent_beat_candidates",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_agent_beat_candidates_project_id"),
        table_name="agent_beat_candidates",
    )
    op.drop_index(
        op.f("ix_agent_beat_candidates_action_request_id"),
        table_name="agent_beat_candidates",
    )
    op.drop_table("agent_beat_candidates")
