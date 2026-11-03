"""Lead consent policy: consent purpose, version, exact text and expiry; owner attestations.

Revision ID: 0006_lead_consent
Revises: 0006_phones
Create Date: 2026-11-03

* ``consent_record`` gains ``purpose`` (e.g. ``enquiry_response``), ``text_version`` and
  ``consent_text`` (the exact words the person agreed to), and ``expires_at`` (portal enquiries
  count as service consent for 30 days; ``telephony.service.load_facts`` ignores expired rows).
* ``tel_consent_source`` gains the lead sources, so a record names the form or portal it came
  from, plus ``owner_attested`` for generic sources (API, Sheets, Zapier...).
* ``lead_consent_attestation``: who ticked "These people asked to be contacted about their
  enquiry" for a generic source, when, and with which text (append-only; revoking sets
  ``revoked_at``). A tenant table under RLS.
* ``lead.status`` allows ``no_attestation`` (stored, not called: no consent confirmed).

Downgrade note: Postgres cannot drop enum values, so the added ``tel_consent_source`` values stay.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mitra_core.config import get_settings

revision: str = "0006_lead_consent"
down_revision: str | None = "0006_phones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_SOURCES = (
    "website_form",
    "google_forms",
    "meta",
    "google_ads",
    "indiamart",
    "justdial",
    "owner_attested",
)
OLD_STATUSES = (
    "queued",
    "scheduled",
    "duplicate",
    "not_called",
    "blocked",
    "no_consent",
    "no_employee",
    "failed",
)
NEW_STATUSES = (*OLD_STATUSES, "no_attestation")
CURRENT_BUSINESS = "app_current_business_id()"


def _status_check(values: Sequence[str]) -> str:
    return f"status IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    role = get_settings().app_db_role
    for value in NEW_SOURCES:
        op.execute(f"ALTER TYPE tel_consent_source ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column("consent_record", sa.Column("purpose", sa.String(40), nullable=True))
    op.add_column("consent_record", sa.Column("text_version", sa.String(20), nullable=True))
    op.add_column("consent_record", sa.Column("consent_text", sa.Text(), nullable=True))
    op.add_column(
        "consent_record", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.drop_constraint("ck_lead_status", "lead", type_="check")
    op.create_check_constraint("ck_lead_status", "lead", _status_check(NEW_STATUSES))

    op.create_table(
        "lead_consent_attestation",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("user_name", sa.String(120), nullable=True),
        sa.Column("text_version", sa.String(20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "attested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_lead_consent_attestation"),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["business.id"],
            name="fk_lead_consent_attestation_business_id_business",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name="fk_lead_consent_attestation_user_id_app_user",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "source IN ('api', 'google_sheets', 'zapier')",
            name="ck_lead_consent_attestation_source",
        ),
    )
    op.create_index(
        "ix_lead_consent_attestation_active",
        "lead_consent_attestation",
        ["business_id", "source", "attested_at"],
    )
    op.execute("ALTER TABLE lead_consent_attestation ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE lead_consent_attestation FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON lead_consent_attestation FOR ALL "
        f"USING (business_id = {CURRENT_BUSINESS}) WITH CHECK (business_id = {CURRENT_BUSINESS})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON lead_consent_attestation TO {role}")


def downgrade() -> None:
    role = get_settings().app_db_role
    op.execute(f"REVOKE ALL ON lead_consent_attestation FROM {role}")
    op.drop_table("lead_consent_attestation")
    op.execute("UPDATE lead SET status = 'not_called' WHERE status = 'no_attestation'")
    op.drop_constraint("ck_lead_status", "lead", type_="check")
    op.create_check_constraint("ck_lead_status", "lead", _status_check(OLD_STATUSES))
    for column in ("expires_at", "consent_text", "text_version", "purpose"):
        op.drop_column("consent_record", column)
