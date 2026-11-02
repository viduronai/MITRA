"""Outbound dialer queue + campaigns: dialer_config, campaign, campaign_contact, outbound_job.

Revision ID: 0005_campaigns
Revises: 0004_demo
Create Date: 2026-11-02

Row-Level Security
------------------
* All four tables are tenant tables: ENABLE + FORCE RLS, a ``tenant_isolation`` policy on
  ``business_id`` and explicit grants to the app role (as in 0004_telephony).
* The dialer worker serves every business. ``internal_dialer_businesses(timestamptz)`` is a
  SECURITY DEFINER function returning ONLY the ids of businesses with queued jobs due by then or
  calls still dialing; the worker then binds each tenant and reads through RLS. EXECUTE is
  granted to the app role only and ``search_path`` is pinned; a SELECT policy scoped to the
  owning role keeps it working when the owner is not a superuser.
* Contacts' numbers are HMAC-indexed (``phone_hash``) and sealed (``phone_enc``), never clear.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mitra_core.config import get_settings

revision: str = "0005_campaigns"
down_revision: str | None = "0004_demo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS: dict[str, tuple[str, ...]] = {
    "dlr_job_status": ("queued", "dialing", "completed", "failed", "blocked", "cancelled"),
    "dlr_campaign_status": (
        "draft",
        "pending_approval",
        "running",
        "paused",
        "completed",
        "cancelled",
    ),
    "dlr_contact_status": ("pending", "queued", "done", "skipped"),
    "dlr_result_bucket": ("interested", "call_back", "not_interested", "no_answer", "blocked"),
}
TENANT_TABLES = ("dialer_config", "campaign", "campaign_contact", "outbound_job")
CURRENT_BUSINESS = "app_current_business_id()"
DUE_FN = "internal_dialer_businesses(timestamptz)"


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def _existing(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(name=name, create_type=False)


def _pk() -> sa.Column[sa.Uuid]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _ts(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=f"fk_{table}_{column}_{target}", ondelete=ondelete
    )


def _phone_columns() -> list[sa.Column[sa.Text]]:
    return [
        sa.Column("phone_hash", sa.Text(), nullable=False),
        sa.Column("phone_last4", sa.String(4), nullable=False),
        sa.Column("phone_enc", sa.Text(), nullable=False),
    ]


def _create_tables() -> None:
    op.create_table(
        "dialer_config",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("channels", sa.SmallInteger(), server_default=sa.text("5"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("business_id", name="pk_dialer_config"),
        _fk("dialer_config", "business_id", "business", "CASCADE"),
        sa.CheckConstraint("channels BETWEEN 1 AND 50", name="ck_dialer_config_channels"),
    )

    op.create_table(
        "campaign",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("purpose", _existing("tel_call_purpose"), nullable=False),
        sa.Column("status", _enum("dlr_campaign_status"), server_default="draft", nullable=False),
        sa.Column(
            "column_map",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "skip_recent_days", sa.SmallInteger(), server_default=sa.text("7"), nullable=False
        ),
        sa.Column(
            "calling_days",
            postgresql.ARRAY(sa.SmallInteger()),
            server_default=sa.text("'{0,1,2,3,4,5}'::smallint[]"),
            nullable=False,
        ),
        sa.Column(
            "holidays",
            postgresql.ARRAY(sa.Date()),
            server_default=sa.text("'{}'::date[]"),
            nullable=False,
        ),
        sa.Column(
            "retry_ladder",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{30,120,1440}'::integer[]"),
            nullable=False,
        ),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("avg_call_seconds", sa.Integer(), server_default=sa.text("90"), nullable=False),
        sa.Column("pause_reason", sa.String(40), nullable=True),
        sa.Column(
            "carrier_strikes", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_campaign"),
        _fk("campaign", "business_id", "business", "CASCADE"),
        _fk("campaign", "employee_id", "employee", "SET NULL"),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name="fk_campaign_created_by_app_user",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_campaign_business_id", "campaign", ["business_id"])

    op.create_table(
        "campaign_contact",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        *_phone_columns(),
        sa.Column("name", sa.String(120), nullable=True),
        sa.Column(
            "variables", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("status", _enum("dlr_contact_status"), server_default="pending", nullable=False),
        sa.Column("bucket", _enum("dlr_result_bucket"), nullable=True),
        sa.Column(
            "reasons",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_outcome", _existing("tel_attempt_outcome"), nullable=True),
        sa.Column("call_id", sa.Uuid(), nullable=True),
        sa.Column("summary", sa.String(800), nullable=True),
        sa.Column("last_called_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_campaign_contact"),
        _fk("campaign_contact", "business_id", "business", "CASCADE"),
        _fk("campaign_contact", "campaign_id", "campaign", "CASCADE"),
    )
    op.create_index("ix_campaign_contact_business_id", "campaign_contact", ["business_id"])
    op.create_index(
        "uq_campaign_contact_phone", "campaign_contact", ["campaign_id", "phone_hash"], unique=True
    )
    op.create_index(
        "ix_campaign_contact_campaign_status", "campaign_contact", ["campaign_id", "status"]
    )

    op.create_table(
        "outbound_job",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("campaign_contact_id", sa.Uuid(), nullable=True),
        *_phone_columns(),
        sa.Column("purpose", _existing("tel_call_purpose"), nullable=False),
        sa.Column(
            "variables", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("dedupe_key", sa.String(120), nullable=True),
        sa.Column("status", _enum("dlr_job_status"), server_default="queued", nullable=False),
        _ts("not_before"),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "retry_ladder",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{30,120,1440}'::integer[]"),
            nullable=False,
        ),
        sa.Column("called_number_id", sa.Uuid(), nullable=True),
        sa.Column("last_outcome", _existing("tel_attempt_outcome"), nullable=True),
        sa.Column(
            "reasons",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("attempt_id", sa.Uuid(), nullable=True),
        sa.Column("carrier_call_sid", sa.String(64), nullable=True),
        sa.Column("dialed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_outbound_job"),
        _fk("outbound_job", "business_id", "business", "CASCADE"),
        _fk("outbound_job", "employee_id", "employee", "CASCADE"),
        _fk("outbound_job", "campaign_id", "campaign", "CASCADE"),
        _fk("outbound_job", "campaign_contact_id", "campaign_contact", "CASCADE"),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["outbound_attempt.id"],
            name="fk_outbound_job_attempt_id_outbound_attempt",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_outbound_job_due", "outbound_job", ["business_id", "status", "not_before"])
    op.create_index(
        "ix_outbound_job_contact", "outbound_job", ["business_id", "phone_hash", "status"]
    )
    op.create_index("ix_outbound_job_campaign", "outbound_job", ["campaign_id", "status"])
    op.create_index(
        "uq_outbound_job_dedupe",
        "outbound_job",
        ["business_id", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'dialing')"),
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
        "CREATE POLICY internal_lookup ON outbound_job FOR SELECT TO CURRENT_USER USING (true)"
    )
    op.execute(
        "CREATE FUNCTION internal_dialer_businesses(p_now timestamptz) RETURNS SETOF uuid "
        "LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS "
        "$$ SELECT DISTINCT business_id FROM outbound_job "
        "WHERE (status = 'queued' AND not_before <= p_now) OR status = 'dialing' $$"
    )
    op.execute(f"REVOKE ALL ON FUNCTION {DUE_FN} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {DUE_FN} TO {role}")


def downgrade() -> None:
    role = get_settings().app_db_role
    op.execute(f"DROP FUNCTION {DUE_FN}")
    op.execute("DROP POLICY internal_lookup ON outbound_job")
    for table in reversed(TENANT_TABLES):
        op.execute(f"REVOKE ALL ON {table} FROM {role}")
        op.drop_table(table)
    bind = op.get_bind()
    for name in reversed(ENUMS):
        postgresql.ENUM(name=name).drop(bind)
