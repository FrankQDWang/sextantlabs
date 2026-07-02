"""include graph edge subject in identity

Revision ID: 2d3e4f5a6b7c
Revises: 1c2d3e4f5a6b
Create Date: 2026-06-04 16:36:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "2d3e4f5a6b7c"
down_revision: str | None = "1c2d3e4f5a6b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("memory_graph_projection_edges") as batch_op:
        batch_op.drop_constraint(
            "uq_memory_graph_projection_edges_identity",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_memory_graph_projection_edges_identity",
            ["project_id", "source_ref", "subject_ref", "relation", "target_ref"],
        )


def downgrade() -> None:
    with op.batch_alter_table("memory_graph_projection_edges") as batch_op:
        batch_op.drop_constraint(
            "uq_memory_graph_projection_edges_identity",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_memory_graph_projection_edges_identity",
            ["project_id", "source_ref", "relation", "target_ref"],
        )
