"""add story status constraints

Revision ID: d2f8a1c4e6b9
Revises: b7f4e2a9d6c1
Create Date: 2026-06-01 22:25:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "d2f8a1c4e6b9"
down_revision: str | None = "b7f4e2a9d6c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("story_alias_records") as batch_op:
        batch_op.drop_constraint("ck_story_alias_records_status", type_="check")
        batch_op.create_check_constraint(
            "ck_story_alias_records_status",
            "status in ('auto_accepted', 'proposed', 'low_confidence', "
            "'rejected', 'user_confirmed', 'user_corrected')",
        )

    with op.batch_alter_table("story_event_candidates") as batch_op:
        batch_op.create_check_constraint(
            "ck_story_event_candidates_aggregation_status",
            "aggregation_status in ('new', 'merged', 'related', 'conflict_version', 'rejected')",
        )

    with op.batch_alter_table("story_canonical_events") as batch_op:
        batch_op.create_check_constraint(
            "ck_story_canonical_events_status",
            "event_status in ('proposed', 'canon', 'disputed', 'deprecated', "
            "'external_canon', 'author_note')",
        )


def downgrade() -> None:
    with op.batch_alter_table("story_canonical_events") as batch_op:
        batch_op.drop_constraint("ck_story_canonical_events_status", type_="check")

    with op.batch_alter_table("story_event_candidates") as batch_op:
        batch_op.drop_constraint(
            "ck_story_event_candidates_aggregation_status",
            type_="check",
        )

    with op.batch_alter_table("story_alias_records") as batch_op:
        batch_op.drop_constraint("ck_story_alias_records_status", type_="check")
        batch_op.create_check_constraint(
            "ck_story_alias_records_status",
            "status in ('auto_accepted', 'proposed', 'rejected', "
            "'user_confirmed', 'user_corrected')",
        )
