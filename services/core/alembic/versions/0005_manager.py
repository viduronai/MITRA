"""WhatsApp messages, approvals and the AI Manager.

Revision ID: 0005_manager
Revises: 0005_leads
Create Date: 2026-11-02

Tenant tables (ENABLE + FORCE RLS, ``tenant_isolation`` on ``business_id``): wa_message,
approval, approval_event, approval_rule, manager_settings, manager_message. ``approval_event``
is append-only for the app role (SELECT + INSERT only), like the billing ledger.

Inbound WhatsApp arrives with no tenant: ``wa_resolve_sender(phone)`` is a SECURITY DEFINER
function returning the owner/manager memberships of a phone number (nothing else), so the
webhook can bind the right business without the app role ever reading other tenants.
Scheduled jobs (morning report, approval timeouts) use ``manager_due_businesses()`` the same way.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mitra_core.config import get_settings

revision: str = "0005_manager"
down_revision: str | None = "0005_leads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_BUSINESS = "app_current_business_id()"
CRUD_TABLES = ("wa_message", "approval", "approval_rule", "manager_settings", "manager_message")
APPEND_ONLY = ("approval_event",)
RESOLVE_FN = "wa_resolve_sender(text)"
DUE_FN = "manager_due_businesses()"

RESOLVE_SQL = """
CREATE FUNCTION wa_resolve_sender(p_phone text)
RETURNS TABLE (user_id uuid, business_id uuid, role text, locale text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT u.id, m.business_id, m.role::text, u.preferred_locale::text
      FROM app_user u JOIN membership m ON m.user_id = u.id
     WHERE u.phone_e164 = p_phone AND m.role IN ('owner', 'manager')
     ORDER BY CASE m.role WHEN 'owner' THEN 0 ELSE 1 END, m.created_at
$$
"""

# Every business id plus its timezone; workers then open a tenant session per business.
DUE_SQL = """
CREATE FUNCTION manager_due_businesses()
RETURNS TABLE (business_id uuid, timezone text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT b.id, b.timezone FROM business b ORDER BY b.created_at
$$
"""


def _pk() -> sa.Column[sa.Uuid]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _ts(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _clock_ts() -> sa.Column[sa.DateTime]:
    # clock_timestamp(): rows written in one transaction keep their order.
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("clock_timestamp()"),
        nullable=False,
    )


def _jsonb(name: str, default: str) -> sa.Column[postgresql.JSONB]:
    return sa.Column(name, postgresql.JSONB(), server_default=default, nullable=False)


def _biz_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["business_id"],
        ["business.id"],
        name=f"fk_{table}_business_id_business",
        ondelete="CASCADE",
    )


def _user_fk(table: str, column: str, ondelete: str = "SET NULL") -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], ["app_user.id"], name=f"fk_{table}_{column}_app_user", ondelete=ondelete
    )


def _create_tables() -> None:
    op.create_table(
        "wa_message",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("phone_hash", sa.Text(), nullable=False),
        sa.Column("phone_last4", sa.String(4), nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("template", sa.String(64), nullable=True),
        _jsonb("params", "{}"),
        _jsonb("buttons", "[]"),
        _jsonb("ref", "{}"),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("provider_message_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("dedupe_key", sa.String(160), nullable=True),
        _clock_ts(),
        sa.CheckConstraint("direction IN ('out', 'in')", name="ck_wa_message_direction"),
        sa.CheckConstraint(
            "kind IN ('text', 'template', 'buttons', 'voice', 'button_reply')",
            name="ck_wa_message_kind",
        ),
        sa.CheckConstraint("status IN ('sent', 'failed', 'received')", name="ck_wa_message_status"),
        _biz_fk("wa_message"),
        _user_fk("wa_message", "user_id"),
        sa.PrimaryKeyConstraint("id", name="pk_wa_message"),
    )
    op.create_index("ix_wa_message_business_id", "wa_message", ["business_id", "created_at"])
    op.create_index("ix_wa_message_user_id", "wa_message", ["user_id"])
    # One message per (business, recipient, dedupe key): repeated alerts are no-ops.
    op.create_index(
        "uq_wa_message_dedupe",
        "wa_message",
        ["business_id", "phone_hash", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )

    op.create_table(
        "approval",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        _jsonb("payload", "{}"),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(12), server_default="pending", nullable=False),
        sa.Column("requested_by", sa.String(120), nullable=False),
        sa.Column("default_action", sa.String(8), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_via", sa.String(12), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(300), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("apply_error", sa.String(300), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'declined', 'expired', 'cancelled')",
            name="ck_approval_status",
        ),
        sa.CheckConstraint(
            "default_action IS NULL OR default_action IN ('approve', 'decline')",
            name="ck_approval_default_action",
        ),
        sa.CheckConstraint(
            "decided_via IS NULL OR decided_via IN ('app', 'whatsapp', 'timeout')",
            name="ck_approval_decided_via",
        ),
        sa.CheckConstraint("version >= 1", name="ck_approval_version"),
        _biz_fk("approval"),
        _user_fk("approval", "decided_by"),
        sa.PrimaryKeyConstraint("id", name="pk_approval"),
    )
    op.create_index("ix_approval_business_id", "approval", ["business_id", "status", "created_at"])
    op.create_index(
        "ix_approval_expiring",
        "approval",
        ["expires_at"],
        postgresql_where=sa.text("status = 'pending' AND expires_at IS NOT NULL"),
    )

    op.create_table(
        "approval_event",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("event", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("via", sa.String(12), nullable=True),
        _jsonb("detail", "{}"),
        _clock_ts(),
        _biz_fk("approval_event"),
        _user_fk("approval_event", "actor_user_id"),
        sa.ForeignKeyConstraint(
            ["approval_id"],
            ["approval.id"],
            name="fk_approval_event_approval_id_approval",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approval_event"),
    )
    op.create_index("ix_approval_event_business_id", "approval_event", ["business_id"])
    op.create_index("ix_approval_event_approval_id", "approval_event", ["approval_id"])

    op.create_table(
        "approval_rule",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=True),
        sa.Column("timeout_minutes", sa.Integer(), nullable=True),
        sa.Column("default_action", sa.String(8), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "default_action IS NULL OR default_action IN ('approve', 'decline')",
            name="ck_approval_rule_default_action",
        ),
        sa.CheckConstraint(
            "threshold IS NULL OR threshold >= 0", name="ck_approval_rule_threshold"
        ),
        sa.CheckConstraint(
            "timeout_minutes IS NULL OR timeout_minutes BETWEEN 1 AND 10080",
            name="ck_approval_rule_timeout",
        ),
        _biz_fk("approval_rule"),
        sa.PrimaryKeyConstraint("business_id", "kind", name="pk_approval_rule"),
    )

    op.create_table(
        "manager_settings",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("report_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("report_time", sa.Time(), server_default=sa.text("'08:00'"), nullable=False),
        sa.Column("language", postgresql.ENUM(name="locale", create_type=False), nullable=True),
        sa.Column(
            "report_user_ids",
            postgresql.ARRAY(sa.Uuid()),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.Column(
            "alert_user_ids",
            postgresql.ARRAY(sa.Uuid()),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.Column(
            "alert_kinds",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{hot_lead,angry,vip,payment_failed,campaign_paused}'::text[]"),
            nullable=False,
        ),
        sa.Column("last_report_on", sa.Date(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        _biz_fk("manager_settings"),
        sa.PrimaryKeyConstraint("business_id", name="pk_manager_settings"),
    )

    op.create_table(
        "manager_message",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.String(10), nullable=False),
        sa.Column("role", sa.String(8), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("card", postgresql.JSONB(), nullable=True),
        _clock_ts(),
        sa.CheckConstraint("channel IN ('app', 'whatsapp')", name="ck_manager_message_channel"),
        sa.CheckConstraint("role IN ('owner', 'mitra')", name="ck_manager_message_role"),
        _biz_fk("manager_message"),
        _user_fk("manager_message", "user_id", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_manager_message"),
    )
    op.create_index(
        "ix_manager_message_business_id",
        "manager_message",
        ["business_id", "user_id", "created_at"],
    )
    op.create_index("ix_manager_message_user_id", "manager_message", ["user_id"])


def upgrade() -> None:
    role = get_settings().app_db_role
    _create_tables()
    for table in (*CRUD_TABLES, *APPEND_ONLY):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} FOR ALL "
            f"USING (business_id = {CURRENT_BUSINESS}) "
            f"WITH CHECK (business_id = {CURRENT_BUSINESS})"
        )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(CRUD_TABLES)} TO {role}")
    op.execute(f"GRANT SELECT, INSERT ON {', '.join(APPEND_ONLY)} TO {role}")

    # The definer functions read membership / business across tenants (owner role only).
    op.execute(
        "CREATE POLICY wa_definer_select ON membership FOR SELECT TO CURRENT_USER USING (true)"
    )
    op.execute(
        "CREATE POLICY manager_definer_select ON business FOR SELECT TO CURRENT_USER USING (true)"
    )
    op.execute(RESOLVE_SQL)
    op.execute(DUE_SQL)
    for fn in (RESOLVE_FN, DUE_FN):
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {role}")


def downgrade() -> None:
    role = get_settings().app_db_role
    op.execute(f"DROP FUNCTION {DUE_FN}")
    op.execute(f"DROP FUNCTION {RESOLVE_FN}")
    op.execute("DROP POLICY manager_definer_select ON business")
    op.execute("DROP POLICY wa_definer_select ON membership")
    for table in reversed((*CRUD_TABLES, *APPEND_ONLY)):
        op.execute(f"REVOKE ALL ON {table} FROM {role}")
    for table in ("manager_message", "manager_settings", "approval_rule", "approval_event"):
        op.drop_table(table)
    op.drop_table("approval")
    op.drop_table("wa_message")
