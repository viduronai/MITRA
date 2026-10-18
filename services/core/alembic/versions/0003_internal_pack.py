"""Internal employee-pack lookup: employee id -> business id, for service-to-service calls.

Revision ID: 0003_internal_pack
Revises: 0002_onboarding
Create Date: 2026-10-18

The voice service knows only an employee id, but every RLS policy needs ``app.business_id``
first. ``internal_employee_business(uuid)`` is a SECURITY DEFINER function that returns ONLY
that employee's ``business_id`` (no other column, no row data); the API then binds the tenant
from it and reads everything else through the normal RLS policies. EXECUTE is granted to the
app role only and ``search_path`` is pinned. As in 0002, a SELECT policy on ``employee`` scoped
to the owning role keeps the function working when the owner is not a superuser; the app role's
view of ``employee`` is unchanged.
"""

from collections.abc import Sequence

from alembic import op

from mitra_core.config import get_settings

revision: str = "0003_internal_pack"
down_revision: str | None = "0002_onboarding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FN = "internal_employee_business(uuid)"


def upgrade() -> None:
    role = get_settings().app_db_role
    op.execute("CREATE POLICY internal_lookup ON employee FOR SELECT TO CURRENT_USER USING (true)")
    op.execute(
        "CREATE FUNCTION internal_employee_business(p_employee_id uuid) RETURNS uuid "
        "LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS "
        "$$ SELECT business_id FROM employee WHERE id = p_employee_id $$"
    )
    op.execute(f"REVOKE ALL ON FUNCTION {FN} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {FN} TO {role}")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {FN}")
    op.execute("DROP POLICY internal_lookup ON employee")
