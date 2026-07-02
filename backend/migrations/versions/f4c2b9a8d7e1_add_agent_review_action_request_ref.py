"""add agent review action request ref

Revision ID: f4c2b9a8d7e1
Revises: e3a9c7d2f4b1
Create Date: 2026-06-03 10:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4c2b9a8d7e1"
down_revision: str | None = "e3a9c7d2f4b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_review_findings") as batch_op:
        batch_op.add_column(sa.Column("action_request_id", sa.Uuid(), nullable=True))
        batch_op.alter_column("draft_candidate_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.create_index(
            op.f("ix_agent_review_findings_action_request_id"),
            ["action_request_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            op.f("fk_agent_review_findings_action_request_id_agent_action_requests"),
            "agent_action_requests",
            ["action_request_id"],
            ["id"],
        )

    op.execute(
        """
        update agent_review_findings
        set action_request_id = (
            select action_request_id
            from agent_draft_candidates
            where agent_draft_candidates.id = agent_review_findings.draft_candidate_id
        )
        where action_request_id is null
        """
    )

    with op.batch_alter_table("agent_review_findings") as batch_op:
        batch_op.alter_column("action_request_id", existing_type=sa.Uuid(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("agent_review_findings") as batch_op:
        batch_op.alter_column("draft_candidate_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.drop_constraint(
            op.f("fk_agent_review_findings_action_request_id_agent_action_requests"),
            type_="foreignkey",
        )
        batch_op.drop_index(op.f("ix_agent_review_findings_action_request_id"))
        batch_op.drop_column("action_request_id")
