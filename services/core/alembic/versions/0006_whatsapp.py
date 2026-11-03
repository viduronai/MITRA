"""WhatsApp in production: the 24-hour window, blocked sends, customer replies.

Revision ID: 0006_whatsapp
Revises: 0006_lead_consent
Create Date: 2026-11-03

* ``ix_wa_message_window``: "when did this person last write to this business?" is one index
  lookup (the 24-hour customer-service window, decided per business and recipient).
* ``wa_message.status`` gains ``blocked``: a message that was NOT sent because the window was
  closed and no approved template fits, or the person opted out. Kept so the owner can see it.
* ``wa_customer_businesses(phone_hash, context_id)``: inbound messages from customers arrive
  on Mitra's shared number with no tenant. This SECURITY DEFINER function returns only the
  business ids that messaged that number (the one whose message was replied to, if known; else
  every business that wrote to it in the last 30 days), so "STOP" reaches the right businesses.
"""

from collections.abc import Sequence

from alembic import op

from mitra_core.config import get_settings

revision: str = "0006_whatsapp"
down_revision: str | None = "0006_lead_consent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FN = "wa_customer_businesses(text, text)"
STATUS_CHECK = "ck_wa_message_ck_wa_message_status"

FN_SQL = """
CREATE FUNCTION wa_customer_businesses(p_phone_hash text, p_context_id text)
RETURNS TABLE (business_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    WITH replied AS (
        SELECT m.business_id FROM wa_message m
         WHERE p_context_id IS NOT NULL AND m.direction = 'out'
           AND m.provider_message_id = p_context_id AND m.phone_hash = p_phone_hash
         LIMIT 1
    )
    SELECT business_id FROM replied
    UNION
    SELECT DISTINCT m.business_id FROM wa_message m
     WHERE NOT EXISTS (SELECT 1 FROM replied)
       AND m.direction = 'out' AND m.phone_hash = p_phone_hash
       AND m.created_at > now() - interval '30 days'
$$
"""


def _replace_status_check(values: str) -> None:
    # 0005 named it through the metadata naming convention (prefix applied twice); raw SQL
    # keeps the name exact whichever way it was created.
    for name in (STATUS_CHECK, "ck_wa_message_status"):
        op.execute(f"ALTER TABLE wa_message DROP CONSTRAINT IF EXISTS {name}")
    op.execute(f"ALTER TABLE wa_message ADD CONSTRAINT {STATUS_CHECK} CHECK (status IN ({values}))")


def upgrade() -> None:
    role = get_settings().app_db_role
    op.create_index(
        "ix_wa_message_window",
        "wa_message",
        ["business_id", "phone_hash", "direction", "created_at"],
    )
    op.create_index("ix_wa_message_provider_id", "wa_message", ["provider_message_id"])
    _replace_status_check("'sent', 'failed', 'received', 'blocked'")
    op.execute(
        "CREATE POLICY wa_definer_select ON wa_message FOR SELECT TO CURRENT_USER USING (true)"
    )
    op.execute(FN_SQL)
    op.execute(f"REVOKE ALL ON FUNCTION {FN} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {FN} TO {role}")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {FN}")
    op.execute("DROP POLICY wa_definer_select ON wa_message")
    op.execute("DELETE FROM wa_message WHERE status = 'blocked'")
    _replace_status_check("'sent', 'failed', 'received'")
    op.drop_index("ix_wa_message_provider_id", "wa_message")
    op.drop_index("ix_wa_message_window", "wa_message")
