from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import log_audit, model_to_dict
from app.db.models.core import CostCenter, Organization, Project, Site

_ERR_ORG_NOT_FOUND = "Organization not found"


def list_organizations(db: Session) -> list[Organization]:
    return list(db.execute(select(Organization).order_by(Organization.id.desc())).scalars().all())


def create_organization(
    db: Session,
    *,
    code: str,
    name: str,
    is_active: bool,
) -> Organization:
    existing = db.execute(
        select(Organization).where((Organization.code == code) | (Organization.name == name))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Organization already exists",
        )

    org = Organization(code=code, name=name, is_active=is_active)
    db.add(org)
    db.commit()
    db.refresh(org)

    log_audit(
        db,
        entity_type="organizations",
        entity_id=str(org.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(org),
    )
    return org


def update_organization(
    db: Session,
    *,
    org: Organization,
    code: str | None,
    name: str | None,
    is_active: bool | None,
) -> Organization:
    before = model_to_dict(org)
    if code and code != org.code:
        existing = db.execute(
            select(Organization).where(Organization.code == code)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Organization code exists",
            )
        org.code = code

    if name and name != org.name:
        existing = db.execute(
            select(Organization).where(Organization.name == name)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Organization name exists",
            )
        org.name = name

    if is_active is not None:
        org.is_active = is_active

    db.add(org)
    db.commit()
    db.refresh(org)

    log_audit(
        db,
        entity_type="organizations",
        entity_id=str(org.id),
        action="update",
        before_json=before,
        after_json=model_to_dict(org),
    )
    return org


def delete_organization(db: Session, *, org: Organization) -> None:
    before = model_to_dict(org)
    db.delete(org)
    db.commit()

    log_audit(
        db,
        entity_type="organizations",
        entity_id=str(org.id),
        action="delete",
        before_json=before,
        after_json=None,
    )


def list_sites(db: Session) -> list[Site]:
    return list(db.execute(select(Site).order_by(Site.id.desc())).scalars().all())


def create_site(
    db: Session,
    *,
    organization_id: int,
    code: str,
    name: str,
    is_active: bool,
) -> Site:
    if not db.get(Organization, organization_id):
        raise HTTPException(status_code=400, detail=_ERR_ORG_NOT_FOUND)

    existing = db.execute(
        select(Site).where(
            Site.organization_id == organization_id,
            Site.code == code,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Site code exists")

    site = Site(
        organization_id=organization_id,
        code=code,
        name=name,
        is_active=is_active,
    )
    db.add(site)
    db.commit()
    db.refresh(site)

    log_audit(
        db,
        entity_type="sites",
        entity_id=str(site.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(site),
    )
    return site


def update_site(
    db: Session,
    *,
    site: Site,
    organization_id: int | None,
    code: str | None,
    name: str | None,
    is_active: bool | None,
) -> Site:
    before = model_to_dict(site)
    new_org_id = organization_id if organization_id is not None else site.organization_id
    new_code = code if code is not None else site.code

    if new_org_id != site.organization_id and not db.get(Organization, new_org_id):
        raise HTTPException(status_code=400, detail=_ERR_ORG_NOT_FOUND)

    if (new_org_id != site.organization_id) or (new_code != site.code):
        existing = db.execute(
            select(Site).where(
                Site.organization_id == new_org_id,
                Site.code == new_code,
                Site.id != site.id,
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Site code exists")

    site.organization_id = new_org_id
    site.code = new_code

    if name is not None:
        site.name = name
    if is_active is not None:
        site.is_active = is_active

    db.add(site)
    db.commit()
    db.refresh(site)

    log_audit(
        db,
        entity_type="sites",
        entity_id=str(site.id),
        action="update",
        before_json=before,
        after_json=model_to_dict(site),
    )
    return site


def delete_site(db: Session, *, site: Site) -> None:
    before = model_to_dict(site)
    db.delete(site)
    db.commit()

    log_audit(
        db,
        entity_type="sites",
        entity_id=str(site.id),
        action="delete",
        before_json=before,
        after_json=None,
    )


def list_projects(db: Session) -> list[Project]:
    return list(db.execute(select(Project).order_by(Project.id.desc())).scalars().all())


def create_project(
    db: Session,
    *,
    organization_id: int,
    site_id: int | None,
    code: str,
    name: str,
    is_active: bool,
) -> Project:
    if not db.get(Organization, organization_id):
        raise HTTPException(status_code=400, detail=_ERR_ORG_NOT_FOUND)

    if site_id is not None:
        site = db.get(Site, site_id)
        if not site or site.organization_id != organization_id:
            raise HTTPException(status_code=400, detail="Invalid site")

    existing = db.execute(
        select(Project).where(
            Project.organization_id == organization_id,
            Project.code == code,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Project code exists")

    project = Project(
        organization_id=organization_id,
        site_id=site_id,
        code=code,
        name=name,
        is_active=is_active,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    log_audit(
        db,
        entity_type="projects",
        entity_id=str(project.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(project),
    )
    return project


def update_project(
    db: Session,
    *,
    project: Project,
    organization_id: int | None,
    site_id: int | None,
    code: str | None,
    name: str | None,
    is_active: bool | None,
) -> Project:
    before = model_to_dict(project)
    new_org_id = organization_id if organization_id is not None else project.organization_id
    new_code = code if code is not None else project.code

    if new_org_id != project.organization_id and not db.get(Organization, new_org_id):
        raise HTTPException(status_code=400, detail=_ERR_ORG_NOT_FOUND)

    if (new_org_id != project.organization_id) or (new_code != project.code):
        existing = db.execute(
            select(Project).where(
                Project.organization_id == new_org_id,
                Project.code == new_code,
                Project.id != project.id,
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Project code exists")

    new_site_id = site_id if site_id is not None else project.site_id
    if new_site_id is not None:
        site = db.get(Site, new_site_id)
        if not site or site.organization_id != new_org_id:
            raise HTTPException(status_code=400, detail="Invalid site")

    project.organization_id = new_org_id
    project.code = new_code
    project.site_id = new_site_id

    if name is not None:
        project.name = name
    if is_active is not None:
        project.is_active = is_active

    db.add(project)
    db.commit()
    db.refresh(project)

    log_audit(
        db,
        entity_type="projects",
        entity_id=str(project.id),
        action="update",
        before_json=before,
        after_json=model_to_dict(project),
    )
    return project


def delete_project(db: Session, *, project: Project) -> None:
    before = model_to_dict(project)
    db.delete(project)
    db.commit()

    log_audit(
        db,
        entity_type="projects",
        entity_id=str(project.id),
        action="delete",
        before_json=before,
        after_json=None,
    )


def list_cost_centers(db: Session) -> list[CostCenter]:
    return list(db.execute(select(CostCenter).order_by(CostCenter.id.desc())).scalars().all())


def create_cost_center(
    db: Session,
    *,
    organization_id: int,
    code: str,
    name: str,
    is_active: bool,
) -> CostCenter:
    if not db.get(Organization, organization_id):
        raise HTTPException(status_code=400, detail=_ERR_ORG_NOT_FOUND)

    existing = db.execute(
        select(CostCenter).where(
            CostCenter.organization_id == organization_id,
            CostCenter.code == code,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Cost center code exists")

    cc = CostCenter(
        organization_id=organization_id,
        code=code,
        name=name,
        is_active=is_active,
    )
    db.add(cc)
    db.commit()
    db.refresh(cc)

    log_audit(
        db,
        entity_type="cost_centers",
        entity_id=str(cc.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(cc),
    )
    return cc


def update_cost_center(
    db: Session,
    *,
    cost_center: CostCenter,
    organization_id: int | None,
    code: str | None,
    name: str | None,
    is_active: bool | None,
) -> CostCenter:
    before = model_to_dict(cost_center)
    new_org_id = organization_id if organization_id is not None else cost_center.organization_id
    new_code = code if code is not None else cost_center.code

    if new_org_id != cost_center.organization_id and not db.get(Organization, new_org_id):
        raise HTTPException(status_code=400, detail=_ERR_ORG_NOT_FOUND)

    if (new_org_id != cost_center.organization_id) or (new_code != cost_center.code):
        existing = db.execute(
            select(CostCenter).where(
                CostCenter.organization_id == new_org_id,
                CostCenter.code == new_code,
                CostCenter.id != cost_center.id,
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Cost center code exists",
            )

    cost_center.organization_id = new_org_id
    cost_center.code = new_code

    if name is not None:
        cost_center.name = name
    if is_active is not None:
        cost_center.is_active = is_active

    db.add(cost_center)
    db.commit()
    db.refresh(cost_center)

    log_audit(
        db,
        entity_type="cost_centers",
        entity_id=str(cost_center.id),
        action="update",
        before_json=before,
        after_json=model_to_dict(cost_center),
    )
    return cost_center


def delete_cost_center(db: Session, *, cost_center: CostCenter) -> None:
    before = model_to_dict(cost_center)
    db.delete(cost_center)
    db.commit()

    log_audit(
        db,
        entity_type="cost_centers",
        entity_id=str(cost_center.id),
        action="delete",
        before_json=before,
        after_json=None,
    )
