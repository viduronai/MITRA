from fastapi import APIRouter

from mitra_core.api.v1 import (
    approvals,
    auth,
    billing,
    businesses,
    calls,
    campaigns,
    catalog,
    customers,
    demo_calls,
    employees,
    home,
    knowledge,
    leads,
    live_calls,
    manager,
    me,
    missed_calls,
    onboarding,
    payments,
    payments_public,
    phone_numbers,
    routines,
    staff,
    team,
    test_calls,
    webhooks,
)
from mitra_core.schemas.common import ErrorResponse

router = APIRouter(
    prefix="/v1",
    responses={
        401: {"model": ErrorResponse, "description": "Unauthenticated"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        404: {"model": ErrorResponse, "description": "Not found"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
)
router.include_router(auth.router)
router.include_router(approvals.router)
router.include_router(manager.router)
router.include_router(me.router)
router.include_router(businesses.router)
router.include_router(employees.router)
router.include_router(catalog.router)
router.include_router(knowledge.router)
router.include_router(test_calls.router)
router.include_router(onboarding.router)
router.include_router(demo_calls.router)
router.include_router(billing.router)
router.include_router(payments_public.router)
router.include_router(payments.router)
router.include_router(calls.router)
router.include_router(customers.router)
router.include_router(home.router)
router.include_router(phone_numbers.router)
router.include_router(phone_numbers.compliance_router)
router.include_router(missed_calls.router)
router.include_router(campaigns.router)
router.include_router(team.router)
router.include_router(staff.router)
router.include_router(routines.router)
router.include_router(live_calls.router)
router.include_router(leads.router)
router.include_router(webhooks.router)
