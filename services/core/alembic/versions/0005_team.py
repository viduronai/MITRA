"""AI team, hand-offs, follow-up tasks, staff ladder, hand-off cards, routines, live supervision.

Revision ID: 0005_team
Revises: 0005_manager
Create Date: 2026-11-02

Nine ordinary tenant tables (ENABLE + FORCE RLS, ``tenant_isolation`` on ``business_id``,
explicit grants). Status-like columns are short strings checked by constraints rather than
native enums, so parallel 0005 migrations cannot collide on type names.

The routine scheduler runs outside any request and must find due work across businesses:
``team_due_work(timestamptz)`` is a SECURITY DEFINER function returning only
``(kind, business_id, id)`` of due routines and due follow-up tasks; the worker then binds each
business as the RLS tenant and reads everything through the normal policies (as 0003 does for
the voice service). Owner-scoped SELECT policies keep it working when the owner is not a
superuser.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mitra_core.config import get_settings

revision: str = "0005_team"
down_revision: str | None = "0005_manager"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = (
    "team",
    "team_member",
    "handoff_rule",
    "staff_member",
    "routine",
    "routine_run",
    "follow_up_task",
    "handoff_card",
    "supervisor_action",
)
CURRENT_BUSINESS = "app_current_business_id()"
FN = "team_due_work(timestamptz)"
DUE_SQL = """
CREATE FUNCTION team_due_work(p_now timestamptz)
RETURNS TABLE (kind text, business_id uuid, id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT 'routine', r.business_id, r.id FROM routine r
     WHERE r.enabled AND r.next_run_at IS NOT NULL AND r.next_run_at <= p_now
    UNION ALL
    SELECT 'task', t.business_id, t.id FROM follow_up_task t
     WHERE t.status = 'pending' AND t.due_at <= p_now
$$
"""


def _pk() -> sa.Column[sa.Uuid]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _ts(name: str, nullable: bool = False) -> sa.Column[sa.DateTime]:
    default = None if nullable else sa.text("now()")
    return sa.Column(name, sa.DateTime(timezone=True), server_default=default, nullable=nullable)


def _jsonb(name: str, default: str = "{}") -> sa.Column[postgresql.JSONB]:
    return sa.Column(name, postgresql.JSONB(), server_default=default, nullable=False)


def _uuid(name: str, nullable: bool = True) -> sa.Column[sa.Uuid]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _fk(table: str, column: str, target: str, ondelete: str = "CASCADE") -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=f"fk_{table}_{column}_{target}", ondelete=ondelete
    )


def _check(table: str, name: str, sql: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(sql, name=f"ck_{table}_{name}")


def _index(table: str, *columns: str) -> None:
    op.create_index(f"ix_{table}_{'_'.join(columns)}", table, list(columns))


def _team_tables() -> None:
    op.create_table(
        "team",
        _pk(),
        _uuid("business_id", False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("template_id", sa.String(40), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_team"),
        _fk("team", "business_id", "business"),
    )
    _index("team", "business_id")

    op.create_table(
        "team_member",
        _pk(),
        _uuid("business_id", False),
        _uuid("team_id", False),
        _uuid("employee_id", False),
        sa.Column("team_role", sa.String(40), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_team_member"),
        sa.UniqueConstraint("team_id", "employee_id", name="uq_team_member_team_id_employee_id"),
        _fk("team_member", "business_id", "business"),
        _fk("team_member", "team_id", "team"),
        _fk("team_member", "employee_id", "employee"),
    )
    for col in ("business_id", "team_id", "employee_id"):
        _index("team_member", col)

    op.create_table(
        "handoff_rule",
        _pk(),
        _uuid("business_id", False),
        _uuid("team_id"),
        _uuid("from_employee_id", False),
        sa.Column("when_result", sa.String(32), nullable=False),
        _jsonb("condition"),
        _uuid("to_employee_id"),
        sa.Column("task", sa.String(40), nullable=False),
        sa.Column("channel", sa.String(24), nullable=False),
        sa.Column("delay_minutes", sa.Integer(), server_default=sa.text("10"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_handoff_rule"),
        _check("handoff_rule", "delay", "delay_minutes BETWEEN 0 AND 10080"),
        _check("handoff_rule", "channel", "channel IN ('call', 'whatsapp', 'whatsapp_then_call')"),
        _fk("handoff_rule", "business_id", "business"),
        _fk("handoff_rule", "team_id", "team"),
        _fk("handoff_rule", "from_employee_id", "employee"),
        _fk("handoff_rule", "to_employee_id", "employee"),
    )
    for col in ("business_id", "team_id", "from_employee_id"):
        _index("handoff_rule", col)

    op.create_table(
        "staff_member",
        _pk(),
        _uuid("business_id", False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("phone_e164", sa.String(16), nullable=False),
        sa.Column("role_label", sa.String(60), nullable=True),
        sa.Column("ladder_position", sa.SmallInteger(), nullable=True),
        sa.Column("ring_timeout_s", sa.SmallInteger(), server_default="20", nullable=False),
        sa.Column("receives_briefs", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_owner", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_staff_member"),
        _check("staff_member", "phone", "phone_e164 ~ '^\\+[1-9][0-9]{7,14}$'"),
        _check("staff_member", "ring", "ring_timeout_s BETWEEN 5 AND 60"),
        _fk("staff_member", "business_id", "business"),
    )
    _index("staff_member", "business_id")


def _routine_tables() -> None:
    op.create_table(
        "routine",
        _pk(),
        _uuid("business_id", False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("library_id", sa.String(40), nullable=True),
        _jsonb("spec"),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _ts("next_run_at", nullable=True),
        _ts("last_run_at", nullable=True),
        _uuid("created_by"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_routine"),
        _fk("routine", "business_id", "business"),
        _fk("routine", "created_by", "app_user", "SET NULL"),
    )
    _index("routine", "business_id")
    _index("routine", "next_run_at")

    op.create_table(
        "routine_run",
        _pk(),
        _uuid("business_id", False),
        _uuid("routine_id", False),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("audience_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("contacted_count", sa.Integer(), server_default="0", nullable=False),
        _jsonb("skipped"),
        _jsonb("contacts", "[]"),
        sa.Column("approval_ref", sa.String(64), nullable=True),
        _ts("started_at"),
        _ts("finished_at", nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_routine_run"),
        _check(
            "routine_run",
            "status",
            "status IN ('awaiting_approval', 'running', 'done', 'declined', 'failed')",
        ),
        _fk("routine_run", "business_id", "business"),
        _fk("routine_run", "routine_id", "routine"),
    )
    _index("routine_run", "business_id")
    _index("routine_run", "routine_id")


def _task_tables() -> None:
    op.create_table(
        "follow_up_task",
        _pk(),
        _uuid("business_id", False),
        _uuid("contact_id"),
        _uuid("from_employee_id"),
        _uuid("to_employee_id"),
        _uuid("source_call_id"),
        _uuid("rule_id"),
        _uuid("routine_run_id"),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("task", sa.String(40), nullable=False),
        sa.Column("channel", sa.String(24), nullable=False),
        _ts("due_at"),
        sa.Column("status", sa.String(16), nullable=False),
        _jsonb("context"),
        _jsonb("outcome"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_follow_up_task"),
        _check(
            "follow_up_task",
            "status",
            "status IN ('pending', 'queued', 'sent', 'done', 'cancelled', 'failed', 'no_phone')",
        ),
        _fk("follow_up_task", "business_id", "business"),
        _fk("follow_up_task", "contact_id", "contact"),
        _fk("follow_up_task", "from_employee_id", "employee", "SET NULL"),
        _fk("follow_up_task", "to_employee_id", "employee", "SET NULL"),
        _fk("follow_up_task", "source_call_id", "call", "SET NULL"),
        _fk("follow_up_task", "rule_id", "handoff_rule", "SET NULL"),
        _fk("follow_up_task", "routine_run_id", "routine_run"),
    )
    for col in ("business_id", "contact_id", "to_employee_id", "source_call_id", "routine_run_id"):
        _index("follow_up_task", col)
    _index("follow_up_task", "status", "due_at")

    op.create_table(
        "handoff_card",
        _pk(),
        _uuid("business_id", False),
        _uuid("call_id"),
        _uuid("contact_id"),
        _uuid("employee_id"),
        sa.Column("caller_last4", sa.String(4), nullable=True),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        _ts("callback_by", nullable=True),
        _jsonb("attempts", "[]"),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        _ts("created_at"),
        _ts("resolved_at", nullable=True),
        _uuid("resolved_by"),
        sa.PrimaryKeyConstraint("id", name="pk_handoff_card"),
        _check("handoff_card", "status", "status IN ('open', 'done')"),
        _fk("handoff_card", "business_id", "business"),
        _fk("handoff_card", "contact_id", "contact"),
        _fk("handoff_card", "employee_id", "employee", "SET NULL"),
        _fk("handoff_card", "resolved_by", "app_user", "SET NULL"),
    )
    _index("handoff_card", "business_id")
    _index("handoff_card", "call_id")

    op.create_table(
        "supervisor_action",
        _pk(),
        _uuid("business_id", False),
        _uuid("call_id", False),
        _uuid("user_id"),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("text", sa.String(300), nullable=True),
        _ts("delivered_at", nullable=True),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_supervisor_action"),
        _check("supervisor_action", "kind", "kind IN ('listen', 'whisper', 'takeover')"),
        _fk("supervisor_action", "business_id", "business"),
        _fk("supervisor_action", "user_id", "app_user", "SET NULL"),
    )
    _index("supervisor_action", "business_id")
    _index("supervisor_action", "call_id")


def upgrade() -> None:
    role = get_settings().app_db_role
    _team_tables()
    _routine_tables()
    _task_tables()
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} FOR ALL "
            f"USING (business_id = {CURRENT_BUSINESS}) "
            f"WITH CHECK (business_id = {CURRENT_BUSINESS})"
        )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(TENANT_TABLES)} TO {role}")
    for table in ("routine", "follow_up_task"):
        op.execute(f"CREATE POLICY due_lookup ON {table} FOR SELECT TO CURRENT_USER USING (true)")
    op.execute(DUE_SQL)
    op.execute(f"REVOKE ALL ON FUNCTION {FN} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {FN} TO {role}")


def downgrade() -> None:
    role = get_settings().app_db_role
    op.execute(f"DROP FUNCTION {FN}")
    for table in reversed(TENANT_TABLES):
        op.execute(f"REVOKE ALL ON {table} FROM {role}")
        op.drop_table(table)
