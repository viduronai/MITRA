from fastapi import APIRouter

from mitra_core.api.v1 import businesses, employees, me
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
router.include_router(me.router)
router.include_router(businesses.router)
router.include_router(employees.router)
