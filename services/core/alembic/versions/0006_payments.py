"""UPI collections: collection settings, payment requests, applied provider events.

Revision ID: 0006_payments
Revises: 0006_whatsapp
Create Date: 2026-11-03

Three ordinary tenant tables (ENABLE + FORCE RLS, ``tenant_isolation`` on ``business_id``,
explicit grants). This is the business's own money and is kept apart from Mitra's wallet.

SECURITY DEFINER lookups for work that starts outside any tenant:

* ``payments_webhook_business(text)``: the business whose webhook URL token this is (the
  webhook then verifies the signature with that business's own sealed secret).
* ``payments_due_work(timestamptz)``: ``(business_id, id)`` of open requests whose reminder
  step is due, for the reminder tick.
* ``payments_link_business(text)``: the business owning a provider link id (the local
  Payment Links simulator page only).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mitra_core.config import get_settings

revision: str = "0006_payments"
down_revision: str | None = "0006_whatsapp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("collection_settings", "payment_request", "payment_event")
CURRENT_BUSINESS = "app_current_business_id()"
WEBHOOK_FN = "payments_webhook_business(text)"
DUE_FN = "payments_due_work(timestamptz)"
LINK_FN = "payments_link_business(text)"
WEBHOOK_SQL = """
CREATE FUNCTION payments_webhook_business(p_token text) RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT business_id FROM collection_settings WHERE webhook_token = p_token
$$
"""
LINK_SQL = """
CREATE FUNCTION payments_link_business(p_link_id text) RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT business_id FROM payment_request WHERE provider_link_id = p_link_id LIMIT 1
$$
"""
DUE_SQL = """
CREATE FUNCTION payments_due_work(p_now timestamptz)
RETURNS TABLE (business_id uuid, id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT p.business_id, p.id FROM payment_request p
     WHERE p.status IN ('sent', 'failed') AND p.remind_at IS NOT NULL AND p.remind_at <= p_now
$$
"""


def _ts(name: str, nullable: bool = False) -> sa.Column[sa.DateTime]:
    default = None if nullable else sa.text("now()")
    return sa.Column(name, sa.DateTime(timezone=True), server_default=default, nullable=nullable)


def _fk(table: str, column: str, target: str, ondelete: str = "CASCADE") -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=f"fk_{table}_{column}_{target}", ondelete=ondelete
    )


def _check(table: str, name: str, sql: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(sql, name=f"ck_{table}_{name}")


def _tables() -> None:
    op.create_table(
        "collection_settings",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(10), server_default="none", nullable=False),
        sa.Column("razorpay_key_id", sa.String(64), nullable=True),
        sa.Column("razorpay_key_secret_sealed", sa.Text(), nullable=True),
        sa.Column("razorpay_webhook_secret_sealed", sa.Text(), nullable=True),
        sa.Column("webhook_token", sa.String(64), nullable=False),
        sa.Column("upi_vpa", sa.String(100), nullable=True),
        sa.Column("payee_name", sa.String(100), nullable=True),
        sa.Column(
            "reminders_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("link_expiry_days", sa.SmallInteger(), server_default="15", nullable=False),
        # Lending / BFSI: collection calls only 08:00-19:00 (RBI recovery conduct, 08 §5.1).
        sa.Column("is_lender", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("business_id", name="pk_collection_settings"),
        sa.UniqueConstraint("webhook_token", name="uq_collection_settings_webhook_token"),
        _check("collection_settings", "mode", "mode IN ('none', 'razorpay', 'upi')"),
        _check("collection_settings", "expiry", "link_expiry_days BETWEEN 1 AND 180"),
        _fk("collection_settings", "business_id", "business"),
    )

    op.create_table(
        "payment_request",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("customer_name", sa.String(120), nullable=True),
        sa.Column("phone_last4", sa.String(4), nullable=True),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(200), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("provider", sa.String(16), nullable=True),
        sa.Column("provider_link_id", sa.String(64), nullable=True),
        sa.Column("short_url", sa.Text(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("client_ref", sa.String(120), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("employee_id", sa.Uuid(), nullable=True),
        sa.Column("call_id", sa.Uuid(), nullable=True),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("discount_percent", sa.SmallInteger(), server_default="0", nullable=False),
        _ts("sent_at", True),
        sa.Column("send_error", sa.String(200), nullable=True),
        _ts("paid_at", True),
        sa.Column("paid_via", sa.String(16), nullable=True),
        sa.Column("provider_payment_id", sa.String(64), nullable=True),
        sa.Column("failure_reason", sa.String(200), nullable=True),
        _ts("cancelled_at", True),
        _ts("expires_at", True),
        _ts("customer_says_paid_at", True),
        _ts("remind_at", True),
        sa.Column("reminder_stage", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("reminders", postgresql.JSONB(), server_default="{}", nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_payment_request"),
        sa.UniqueConstraint(
            "business_id", "client_ref", name="uq_payment_request_business_id_client_ref"
        ),
        # Up to ₹10 lakh per link; ₹1 minimum (Razorpay's minimum).
        _check("payment_request", "amount", "amount_paise BETWEEN 100 AND 100000000"),
        _check("payment_request", "discount", "discount_percent BETWEEN 0 AND 100"),
        _check(
            "payment_request",
            "status",
            "status IN ('awaiting_approval', 'sent', 'paid', 'failed', 'expired', 'cancelled')",
        ),
        _check("payment_request", "mode", "mode IN ('razorpay', 'upi')"),
        _check("payment_request", "source", "source IN ('owner', 'employee', 'manager')"),
        _fk("payment_request", "business_id", "business"),
        _fk("payment_request", "contact_id", "contact", "SET NULL"),
        _fk("payment_request", "created_by", "app_user", "SET NULL"),
        _fk("payment_request", "employee_id", "employee", "SET NULL"),
        _fk("payment_request", "call_id", "call", "SET NULL"),
    )
    op.create_index("ix_payment_request_business_id", "payment_request", ["business_id"])
    op.create_index("ix_payment_request_contact_id", "payment_request", ["contact_id"])
    op.create_index(
        "ix_payment_request_business_id_status", "payment_request", ["business_id", "status"]
    )
    op.create_index(
        "ix_payment_request_remind_at",
        "payment_request",
        ["remind_at"],
        postgresql_where=sa.text("remind_at IS NOT NULL"),
    )
    op.create_index(
        "ix_payment_request_provider_link_id",
        "payment_request",
        ["business_id", "provider_link_id"],
        unique=True,
        postgresql_where=sa.text("provider_link_id IS NOT NULL"),
    )

    op.create_table(
        "payment_event",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.String(80), nullable=False),
        sa.Column("event", sa.String(40), nullable=False),
        sa.Column("payment_request_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=False),
        _ts("received_at"),
        sa.PrimaryKeyConstraint("id", name="pk_payment_event"),
        sa.UniqueConstraint(
            "business_id", "event_id", name="uq_payment_event_business_id_event_id"
        ),
        _fk("payment_event", "business_id", "business"),
        _fk("payment_event", "payment_request_id", "payment_request", "SET NULL"),
    )
    op.create_index("ix_payment_event_business_id", "payment_event", ["business_id"])


def upgrade() -> None:
    role = get_settings().app_db_role
    _tables()
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} FOR ALL "
            f"USING (business_id = {CURRENT_BUSINESS}) "
            f"WITH CHECK (business_id = {CURRENT_BUSINESS})"
        )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(TENANT_TABLES)} TO {role}")
    # Owner-only policies so the SECURITY DEFINER lookups work for a non-superuser owner.
    for table in ("collection_settings", "payment_request"):
        op.execute(
            f"CREATE POLICY definer_lookup ON {table} FOR SELECT TO CURRENT_USER USING (true)"
        )
    op.execute(WEBHOOK_SQL)
    op.execute(DUE_SQL)
    op.execute(LINK_SQL)
    for fn in (WEBHOOK_FN, DUE_FN, LINK_FN):
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {role}")


def downgrade() -> None:
    role = get_settings().app_db_role
    for fn in (LINK_FN, DUE_FN, WEBHOOK_FN):
        op.execute(f"DROP FUNCTION {fn}")
    for table in reversed(TENANT_TABLES):
        op.execute(f"REVOKE ALL ON {table} FROM {role}")
        op.drop_table(table)
