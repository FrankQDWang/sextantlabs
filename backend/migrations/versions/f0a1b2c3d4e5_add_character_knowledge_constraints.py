"""add character knowledge constraints

Revision ID: f0a1b2c3d4e5
Revises: e9c1a0d7b2f3
Create Date: 2026-06-04 14:45:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: str | None = "e9c1a0d7b2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CHARACTER_KNOWLEDGE_CERTAINTIES = (
    "'known', 'suspected', 'false_belief', 'misunderstands', 'does_not_know'"
)
CHARACTER_KNOWLEDGE_STATUSES = "'active', 'superseded'"


def upgrade() -> None:
    with op.batch_alter_table("memory_character_knowledge") as batch_op:
        batch_op.create_check_constraint(
            "ck_memory_character_knowledge_certainty",
            f"certainty in ({CHARACTER_KNOWLEDGE_CERTAINTIES})",
        )
        batch_op.create_check_constraint(
            "ck_memory_character_knowledge_status",
            f"status in ({CHARACTER_KNOWLEDGE_STATUSES})",
        )


def downgrade() -> None:
    with op.batch_alter_table("memory_character_knowledge") as batch_op:
        batch_op.drop_constraint("ck_memory_character_knowledge_status", type_="check")
        batch_op.drop_constraint("ck_memory_character_knowledge_certainty", type_="check")
