"""add canonical entity constraints

Revision ID: c6e4b2d1a9f0
Revises: a5d3f1c9b8e7
Create Date: 2026-06-03 14:50:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c6e4b2d1a9f0"
down_revision: str | None = "a5d3f1c9b8e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ENTITY_TYPE_VALUES = (
    "'character', 'location', 'faction', 'object', 'event', 'scene', "
    "'chapter', 'plotline', 'lore', 'source', 'other'"
)
ENTITY_STATUS_VALUES = "'canon', 'draft', 'provisional', 'discarded', 'contradicted'"
CAST_TIER_VALUES = "'local_extra', 'minor_supporting', 'recurring', 'major', 'unknown'"


def upgrade() -> None:
    with op.batch_alter_table("story_canonical_entities") as batch_op:
        batch_op.create_check_constraint(
            "ck_story_canonical_entities_type",
            f"entity_type in ({ENTITY_TYPE_VALUES})",
        )
        batch_op.create_check_constraint(
            "ck_story_canonical_entities_status",
            f"canonical_status in ({ENTITY_STATUS_VALUES})",
        )
        batch_op.create_check_constraint(
            "ck_story_canonical_entities_cast_tier",
            f"cast_tier is null or cast_tier in ({CAST_TIER_VALUES})",
        )
        batch_op.create_check_constraint(
            "ck_story_canonical_entities_cast_tier_character_only",
            "entity_type = 'character' or cast_tier is null",
        )


def downgrade() -> None:
    with op.batch_alter_table("story_canonical_entities") as batch_op:
        batch_op.drop_constraint(
            "ck_story_canonical_entities_cast_tier_character_only",
            type_="check",
        )
        batch_op.drop_constraint("ck_story_canonical_entities_cast_tier", type_="check")
        batch_op.drop_constraint("ck_story_canonical_entities_status", type_="check")
        batch_op.drop_constraint("ck_story_canonical_entities_type", type_="check")
