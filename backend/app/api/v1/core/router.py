from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.core.cost_centers import router as cost_centers_router
from app.api.v1.core.organizations import router as organizations_router
from app.api.v1.core.projects import router as projects_router
from app.api.v1.core.sites import router as sites_router

router = APIRouter(prefix="/core", tags=["core"])
router.include_router(organizations_router)
router.include_router(sites_router)
router.include_router(projects_router)
router.include_router(cost_centers_router)
