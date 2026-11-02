from fastapi import APIRouter

from mitra_core.api.v1 import (
    auth,
    billing,
    businesses,
    calls,
    catalog,
    customers,
    demo_calls,
    employees,
    home,
    knowledge,
    me,
    onboarding,
    phone_numbers,
    test_calls,
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
router.include_router(me.router)
router.include_router(businesses.router)
router.include_router(employees.router)
router.include_router(catalog.router)
router.include_router(knowledge.router)
router.include_router(test_calls.router)
router.include_router(onboarding.router)
router.include_router(demo_calls.router)
router.include_router(billing.router)
router.include_router(calls.router)
router.include_router(customers.router)
router.include_router(home.router)
router.include_router(phone_numbers.router)
router.include_router(phone_numbers.compliance_router)
