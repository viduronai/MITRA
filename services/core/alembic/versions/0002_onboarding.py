"""Step 2 onboarding: phone OTP, knowledge (sources + facts), employee voice/behaviour, test calls.

Revision ID: 0002_onboarding
Revises: 0001_initial
Create Date: 2026-10-18

Row-Level Security
------------------
* ``knowledge_source``, ``fact`` and ``test_call`` are ordinary tenant tables: ENABLE + FORCE
  RLS, a ``tenant_isolation`` policy on ``business_id`` and explicit grants to the app role.
* ``otp_request`` is pre-auth (no business and no user exist yet), so it cannot be keyed on
  ``app_current_business_id()``. It is locked down differently:
    - the app role gets NO privileges on the table (not even SELECT), so it can never list
      pending requests or read code hashes;
    - all access goes through two SECURITY DEFINER functions with fixed behaviour
      (``auth_otp_issue`` applies the per-phone rate limit; ``auth_otp_verify`` counts attempts,
      checks expiry, consumes the request and only then finds or creates the user). EXECUTE is
      revoked from PUBLIC and granted to the app role only, and each pins ``search_path``;
    - RLS is still ENABLE + FORCE, with policies scoped ``TO`` the owning (migration) role only,
      so the definer functions work even when the owner is not a superuser.
* ``auth_otp_verify`` must look up ``app_user`` by phone, which the app role's policies never
  allow (that would be a phone -> user enumeration oracle). Narrow SELECT/INSERT/UPDATE policies
  on ``app_user`` are therefore added for the owning role only; the app role's view of
  ``app_user`` is unchanged.
* The OTP code is hashed in the API with an HMAC key the database never sees, so even direct
  EXECUTE access cannot brute-force a code.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mitra_core.config import get_settings

revision: str = "0002_onboarding"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS: dict[str, tuple[str, ...]] = {
    "knowledge_source_type": ("url", "text"),
    "knowledge_source_status": ("processing", "ready", "failed"),
    "fact_category": ("services", "prices", "timings", "location", "contact", "faq", "policy"),
    "fact_status": ("suggested", "confirmed"),
}
TENANT_TABLES = ("knowledge_source", "fact", "test_call")
CURRENT_BUSINESS = "app_current_business_id()"
EMPTY_BEHAVIOUR = """'{"ask_for": [], "never_say": [], "transfer_when": []}'::jsonb"""

ISSUE_FN = "auth_otp_issue(uuid, text, text, text, integer, integer, integer)"
VERIFY_FN = "auth_otp_verify(uuid, text, integer, text)"

# Outcomes: 'ok' | 'rate_limited' (retry_after = seconds until the oldest request in the window
# ages out). Also purges requests older than a day.
ISSUE_SQL = """
CREATE FUNCTION auth_otp_issue(
    p_id uuid, p_phone text, p_phone_hash text, p_code_hash text,
    p_ttl_seconds integer, p_max_requests integer, p_window_seconds integer,
    OUT outcome text, OUT retry_after integer
) LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    v_count integer;
    v_oldest timestamptz;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('otp:' || p_phone_hash, 0));
    DELETE FROM otp_request WHERE created_at < now() - interval '1 day';
    SELECT count(*), min(created_at) INTO v_count, v_oldest FROM otp_request
     WHERE phone_hash = p_phone_hash
       AND created_at > now() - make_interval(secs => p_window_seconds);
    IF v_count >= p_max_requests THEN
        outcome := 'rate_limited';
        retry_after := greatest(1, ceil(extract(epoch FROM
            v_oldest + make_interval(secs => p_window_seconds) - now()))::integer);
        RETURN;
    END IF;
    INSERT INTO otp_request (id, phone_e164, phone_hash, code_hash, expires_at)
    VALUES (p_id, p_phone, p_phone_hash, p_code_hash,
            now() + make_interval(secs => p_ttl_seconds));
    outcome := 'ok';
    retry_after := 0;
END $$
"""

# Outcomes: 'ok' (user_id set) | 'invalid' (unknown request or wrong code) | 'expired' |
# 'consumed' | 'locked' (attempts exhausted). A wrong code still increments ``attempts``, so the
# caller must COMMIT failed verifications too.
VERIFY_SQL = """
CREATE FUNCTION auth_otp_verify(
    p_id uuid, p_code_hash text, p_max_attempts integer, p_name text,
    OUT outcome text, OUT user_id uuid, OUT attempts_left integer
) LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    r otp_request%ROWTYPE;
BEGIN
    attempts_left := 0;
    SELECT * INTO r FROM otp_request WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        outcome := 'invalid';
        RETURN;
    END IF;
    IF r.consumed_at IS NOT NULL THEN
        outcome := 'consumed';
        RETURN;
    END IF;
    IF r.expires_at <= now() THEN
        outcome := 'expired';
        RETURN;
    END IF;
    IF r.attempts >= p_max_attempts THEN
        outcome := 'locked';
        RETURN;
    END IF;
    UPDATE otp_request SET attempts = attempts + 1 WHERE id = p_id;
    IF r.code_hash <> p_code_hash THEN
        attempts_left := p_max_attempts - r.attempts - 1;
        outcome := CASE WHEN attempts_left <= 0 THEN 'locked' ELSE 'invalid' END;
        RETURN;
    END IF;
    UPDATE otp_request SET consumed_at = now() WHERE id = p_id;

    SELECT u.id INTO user_id FROM app_user u WHERE u.phone_e164 = r.phone_e164;
    IF user_id IS NULL THEN
        INSERT INTO app_user (phone_e164, name) VALUES (r.phone_e164, nullif(p_name, ''))
        ON CONFLICT (phone_e164) DO NOTHING
        RETURNING id INTO user_id;
        IF user_id IS NULL THEN  -- lost a race with a concurrent first login
            SELECT u.id INTO user_id FROM app_user u WHERE u.phone_e164 = r.phone_e164;
        END IF;
    ELSIF nullif(p_name, '') IS NOT NULL THEN
        UPDATE app_user SET name = p_name WHERE id = user_id AND name IS NULL;
    END IF;
    outcome := 'ok';
