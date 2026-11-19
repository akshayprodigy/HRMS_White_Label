"""Asset state machine + allocation log (Roadmap v2 Phase 5, Task 3).

This is the ONLY place that may set ``Asset.status``. Callers must obtain the
``asset`` via :func:`get_asset_for_update` (row lock) before calling any
transition. Nothing here commits; endpoints commit (and map AssetStateError
to HTTP 409, LookupError to 404).
"""
from datetime import date
from typing import Any, Optional

from sqlalchemy import select

from app.models.asset import Asset, AssetCategory, AssetStatus
from app.models.audit import AuditLog
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_asset import EmployeeAsset


class AssetStateError(ValueError):
    """Invalid asset transition; message is safe to show to the user."""


_RETURN_TARGETS = (AssetStatus.IN_STOCK, AssetStatus.IN_REPAIR, AssetStatus.RETIRED)


def _audit(db, actor, action: str, asset: Asset, details: dict[str, Any]) -> None:
    db.add(AuditLog(
        user_id=actor.id, action=action, resource_type="asset",
        resource_id=str(asset.id), details=details))


def _append(existing: Optional[str], new: Optional[str]) -> Optional[str]:
    new = (new or "").strip()
    if not new:
        return existing
    return f"{existing}\n{new}" if existing else new


async def next_asset_tag(db, category) -> str:
    """Next tag for the category. Locks the category row and reads tags with
    FOR UPDATE; callers must keep the transaction open until the asset insert
    is committed."""
    await db.execute(select(AssetCategory.id).where(
        AssetCategory.id == category.id).with_for_update())
    prefix = f"{category.code}-"
    esc = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    tags = (await db.execute(
        select(Asset.asset_tag).where(Asset.asset_tag.like(f"{esc}%", escape="\\")).with_for_update()
    )).scalars().all()
    top = 0
    for t in tags:
        suffix = t[len(prefix):]
        if (t[:len(prefix)].upper() == prefix.upper()
                and suffix.isascii() and suffix.isdigit()):
            top = max(top, int(suffix))
    return f"{category.code}-{top + 1:06d}"


async def get_asset_for_update(db, asset_id) -> Asset:
    asset = (await db.execute(
        select(Asset).where(Asset.id == asset_id).with_for_update()
        .execution_options(populate_existing=True))).scalars().first()
    if asset is None:
        raise LookupError("Asset not found")
    return asset


async def open_allocation(db, asset_id, *, lock: bool = False
                          ) -> Optional[EmployeeAsset]:
    """Open allocation for an asset. Use lock=True only when the caller updates
    the row it finds; a locking read of an empty range takes a gap lock that
    deadlocks concurrent inserts."""
    q = (select(EmployeeAsset).where(
        EmployeeAsset.asset_id == asset_id,
        EmployeeAsset.status == "allocated")
        .order_by(EmployeeAsset.id.desc()))
    if lock:
        q = q.with_for_update()
    return (await db.execute(
        q.execution_options(populate_existing=True))).scalars().first()


async def open_allocations_for_employee(db, employee_id, *, lock: bool = False
                                        ) -> list[EmployeeAsset]:
    q = (select(EmployeeAsset).where(
        EmployeeAsset.employee_id == employee_id,
        EmployeeAsset.status == "allocated")
        .order_by(EmployeeAsset.id))
    if lock:
        q = q.with_for_update()
    return list((await db.execute(
        q.execution_options(populate_existing=True))).scalars().all())


async def allocate(db, *, asset, employee, actor, issued_date=None,
                   condition=None, remarks=None) -> EmployeeAsset:
    if asset.status != AssetStatus.IN_STOCK:
        raise AssetStateError(
            f"Only in-stock assets can be allocated (asset is {asset.status})")
    if await open_allocation(db, asset.id) is not None:
        raise AssetStateError("Asset already has an open allocation")
    # Locking re-read (lock order: asset -> employee -> allocation insert) so
    # this serialises with exit release, which locks the employee first.
    employee = (await db.execute(
        select(Employee).where(Employee.id == employee.id).with_for_update()
        .execution_options(populate_existing=True))).scalars().first()
    if employee is None:
        raise AssetStateError("Employee not found")
    if employee.status == EmployeeStatus.INACTIVE:
        raise AssetStateError("Cannot allocate an asset to an inactive employee")
    if issued_date and issued_date > date.today():
        raise AssetStateError("Issue date cannot be in the future")
    category = await db.get(AssetCategory, asset.category_id)
    alloc = EmployeeAsset(
        employee_id=employee.id, asset_id=asset.id, status="allocated",
        asset_type=(category.name if category else "Asset")[:50],
        model=asset.name[:150], serial_no=asset.serial_no,
        identifier=asset.asset_tag, issued_date=issued_date or date.today(),
        condition=condition, remarks=remarks,
        allocated_by_id=actor.id, created_by_id=actor.id)
    db.add(alloc)
    asset.status = AssetStatus.ALLOCATED
    await db.flush()
    _audit(db, actor, "ASSET_ALLOCATE", asset, {
        "from_status": AssetStatus.IN_STOCK, "to_status": AssetStatus.ALLOCATED,
        "employee_id": employee.id, "allocation_id": alloc.id,
        "issued_date": alloc.issued_date.isoformat()})
    return alloc


