"""Encrypted customer phone numbers, phone access log, missed-call number (CALL-20).

Revision ID: 0006_phones
Revises: 0005_team
Create Date: 2026-11-03

- ``contact.phone_enc``: the number sealed per business (``mitra_core.phones``, AES-256-GCM).
  Backfilled here from the dialer's sealed copies (``outbound_job`` / ``campaign_contact``),
  whose ``v1`` values are re-sealed as ``v2``. Rows the migration cannot open are left alone;
  ``phones.reveal_phone`` still finds them on the dialer rows and upgrades them lazily.
- ``phone_number.missed_call``: at most one missed-call number per business.
- New tenant tables (ENABLE + FORCE RLS, ``tenant_isolation``): ``phone_access_log``,
  ``missed_call``, ``caller_block``.
- ``tel_consent_source`` gains ``missed_call`` (enum values cannot be dropped on downgrade).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mitra_core.config import get_settings

revision: str = "0006_phones"
down_revision: str | None = "0005_team"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("phone_access_log", "missed_call", "caller_block")
CURRENT_BUSINESS = "app_current_business_id()"


def _pk() -> sa.Column[sa.Uuid]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _ts(name: str, nullable: bool = False) -> sa.Column[sa.DateTime]:
    default = None if nullable else sa.text("now()")
    return sa.Column(name, sa.DateTime(timezone=True), server_default=default, nullable=nullable)


def _fk(table: str, column: str, target: str, ondelete: str = "CASCADE") -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=f"fk_{table}_{column}_{target}", ondelete=ondelete
    )


def _tables() -> None:
    op.create_table(
        "phone_access_log",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("actor", sa.String(80), nullable=False),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_phone_access_log"),
        _fk("phone_access_log", "business_id", "business"),
        _fk("phone_access_log", "contact_id", "contact", "SET NULL"),
    )
    op.create_index(
        "ix_phone_access_log_business_created", "phone_access_log", ["business_id", "created_at"]
    )
    op.create_index("ix_phone_access_log_contact_id", "phone_access_log", ["contact_id"])

    op.create_table(
        "missed_call",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("phone_number_id", sa.Uuid(), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("phone_hash", sa.Text(), nullable=False),
        sa.Column("phone_last4", sa.String(4), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        _ts("call_back_at", nullable=True),
        sa.Column("carrier_call_sid", sa.String(64), nullable=True),
        _ts("received_at"),
        sa.PrimaryKeyConstraint("id", name="pk_missed_call"),
        sa.CheckConstraint(
            "status IN ('queued', 'deduped', 'rate_limited', 'blocked')",
            name="ck_missed_call_status",
        ),
        _fk("missed_call", "business_id", "business"),
        _fk("missed_call", "phone_number_id", "phone_number", "SET NULL"),
        _fk("missed_call", "contact_id", "contact", "SET NULL"),
        _fk("missed_call", "job_id", "outbound_job", "SET NULL"),
    )
    op.create_index(
        "ix_missed_call_business_received", "missed_call", ["business_id", "received_at"]
    )
    op.create_index(
        "ix_missed_call_caller", "missed_call", ["business_id", "phone_hash", "received_at"]
    )

    op.create_table(
        "caller_block",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("phone_hash", sa.Text(), nullable=False),
        sa.Column("phone_last4", sa.String(4), nullable=False),
        sa.Column("reason", sa.String(120), nullable=True),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_caller_block"),
        _fk("caller_block", "business_id", "business"),
    )
    op.create_index("uq_caller_block", "caller_block", ["business_id", "phone_hash"], unique=True)


def _backfill() -> None:
    """Seal each contact's number (v2) from the newest dialer copy with the same hash.

    Runs as the schema owner; each business is bound as the RLS tenant so FORCE RLS still
    returns its rows when the owner is not a superuser.
    """
    from mitra_core.phones import PhoneSealError, seal_phone, unseal_phone

    conn = op.get_bind()
    businesses = conn.execute(
        sa.text(
            "SELECT DISTINCT business_id FROM outbound_job "
            "UNION SELECT DISTINCT business_id FROM campaign_contact"
        )
    ).scalars()
    for business_id in list(businesses):
        conn.execute(
            sa.text("SELECT set_config('app.business_id', :b, true)"), {"b": str(business_id)}
        )
        rows = conn.execute(
            sa.text(
                "SELECT c.id, s.phone_enc FROM contact c CROSS JOIN LATERAL ("
                " SELECT phone_enc, created_at FROM outbound_job j"
                "  WHERE j.business_id = c.business_id AND j.phone_hash = c.phone_hash"
                " UNION ALL"
                " SELECT phone_enc, created_at FROM campaign_contact k"
                "  WHERE k.business_id = c.business_id AND k.phone_hash = c.phone_hash"
                " ORDER BY created_at DESC LIMIT 1) s"
                " WHERE c.business_id = :b AND c.phone_enc IS NULL AND s.phone_enc <> ''"
            ),
            {"b": business_id},
        ).all()
        for contact_id, sealed in rows:
            try:
                phone = unseal_phone(business_id, sealed)
            except (PhoneSealError, ValueError):
                continue  # sealed with another key: reveal_phone retries at runtime
            conn.execute(
                sa.text("UPDATE contact SET phone_enc = :e WHERE id = :id"),
                {"e": seal_phone(business_id, phone), "id": contact_id},
            )
    conn.execute(sa.text("SELECT set_config('app.business_id', '', true)"))


def upgrade() -> None:
    role = get_settings().app_db_role
    op.execute("ALTER TYPE tel_consent_source ADD VALUE IF NOT EXISTS 'missed_call'")
    op.add_column("contact", sa.Column("phone_enc", sa.Text(), nullable=True))
    op.add_column(
        "phone_number",
        sa.Column("missed_call", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index(
        "uq_phone_number_missed_call",
        "phone_number",
        ["business_id"],
        unique=True,
        postgresql_where=sa.text("missed_call"),
    )
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
    _backfill()


def downgrade() -> None:
    role = get_settings().app_db_role
    for table in reversed(TENANT_TABLES):
        op.execute(f"REVOKE ALL ON {table} FROM {role}")
        op.drop_table(table)
    op.drop_index("uq_phone_number_missed_call", table_name="phone_number")
    op.drop_column("phone_number", "missed_call")
    op.drop_column("contact", "phone_enc")
