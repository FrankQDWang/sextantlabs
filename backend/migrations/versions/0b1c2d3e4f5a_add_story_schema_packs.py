"""add story schema packs

Revision ID: 0b1c2d3e4f5a
Revises: f0a1b2c3d4e5
Create Date: 2026-06-04 15:25:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0b1c2d3e4f5a"
down_revision: str | None = "f0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def json_type() -> sa.types.TypeEngine:
    if op.get_context().dialect.name == "postgresql":
        return postgresql.JSONB()
    return sa.JSON()


def upgrade() -> None:
    op.create_table(
        "story_schema_packs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("pack_type", sa.String(length=40), nullable=False),
        sa.Column("pack_name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("entity_types", json_type(), nullable=False),
        sa.Column("event_types", json_type(), nullable=False),
        sa.Column("relations", json_type(), nullable=False),
        sa.Column("extraction_hints", json_type(), nullable=False),
        sa.Column("risk_rules", json_type(), nullable=False),
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
            "((pack_type = 'project_override' and project_id is not null) or "
            "(pack_type in ('base', 'genre') and project_id is null))",
            name="ck_story_schema_packs_project_scope",
        ),
        sa.CheckConstraint(
            "pack_type in ('base', 'genre', 'project_override')",
            name="ck_story_schema_packs_type",
        ),
        sa.CheckConstraint(
            "status in ('active', 'deprecated')",
            name="ck_story_schema_packs_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_story_schema_packs_project_id"),
        "story_schema_packs",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "uq_story_schema_packs_global_version",
        "story_schema_packs",
        ["pack_type", "pack_name", "version"],
        unique=True,
        sqlite_where=sa.text("project_id is null"),
        postgresql_where=sa.text("project_id is null"),
    )
    op.create_index(
        "uq_story_schema_packs_project_version",
        "story_schema_packs",
        ["project_id", "pack_type", "pack_name", "version"],
        unique=True,
        sqlite_where=sa.text("project_id is not null"),
        postgresql_where=sa.text("project_id is not null"),
    )

    op.create_table(
        "project_story_schema_bindings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("base_schema_pack_id", sa.Uuid(), nullable=False),
        sa.Column("genre_schema_pack_id", sa.Uuid(), nullable=True),
        sa.Column("project_override_pack_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
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
            "status in ('active', 'superseded')",
            name="ck_project_story_schema_bindings_status",
        ),
        sa.ForeignKeyConstraint(["base_schema_pack_id"], ["story_schema_packs.id"]),
        sa.ForeignKeyConstraint(["genre_schema_pack_id"], ["story_schema_packs.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["project_override_pack_id"], ["story_schema_packs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_project_story_schema_bindings_base_schema_pack_id"),
        "project_story_schema_bindings",
        ["base_schema_pack_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_story_schema_bindings_genre_schema_pack_id"),
        "project_story_schema_bindings",
        ["genre_schema_pack_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_story_schema_bindings_project_id"),
        "project_story_schema_bindings",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_story_schema_bindings_project_override_pack_id"),
        "project_story_schema_bindings",
        ["project_override_pack_id"],
        unique=False,
    )
    op.create_index(
        "uq_project_story_schema_bindings_active",
        "project_story_schema_bindings",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_project_story_schema_bindings_active",
        table_name="project_story_schema_bindings",
    )
    op.drop_index(
        op.f("ix_project_story_schema_bindings_project_override_pack_id"),
        table_name="project_story_schema_bindings",
    )
    op.drop_index(
        op.f("ix_project_story_schema_bindings_project_id"),
        table_name="project_story_schema_bindings",
    )
    op.drop_index(
        op.f("ix_project_story_schema_bindings_genre_schema_pack_id"),
        table_name="project_story_schema_bindings",
    )
    op.drop_index(
        op.f("ix_project_story_schema_bindings_base_schema_pack_id"),
        table_name="project_story_schema_bindings",
    )
    op.drop_table("project_story_schema_bindings")
    op.drop_index("uq_story_schema_packs_project_version", table_name="story_schema_packs")
    op.drop_index("uq_story_schema_packs_global_version", table_name="story_schema_packs")
    op.drop_index(op.f("ix_story_schema_packs_project_id"), table_name="story_schema_packs")
    op.drop_table("story_schema_packs")
