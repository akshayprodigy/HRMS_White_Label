"""Asset maintenance log (Roadmap v2 Phase 5, Task 5). Mounted at /assets
AFTER the register router so its static paths (by-tag, summary) win; nothing
there shadows the two-segment /maintenance/{mid}. Every route needs 'asset manage'.

Writes: lock asset row -> maintenance row -> service call -> commit_or_409
once. Audit rows are added with db.add (never hr.log_audit: it commits)."""
from datetime import date
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from app.api import deps
from app.api.v1.endpoints.roster_common import commit_or_409, guard_conflicts
from app.models.asset import Asset, AssetMaintenance, AssetStatus
from app.models.audit import AuditLog
from app.services import assets as svc

PERM_ASSET = "asset manage"
router = APIRouter(dependencies=[Depends(deps.check_permissions([PERM_ASSET]))])

Kind = Literal["repair", "service", "amc_visit", "upgrade"]


def _nonblank(v):
    if v is None:
        return v
    v = v.strip()
    if not v:
        raise ValueError("must not be blank")
    return v


class MaintenanceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Kind
    description: str = Field(min_length=1)
    vendor: Optional[str] = Field(default=None, max_length=150)
    cost_paise: int = Field(default=0, ge=0)
    started_on: date
    completed_on: Optional[date] = None
    move_to_repair: bool = False

    _strip = field_validator("description")(_nonblank)
    _vendor = field_validator("vendor")(lambda v: (v or "").strip() or None)


class MaintenancePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Optional[Kind] = None
    description: Optional[str] = Field(default=None, min_length=1)
    vendor: Optional[str] = Field(default=None, max_length=150)
    cost_paise: Optional[int] = Field(default=None, ge=0)
    started_on: Optional[date] = None
    completed_on: Optional[date] = None
    complete: bool = False
    return_to_stock: bool = True

    _strip = field_validator("description")(_nonblank)
    _vendor = field_validator("vendor")(lambda v: (v or "").strip() or None)


def _out(m: AssetMaintenance) -> dict:
    return {
        "id": m.id, "asset_id": m.asset_id, "kind": m.kind,
        "description": m.description, "vendor": m.vendor,
        "cost_paise": m.cost_paise,
        "started_on": m.started_on.isoformat() if m.started_on else None,
        "completed_on": m.completed_on.isoformat() if m.completed_on else None,
    }


def _audit(db, actor, action: str, asset_id: int, details: dict) -> None:
    db.add(AuditLog(user_id=actor.id, action=action, resource_type="asset",
                    resource_id=str(asset_id), details=details))


def _check_dates(started: date, completed: Optional[date],
                 check_future: bool = True) -> None:
    if check_future and started > date.today():
        raise HTTPException(422, "Start date cannot be in the future")
    if completed is not None and completed < started:
        raise HTTPException(422, "Completion date cannot be before start date")
    if completed is not None and completed > date.today():
        raise HTTPException(422, "Completion date cannot be in the future")


async def _lock_asset(db, asset_id: int) -> Asset:
    try:
        return await svc.get_asset_for_update(db, asset_id)
    except LookupError:
        raise HTTPException(404, "Asset not found")