END $$
"""


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


def _create_tables() -> None:
    op.create_table(
        "otp_request",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("phone_e164", sa.String(16), nullable=False),
        sa.Column("phone_hash", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_otp_request"),
    )
    op.create_index(
        "ix_otp_request_phone_hash_created_at", "otp_request", ["phone_hash", "created_at"]
    )

    op.create_table(
        "knowledge_source",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("type", _enum("knowledge_source_type"), nullable=False),
        sa.Column("status", _enum("knowledge_source_status"), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("url", sa.String(2048), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_source"),
        _business_fk("knowledge_source"),
    )
    op.create_index("ix_knowledge_source_business_id", "knowledge_source", ["business_id"])

    op.create_table(
        "fact",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("category", _enum("fact_category"), nullable=False),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("status", _enum("fact_status"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_fact"),
        _business_fk("fact"),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["knowledge_source.id"],
            name="fk_fact_source_id_knowledge_source",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_fact_business_id", "fact", ["business_id"])
    op.create_index("ix_fact_source_id", "fact", ["source_id"])

    op.create_table(
        "test_call",
        _pk(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("phone_hash", sa.Text(), nullable=False),
        sa.Column("phone_last4", sa.String(4), nullable=False),
        sa.Column("transcript", postgresql.JSONB(), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("corrections", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_test_call"),
        _business_fk("test_call"),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employee.id"],
            name="fk_test_call_employee_id_employee",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name="fk_test_call_created_by_app_user",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_test_call_business_id", "test_call", ["business_id"])
    op.create_index("ix_test_call_employee_id", "test_call", ["employee_id"])


def upgrade() -> None:
    role = get_settings().app_db_role
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind)

    op.add_column("employee", sa.Column("voice_id", sa.String(64), nullable=True))
    op.add_column("employee", sa.Column("greeting", sa.String(300), nullable=True))
    op.add_column(
        "employee",
        sa.Column(
            "behaviour",
            postgresql.JSONB(),
            server_default=sa.text(EMPTY_BEHAVIOUR),
            nullable=False,
        ),
    )

    _create_tables()

    for table in (*TENANT_TABLES, "otp_request"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    for table in TENANT_TABLES:
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} FOR ALL "
            f"USING (business_id = {CURRENT_BUSINESS}) "
            f"WITH CHECK (business_id = {CURRENT_BUSINESS})"
        )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(TENANT_TABLES)} TO {role}")

    # Pre-auth: owner-only policies (used by the SECURITY DEFINER functions), nothing for the app.
    op.execute(
        "CREATE POLICY definer_access ON otp_request FOR ALL TO CURRENT_USER "
        "USING (true) WITH CHECK (true)"
    )
    op.execute(
        "CREATE POLICY otp_definer_select ON app_user FOR SELECT TO CURRENT_USER USING (true)"
    )
    op.execute(
        "CREATE POLICY otp_definer_insert ON app_user FOR INSERT TO CURRENT_USER WITH CHECK (true)"
    )
    op.execute(
        "CREATE POLICY otp_definer_update ON app_user FOR UPDATE TO CURRENT_USER "
        "USING (true) WITH CHECK (true)"
    )
    op.execute(ISSUE_SQL)
    op.execute(VERIFY_SQL)
    for fn in (ISSUE_FN, VERIFY_FN):
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {role}")


def downgrade() -> None:
    role = get_settings().app_db_role
    op.execute(f"DROP FUNCTION {VERIFY_FN}")
    op.execute(f"DROP FUNCTION {ISSUE_FN}")
    for policy in ("otp_definer_update", "otp_definer_insert", "otp_definer_select"):
        op.execute(f"DROP POLICY {policy} ON app_user")
    for table in ("test_call", "fact", "knowledge_source", "otp_request"):
        op.execute(f"REVOKE ALL ON {table} FROM {role}")
        op.drop_table(table)
    op.drop_column("employee", "behaviour")
    op.drop_column("employee", "greeting")
    op.drop_column("employee", "voice_id")
    bind = op.get_bind()
    for name in reversed(ENUMS):
        postgresql.ENUM(name=name).drop(bind)
