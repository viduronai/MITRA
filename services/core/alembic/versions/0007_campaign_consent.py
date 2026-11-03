"""Campaign list consent: the owner's attestation on a campaign; consent records it creates.

Revision ID: 0007_campaign_consent
Revises: 0006_payments
Create Date: 2026-11-03

* ``campaign`` gains the owner's list attestation (lead consent policy for pasted / uploaded
  lists, docs/08 section 8.5): scope (service, or promotional for promotional lists), the exact
  words ticked, their version, who ticked them (id + name) and when.
* ``tel_consent_source`` gains ``owner_attested_list``: consent records written for the people
  on an attested campaign (purpose = the campaign; they expire when the campaign ends, after 30
  days at most). The dial-time compliance gate still decides every call.

Downgrade note: Postgres cannot drop enum values, so ``owner_attested_list`` stays.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_campaign_consent"
down_revision: str | None = "0006_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE tel_consent_source ADD VALUE IF NOT EXISTS 'owner_attested_list'")
    scope = postgresql.ENUM(name="tel_consent_scope", create_type=False)
    op.add_column("campaign", sa.Column("consent_scope", scope, nullable=True))
    op.add_column("campaign", sa.Column("consent_text", sa.Text(), nullable=True))
    op.add_column("campaign", sa.Column("consent_text_version", sa.String(20), nullable=True))
    op.add_column("campaign", sa.Column("consent_by", sa.Uuid(), nullable=True))
    op.add_column("campaign", sa.Column("consent_by_name", sa.String(120), nullable=True))
    op.add_column("campaign", sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_campaign_consent_by_app_user",
        "campaign",
        "app_user",
        ["consent_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_campaign_consent_by_app_user", "campaign", type_="foreignkey")
    for column in (
        "consent_at",
        "consent_by_name",
        "consent_by",
        "consent_text_version",
        "consent_text",
        "consent_scope",
    ):
        op.drop_column("campaign", column)
