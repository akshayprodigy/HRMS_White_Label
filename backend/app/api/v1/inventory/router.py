from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.inventory.grns import router as grns_router
from app.api.v1.inventory.issues import router as issues_router
from app.api.v1.inventory.items import router as items_router
from app.api.v1.inventory.reports import router as reports_router
from app.api.v1.inventory.uoms import router as uoms_router
from app.api.v1.inventory.warehouses import router as warehouses_router

router = APIRouter(prefix="/inventory", tags=["inventory"])
router.include_router(uoms_router)
router.include_router(items_router)
router.include_router(warehouses_router)
router.include_router(grns_router)
router.include_router(issues_router)
router.include_router(reports_router)
