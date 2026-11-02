"""Real calls and customer memory: call, call_action, interaction_summary, memory_fact, commitment.

Revision ID: 0004_calls
Revises: 0003_internal_pack
Create Date: 2026-10-20

All five are ordinary tenant tables: ENABLE + FORCE RLS, a ``tenant_isolation`` policy on
``business_id`` and explicit grants to the app role. Everything about a customer cascades from
``contact`` so erasing a contact (MEM-04, DPDP) erases their calls, transcripts and memory.
Recording / transcript object-storage URIs are columns already; transcripts live inline as
JSON until recordings move to S3.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mitra_core.config import get_settings

revision: str = "0004_calls"
down_revision: str | None = "0003_internal_pack"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS: dict[str, tuple[str, ...]] = {
    "call_direction": ("inbound", "outbound", "web"),
    "call_status": ("live", "ended", "processed"),
    "call_result": (
        "booked",
        "interested",
        "call_back",
        "transferred",
        "not_interested",
        "info_only",
        "missed",
    ),
    "call_sentiment": ("positive", "neutral", "negative"),
    "call_rating": ("up", "down"),
    "memory_status": ("confirmed", "inferred"),
    "commitment_status": ("open", "done", "cancelled"),
}
TENANT_TABLES = ("call", "call_action", "interaction_summary", "memory_fact", "commitment")
CURRENT_BUSINESS = "app_current_business_id()"


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def _locale() -> postgresql.ENUM:
    return postgresql.ENUM(name="locale", create_type=False)


def _pk() -> sa.Column[sa.Uuid]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _ts(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _jsonb(name: str, default: str) -> sa.Column[postgresql.JSONB]:
    return sa.Column(name, postgresql.JSONB(), server_default=default, nullable=False)


def _fk(table: str, column: str, target: str, ondelete: str = "CASCADE") -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=f"fk_{table}_{column}_{target}", ondelete=ondelete
    )


def _create_tables() -> None:
    op.create_table(
        "call",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("direction", _enum("call_direction"), nullable=False),
        sa.Column("status", _enum("call_status"), nullable=False),
        sa.Column("phone_last4", sa.String(4), nullable=True),
        sa.Column("external_ref", sa.String(64), nullable=True),
        sa.Column("language", _locale(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("result", _enum("call_result"), nullable=True),
        sa.Column("summary", sa.String(800), nullable=True),
        sa.Column("next_step", sa.String(300), nullable=True),
        sa.Column("sentiment", _enum("call_sentiment"), nullable=True),
        _jsonb("fields", "{}"),
        _jsonb("transcript", "[]"),
        sa.Column("transcript_text", sa.Text(), server_default="", nullable=False),
        sa.Column("recording_uri", sa.String(1024), nullable=True),
        sa.Column("transcript_uri", sa.String(1024), nullable=True),
        _jsonb("latency_stats", "{}"),
        _jsonb("usage", "{}"),
        _jsonb("unknown_questions", "[]"),
        _jsonb("alerts", "[]"),
        sa.Column("rating", _enum("call_rating"), nullable=True),
        sa.Column("rating_reason", sa.String(300), nullable=True),
        sa.Column("rated_by", sa.Uuid(), nullable=True),
        sa.Column("rated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_call"),
        _fk("call", "business_id", "business"),
        _fk("call", "employee_id", "employee", "SET NULL"),
        _fk("call", "contact_id", "contact"),
        _fk("call", "rated_by", "app_user", "SET NULL"),
    )
    op.create_index("ix_call_business_id", "call", ["business_id"])
    op.create_index("ix_call_employee_id", "call", ["employee_id"])
    op.create_index("ix_call_contact_id", "call", ["contact_id"])
    op.create_index("ix_call_business_id_started_at", "call", ["business_id", "started_at"])

    op.create_table(
        "call_action",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        _jsonb("args", "{}"),
        _jsonb("result", "{}"),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_call_action"),
        _fk("call_action", "business_id", "business"),
        _fk("call_action", "call_id", "call"),
    )
    op.create_index("ix_call_action_business_id", "call_action", ["business_id"])
    op.create_index("ix_call_action_call_id", "call_action", ["call_id"])

    op.create_table(
        "interaction_summary",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column("summary", sa.String(800), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_interaction_summary"),
        sa.UniqueConstraint("call_id", name="uq_interaction_summary_call_id"),
        _fk("interaction_summary", "business_id", "business"),
        _fk("interaction_summary", "contact_id", "contact"),
        _fk("interaction_summary", "call_id", "call"),
    )
    op.create_index("ix_interaction_summary_business_id", "interaction_summary", ["business_id"])
    op.create_index("ix_interaction_summary_contact_id", "interaction_summary", ["contact_id"])

    op.create_table(
        "memory_fact",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("source_call_id", sa.Uuid(), nullable=True),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("value", sa.String(300), nullable=False),
        sa.Column("status", _enum("memory_status"), nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_memory_fact"),
        sa.UniqueConstraint("contact_id", "key", name="uq_memory_fact_contact_id_key"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_memory_fact_confidence"),
        _fk("memory_fact", "business_id", "business"),
        _fk("memory_fact", "contact_id", "contact"),
        _fk("memory_fact", "source_call_id", "call", "SET NULL"),
    )
    op.create_index("ix_memory_fact_business_id", "memory_fact", ["business_id"])
    op.create_index("ix_memory_fact_contact_id", "memory_fact", ["contact_id"])
    op.create_index("ix_memory_fact_source_call_id", "memory_fact", ["source_call_id"])

    op.create_table(
        "commitment",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("call_id", sa.Uuid(), nullable=True),
        sa.Column("employee_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", _enum("commitment_status"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_commitment"),
        _fk("commitment", "business_id", "business"),
        _fk("commitment", "contact_id", "contact"),
        _fk("commitment", "call_id", "call"),
        _fk("commitment", "employee_id", "employee", "SET NULL"),
    )
    op.create_index("ix_commitment_business_id", "commitment", ["business_id"])
    op.create_index("ix_commitment_contact_id", "commitment", ["contact_id"])
    op.create_index("ix_commitment_call_id", "commitment", ["call_id"])


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


def downgrade() -> None:
    role = get_settings().app_db_role
    for table in reversed(TENANT_TABLES):
        op.execute(f"REVOKE ALL ON {table} FROM {role}")
        op.drop_table(table)
    bind = op.get_bind()
    for name in reversed(ENUMS):
        postgresql.ENUM(name=name).drop(bind)
