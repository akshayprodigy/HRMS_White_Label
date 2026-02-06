from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.db.models.core import Project
from app.modules.core.schemas import (
    ProjectCreate,
    ProjectPublic,
    ProjectUpdate,
)
from app.modules.core.service import (
    create_project,
    delete_project,
    list_projects,
    update_project,
)

router = APIRouter(prefix="/projects")

_PROJECT_NOT_FOUND = "Project not found"


@router.get(
    "",
    response_model=list[ProjectPublic],
    dependencies=[Depends(require_permissions({"core.projects.read"}))],
)
def core_list_projects(db: Session = Depends(get_db)) -> list[ProjectPublic]:
    return [ProjectPublic.model_validate(p) for p in list_projects(db)]


@router.post(
    "",
    response_model=ProjectPublic,
    dependencies=[Depends(require_permissions({"core.projects.write"}))],
)
def core_create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
) -> ProjectPublic:
    project = create_project(
        db,
        organization_id=payload.organization_id,
        site_id=payload.site_id,
        code=payload.code,
        name=payload.name,
        is_active=payload.is_active,
    )
    return ProjectPublic.model_validate(project)


@router.get(
    "/{project_id}",
    response_model=ProjectPublic,
    dependencies=[Depends(require_permissions({"core.projects.read"}))],
)
def core_get_project(
    project_id: int,
    db: Session = Depends(get_db),
) -> ProjectPublic:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=_PROJECT_NOT_FOUND)
    return ProjectPublic.model_validate(project)


@router.put(
    "/{project_id}",
    response_model=ProjectPublic,
    dependencies=[Depends(require_permissions({"core.projects.write"}))],
)
def core_update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
) -> ProjectPublic:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=_PROJECT_NOT_FOUND)

    updated = update_project(
        db,
        project=project,
        organization_id=payload.organization_id,
        site_id=payload.site_id,
        code=payload.code,
        name=payload.name,
        is_active=payload.is_active,
    )
    return ProjectPublic.model_validate(updated)


@router.delete(
    "/{project_id}",
    dependencies=[Depends(require_permissions({"core.projects.write"}))],
)
def core_delete_project(
    project_id: int,
    db: Session = Depends(get_db),
) -> dict:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=_PROJECT_NOT_FOUND)
    delete_project(db, project=project)
    return {"status": "ok"}
