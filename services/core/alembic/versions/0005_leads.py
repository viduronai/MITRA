"""Lead intake, lead sources, leads and outgoing webhooks.

Revision ID: 0005_leads
Revises: 0005_campaigns
Create Date: 2026-11-02

Row-Level Security
------------------
* All five tables are ordinary tenant tables: ENABLE + FORCE RLS, a ``tenant_isolation`` policy
  on ``business_id`` and explicit grants to the app role.
* Public intake requests only know a URL slug (or a Meta page id). SECURITY DEFINER functions map
  them to a ``business_id`` and nothing else; the API then binds that tenant and reads everything
  through RLS (as in 0003/0004):
  - ``lead_intake_business(slug, secret_hash)``: the business only when the hashed secret matches
    the current one, or the previous one inside its rotation grace period;
  - ``lead_intake_form_business(slug)``: the business only when its website-form source is on
    (browser forms cannot keep a secret);
  - ``lead_source_business(kind, external_id)``: e.g. the business owning a Meta page;
  - ``internal_lead_pull_businesses(kind)`` / ``internal_webhook_due_businesses(now)``: business
    ids for the pull and delivery jobs.
  EXECUTE is granted to the app role only and ``search_path`` is pinned. SELECT policies scoped
  to the owning role keep the functions working when the owner is not a superuser.
* Phone numbers are stored only as HMACs (``phone_hash``) plus the last four digits.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mitra_core.config import get_settings

revision: str = "0005_leads"
down_revision: str | None = "0005_campaigns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("lead_intake", "lead_source", "lead", "webhook_endpoint", "webhook_delivery")
CURRENT_BUSINESS = "app_current_business_id()"
KINDS = (
    "api",
    "website_form",
    "google_sheets",
    "google_forms",
    "meta",
    "google_ads",
    "indiamart",
    "justdial",
    "zapier",
)
LEAD_STATUSES = (
    "queued",
    "scheduled",
    "duplicate",
    "not_called",
    "blocked",
    "no_consent",
    "no_employee",
    "failed",
)
DEFINER = "LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public"
FUNCTIONS = {
    "lead_intake_business(text, text)": (
        "CREATE FUNCTION lead_intake_business(p_slug text, p_secret_hash text) RETURNS uuid "
        f"{DEFINER} AS $$ SELECT business_id FROM lead_intake WHERE slug = p_slug AND ("
        "secret_hash = p_secret_hash OR (previous_secret_hash = p_secret_hash "
        "AND previous_valid_until > now())) $$"
    ),
    "lead_intake_form_business(text)": (
        "CREATE FUNCTION lead_intake_form_business(p_slug text) RETURNS uuid "
        f"{DEFINER} AS $$ SELECT i.business_id FROM lead_intake i WHERE i.slug = p_slug "
        "AND EXISTS (SELECT 1 FROM lead_source s WHERE s.business_id = i.business_id "
        "AND s.kind = 'website_form' AND s.enabled) $$"
    ),
    "lead_source_business(text, text)": (
        "CREATE FUNCTION lead_source_business(p_kind text, p_external_id text) RETURNS uuid "
        f"{DEFINER} AS $$ SELECT business_id FROM lead_source "
        "WHERE kind = p_kind AND external_id = p_external_id AND enabled $$"
    ),
    "internal_lead_pull_businesses(text)": (
        "CREATE FUNCTION internal_lead_pull_businesses(p_kind text) RETURNS SETOF uuid "
        f"{DEFINER} AS $$ SELECT business_id FROM lead_source "
        "WHERE kind = p_kind AND enabled AND credential IS NOT NULL $$"
    ),
    "internal_webhook_due_businesses(timestamptz)": (
        "CREATE FUNCTION internal_webhook_due_businesses(p_now timestamptz) RETURNS SETOF uuid "
        f"{DEFINER} AS $$ SELECT DISTINCT business_id FROM webhook_delivery "
        "WHERE status = 'pending' AND next_attempt_at <= p_now $$"
    ),
}
DEFINER_TABLES = ("lead_intake", "lead_source", "webhook_delivery")


def _pk() -> sa.Column[sa.Uuid]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _ts(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _dt(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=f"fk_{table}_{column}_{target}", ondelete=ondelete
    )


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _jsonb(name: str) -> sa.Column[postgresql.JSONB]:
    return sa.Column(name, postgresql.JSONB(), server_default="{}", nullable=False)


def _create_lead_tables() -> None:
    op.create_table(
        "lead_intake",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(40), nullable=False),
        sa.Column("secret_hash", sa.Text(), nullable=False),
        sa.Column("secret_hint", sa.String(12), nullable=False),
        sa.Column("previous_secret_hash", sa.Text(), nullable=True),
        _dt("previous_valid_until"),
        _dt("rotated_at"),
        sa.Column("dedupe_minutes", sa.Integer(), server_default=sa.text("10"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("business_id", name="pk_lead_intake"),
        _fk("lead_intake", "business_id", "business", "CASCADE"),
        sa.UniqueConstraint("slug", name="uq_lead_intake_slug"),
        sa.CheckConstraint("slug ~ '^[a-z0-9-]{6,40}$'", name="ck_lead_intake_slug"),
        sa.CheckConstraint("dedupe_minutes BETWEEN 0 AND 1440", name="ck_lead_intake_dedupe"),
    )

    op.create_table(
        "lead_source",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("auto_call", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("call_delay_seconds", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("heads_up", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=True),
        sa.Column("external_id", sa.String(64), nullable=True),
        _jsonb("config"),
        sa.Column("credential", sa.Text(), nullable=True),
        sa.Column("credential_hint", sa.String(12), nullable=True),
        _dt("last_lead_at"),
        _dt("last_pulled_at"),
        sa.Column("lead_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.String(300), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_lead_source"),
        _fk("lead_source", "business_id", "business", "CASCADE"),
        _fk("lead_source", "employee_id", "employee", "SET NULL"),
        sa.UniqueConstraint("business_id", "kind", name="uq_lead_source_business_id_kind"),
        sa.CheckConstraint(_in("kind", KINDS), name="ck_lead_source_kind"),
        sa.CheckConstraint(
            "call_delay_seconds BETWEEN 0 AND 86400", name="ck_lead_source_call_delay"
        ),
    )
    op.create_index("ix_lead_source_business_id", "lead_source", ["business_id"])
    # A Meta page (or any portal account) feeds exactly one business.
    op.execute(
        "CREATE UNIQUE INDEX uq_lead_source_kind_external_id ON lead_source (kind, external_id) "
        "WHERE external_id IS NOT NULL"
    )

    op.create_table(
        "lead",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("source_detail", sa.String(120), nullable=True),
        sa.Column("external_id", sa.String(80), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("phone_hash", sa.Text(), nullable=False),
        sa.Column("phone_last4", sa.String(4), nullable=False),
        sa.Column("name", sa.String(120), nullable=True),
        _jsonb("fields"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "reasons",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("duplicate_of", sa.Uuid(), nullable=True),
        sa.Column("employee_id", sa.Uuid(), nullable=True),
        sa.Column("call_job_id", sa.Uuid(), nullable=True),
        _dt("call_at"),
        sa.Column("consent_record_id", sa.Uuid(), nullable=True),
        sa.Column("ip_hash", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_lead"),
        _fk("lead", "business_id", "business", "CASCADE"),
        _fk("lead", "source_id", "lead_source", "SET NULL"),
        _fk("lead", "contact_id", "contact", "CASCADE"),
        _fk("lead", "duplicate_of", "lead", "SET NULL"),
        _fk("lead", "employee_id", "employee", "SET NULL"),
        _fk("lead", "consent_record_id", "consent_record", "SET NULL"),
        sa.CheckConstraint(_in("source", KINDS), name="ck_lead_source"),
        sa.CheckConstraint(_in("status", LEAD_STATUSES), name="ck_lead_status"),
    )
    op.create_index("ix_lead_dedupe", "lead", ["business_id", "phone_hash", "received_at"])
    op.create_index("ix_lead_recent", "lead", ["business_id", "received_at"])
    op.create_index("ix_lead_contact_id", "lead", ["contact_id"])
    # The same portal lead id is accepted once (portals and Meta retry deliveries).
    op.execute(
        "CREATE UNIQUE INDEX uq_lead_external ON lead (business_id, source, external_id) "
        "WHERE external_id IS NOT NULL"
    )


def _create_webhook_tables() -> None:
    op.create_table(
        "webhook_endpoint",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("description", sa.String(120), nullable=True),
        sa.Column("events", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("secret", sa.Text(), nullable=False),
        sa.Column("secret_hint", sa.String(12), nullable=False),
        _jsonb("headers"),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "consecutive_failures", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_webhook_endpoint"),
        _fk("webhook_endpoint", "business_id", "business", "CASCADE"),
        sa.CheckConstraint("url ~ '^https?://'", name="ck_webhook_endpoint_url"),
    )
    op.create_index("ix_webhook_endpoint_business_id", "webhook_endpoint", ["business_id"])

    op.create_table(
        "webhook_delivery",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event", sa.String(40), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        _dt("next_attempt_at"),
        _dt("last_attempt_at"),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_webhook_delivery"),
        _fk("webhook_delivery", "business_id", "business", "CASCADE"),
        _fk("webhook_delivery", "endpoint_id", "webhook_endpoint", "CASCADE"),
        sa.CheckConstraint(
            _in("status", ("pending", "succeeded", "failed")), name="ck_webhook_delivery_status"
        ),
    )
    op.create_index(
        "ix_webhook_delivery_due", "webhook_delivery", ["business_id", "status", "next_attempt_at"]
    )
    op.create_index(
        "ix_webhook_delivery_endpoint", "webhook_delivery", ["endpoint_id", "created_at"]
    )


def upgrade() -> None:
    role = get_settings().app_db_role
    _create_lead_tables()
    _create_webhook_tables()

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} FOR ALL "
            f"USING (business_id = {CURRENT_BUSINESS}) "
            f"WITH CHECK (business_id = {CURRENT_BUSINESS})"
        )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(TENANT_TABLES)} TO {role}")

    for table in DEFINER_TABLES:
        op.execute(
            f"CREATE POLICY definer_lookup ON {table} FOR SELECT TO CURRENT_USER USING (true)"
        )
    for signature, ddl in FUNCTIONS.items():
        op.execute(ddl)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {role}")


def downgrade() -> None:
    role = get_settings().app_db_role
    for signature in FUNCTIONS:
        op.execute(f"DROP FUNCTION {signature}")
    for table in DEFINER_TABLES:
        op.execute(f"DROP POLICY definer_lookup ON {table}")
    for table in reversed(TENANT_TABLES):
        op.execute(f"REVOKE ALL ON {table} FROM {role}")
        op.drop_table(table)
