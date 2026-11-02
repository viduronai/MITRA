"""Public "Call me now" demo requests from the marketing site.

Revision ID: 0004_demo
Revises: 0004_telephony
Create Date: 2026-10-20

``demo_call`` is pre-auth (anyone on the landing page), so it is locked down like
``otp_request`` in 0002:

* the app role gets NO privileges on the table, so it can never list requests;
* all access goes through ``demo_call_request``, a SECURITY DEFINER function with fixed
  behaviour: it serialises on the phone and IP hashes, applies both rate limits, purges rows
  older than 30 days and only then inserts. EXECUTE is revoked from PUBLIC and granted to the
  app role only, and ``search_path`` is pinned;
* RLS is ENABLE + FORCE with a policy scoped ``TO`` the owning role only, so the function works
  even when the owner is not a superuser.

The phone number and client IP arrive already HMAC-hashed by the API; the database never sees
either in the clear.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mitra_core.config import get_settings

revision: str = "0004_demo"
down_revision: str | None = "0004_telephony"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FN = "demo_call_request(uuid, text, text, text, text, text, integer, integer, integer, integer)"

# Outcomes: 'ok' | 'phone_limited' | 'ip_limited' (retry_after = seconds until the oldest request
# in that window ages out). The phone limit is checked first so a shared office IP never hides
# the per-number limit.
REQUEST_SQL = """
CREATE FUNCTION demo_call_request(
    p_id uuid, p_phone_hash text, p_phone_last4 text, p_ip_hash text,
    p_language text, p_industry text,
    p_max_per_phone integer, p_phone_window_seconds integer,
    p_max_per_ip integer, p_ip_window_seconds integer,
    OUT outcome text, OUT retry_after integer
) LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    v_count integer;
    v_oldest timestamptz;
BEGIN
    -- Fixed order (phone, then IP) so concurrent requests cannot deadlock.
    PERFORM pg_advisory_xact_lock(hashtextextended('demo:phone:' || p_phone_hash, 0));
    PERFORM pg_advisory_xact_lock(hashtextextended('demo:ip:' || p_ip_hash, 0));
    DELETE FROM demo_call WHERE created_at < now() - interval '30 days';

    SELECT count(*), min(created_at) INTO v_count, v_oldest FROM demo_call
     WHERE phone_hash = p_phone_hash
       AND created_at > now() - make_interval(secs => p_phone_window_seconds);
    IF v_count >= p_max_per_phone THEN
        outcome := 'phone_limited';
        retry_after := greatest(1, ceil(extract(epoch FROM
            v_oldest + make_interval(secs => p_phone_window_seconds) - now()))::integer);
        RETURN;
    END IF;

    SELECT count(*), min(created_at) INTO v_count, v_oldest FROM demo_call
     WHERE ip_hash = p_ip_hash
       AND created_at > now() - make_interval(secs => p_ip_window_seconds);
    IF v_count >= p_max_per_ip THEN
        outcome := 'ip_limited';
        retry_after := greatest(1, ceil(extract(epoch FROM
            v_oldest + make_interval(secs => p_ip_window_seconds) - now()))::integer);
        RETURN;
    END IF;

    INSERT INTO demo_call (id, phone_hash, phone_last4, ip_hash, language, industry, consented_at)
    VALUES (p_id, p_phone_hash, p_phone_last4, p_ip_hash, p_language, p_industry, now());
    outcome := 'ok';
    retry_after := 0;
END $$
"""


def upgrade() -> None:
    role = get_settings().app_db_role
    op.create_table(
        "demo_call",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("phone_hash", sa.Text(), nullable=False),
        sa.Column("phone_last4", sa.String(4), nullable=False),
        sa.Column("ip_hash", sa.Text(), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("industry", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("simulated", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("language IN ('te', 'hi', 'en')", name="ck_demo_call_language"),
        sa.CheckConstraint(
            "industry IN ('clinic', 'real_estate', 'coaching')", name="ck_demo_call_industry"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_demo_call"),
    )
    op.create_index("ix_demo_call_phone_hash_created_at", "demo_call", ["phone_hash", "created_at"])
    op.create_index("ix_demo_call_ip_hash_created_at", "demo_call", ["ip_hash", "created_at"])

    op.execute("ALTER TABLE demo_call ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE demo_call FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY definer_access ON demo_call FOR ALL TO CURRENT_USER "
        "USING (true) WITH CHECK (true)"
    )
    op.execute(REQUEST_SQL)
    op.execute(f"REVOKE ALL ON FUNCTION {FN} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {FN} TO {role}")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {FN}")
    op.drop_table("demo_call")
