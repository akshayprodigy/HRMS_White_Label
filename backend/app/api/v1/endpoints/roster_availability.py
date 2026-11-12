"""Employee availability & shift preferences."""
from datetime import date as pydate
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.api import deps
from app.api.v1.endpoints.roster_common import (
    check_window, commit_or_409, guard_conflicts, lock_user_rows,
    validate_templates,
)
from app.models.availability import EmployeeAvailability
from app.models.user import User
from app.schemas.availability import (
    AvailabilityCreate, AvailabilityRead, AvailabilityUpdate,
)
from app.schemas.roster import IntId
from app.services import roster as roster_svc

router = APIRouter()

MAX_RULES = 50


def _validate(kind, weekday, specific_date, tpl, vfrom, vto) -> None:
    if (weekday is None) == (specific_date is None):
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of weekday or specific_date")
    if specific_date is not None and (vfrom or vto):
        raise HTTPException(
            status_code=422,
            detail="valid_from/valid_to apply to weekday rules only")
    if vfrom and vto and vfrom > vto:
        raise HTTPException(
            status_code=422, detail="valid_from must be <= valid_to")
    if kind == "preferred" and tpl is None:
        raise HTTPException(
            status_code=422, detail="A preferred rule needs a shift template")


@router.get("/availability/my", response_model=List[AvailabilityRead])
async def list_my(
    db: deps.DBDep, current_user: User = Depends(deps.get_current_user),
) -> Any:
    rows = (await db.execute(
        select(EmployeeAvailability)
        .where(EmployeeAvailability.user_id == current_user.id)
        .order_by(EmployeeAvailability.id))).scalars().all()
    return rows


@router.post("/availability/my", response_model=AvailabilityRead)
@guard_conflicts
async def create_my(
    body: AvailabilityCreate, *, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _validate(body.kind, body.weekday, body.specific_date,
              body.shift_template_id, body.valid_from, body.valid_to)
    await validate_templates(db, [body.shift_template_id])
    # Serialize concurrent creates for this user; the reads below must be
    # locking reads because the REPEATABLE READ snapshot predates the lock.
    await lock_user_rows(db, [current_user.id])
    count = len((await db.execute(
        select(EmployeeAvailability.id).where(
            EmployeeAvailability.user_id == current_user.id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().all())
    if count >= MAX_RULES:
        raise HTTPException(
            status_code=400,
            detail=f"At most {MAX_RULES} availability rules per employee")
    await _check_duplicate(
        db, current_user.id, body.kind, body.weekday, body.specific_date,
        body.shift_template_id, body.valid_from, body.valid_to, lock=True)
    row = EmployeeAvailability(user_id=current_user.id, **body.model_dump())
    db.add(row)
    await commit_or_409(db)
    await db.refresh(row)
    return row


async def _check_duplicate(
    db, user_id, kind, weekday, specific_date, tpl, vfrom, vto,
    exclude_id: Optional[int] = None, lock: bool = False,
) -> None:
    def eq(col, v):
        return col.is_(None) if v is None else col == v
    q = select(EmployeeAvailability.id).where(
        EmployeeAvailability.user_id == user_id,
        EmployeeAvailability.kind == kind,
        eq(EmployeeAvailability.weekday, weekday),
        eq(EmployeeAvailability.specific_date, specific_date),
        eq(EmployeeAvailability.shift_template_id, tpl),
        eq(EmployeeAvailability.valid_from, vfrom),
        eq(EmployeeAvailability.valid_to, vto),
    )
    if exclude_id is not None:
        q = q.where(EmployeeAvailability.id != exclude_id)
    if lock:
        q = q.with_for_update().execution_options(populate_existing=True)
    if (await db.execute(q)).first() is not None:
        raise HTTPException(status_code=409, detail="This rule already exists")


async def _own(db, rule_id: int, user: User) -> EmployeeAvailability:
    row = (await db.execute(
        select(EmployeeAvailability).where(
            EmployeeAvailability.id == rule_id,
            EmployeeAvailability.user_id == user.id))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return row


@router.patch("/availability/my/{rule_id}", response_model=AvailabilityRead)
@guard_conflicts
async def update_my(
    rule_id: IntId, body: AvailabilityUpdate, *, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    row = await _own(db, rule_id, current_user)
    data = body.model_dump(exclude_unset=True)
    # Switching between weekday / one-off: setting one clears the other
    # unless the caller set both explicitly.
    if data.get("weekday") is not None and "specific_date" not in data:
        data["specific_date"] = None
    if data.get("specific_date") is not None and "weekday" not in data:
        data["weekday"] = None
        data.setdefault("valid_from", None)
        data.setdefault("valid_to", None)
    if data.get("kind") is None:
        data.pop("kind", None)
    merged = {
        k: data.get(k, getattr(row, k))
        for k in ("kind", "weekday", "specific_date", "shift_template_id",
                  "valid_from", "valid_to")
    }
    _validate(**{("tpl" if k == "shift_template_id" else
                  "vfrom" if k == "valid_from" else
                  "vto" if k == "valid_to" else k): v
                 for k, v in merged.items()})
    await _check_duplicate(
        db, row.user_id, merged["kind"], merged["weekday"],
        merged["specific_date"], merged["shift_template_id"],
        merged["valid_from"], merged["valid_to"], exclude_id=row.id)
    if "shift_template_id" in data:
        await validate_templates(db, [data["shift_template_id"]])
    for k, v in data.items():
        setattr(row, k, v)
    await commit_or_409(db)
    await db.refresh(row)
    return row


@router.delete("/availability/my/{rule_id}")
@guard_conflicts
async def delete_my(
    rule_id: IntId, *, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    row = await _own(db, rule_id, current_user)
    await db.delete(row)
    await commit_or_409(db)
    return {"ok": True}


@router.get("/availability", response_model=List[AvailabilityRead])
async def list_scoped(
    db: deps.DBDep,
    start: pydate = Query(...),
    end: pydate = Query(...),
    department: Optional[str] = None,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Raw rules of employees the caller may manage. start/end bound the
    window (<= 62 days) and filter out rules that cannot apply in it."""
    check_window(start, end)
    scoped = await roster_svc.scoped_employees(db, current_user)
    if not scoped and not roster_svc.is_roster_admin(current_user):
        raise HTTPException(status_code=403, detail="You have no roster scope.")
    if department:
        scoped = [e for e in scoped if e.department == department]
    ids = await roster_svc.manageable_subset(
        db, current_user, {e.user_id for e in scoped})
    names = {e.user_id: (e.user.full_name if e.user else None) for e in scoped}
    if not ids:
        return []
    rows = (await db.execute(
        select(EmployeeAvailability)
        .where(EmployeeAvailability.user_id.in_(ids))
        .order_by(EmployeeAvailability.user_id, EmployeeAvailability.id)
    )).scalars().all()
    out = []
    for r in rows:
        if r.specific_date is not None and not (start <= r.specific_date <= end):
            continue
        if r.valid_from is not None and r.valid_from > end:
            continue
        if r.valid_to is not None and r.valid_to < start:
            continue
        item = AvailabilityRead.model_validate(r)
        item.employee_name = names.get(r.user_id)
        out.append(item)
    return out
