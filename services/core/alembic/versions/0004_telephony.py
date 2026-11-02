"""Telephony & compliance: business phone numbers, consent, opt-outs, attempts, decisions, DND.

Revision ID: 0004_telephony
Revises: 0004_billing
Create Date: 2026-10-20

A parallel branch next to the other 0004 revisions (tests run ``upgrade heads``).

Row-Level Security
------------------
* All six tables are ordinary tenant tables: ENABLE + FORCE RLS, a ``tenant_isolation`` policy
  on ``business_id`` and explicit grants to the app role.
* Inbound routing only knows the dialled number. ``internal_number_business(text)`` is a
  SECURITY DEFINER function returning ONLY the owning ``business_id`` of a live (KYC-approved)
  number; the API then binds that tenant and reads everything else through RLS (as in 0003).
  ``internal_numbered_businesses()`` returns the ids of businesses that have any number, for
  the health-monitor job. EXECUTE is granted to the app role only and ``search_path`` is pinned.
  A SELECT policy on ``phone_number`` scoped to the owning role keeps both working when the owner
  is not a superuser; the app role's view is unchanged.
* Contacts' numbers are stored only as HMACs (``phone_hash``), never in the clear.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mitra_core.config import get_settings

revision: str = "0004_telephony"
down_revision: str | None = "0004_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS: dict[str, tuple[str, ...]] = {
    "tel_number_type": ("local", "mobile_virtual", "byo_sip", "1600", "1601", "140"),
    "tel_carrier": ("exotel", "plivo", "sip", "sim"),
    "tel_kyc_status": ("pending_kyc", "submitted", "approved", "rejected"),
    "tel_verification_status": ("not_started", "pending", "verified", "rejected"),
    "tel_number_health": ("healthy", "watch", "paused"),
    "tel_call_purpose": ("callback", "service", "mandated_service", "promotional"),
    "tel_consent_scope": ("service", "promotional"),
    "tel_consent_source": ("lead_form", "existing_customer", "explicit_opt_in", "inbound_call"),
    "tel_opt_out_source": ("voice", "whatsapp", "owner"),
    "tel_attempt_outcome": ("answered", "no_answer", "busy", "voicemail", "failed"),
    "tel_decision": ("allow", "block", "defer"),
    "tel_dnd_status": ("registered", "not_registered", "unknown"),
}
TENANT_TABLES = (
    "phone_number",
    "consent_record",
    "opt_out",
    "outbound_attempt",
    "compliance_decision",
    "dnd_cache",
)
CURRENT_BUSINESS = "app_current_business_id()"
NUMBER_FN = "internal_number_business(text)"
NUMBERED_FN = "internal_numbered_businesses()"


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def _pk() -> sa.Column[sa.Uuid]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _ts(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _business_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["business_id"],
        ["business.id"],
        name=f"fk_{table}_business_id_business",
        ondelete="CASCADE",
    )


def _number_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["phone_number_id"],
        ["phone_number.id"],
        name=f"fk_{table}_phone_number_id_phone_number",
        ondelete="SET NULL",
    )


def _create_tables() -> None:
    op.create_table(
        "phone_number",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=True),
        sa.Column("e164", sa.String(16), nullable=True),
        sa.Column("type", _enum("tel_number_type"), nullable=False),
        sa.Column("carrier", _enum("tel_carrier"), nullable=False),
        sa.Column("carrier_sid", sa.String(64), nullable=True),
        sa.Column("city", sa.String(80), nullable=True),
        sa.Column("label", sa.String(60), nullable=True),
        sa.Column("kyc_status", _enum("tel_kyc_status"), nullable=False),
        sa.Column("kyc_document", postgresql.JSONB(), nullable=True),
        sa.Column("display_name", sa.String(60), nullable=True),
        sa.Column(
            "truecaller_status",
            _enum("tel_verification_status"),
            server_default="not_started",
            nullable=False,
        ),
        sa.Column(
            "cnap_status",
            _enum("tel_verification_status"),
            server_default="not_started",
            nullable=False,
        ),
        sa.Column("answer_rate_7d", sa.Float(), nullable=True),
        sa.Column("spam_flag", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("health", _enum("tel_number_health"), server_default="healthy", nullable=False),
        sa.Column(
            "health_reasons",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("health_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outbound_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("forwarding_tested_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_phone_number"),
        sa.UniqueConstraint("e164", name="uq_phone_number_e164"),
        _business_fk("phone_number"),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employee.id"],
            name="fk_phone_number_employee_id_employee",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("e164 ~ '^\\+[1-9][0-9]{7,14}$'", name="ck_phone_number_e164_format"),
        sa.CheckConstraint(
            "kyc_status <> 'approved' OR e164 IS NOT NULL", name="ck_phone_number_live_has_number"
        ),
        sa.CheckConstraint(
            "answer_rate_7d IS NULL OR answer_rate_7d BETWEEN 0 AND 1",
            name="ck_phone_number_answer_rate",
        ),
    )
    op.create_index("ix_phone_number_business_id", "phone_number", ["business_id"])
    op.create_index("ix_phone_number_employee_id", "phone_number", ["employee_id"])

    op.create_table(
        "consent_record",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("phone_hash", sa.Text(), nullable=False),
        sa.Column("scope", _enum("tel_consent_scope"), nullable=False),
        sa.Column("source", _enum("tel_consent_source"), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        _ts("captured_at"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_consent_record"),
        _business_fk("consent_record"),
    )
    op.create_index(
        "ix_consent_record_business_id_phone_hash", "consent_record", ["business_id", "phone_hash"]
    )

    op.create_table(
        "opt_out",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("phone_hash", sa.Text(), nullable=False),
        sa.Column("purpose", _enum("tel_call_purpose"), nullable=True),
        sa.Column("source", _enum("tel_opt_out_source"), nullable=False),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_opt_out"),
        _business_fk("opt_out"),
    )
    op.create_index("ix_opt_out_business_id", "opt_out", ["business_id"])
    # One row per (contact, purpose); NULL purpose (= everything) is unique too.
    op.execute(
        "CREATE UNIQUE INDEX uq_opt_out_contact_purpose ON opt_out "
        "(business_id, phone_hash, purpose) NULLS NOT DISTINCT"
    )

    op.create_table(
        "outbound_attempt",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("phone_hash", sa.Text(), nullable=False),
        sa.Column("phone_number_id", sa.Uuid(), nullable=True),
        sa.Column("purpose", _enum("tel_call_purpose"), nullable=False),
        sa.Column("outcome", _enum("tel_attempt_outcome"), nullable=True),
        sa.Column("carrier_call_sid", sa.String(64), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_outbound_attempt"),
        _business_fk("outbound_attempt"),
        _number_fk("outbound_attempt"),
    )
    op.create_index(
        "ix_outbound_attempt_contact",
        "outbound_attempt",
        ["business_id", "phone_hash", "attempted_at"],
    )
    op.create_index(
        "ix_outbound_attempt_number", "outbound_attempt", ["phone_number_id", "attempted_at"]
    )

    op.create_table(
        "compliance_decision",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("phone_hash", sa.Text(), nullable=False),
        sa.Column("purpose", _enum("tel_call_purpose"), nullable=False),
        sa.Column("decision", _enum("tel_decision"), nullable=False),
        sa.Column("reasons", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("phone_number_id", sa.Uuid(), nullable=True),
        sa.Column("defer_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_compliance_decision"),
        _business_fk("compliance_decision"),
        _number_fk("compliance_decision"),
    )
    op.create_index(
        "ix_compliance_decision_recent", "compliance_decision", ["business_id", "created_at"]
    )

    op.create_table(
        "dnd_cache",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("phone_hash", sa.Text(), nullable=False),
        sa.Column("status", _enum("tel_dnd_status"), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("business_id", "phone_hash", name="pk_dnd_cache"),
        _business_fk("dnd_cache"),
    )


def upgrade() -> None:
    role = get_settings().app_db_role
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind)
    _create_tables()

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} FOR ALL "
            f"USING (business_id = {CURRENT_BUSINESS}) "
            f"WITH CHECK (business_id = {CURRENT_BUSINESS})"
        )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(TENANT_TABLES)} TO {role}")

    op.execute(
        "CREATE POLICY internal_lookup ON phone_number FOR SELECT TO CURRENT_USER USING (true)"
    )
    op.execute(
        "CREATE FUNCTION internal_number_business(p_e164 text) RETURNS uuid "
        "LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS "
        "$$ SELECT business_id FROM phone_number "
        "WHERE e164 = p_e164 AND kyc_status = 'approved' $$"
    )
    op.execute(
        "CREATE FUNCTION internal_numbered_businesses() RETURNS SETOF uuid "
        "LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS "
        "$$ SELECT DISTINCT business_id FROM phone_number $$"
    )
    for fn in (NUMBER_FN, NUMBERED_FN):
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {role}")


def downgrade() -> None:
    role = get_settings().app_db_role
    for fn in (NUMBERED_FN, NUMBER_FN):
        op.execute(f"DROP FUNCTION {fn}")
    op.execute("DROP POLICY internal_lookup ON phone_number")
    for table in reversed(TENANT_TABLES):
        op.execute(f"REVOKE ALL ON {table} FROM {role}")
        op.drop_table(table)
    bind = op.get_bind()
    for name in reversed(ENUMS):
        postgresql.ENUM(name=name).drop(bind)
