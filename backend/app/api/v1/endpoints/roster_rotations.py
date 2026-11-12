"""Roster rotation patterns."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select

from app.api import deps
from app.api.v1.endpoints.hr import log_audit
from app.models.user import User
from app.schemas.roster import (
    RosterBulkResult,
    RotationPatternCreate, RotationPatternUpdate, RotationPatternRead,
    RotationApplyRequest,
)
from app.models.rotation_pattern import RotationPattern
from app.services import roster as roster_svc

from app.api.v1.endpoints.roster_common import (
    require_admin, commit_or_409,
    validate_templates, write_cells,
)

router = APIRouter()


# ----------------------------- rotation patterns -----------------------------

async def _validate_cycle(db, cycle) -> None:
    await validate_templates(db, cycle)



async def _check_name(db, name: str, exclude_id: Optional[int] = None) -> None:
    q = select(RotationPattern).where(RotationPattern.name == name)
    if exclude_id is not None:
        q = q.where(RotationPattern.id != exclude_id)
    other = (await db.execute(q)).scalars().first()
    if other is not None:
        msg = "Pattern name already exists"
        if not other.is_active:
            msg += " (inactive) \u2014 reactivate it instead"
        raise HTTPException(status_code=409, detail=msg)


@router.get("/rotations", response_model=List[RotationPatternRead])
async def list_rotations(
    db: deps.DBDep,
    include_inactive: bool = Query(False),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    admin = roster_svc.is_roster_admin(current_user)
    if not admin and not await roster_svc.scoped_employees(db, current_user):
        raise HTTPException(status_code=403, detail="You have no roster scope.")
    q = select(RotationPattern).order_by(RotationPattern.name)
    if not (admin and include_inactive):
        q = q.where(RotationPattern.is_active.is_(True))
    return list((await db.execute(q)).scalars().all())


@router.post("/rotations", response_model=RotationPatternRead)
async def create_rotation(
    *,
    db: deps.DBDep,
    request: Request,
    body: RotationPatternCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    require_admin(current_user)
    await _validate_cycle(db, body.cycle)
    await _check_name(db, body.name)
    p = RotationPattern(
        name=body.name, description=body.description,
        cycle=list(body.cycle), created_by_id=current_user.id,
    )
    db.add(p)
    await commit_or_409(db, "Rotation name already exists")
    await db.refresh(p)
    await log_audit(
        db, current_user.id, "roster.rotation.create",
        "rotation_pattern", str(p.id), {"name": p.name}, request,
    )
    return p


@router.patch("/rotations/{rotation_id}", response_model=RotationPatternRead)
async def update_rotation(
    *,
    db: deps.DBDep,
    request: Request,
    rotation_id: int,
    body: RotationPatternUpdate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    require_admin(current_user)
    p = await db.get(RotationPattern, rotation_id)
    if not p:
        raise HTTPException(status_code=404, detail="Rotation pattern not found")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("name") is None:
        changes.pop("name", None)
    if changes.get("cycle") is None:
        changes.pop("cycle", None)
    if changes.get("is_active") is None:
        changes.pop("is_active", None)
    if "cycle" in changes:
        await _validate_cycle(db, changes["cycle"])
    if "name" in changes:
        await _check_name(db, changes["name"], p.id)
    if changes.get("is_active") is True and "cycle" not in changes:
        await _validate_cycle(db, p.cycle)
    for k, v in changes.items():
        setattr(p, k, v)
    await commit_or_409(db, "Rotation name already exists")
    await db.refresh(p)
    await log_audit(
        db, current_user.id, "roster.rotation.update",
        "rotation_pattern", str(p.id), {"changed": list(changes.keys())}, request,
    )
    return p


@router.delete("/rotations/{rotation_id}")
async def delete_rotation(
    *,
    db: deps.DBDep,
    request: Request,
    rotation_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    require_admin(current_user)
    p = await db.get(RotationPattern, rotation_id)
    if not p:
        raise HTTPException(status_code=404, detail="Rotation pattern not found")
    p.is_active = False
    await db.commit()
    await log_audit(
        db, current_user.id, "roster.rotation.delete",
        "rotation_pattern", str(p.id), {}, request,
    )
    return {"status": "deactivated", "id": rotation_id}



@router.post("/rotations/{rotation_id}/apply", response_model=RosterBulkResult)
async def apply_rotation(
    *,
    db: deps.DBDep,
    request: Request,
    rotation_id: int,
    body: RotationApplyRequest,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    p = await db.get(RotationPattern, rotation_id)
    if not p:
        raise HTTPException(status_code=404, detail="Rotation pattern not found")
    if not p.is_active:
        raise HTTPException(status_code=409, detail="Rotation pattern is inactive")
    if not roster_svc.is_roster_admin(current_user) and not (
        await roster_svc.scoped_employees(db, current_user)
    ):
        raise HTTPException(status_code=403, detail="You have no roster scope.")
    await _validate_cycle(db, p.cycle)
    result = RosterBulkResult()
    if body.employee_ids is not None:
        target_ids = set(body.employee_ids)
    else:
        emps = await roster_svc.scoped_employees(
            db, current_user, body.department
        )
        target_ids = {e.user_id for e in emps}
    allowed = await roster_svc.manageable_subset(db, current_user, target_ids)
    result.out_of_scope.extend(sorted(target_ids - allowed))
    if allowed:
        offsets = body.offsets or {}
        cells = []
        for uid in sorted(allowed):
            for (wd, tpl_id, wo) in roster_svc.expand_rotation(
                p.cycle, body.anchor, body.start, body.end,
                offsets.get(uid, body.default_offset),
            ):
                cells.append((uid, wd, tpl_id, wo))
        await write_cells(
            db, current_user, allowed, cells, body.status, body.overwrite,
            result,
        )
        await commit_or_409(db)
    if not (result.created or result.updated):
        return result
    await log_audit(
        db, current_user.id, "roster.rotation.apply",
        "rotation_pattern", str(p.id),
        {
            "created": result.created, "updated": result.updated,
            "skipped": result.skipped,
            "out_of_scope": len(result.out_of_scope),
            "start": body.start.isoformat(), "end": body.end.isoformat(),
            "status": body.status,
        },
        request,
    )
    return result


