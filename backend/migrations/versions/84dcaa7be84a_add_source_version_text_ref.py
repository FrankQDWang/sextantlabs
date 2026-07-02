from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "84dcaa7be84a"
down_revision = "5a73073bd5ac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_versions",
        sa.Column("raw_text_ref", sa.String(length=1000), nullable=True),
    )
    op.execute(
        """
        UPDATE source_versions
        SET raw_text_ref = (
          SELECT source_raw_sources.raw_text_ref
          FROM source_raw_sources
          WHERE source_raw_sources.id = source_versions.source_id
        )
        WHERE raw_text_ref IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("source_versions", "raw_text_ref")
