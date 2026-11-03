"""Approval summaries the server builds from the payload, in the viewer's language.

Revision ID: 0007_approval_summary
Revises: 0007_campaign_consent
Create Date: 2026-11-03

``approval.summary_key`` + ``summary_params`` (see ``approvals/summaries.py``): the app renders
``approvals.summaries.<key>`` with the params in te / hi / en; ``summary`` stays the English
fallback. Both are rebuilt after every edit, so a lowered list never says the old count.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_approval_summary"
down_revision: str | None = "0007_campaign_consent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("approval", sa.Column("summary_key", sa.String(48), nullable=True))
    op.add_column(
        "approval",
        sa.Column("summary_params", postgresql.JSONB(), server_default="{}", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("approval", "summary_params")
    op.drop_column("approval", "summary_key")
