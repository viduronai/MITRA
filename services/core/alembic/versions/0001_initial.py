"""Initial schema: tenancy, users, employees, contacts, idempotency + RLS and the app role.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-18

Row-Level Security model
------------------------
* ``app_current_business_id()`` / ``app_current_user_id()`` read the transaction-local settings
  ``app.business_id`` / ``app.user_id`` that the API sets per transaction. NULLIF(...,'') matters:
  once a custom setting has been used on a pooled connection, it reads back as '' (not NULL)
  after the transaction ends, and ''::uuid would raise instead of matching nothing.
* Every table is ENABLE + FORCE ROW LEVEL SECURITY (FORCE also binds the table owner).
  Superusers still bypass RLS, which is why the API connects as the non-superuser app role
  created below, while migrations run as the schema owner.
* No ALTER DEFAULT PRIVILEGES: each migration grants on its own tables, so a new table that
  forgets its policy is unreachable by the API (fails closed).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mitra_core.config import get_settings

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS: dict[str, tuple[str, ...]] = {
    "industry": ("clinic", "real_estate", "education", "other"),
    "locale": ("en", "te", "hi"),
    "member_role": ("owner", "manager", "staff", "agency_admin"),
    "role_template": ("receptionist", "lead_caller", "reminder_caller", "payment_caller"),
    "voice_tier": ("smart", "natural", "signature"),
    "employee_status": ("working", "paused", "training"),
}

# Tables isolated purely by business_id.
TENANT_TABLES = ("branch", "membership", "employee", "contact", "idempotency_record")
ALL_TABLES = ("agency", "business", "app_user", *TENANT_TABLES)

CURRENT_BUSINESS = "app_current_business_id()"
CURRENT_USER = "app_current_user_id()"


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def _pk() -> sa.Column[sa.Uuid]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _timestamps() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _business_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["business_id"],
        ["business.id"],
        name=f"fk_{table}_business_id_business",
        ondelete="CASCADE",
    )


def _create_tables() -> None:
    op.create_table(
        "agency",
        _pk(),
        sa.Column("name", sa.String(120), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_agency"),
    )
    op.create_table(
        "business",
        _pk(),
        sa.Column("agency_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("industry", _enum("industry"), nullable=False),
        sa.Column("city", sa.String(80), nullable=True),
        sa.Column(
            "languages",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "timezone", sa.String(64), server_default=sa.text("'Asia/Kolkata'"), nullable=False
        ),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_business"),
        sa.ForeignKeyConstraint(
            ["agency_id"], ["agency.id"], name="fk_business_agency_id_agency", ondelete="SET NULL"
        ),
    )
    op.create_index("ix_business_agency_id", "business", ["agency_id"])

    op.create_table(
        "branch",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("city", sa.String(80), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_branch"),
        _business_fk("branch"),
    )
    op.create_index("ix_branch_business_id", "branch", ["business_id"])

    op.create_table(
        "app_user",
        _pk(),
        sa.Column("phone_e164", sa.String(16), nullable=False),
        sa.Column("name", sa.String(120), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("preferred_locale", _enum("locale"), server_default="en", nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_app_user"),
        sa.UniqueConstraint("phone_e164", name="uq_app_user_phone_e164"),
    )

    op.create_table(
        "membership",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", _enum("member_role"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_membership"),
        _business_fk("membership"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name="fk_membership_user_id_app_user", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("business_id", "user_id", name="uq_membership_business_id_user_id"),
    )
    op.create_index("ix_membership_user_id", "membership", ["user_id"])

    op.create_table(
        "employee",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("role_template", _enum("role_template"), nullable=False),
        sa.Column("voice_tier", _enum("voice_tier"), server_default="natural", nullable=False),
        sa.Column("status", _enum("employee_status"), server_default="training", nullable=False),
        sa.Column(
            "languages",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("working_hours", postgresql.JSONB(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_employee"),
        _business_fk("employee"),
    )
    op.create_index("ix_employee_business_id", "employee", ["business_id"])

    # Contact phone numbers are stored only as an HMAC index + last 4 digits. Encrypted full
    # numbers (phone_enc, KMS envelope encryption) come in a later migration.
    op.create_table(
        "contact",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("phone_hash", sa.Text(), nullable=False),
        sa.Column("phone_last4", sa.String(4), nullable=False),
        sa.Column("name", sa.String(120), nullable=True),
        sa.Column("language", _enum("locale"), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_contact"),
        _business_fk("contact"),
        sa.UniqueConstraint("business_id", "phone_hash", name="uq_contact_business_id_phone_hash"),
    )

    op.create_table(
        "idempotency_record",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint", sa.String(64), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.SmallInteger(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_record"),
        _business_fk("idempotency_record"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name="fk_idempotency_record_user_id_app_user",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "business_id", "endpoint", "key", name="uq_idempotency_record_business_id_endpoint_key"
        ),
    )
    op.create_index(
        "uq_idempotency_record_user_business_create",
        "idempotency_record",
        ["user_id", "key"],
        unique=True,
        postgresql_where=sa.text("endpoint = 'POST /v1/businesses'"),
    )


def _create_policies() -> None:
    for table in ALL_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # agency: no policies yet => deny-all for the app role until agency features exist.

    # business: the tenant row itself (keyed on id) ...
    op.execute(
        f"CREATE POLICY tenant_isolation ON business FOR ALL "
        f"USING (id = {CURRENT_BUSINESS}) WITH CHECK (id = {CURRENT_BUSINESS})"
    )
    # ... plus read-only access to every business the current user belongs to (for /v1/me).
    op.execute(
        "CREATE POLICY member_read ON business FOR SELECT USING (EXISTS ("
        "SELECT 1 FROM membership m "
        f"WHERE m.business_id = business.id AND m.user_id = {CURRENT_USER}))"
    )

    for table in TENANT_TABLES:
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} FOR ALL "
            f"USING (business_id = {CURRENT_BUSINESS}) "
            f"WITH CHECK (business_id = {CURRENT_BUSINESS})"
        )

    # A user can list their own memberships across businesses (for /v1/me).
    op.execute(f"CREATE POLICY self_read ON membership FOR SELECT USING (user_id = {CURRENT_USER})")
    # Idempotency for POST /v1/businesses is looked up (and expired) by user, not business.
    op.execute(
        f"CREATE POLICY self_read ON idempotency_record FOR SELECT USING (user_id = {CURRENT_USER})"
    )
    op.execute(
        f"CREATE POLICY self_delete ON idempotency_record FOR DELETE "
        f"USING (user_id = {CURRENT_USER})"
    )

    # app_user is global identity: visible to self and to co-members of the current business;
    # writable only by self.
    op.execute(
        f"CREATE POLICY visible ON app_user FOR SELECT USING (id = {CURRENT_USER} OR EXISTS ("
        "SELECT 1 FROM membership m "
        f"WHERE m.user_id = app_user.id AND m.business_id = {CURRENT_BUSINESS}))"
    )
    op.execute(f"CREATE POLICY self_insert ON app_user FOR INSERT WITH CHECK (id = {CURRENT_USER})")
    op.execute(
        f"CREATE POLICY self_update ON app_user FOR UPDATE "
        f"USING (id = {CURRENT_USER}) WITH CHECK (id = {CURRENT_USER})"
    )


def _ensure_app_role() -> str:
    """Create (or update the password of) the NON-superuser login role used by the API."""
    settings = get_settings()
    role = settings.app_db_role  # validated as a plain lowercase identifier in Settings
    password = settings.app_db_password.replace("'", "''")
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role}
    ).scalar()
    verb = "ALTER" if exists else "CREATE"
    bind.exec_driver_sql(
        f"{verb} ROLE {role} WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE "
        f"PASSWORD '{password}'"
    )
    return role


def upgrade() -> None:
    op.execute(
        "CREATE FUNCTION app_current_business_id() RETURNS uuid LANGUAGE sql STABLE AS "
        "$$ SELECT NULLIF(current_setting('app.business_id', true), '')::uuid $$"
    )
    op.execute(
        "CREATE FUNCTION app_current_user_id() RETURNS uuid LANGUAGE sql STABLE AS "
        "$$ SELECT NULLIF(current_setting('app.user_id', true), '')::uuid $$"
    )
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind)

    _create_tables()
    _create_policies()

    role = _ensure_app_role()
    op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(ALL_TABLES)} TO {role}")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION app_current_business_id(), app_current_user_id() TO {role}"
    )


def downgrade() -> None:
    role = get_settings().app_db_role
    # These policies reference membership, so they must go before the tables.
    op.execute("DROP POLICY member_read ON business")
    op.execute("DROP POLICY visible ON app_user")
    for table in reversed(ALL_TABLES):
        op.execute(f"REVOKE ALL ON {table} FROM {role}")
        op.drop_table(table)
    bind = op.get_bind()
    for name in reversed(ENUMS):
        postgresql.ENUM(name=name).drop(bind)
    op.execute("DROP FUNCTION app_current_user_id()")
    op.execute("DROP FUNCTION app_current_business_id()")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {role}")
    # The role itself is cluster-wide (shared by the dev and test databases), so it is kept.
