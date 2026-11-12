"""Scheduling delegation API (Roadmap v2 Phase 1A), mounted at
/roster/delegations. HR / roster admins grant any employee scheduling rights
over a scope; `GET /my` is open to every user."""
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select

from app.api import deps
from app.api.v1.endpoints.hr import log_audit
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.schedule_delegation import DelegationScope, ScheduleDelegation
from app.models.user import User
from app.schemas.schedule_delegation import (
    DelegationCreate, DelegationPreviewRow, DelegationRead, DelegationUpdate,
)
from app.api.v1.endpoints.roster_common import names, require_admin
from app.services import roster as roster_svc

logger = logging.getLogger(__name__)
router = APIRouter()


async def _to_reads(db, rows: List[ScheduleDelegation]) -> List[DelegationRead]:
    nm = await names(
        db, [d.grantee_id for d in rows] + [d.granted_by_id for d in rows]
    )
    out = []
    for d in rows:
        r = DelegationRead.model_validate(d)
        r.employee_ids = list(d.employee_ids or [])
        r.grantee_name = nm.get(d.grantee_id)
        r.granted_by_name = nm.get(d.granted_by_id)
        r.covered_count = len(await roster_svc.delegation_user_ids(db, d))
        out.append(r)
    return out


async def _validate_scope(
    db, scope_type: str, scope_value: Optional[str], employee_ids: List[int],
) -> None:
    if scope_type not in DelegationScope.ALL:
        raise HTTPException(status_code=422, detail="Invalid scope_type.")
    if scope_type != DelegationScope.EMPLOYEES and employee_ids:
        raise HTTPException(
            status_code=422,
            detail="employee_ids is only allowed for employees scope.",
        )
    if scope_type == DelegationScope.EMPLOYEES:
        if scope_value is not None:
            raise HTTPException(
                status_code=422,
                detail="scope_value must be empty for employees scope.",
            )
        ids = set(employee_ids or [])
        if not ids:
            raise HTTPException(status_code=422, detail="employee_ids is required.")
        found = set((await db.execute(
            select(User.id).where(User.id.in_(ids))
        )).scalars().all())
        if found != ids:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown employee ids: {sorted(ids - found)}",
            )
    elif scope_type == DelegationScope.DEPARTMENT:
        ok = scope_value and (await db.execute(
            select(Department.id).where(Department.name == scope_value)
        )).first()
        if not ok:
            raise HTTPException(status_code=422, detail="Unknown department.")
    elif scope_type == DelegationScope.LOCATION:
        ok = scope_value and (await db.execute(
            select(Employee.id).where(Employee.location == scope_value).limit(1)
        )).first()
        if not ok:
            raise HTTPException(status_code=422, detail="Unknown location.")
    elif scope_value is not None:
        raise HTTPException(
            status_code=422, detail="scope_value must be empty for team scope.",
        )


