from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.db.models.core import Organization
from app.modules.core.schemas import (
    OrganizationCreate,
    OrganizationPublic,
    OrganizationUpdate,
)
from app.modules.core.service import (
    create_organization,
    delete_organization,
    list_organizations,
    update_organization,
)

router = APIRouter(prefix="/organizations")

_ORG_NOT_FOUND = "Organization not found"


@router.get(
    "",
    response_model=list[OrganizationPublic],
    dependencies=[Depends(require_permissions({"core.organizations.read"}))],
)
def core_list_organizations(
    db: Session = Depends(get_db),
) -> list[OrganizationPublic]:
    return [OrganizationPublic.model_validate(o) for o in list_organizations(db)]


@router.post(
    "",
    response_model=OrganizationPublic,
    dependencies=[Depends(require_permissions({"core.organizations.write"}))],
)
def core_create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
) -> OrganizationPublic:
    org = create_organization(
        db,
        code=payload.code,
        name=payload.name,
        is_active=payload.is_active,
    )
    return OrganizationPublic.model_validate(org)


@router.get(
    "/{org_id}",
    response_model=OrganizationPublic,
    dependencies=[Depends(require_permissions({"core.organizations.read"}))],
)
def core_get_organization(
    org_id: int,
    db: Session = Depends(get_db),
) -> OrganizationPublic:
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail=_ORG_NOT_FOUND)
    return OrganizationPublic.model_validate(org)


@router.put(
    "/{org_id}",
    response_model=OrganizationPublic,
    dependencies=[Depends(require_permissions({"core.organizations.write"}))],
)
def core_update_organization(
    org_id: int,
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
) -> OrganizationPublic:
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail=_ORG_NOT_FOUND)

    updated = update_organization(
        db,
        org=org,
        code=payload.code,
        name=payload.name,
        is_active=payload.is_active,
    )
    return OrganizationPublic.model_validate(updated)


@router.delete(
    "/{org_id}",
    dependencies=[Depends(require_permissions({"core.organizations.write"}))],
)
def core_delete_organization(
    org_id: int,
    db: Session = Depends(get_db),
) -> dict:
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail=_ORG_NOT_FOUND)
    delete_organization(db, org=org)
    return {"status": "ok"}
