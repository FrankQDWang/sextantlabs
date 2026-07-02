"""allow dynamic graph projection relations

Revision ID: 1c2d3e4f5a6b
Revises: 0b1c2d3e4f5a
Create Date: 2026-06-04 16:22:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "1c2d3e4f5a6b"
down_revision: str | None = "0b1c2d3e4f5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BASE_RELATIONS = (
    "appears_in",
    "present_at",
    "occurred_at",
    "involves_object",
    "located_in",
    "owns",
    "member_of",
    "family_of",
    "ally_of",
    "enemy_of",
    "knows",
    "does_not_know",
    "reveals",
    "causes",
    "follows",
    "foreshadows",
    "contradicts",
    "belongs_to_plotline",
    "related_to",
)


def upgrade() -> None:
    with op.batch_alter_table("memory_graph_projection_edges") as batch_op:
        batch_op.drop_constraint(
            "ck_memory_graph_projection_edges_relation",
            type_="check",
        )


def downgrade() -> None:
    with op.batch_alter_table("memory_graph_projection_edges") as batch_op:
        batch_op.create_check_constraint(
            "ck_memory_graph_projection_edges_relation",
            f"relation in ({_sql_values(BASE_RELATIONS)})",
        )


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)