@router.get("", response_model=List[DelegationRead])
@router.get("/", response_model=List[DelegationRead], include_in_schema=False)
async def list_delegations(
    db: deps.DBDep,
    include_inactive: bool = Query(False),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    require_admin(current_user)
    q = select(ScheduleDelegation).order_by(ScheduleDelegation.id.desc())
    if not include_inactive:
        today = datetime.now(timezone.utc).date()
        q = q.where(
            ScheduleDelegation.revoked_at.is_(None),
            or_(ScheduleDelegation.valid_to.is_(None),
                ScheduleDelegation.valid_to >= today),
        )
    rows = list((await db.execute(q)).scalars().all())
    return await _to_reads(db, rows)


@router.post("", response_model=DelegationRead)
@router.post("/", response_model=DelegationRead, include_in_schema=False)
async def create_delegation(
    *,
    db: deps.DBDep,
    request: Request,
    body: DelegationCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    require_admin(current_user)
    grantee = await db.get(User, body.grantee_id)
    if grantee is None or not grantee.is_active:
        raise HTTPException(status_code=422, detail="Grantee must be an active user.")
    if body.valid_to is not None and body.valid_to < body.valid_from:
        raise HTTPException(status_code=422, detail="valid_to must be >= valid_from.")
    await _validate_scope(db, body.scope_type, body.scope_value, body.employee_ids)
    d = ScheduleDelegation(
        grantee_id=body.grantee_id,
        scope_type=body.scope_type,
        scope_value=body.scope_value,
        employee_ids=(
            sorted(set(body.employee_ids))
            if body.scope_type == DelegationScope.EMPLOYEES else []
        ),
        can_publish=body.can_publish,
        can_approve_changes=body.can_approve_changes,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        granted_by_id=current_user.id,
        note=body.note,
    )
    db.add(d)
    await db.flush()
    await roster_svc.notify(
        db, d.grantee_id, "Scheduling rights granted",
        f"You have been given scheduling rights ({d.scope_type}"
        f"{': ' + d.scope_value if d.scope_value else ''}) from "
        f"{d.valid_from.isoformat()}.",
        "schedule_delegation", str(d.id),
    )
    await db.commit()
    await db.refresh(d)
    await log_audit(
        db, current_user.id, "schedule_delegation.grant",
        "schedule_delegation", str(d.id),
        {"grantee_id": d.grantee_id, "scope_type": d.scope_type,
         "scope_value": d.scope_value}, request,
    )
    return (await _to_reads(db, [d]))[0]


@router.get("/my", response_model=List[DelegationRead])
async def my_delegations(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    rows = await roster_svc.active_delegations(db, current_user)
    return await _to_reads(db, rows)


@router.get("/preview", response_model=List[DelegationPreviewRow])
async def preview_scope(
    db: deps.DBDep,
    scope_type: str = Query(...),
    scope_value: Optional[str] = Query(None),
    employee_ids: List[int] = Query(default_factory=list),
    grantee_id: Optional[int] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    require_admin(current_user)
    if scope_type not in DelegationScope.ALL:
        raise HTTPException(status_code=422, detail="Invalid scope_type.")
    ids = await roster_svc.resolve_scope_user_ids(
        db, scope_type, scope_value, employee_ids, grantee_id
    )
    if not ids:
        return []
    users = (await db.execute(
        select(User).where(User.id.in_(ids)).order_by(User.full_name)
    )).scalars().all()
    dept = dict((await db.execute(
        select(Employee.user_id, Employee.department)
        .where(Employee.user_id.in_(ids))
    )).all())
    return [
        DelegationPreviewRow(
            user_id=u.id, full_name=u.full_name or u.email,
            department=dept.get(u.id),
        ) for u in users
    ]


@router.patch("/{deleg_id}", response_model=DelegationRead)
async def update_delegation(
    *,
    db: deps.DBDep,
    request: Request,
    deleg_id: int,
    body: DelegationUpdate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    require_admin(current_user)
    d = await db.get(ScheduleDelegation, deleg_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Delegation not found")
    if d.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Delegation is revoked")
    changes = body.model_dump(exclude_unset=True)
    for nn in ("can_publish", "can_approve_changes", "valid_from"):
        if nn in changes and changes[nn] is None:
            raise HTTPException(status_code=422, detail=f"{nn} cannot be null.")
    vf = changes.get("valid_from", d.valid_from)
    vt = changes.get("valid_to", d.valid_to)
    if vt is not None and vt < vf:
        raise HTTPException(status_code=422, detail="valid_to must be >= valid_from.")
    for k, v in changes.items():
        setattr(d, k, v)
    await db.commit()
    await db.refresh(d)
    await log_audit(
        db, current_user.id, "schedule_delegation.update",
        "schedule_delegation", str(d.id),
        {"changed": list(changes.keys())}, request,
    )
    return (await _to_reads(db, [d]))[0]


@router.post("/{deleg_id}/revoke", response_model=DelegationRead)
async def revoke_delegation(
    *,
    db: deps.DBDep,
    request: Request,
    deleg_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    require_admin(current_user)
    d = await db.get(ScheduleDelegation, deleg_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Delegation not found")
    if d.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Delegation already revoked.")
    d.revoked_at = datetime.now(timezone.utc)
    await roster_svc.notify(
        db, d.grantee_id, "Scheduling rights revoked",
        "Your delegated scheduling rights have been revoked.",
        "schedule_delegation", str(d.id),
    )
    await db.commit()
    await db.refresh(d)
    await log_audit(
        db, current_user.id, "schedule_delegation.revoke",
        "schedule_delegation", str(d.id), {}, request,
    )
    return (await _to_reads(db, [d]))[0]
