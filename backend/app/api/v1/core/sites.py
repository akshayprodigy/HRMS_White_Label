from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.db.models.core import Site
from app.modules.core.schemas import SiteCreate, SitePublic, SiteUpdate
from app.modules.core.service import (
    create_site,
    delete_site,
    list_sites,
    update_site,
)

router = APIRouter(prefix="/sites")

_SITE_NOT_FOUND = "Site not found"


@router.get(
    "",
    response_model=list[SitePublic],
    dependencies=[Depends(require_permissions({"core.sites.read"}))],
)
def core_list_sites(db: Session = Depends(get_db)) -> list[SitePublic]:
    return [SitePublic.model_validate(s) for s in list_sites(db)]


@router.post(
    "",
    response_model=SitePublic,
    dependencies=[Depends(require_permissions({"core.sites.write"}))],
)
def core_create_site(
    payload: SiteCreate,
    db: Session = Depends(get_db),
) -> SitePublic:
    site = create_site(
        db,
        organization_id=payload.organization_id,
        code=payload.code,
        name=payload.name,
        is_active=payload.is_active,
    )
    return SitePublic.model_validate(site)


@router.get(
    "/{site_id}",
    response_model=SitePublic,
    dependencies=[Depends(require_permissions({"core.sites.read"}))],
)
def core_get_site(site_id: int, db: Session = Depends(get_db)) -> SitePublic:
    site = db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail=_SITE_NOT_FOUND)
    return SitePublic.model_validate(site)


@router.put(
    "/{site_id}",
    response_model=SitePublic,
    dependencies=[Depends(require_permissions({"core.sites.write"}))],
)
def core_update_site(
    site_id: int,
    payload: SiteUpdate,
    db: Session = Depends(get_db),
) -> SitePublic:
    site = db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail=_SITE_NOT_FOUND)

    updated = update_site(
        db,
        site=site,
        organization_id=payload.organization_id,
        code=payload.code,
        name=payload.name,
        is_active=payload.is_active,
    )
    return SitePublic.model_validate(updated)


@router.delete(
    "/{site_id}",
    dependencies=[Depends(require_permissions({"core.sites.write"}))],
)
def core_delete_site(site_id: int, db: Session = Depends(get_db)) -> dict:
    site = db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail=_SITE_NOT_FOUND)
    delete_site(db, site=site)
    return {"status": "ok"}
