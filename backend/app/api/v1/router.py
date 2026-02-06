from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.admin.router import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.core.router import router as core_router
from app.api.v1.db import router as db_router
from app.api.v1.health import router as health_router
from app.api.v1.hr.router import router as hr_router
from app.api.v1.inventory.router import router as inventory_router
from app.api.v1.projects.router import router as projects_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(db_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(admin_router)
api_v1_router.include_router(core_router)
api_v1_router.include_router(hr_router)
api_v1_router.include_router(inventory_router)
api_v1_router.include_router(projects_router)
