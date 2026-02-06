from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.projects.dprs import router as dprs_router
from app.api.v1.projects.finance import router as finance_router
from app.api.v1.projects.profitability import router as profitability_router

router = APIRouter(prefix="/projects")
router.include_router(dprs_router)
router.include_router(finance_router)
router.include_router(profitability_router)

