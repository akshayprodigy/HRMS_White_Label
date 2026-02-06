from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.admin.audit_logs import router as audit_logs_router
from app.api.v1.admin.jobs import router as jobs_router
from app.api.v1.admin.permissions import router as permissions_router
from app.api.v1.admin.roles import router as roles_router
from app.api.v1.admin.users import router as users_router

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(users_router)
router.include_router(roles_router)
router.include_router(permissions_router)
router.include_router(audit_logs_router)
router.include_router(jobs_router)