async def _lock_entry(db, mid: int):
    """Asset row first (via entry.asset_id), then the maintenance row."""
    asset_id = (await db.execute(select(AssetMaintenance.asset_id).where(
        AssetMaintenance.id == mid))).scalar()
    if asset_id is None:
        raise HTTPException(404, "Maintenance entry not found")
    asset = await _lock_asset(db, asset_id)
    m = (await db.execute(
        select(AssetMaintenance).where(AssetMaintenance.id == mid)
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().first()
    if m is None or m.asset_id != asset.id:
        await db.rollback()
        raise HTTPException(404, "Maintenance entry not found")
    return asset, m


async def _return_if_no_open_repair(db, a, m, actor, remarks: str) -> bool:
    """Asset back to stock when it is in_repair and no OTHER open repair
    remains. Locking read: every inserter holds the asset row lock first."""
    if a.status != AssetStatus.IN_REPAIR:
        return False
    other = (await db.execute(
        select(AssetMaintenance.id).where(
            AssetMaintenance.asset_id == a.id,
            AssetMaintenance.kind == "repair",
            AssetMaintenance.completed_on.is_(None),
            AssetMaintenance.id != m.id).limit(1).with_for_update()
    )).first()
    if other is not None:
        return False
    try:
        await svc.set_status(db, asset=a, actor=actor,
                             to_status=AssetStatus.IN_STOCK, remarks=remarks)
    except svc.AssetStateError as e:
        await db.rollback()
        raise HTTPException(409, str(e))
    return True


@router.get("/{asset_id}/maintenance")
async def list_maintenance(db: deps.DBDep, asset_id: int) -> Any:
    if (await db.execute(select(Asset.id).where(
            Asset.id == asset_id))).first() is None:
        raise HTTPException(404, "Asset not found")
    rows = (await db.execute(
        select(AssetMaintenance).where(AssetMaintenance.asset_id == asset_id)
        .order_by(AssetMaintenance.started_on.desc(),
                  AssetMaintenance.id.desc()))).scalars().all()
    return [_out(m) for m in rows]


@router.post("/{asset_id}/maintenance")
@guard_conflicts
async def add_maintenance(db: deps.DBDep, current_user: deps.CurrentUser,
                          asset_id: int, body: MaintenanceIn) -> Any:
    _check_dates(body.started_on, body.completed_on)
    if body.move_to_repair and body.completed_on is not None:
        raise HTTPException(
            422, "Cannot open and complete a repair in one entry")
    a = await _lock_asset(db, asset_id)
    moved = False
    if body.move_to_repair and a.status != AssetStatus.IN_REPAIR:
        try:
            await svc.set_status(db, asset=a, actor=current_user,
                                 to_status=AssetStatus.IN_REPAIR,
                                 remarks=body.description)
        except svc.AssetStateError as e:
            await db.rollback()
            raise HTTPException(409, str(e))
        moved = True
    m = AssetMaintenance(
        asset_id=a.id, kind=body.kind, description=body.description,
        vendor=body.vendor, cost_paise=body.cost_paise,
        started_on=body.started_on, completed_on=body.completed_on,
        created_by_id=current_user.id)
    db.add(m)
    await db.flush()
    _audit(db, current_user, "ASSET_MAINTENANCE_ADD", a.id, {
        "maintenance_id": m.id, "kind": m.kind, "cost_paise": m.cost_paise,
        "moved_to_repair": moved})
    await commit_or_409(db)
    return _out(m)


@router.patch("/maintenance/{mid}")
@guard_conflicts
async def patch_maintenance(db: deps.DBDep, current_user: deps.CurrentUser,
                            mid: int, body: MaintenancePatch) -> Any:
    data = body.model_dump(exclude_unset=True)
    complete = data.pop("complete", False)
    return_to_stock = data.pop("return_to_stock", True)
    for k in ("kind", "description", "cost_paise", "started_on"):
        if k in data and data[k] is None:
            raise HTTPException(422, f"{k} cannot be null")
    a, m = await _lock_entry(db, mid)
    if complete and m.completed_on is not None:
        await db.rollback()
        raise HTTPException(409, "Maintenance entry is already completed")
    if m.completed_on is not None and "completed_on" in data \
            and data["completed_on"] is None:
        await db.rollback()
        raise HTTPException(
            422, "Completed maintenance can't be reopened")
    if complete and data.get("completed_on") is None:
        data["completed_on"] = date.today()
    # setting completed_on on an open entry is a completion too
    completing = m.completed_on is None and \
        data.get("completed_on") is not None
    started = data.get("started_on", m.started_on)
    completed = data["completed_on"] if "completed_on" in data \
        else m.completed_on
    try:
        _check_dates(started, completed, check_future="started_on" in data)
    except HTTPException:
        await db.rollback()
        raise
    for k, v in data.items():
        setattr(m, k, v)
    await db.flush()
    returned = False
    if completing and return_to_stock and m.kind == "repair":
        returned = await _return_if_no_open_repair(
            db, a, m, current_user, "Maintenance completed")
    _audit(db, current_user, "ASSET_MAINTENANCE_UPDATE", a.id, {
        "maintenance_id": m.id, "fields": sorted(data.keys()),
        "completed": completing, "returned_to_stock": returned})
    await commit_or_409(db)
    return _out(m)


@router.delete("/maintenance/{mid}")
@guard_conflicts
async def delete_maintenance(db: deps.DBDep, current_user: deps.CurrentUser,
                             mid: int) -> Any:
    a, m = await _lock_entry(db, mid)
    if (m.cost_paise or 0) != 0 or m.completed_on is not None:
        await db.rollback()
        raise HTTPException(
            409, "Maintenance records with cost or completion are kept")
    was_repair = m.kind == "repair"
    await db.delete(m)
    await db.flush()
    returned = False
    if was_repair:
        returned = await _return_if_no_open_repair(
            db, a, m, current_user, "Open repair entry deleted")
    _audit(db, current_user, "ASSET_MAINTENANCE_DELETE", a.id, {
        "maintenance_id": mid, "kind": m.kind,
        "returned_to_stock": returned})
    await commit_or_409(db)
    return {"deleted": True, "id": mid}