async def return_asset(db, *, asset, actor, returned_date=None, condition=None,
                       remarks=None, to_status="in_stock") -> EmployeeAsset:
    if to_status not in _RETURN_TARGETS:
        raise AssetStateError(
            "A returned asset can only go to in_stock, in_repair or retired")
    if asset.status != AssetStatus.ALLOCATED:
        raise AssetStateError("Asset is not allocated")
    alloc = await open_allocation(db, asset.id, lock=True)
    if alloc is None:
        raise AssetStateError("Asset has no open allocation to return")
    rdate = returned_date or date.today()
    if rdate > date.today():
        raise AssetStateError("Return date cannot be in the future")
    if alloc.issued_date and rdate < alloc.issued_date:
        raise AssetStateError("Return date cannot be before the issue date")
    from_status = asset.status
    alloc.status = "returned"
    alloc.returned_date = rdate
    alloc.returned_condition = condition
    alloc.returned_to_id = actor.id
    alloc.remarks = _append(alloc.remarks, remarks)
    asset.status = to_status
    await db.flush()
    _audit(db, actor, "ASSET_RETURN", asset, {
        "from_status": from_status, "to_status": to_status,
        "employee_id": alloc.employee_id, "allocation_id": alloc.id,
        "returned_date": rdate.isoformat(), "condition": condition})
    return alloc


async def mark_lost(db, *, asset, actor, remarks) -> Optional[EmployeeAsset]:
    if not (remarks or "").strip():
        raise AssetStateError("Remarks are required when marking an asset lost")
    if asset.status not in (AssetStatus.ALLOCATED, AssetStatus.IN_STOCK,
                            AssetStatus.IN_REPAIR):
        raise AssetStateError(f"Cannot mark a {asset.status} asset as lost")
    from_status = asset.status
    alloc = None
    details: dict[str, Any] = {
        "from_status": from_status, "to_status": AssetStatus.LOST,
        "remarks": remarks.strip()}
    if from_status == AssetStatus.ALLOCATED:
        alloc = await open_allocation(db, asset.id, lock=True)
        if alloc is not None:
            alloc.status = "lost"
            alloc.returned_date = date.today()
            alloc.remarks = _append(alloc.remarks, remarks)
            details["employee_id"] = alloc.employee_id
            details["allocation_id"] = alloc.id
        else:
            details["orphaned_allocation"] = True
    asset.status = AssetStatus.LOST
    await db.flush()
    _audit(db, actor, "ASSET_LOST", asset, details)
    return alloc


async def set_status(db, *, asset, actor, to_status, remarks=None) -> None:
    from_status = asset.status
    if to_status in (AssetStatus.ALLOCATED, AssetStatus.LOST):
        raise AssetStateError(
            "Use allocate to allocate an asset or mark-lost to record a loss")
    if from_status == AssetStatus.ALLOCATED or \
            await open_allocation(db, asset.id) is not None:
        raise AssetStateError("Return the asset first")
    if to_status == from_status:
        raise AssetStateError(f"Asset is already {from_status}")
    allowed = {
        AssetStatus.IN_STOCK: (AssetStatus.IN_REPAIR, AssetStatus.RETIRED),
        AssetStatus.IN_REPAIR: (AssetStatus.IN_STOCK, AssetStatus.RETIRED),
        AssetStatus.RETIRED: (AssetStatus.IN_STOCK,),
        AssetStatus.LOST: (AssetStatus.IN_STOCK,),
    }
    if to_status not in allowed.get(from_status, ()):
        raise AssetStateError(
            f"Cannot move an asset from {from_status} to {to_status}")
    asset.status = to_status
    await db.flush()
    _audit(db, actor, "ASSET_STATUS", asset, {
        "from_status": from_status, "to_status": to_status,
        "remarks": (remarks or "").strip() or None})


async def asset_manager_user_ids(db) -> list[int]:
    """Active users who can manage assets: superusers plus holders of the
    'asset manage' permission through any role."""
    from app.models.user import Permission, Role, User
    sup = (await db.execute(select(User.id).where(
        User.is_active.is_(True), User.is_superuser.is_(True)))).scalars().all()
    perm = (await db.execute(
        select(User.id).join(User.roles).join(Role.permissions)
        .where(User.is_active.is_(True), Permission.name == "asset manage")
    )).scalars().all()
    return sorted(set(sup) | set(perm))
