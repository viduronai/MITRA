"""Billing: rate card, wallet, append-only ledger + usage events, top-ups, GST invoices.

Revision ID: 0004_billing
Revises: 0004_calls
Create Date: 2026-10-20

Money is integer paise (BIGINT) everywhere.

Row-Level Security
------------------
* ``wallet``, ``wallet_txn``, ``usage_event``, ``topup_order`` and ``invoice`` are tenant tables:
  ENABLE + FORCE RLS with a ``tenant_isolation`` policy on ``business_id``.
* ``wallet_txn`` and ``usage_event`` are append-only: the app role gets SELECT + INSERT only, so
  even a buggy query cannot rewrite or delete history. ``invoice`` likewise (issued invoices are
  immutable).
* ``rate_card`` is global reference data: RLS with a read-all SELECT policy, SELECT-only grant.
* The Razorpay webhook arrives without a tenant. ``billing_topup_business(text)`` is a SECURITY
  DEFINER function returning ONLY the business id of a provider order id (like 0003); the
  webhook then binds that tenant and proceeds through the normal policies.
* Invoice numbers are a global per-financial-year series, so ``invoice_counter`` is owner-only
  (no app-role privileges) and is advanced by the SECURITY DEFINER
  ``billing_next_invoice_number(text)``.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mitra_core.config import get_settings

revision: str = "0004_billing"
down_revision: str | None = "0004_calls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_BUSINESS = "app_current_business_id()"
APPEND_ONLY = ("wallet_txn", "usage_event", "invoice")
MUTABLE = ("wallet", "topup_order")
TENANT_TABLES = (*MUTABLE, *APPEND_ONLY)

ORDER_FN = "billing_topup_business(text)"
COUNTER_FN = "billing_next_invoice_number(text)"

# Seeded rates (paise per connected minute), effective 2026-01-01 IST.
RATES = {
    "retail": {"smart": 300, "natural": 450, "signature": 600},
    "agency": {"smart": 240, "natural": 360, "signature": 480},
}
RATES_FROM = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))


def _pk() -> sa.Column[sa.Uuid]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _ts(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _money(name: str, nullable: bool = False) -> sa.Column[sa.BigInteger]:
    return sa.Column(name, sa.BigInteger(), nullable=nullable)


def _business_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["business_id"],
        ["business.id"],
        name=f"fk_{table}_business_id_business",
        ondelete="CASCADE",
    )


def _voice_tier() -> postgresql.ENUM:
    return postgresql.ENUM(name="voice_tier", create_type=False)


def _create_tables() -> None:
    op.create_table(
        "rate_card",
        _pk(),
        sa.Column("tier", _voice_tier(), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("paise_per_min", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rate_card"),
        sa.UniqueConstraint(
            "tier", "channel", "effective_from", name="uq_rate_card_tier_channel_effective_from"
        ),
        sa.CheckConstraint("channel IN ('retail', 'agency')", name="ck_rate_card_channel"),
        sa.CheckConstraint("paise_per_min > 0", name="ck_rate_card_positive"),
    )

    op.create_table(
        "wallet",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("balance_paise", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("bonus_paise", sa.BigInteger(), server_default="0", nullable=False),
        _money("monthly_cap_paise", nullable=True),
        sa.Column(
            "low_balance_threshold_paise", sa.BigInteger(), server_default="20000", nullable=False
        ),
        sa.Column("low_balance_alerted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("autopay_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("autopay_amount_paise", sa.BigInteger(), server_default="100000", nullable=False),
        sa.Column("credits_expire_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usage_month", sa.Date(), nullable=True),
        sa.Column("month_usage_paise", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("grace_day", sa.Date(), nullable=True),
        sa.Column("grace_seconds_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("billing_name", sa.String(120), nullable=True),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("state_code", sa.String(2), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("business_id", name="pk_wallet"),
        _business_fk("wallet"),
        sa.CheckConstraint("bonus_paise >= 0", name="ck_wallet_bonus_non_negative"),
        sa.CheckConstraint(
            "monthly_cap_paise IS NULL OR monthly_cap_paise >= 0", name="ck_wallet_cap_non_negative"
        ),
    )

    op.create_table(
        "wallet_txn",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("category", sa.String(32), nullable=True),
        _money("paid_delta_paise"),
        _money("bonus_delta_paise"),
        _money("balance_after_paise"),
        _money("bonus_after_paise"),
        sa.Column("ref", sa.String(128), nullable=True),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_wallet_txn"),
        _business_fk("wallet_txn"),
        sa.UniqueConstraint(
            "business_id", "kind", "ref", name="uq_wallet_txn_business_id_kind_ref"
        ),
        sa.CheckConstraint(
            "kind IN ('topup', 'bonus', 'usage', 'passthrough', 'refund', 'expiry')",
            name="ck_wallet_txn_kind",
        ),
    )
    op.create_index(
        "ix_wallet_txn_business_id_created_at", "wallet_txn", ["business_id", "created_at"]
    )

    op.create_table(
        "usage_event",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("call_id", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("employee_name", sa.String(60), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("connected_ms", sa.BigInteger(), nullable=False),
        sa.Column("billable_seconds", sa.Integer(), nullable=False),
        sa.Column("grace_seconds", sa.Integer(), nullable=False),
        sa.Column("tier", _voice_tier(), nullable=False),
        sa.Column("rate_paise_per_min", sa.Integer(), nullable=False),
        _money("amount_paise"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_usage_event"),
        _business_fk("usage_event"),
        sa.UniqueConstraint("business_id", "call_id", name="uq_usage_event_business_id_call_id"),
        sa.CheckConstraint("direction IN ('inbound', 'outbound')", name="ck_usage_event_direction"),
        sa.CheckConstraint(
            "outcome IN ('connected', 'unanswered', 'busy', 'voicemail', 'blocked', 'failed')",
            name="ck_usage_event_outcome",
        ),
        sa.CheckConstraint("amount_paise >= 0", name="ck_usage_event_amount_non_negative"),
    )
    op.create_index(
        "ix_usage_event_business_id_created_at", "usage_event", ["business_id", "created_at"]
    )
    op.create_index(
        "ix_usage_event_business_id_started_at", "usage_event", ["business_id", "started_at"]
    )

    op.create_table(
        "topup_order",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("provider_order_id", sa.String(64), nullable=False),
        sa.Column("provider_payment_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        _money("amount_paise"),
        _money("bonus_paise"),
        _money("gst_paise"),
        _money("total_paise"),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_topup_order"),
        _business_fk("topup_order"),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name="fk_topup_order_created_by_app_user",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("provider_order_id", name="uq_topup_order_provider_order_id"),
        sa.CheckConstraint("status IN ('created', 'paid', 'failed')", name="ck_topup_order_status"),
        sa.CheckConstraint("source IN ('manual', 'autopay')", name="ck_topup_order_source"),
        sa.CheckConstraint("amount_paise > 0", name="ck_topup_order_positive"),
    )
    op.create_index("ix_topup_order_business_id", "topup_order", ["business_id"])

    op.create_table(
        "invoice",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("topup_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(16), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("billing_name", sa.String(120), nullable=False),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("place_of_supply", sa.String(2), nullable=True),
        sa.Column("intra_state", sa.Boolean(), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        _money("taxable_paise"),
        _money("cgst_paise"),
        _money("sgst_paise"),
        _money("igst_paise"),
        _money("total_paise"),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_invoice"),
        _business_fk("invoice"),
        sa.ForeignKeyConstraint(
            ["topup_id"],
            ["topup_order.id"],
            name="fk_invoice_topup_id_topup_order",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("topup_id", name="uq_invoice_topup_id"),
        sa.UniqueConstraint("number", name="uq_invoice_number"),
    )
    op.create_index("ix_invoice_business_id", "invoice", ["business_id"])

    op.create_table(
        "invoice_counter",
        sa.Column("fy", sa.String(5), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("fy", name="pk_invoice_counter"),
    )


def upgrade() -> None:
    role = get_settings().app_db_role
    _create_tables()

    for table in (*TENANT_TABLES, "rate_card", "invoice_counter"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    for table in TENANT_TABLES:
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} FOR ALL "
            f"USING (business_id = {CURRENT_BUSINESS}) "
            f"WITH CHECK (business_id = {CURRENT_BUSINESS})"
        )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {', '.join(MUTABLE)} TO {role}")
    op.execute(f"GRANT SELECT, INSERT ON {', '.join(APPEND_ONLY)} TO {role}")

    op.execute("CREATE POLICY read_all ON rate_card FOR SELECT USING (true)")
    op.execute(f"GRANT SELECT ON rate_card TO {role}")

    # Owner-only policies so the SECURITY DEFINER functions work for a non-superuser owner.
    op.execute(
        "CREATE POLICY definer_lookup ON topup_order FOR SELECT TO CURRENT_USER USING (true)"
    )
    op.execute(
        "CREATE POLICY definer_access ON invoice_counter FOR ALL TO CURRENT_USER "
        "USING (true) WITH CHECK (true)"
    )
    op.execute(
        "CREATE FUNCTION billing_topup_business(p_provider_order_id text) RETURNS uuid "
        "LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS "
        "$$ SELECT business_id FROM topup_order WHERE provider_order_id = p_provider_order_id $$"
    )
    op.execute(
        "CREATE FUNCTION billing_next_invoice_number(p_fy text) RETURNS integer "
        "LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public AS "
        "$$ INSERT INTO invoice_counter (fy, last_number) VALUES (p_fy, 1) "
        "ON CONFLICT (fy) DO UPDATE SET last_number = invoice_counter.last_number + 1 "
        "RETURNING last_number $$"
    )
    for fn in (ORDER_FN, COUNTER_FN):
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {role}")

    rate_card = sa.table(
        "rate_card",
        sa.column("tier", _voice_tier()),
        sa.column("channel", sa.String()),
        sa.column("paise_per_min", sa.Integer()),
        sa.column("effective_from", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        rate_card,
        [
            {"tier": tier, "channel": channel, "paise_per_min": paise, "effective_from": RATES_FROM}
            for channel, tiers in RATES.items()
            for tier, paise in tiers.items()
        ],
    )


def downgrade() -> None:
    role = get_settings().app_db_role
    op.execute(f"DROP FUNCTION {COUNTER_FN}")
    op.execute(f"DROP FUNCTION {ORDER_FN}")
    for table in (
        "invoice_counter",
        "invoice",
        "topup_order",
        "usage_event",
        "wallet_txn",
        "wallet",
        "rate_card",
    ):
        op.execute(f"REVOKE ALL ON {table} FROM {role}")
        op.drop_table(table)
