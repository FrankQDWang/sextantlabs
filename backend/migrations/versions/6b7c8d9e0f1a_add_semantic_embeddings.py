"""add semantic embeddings

Revision ID: 6b7c8d9e0f1a
Revises: 4f5a6b7c8d9e
Create Date: 2026-06-16 13:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6b7c8d9e0f1a"
down_revision: str | None = "4f5a6b7c8d9e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JOB_TYPE_VALUES = (
    "'normalize_source', 'split_structure', 'run_memory_writeback', "
    "'refresh_semantic_index', 'extract_mentions', 'resolve_aliases', "
    "'extract_events', 'aggregate_events', 'derive_facts', 'run_conflict_policy', "
    "'rewrite_memory_page', 'rebuild_graph_projection', 'build_context_pack', "
    "'run_agent_candidate', 'run_agent_review', 'run_skill_replay_eval'"
)

PREVIOUS_JOB_TYPE_VALUES = (
    "'normalize_source', 'split_structure', 'run_memory_writeback', "
    "'extract_mentions', 'resolve_aliases', 'extract_events', "
    "'aggregate_events', 'derive_facts', 'run_conflict_policy', "
    "'rewrite_memory_page', 'rebuild_graph_projection', 'build_context_pack', "
    "'run_agent_candidate', 'run_agent_review', 'run_skill_replay_eval'"
)


def upgrade() -> None:
    with op.batch_alter_table("job_records") as batch_op:
        batch_op.drop_constraint("ck_job_records_job_type", type_="check")
        batch_op.create_check_constraint(
            "ck_job_records_job_type",
            f"job_type in ({JOB_TYPE_VALUES})",
        )

    op.create_table(
        "semantic_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("target_ref", sa.JSON(), nullable=False),
        sa.Column("text_hash", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=160), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "dimensions > 0",
            name="ck_semantic_embeddings_dimensions_positive",
        ),
        sa.CheckConstraint(
            "target_type in ('memory_page', 'source_span', 'style_sample')",
            name="ck_semantic_embeddings_target_type",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "target_type",
            "target_id",
            "provider",
            "model_name",
            name="uq_semantic_embeddings_target_model",
        ),
    )
    op.create_index(
        op.f("ix_semantic_embeddings_project_id"),
        "semantic_embeddings",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_semantic_embeddings_target_id"),
        "semantic_embeddings",
        ["target_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_semantic_embeddings_target_id"), table_name="semantic_embeddings")
    op.drop_index(op.f("ix_semantic_embeddings_project_id"), table_name="semantic_embeddings")
    op.drop_table("semantic_embeddings")

    with op.batch_alter_table("job_records") as batch_op:
        batch_op.drop_constraint("ck_job_records_job_type", type_="check")
        batch_op.create_check_constraint(
            "ck_job_records_job_type",
            f"job_type in ({PREVIOUS_JOB_TYPE_VALUES})",
        )
