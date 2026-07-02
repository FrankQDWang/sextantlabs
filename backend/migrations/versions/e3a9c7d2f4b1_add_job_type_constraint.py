"""add job type constraint

Revision ID: e3a9c7d2f4b1
Revises: d2f8a1c4e6b9
Create Date: 2026-06-01 22:45:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "e3a9c7d2f4b1"
down_revision: str | None = "d2f8a1c4e6b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JOB_TYPE_VALUES = (
    "'normalize_source', 'split_structure', 'run_memory_writeback', "
    "'extract_mentions', 'resolve_aliases', 'extract_events', "
    "'aggregate_events', 'derive_facts', 'run_conflict_policy', "
    "'rewrite_memory_page', 'rebuild_graph_projection', 'build_context_pack', "
    "'run_agent_candidate', 'run_agent_review', 'run_skill_replay_eval'"
)


def upgrade() -> None:
    with op.batch_alter_table("job_records") as batch_op:
        batch_op.create_check_constraint(
            "ck_job_records_job_type",
            f"job_type in ({JOB_TYPE_VALUES})",
        )


def downgrade() -> None:
    with op.batch_alter_table("job_records") as batch_op:
        batch_op.drop_constraint("ck_job_records_job_type", type_="check")
