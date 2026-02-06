from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.hr.assets import router as assets_router
from app.api.v1.hr.attendance import router as attendance_router
from app.api.v1.hr.documents import router as documents_router
from app.api.v1.hr.employees import router as employees_router
from app.api.v1.hr.holidays import router as holidays_router
from app.api.v1.hr.leave_balances import router as leave_balances_router
from app.api.v1.hr.leave_policies import router as leave_policies_router
from app.api.v1.hr.leave_requests import router as leave_requests_router
from app.api.v1.hr.leave_types import router as leave_types_router

router = APIRouter(prefix="/hr", tags=["hr"])
router.include_router(employees_router)
router.include_router(attendance_router)
router.include_router(documents_router)
router.include_router(assets_router)
router.include_router(leave_types_router)
router.include_router(leave_policies_router)
router.include_router(leave_balances_router)
router.include_router(leave_requests_router)
router.include_router(holidays_router)
