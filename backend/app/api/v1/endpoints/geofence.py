"""GeoFenceLocation CRUD + EmployeeGeoConfig (allowlist + mode + toggle).

RBAC
----
- "geo fence write" : create/update/delete fences + assign/toggle config
- read endpoints    : any authenticated user (so the punch UI can fetch
                      the employee's own effective fences)
"""
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.v1.endpoints.hr import log_audit
from app.models.employee import Employee
from app.models.geofence import (
    EmployeeGeoConfig,
    EmployeeGeoFenceLink,
    GeoFenceLocation,
)
from app.models.user import User
from app.schemas.geofence import (
    BulkGeoAssignRequest,
    BulkGeoAssignResult,
    EmployeeGeoConfigRead,
    EmployeeGeoConfigToggle,
    EmployeeGeoConfigUpsert,
    GeoFenceLocationCreate,
    GeoFenceLocationRead,
    GeoFenceLocationUpdate,
)
from app.services.geofence import MIN_RADIUS_METERS

router = APIRouter()

PERM_GEO_WRITE = "geo fence write"


# ---- helpers ------------------------------------------------------------


async def _enrich_config(db, cfg: EmployeeGeoConfig) -> EmployeeGeoConfigRead:
    """Hydrate a config row with fence details + employee context."""
    fences = [
        GeoFenceLocationRead.model_validate(link.fence)
        for link in cfg.fences if link.fence is not None
    ]
    fence_ids = [f.id for f in fences]

    employee = None
    if cfg.user is not None:
        employee = (await db.execute(
            select(Employee).where(Employee.user_id == cfg.user_id)
        )).scalars().first()

    return EmployeeGeoConfigRead(
        user_id=cfg.user_id,
        enforcement_mode=cfg.enforcement_mode,
        geo_enabled=cfg.geo_enabled,
        fence_ids=fence_ids,
        updated_at=cfg.updated_at,
        updated_by_id=cfg.updated_by_id,
        employee_name=cfg.user.full_name if cfg.user else None,
        employee_email=cfg.user.email if cfg.user else None,
        employee_department=employee.department if employee else None,
        fences=fences,
    )


async def _load_config(
    db, user_id: int
) -> Optional[EmployeeGeoConfig]:
    stmt = (
        select(EmployeeGeoConfig)
        .where(EmployeeGeoConfig.user_id == user_id)
        .options(
            selectinload(EmployeeGeoConfig.user),
            selectinload(EmployeeGeoConfig.fences)
            .selectinload(EmployeeGeoFenceLink.fence),
        )
    )
    return (await db.execute(stmt)).scalars().first()


async def _set_fences(
    db, cfg: EmployeeGeoConfig, fence_ids: List[int]
) -> None:
    """Replace the fence allowlist on a config row with the given ids.

    Validates that every id exists + is active. Caller commits.
    """
    fence_ids = list({int(x) for x in fence_ids})
    if fence_ids:
        rows = (await db.execute(
            select(GeoFenceLocation.id).where(
                GeoFenceLocation.id.in_(fence_ids),
            )
        )).scalars().all()
        unknown = set(fence_ids) - set(rows)
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown fence id(s): {sorted(unknown)}",
            )

    # Wipe existing links, add fresh ones.
    for link in list(cfg.fences):
        await db.delete(link)
    await db.flush()
    for fid in fence_ids:
        db.add(EmployeeGeoFenceLink(
            user_id=cfg.user_id,
            geofence_location_id=fid,
        ))


# ---- GeoFenceLocation CRUD ---------------------------------------------


@router.get("/fences", response_model=List[GeoFenceLocationRead])
async def list_fences(
    db: deps.DBDep,
    include_inactive: bool = Query(False),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """List fences. Read open to any authenticated user (punch UI uses it
    to show the employee where they're allowed to punch from)."""
    stmt = select(GeoFenceLocation)
    if not include_inactive:
        stmt = stmt.where(GeoFenceLocation.is_active.is_(True))
    stmt = stmt.order_by(GeoFenceLocation.name)
    return list((await db.execute(stmt)).scalars().all())


@router.get("/fences/{fence_id}", response_model=GeoFenceLocationRead)
async def get_fence(
    fence_id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    obj = await db.get(GeoFenceLocation, fence_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Fence not found")
    return obj


@router.post("/fences", response_model=GeoFenceLocationRead)
async def create_fence(
    *,
    db: deps.DBDep,
    payload: GeoFenceLocationCreate,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_GEO_WRITE])),
) -> Any:
    name = payload.name.strip()
    clash = (
        await db.execute(
            select(GeoFenceLocation).where(
                func.lower(GeoFenceLocation.name) == name.lower()
            )
        )
    ).scalars().first()
    if clash is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Fence '{name}' already exists",
        )
    if payload.radius_meters < MIN_RADIUS_METERS:
        # Belt-and-braces; schema also enforces this.
        raise HTTPException(
            status_code=400,
            detail=f"radius_meters must be >= {MIN_RADIUS_METERS}",
        )

    obj = GeoFenceLocation(
        name=name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        radius_meters=payload.radius_meters,
        is_active=payload.is_active,
        created_by_id=current_user.id,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)

    await log_audit(
        db, current_user.id, "geofence.create", "geofence_location",
        str(obj.id),
        {
            "name": obj.name,
            "latitude": obj.latitude,
            "longitude": obj.longitude,
            "radius_meters": obj.radius_meters,
        },
        request,
    )
    return obj


@router.patch("/fences/{fence_id}", response_model=GeoFenceLocationRead)
async def update_fence(
    *,
    fence_id: int,
    db: deps.DBDep,
    payload: GeoFenceLocationUpdate,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_GEO_WRITE])),
) -> Any:
    obj = await db.get(GeoFenceLocation, fence_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Fence not found")

    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        new_name = data["name"].strip()
        clash = (await db.execute(
            select(GeoFenceLocation).where(
                func.lower(GeoFenceLocation.name) == new_name.lower(),
                GeoFenceLocation.id != fence_id,
            )
        )).scalars().first()
        if clash is not None:
            raise HTTPException(
                status_code=400, detail=f"Fence '{new_name}' already exists"
            )
        data["name"] = new_name
    if "radius_meters" in data and data["radius_meters"] < MIN_RADIUS_METERS:
        raise HTTPException(
            status_code=400,
            detail=f"radius_meters must be >= {MIN_RADIUS_METERS}",
        )

    for k, v in data.items():
        setattr(obj, k, v)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)

    await log_audit(
        db, current_user.id, "geofence.update", "geofence_location",
        str(obj.id), {"updated_fields": list(data.keys())},
        request,
    )
    return obj


@router.delete(
    "/fences/{fence_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_fence(
    *,
    fence_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_GEO_WRITE])),
) -> None:
    obj = await db.get(GeoFenceLocation, fence_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Fence not found")
    in_use = (await db.execute(
        select(func.count())
        .select_from(EmployeeGeoFenceLink)
        .where(EmployeeGeoFenceLink.geofence_location_id == fence_id)
    )).scalar_one()
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot delete '{obj.name}' — {in_use} employee(s) "
                "still allowlist it. Deactivate instead."
            ),
        )
    await db.delete(obj)
    await db.commit()
    await log_audit(
        db, current_user.id, "geofence.delete", "geofence_location",
        str(fence_id), {"name": obj.name}, request,
    )
    return None


# ---- EmployeeGeoConfig --------------------------------------------------


@router.get("/employees", response_model=List[EmployeeGeoConfigRead])
async def list_employee_configs(
    db: deps.DBDep,
    department: Optional[str] = Query(None),
    current_user: User = Depends(deps.check_permissions([PERM_GEO_WRITE])),
) -> Any:
    """List every employee currently onboarded into geo fencing."""
    stmt = (
        select(EmployeeGeoConfig)
        .options(
            selectinload(EmployeeGeoConfig.user),
            selectinload(EmployeeGeoConfig.fences)
            .selectinload(EmployeeGeoFenceLink.fence),
        )
    )
    if department:
        stmt = stmt.join(
            Employee, Employee.user_id == EmployeeGeoConfig.user_id
        ).where(Employee.department == department)

    configs = list((await db.execute(stmt)).scalars().all())
    out = []
    for cfg in configs:
        out.append(await _enrich_config(db, cfg))
    return out


@router.get(
    "/employees/{user_id}", response_model=Optional[EmployeeGeoConfigRead]
)
async def get_employee_config(
    user_id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Get a single employee's effective geo config.

    Any authenticated user can read their OWN config; otherwise this
    requires geo fence write. Used by the punch UI to know whether to
    request GPS / mock flag before submitting.
    """
    if current_user.id != user_id and not current_user.is_superuser:
        for r in current_user.roles:
            for p in r.permissions:
                if p.name == PERM_GEO_WRITE:
                    break
            else:
                continue
            break
        else:
            raise HTTPException(
                status_code=403, detail="Not enough permissions"
            )
    cfg = await _load_config(db, user_id)
    if cfg is None:
        return None
    return await _enrich_config(db, cfg)


@router.put("/employees", response_model=EmployeeGeoConfigRead)
async def upsert_employee_config(
    *,
    db: deps.DBDep,
    payload: EmployeeGeoConfigUpsert,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_GEO_WRITE])),
) -> Any:
    """Create-or-update one employee's geo config (mode + toggle +
    fence allowlist). Wipes the prior fence set with the supplied one."""
    target = await db.get(User, payload.user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    cfg = await _load_config(db, payload.user_id)
    created = False
    if cfg is None:
        cfg = EmployeeGeoConfig(
            user_id=payload.user_id,
            enforcement_mode=payload.enforcement_mode,
            geo_enabled=payload.geo_enabled,
            updated_by_id=current_user.id,
        )
        db.add(cfg)
        await db.flush()
        await db.refresh(cfg, ["fences"])
        created = True
    else:
        cfg.enforcement_mode = payload.enforcement_mode
        cfg.geo_enabled = payload.geo_enabled
        cfg.updated_by_id = current_user.id
        db.add(cfg)
        await db.flush()

    await _set_fences(db, cfg, payload.fence_ids)
    await db.commit()

    fresh = await _load_config(db, payload.user_id)
    await log_audit(
        db, current_user.id,
        "geo_config.create" if created else "geo_config.update",
        "employee_geo_config",
        str(payload.user_id),
        {
            "enforcement_mode": payload.enforcement_mode,
            "geo_enabled": payload.geo_enabled,
            "fence_ids": payload.fence_ids,
        },
        request,
    )
    return await _enrich_config(db, fresh) if fresh else await _enrich_config(db, cfg)


@router.patch(
    "/employees/{user_id}/toggle", response_model=EmployeeGeoConfigRead
)
async def toggle_employee_geo(
    *,
    user_id: int,
    db: deps.DBDep,
    payload: EmployeeGeoConfigToggle,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_GEO_WRITE])),
) -> Any:
    """Real-time enable/disable of geo enforcement without touching the
    fence allowlist."""
    cfg = await _load_config(db, user_id)
    if cfg is None:
        raise HTTPException(
            status_code=404,
            detail="No geo config for this employee — use PUT first.",
        )
    cfg.geo_enabled = payload.geo_enabled
    cfg.updated_by_id = current_user.id
    db.add(cfg)
    await db.commit()
    await log_audit(
        db, current_user.id, "geo_config.toggle", "employee_geo_config",
        str(user_id), {"geo_enabled": payload.geo_enabled},
        request,
    )
    fresh = await _load_config(db, user_id)
    return await _enrich_config(db, fresh) if fresh else await _enrich_config(db, cfg)


@router.delete(
    "/employees/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_employee_config(
    *,
    user_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_GEO_WRITE])),
) -> None:
    """Remove the employee from geo fencing entirely. Punch behaviour
    reverts to pre-geo (NO_SHIFT-style fallback at most)."""
    cfg = await _load_config(db, user_id)
    if cfg is None:
        return None
    await db.delete(cfg)
    await db.commit()
    await log_audit(
        db, current_user.id, "geo_config.delete", "employee_geo_config",
        str(user_id), {}, request,
    )
    return None


@router.post("/employees/bulk", response_model=BulkGeoAssignResult)
async def bulk_assign(
    *,
    db: deps.DBDep,
    payload: BulkGeoAssignRequest,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_GEO_WRITE])),
) -> Any:
    """Apply the SAME config to many employees.

    Resolves targets by department string-match OR by employee_ids,
    then per-employee upserts. Per-employee failures don't abort.
    """
    if payload.fence_ids:
        rows = (await db.execute(
            select(GeoFenceLocation.id).where(
                GeoFenceLocation.id.in_(payload.fence_ids)
            )
        )).scalars().all()
        unknown = set(payload.fence_ids) - set(rows)
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown fence id(s): {sorted(unknown)}",
            )

    target_user_ids: List[int] = []
    if payload.employee_ids:
        target_user_ids = list({int(x) for x in payload.employee_ids})
    elif payload.department:
        rows = (await db.execute(
            select(Employee.user_id).where(
                Employee.department == payload.department,
                Employee.status == "active",
            )
        )).scalars().all()
        target_user_ids = list({int(x) for x in rows})

    if not target_user_ids:
        return BulkGeoAssignResult(
            upserted=0, failed=0, errors=["No target employees resolved"]
        )

    upserted = 0
    failed = 0
    errors: List[str] = []

    for uid in target_user_ids:
        try:
            target = await db.get(User, uid)
            if target is None:
                failed += 1
                errors.append(f"User #{uid} not found")
                continue
            cfg = await _load_config(db, uid)
            if cfg is None:
                cfg = EmployeeGeoConfig(
                    user_id=uid,
                    enforcement_mode=payload.enforcement_mode,
                    geo_enabled=payload.geo_enabled,
                    updated_by_id=current_user.id,
                )
                db.add(cfg)
                await db.flush()
                await db.refresh(cfg, ["fences"])
            else:
                cfg.enforcement_mode = payload.enforcement_mode
                cfg.geo_enabled = payload.geo_enabled
                cfg.updated_by_id = current_user.id
                db.add(cfg)
                await db.flush()
            await _set_fences(db, cfg, payload.fence_ids)
            upserted += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append(f"User #{uid}: {exc}")

    await db.commit()
    await log_audit(
        db, current_user.id, "geo_config.bulk_assign",
        "employee_geo_config", "-",
        {
            "target_user_ids": target_user_ids,
            "department": payload.department,
            "enforcement_mode": payload.enforcement_mode,
            "geo_enabled": payload.geo_enabled,
            "fence_ids": payload.fence_ids,
            "upserted": upserted,
            "failed": failed,
        },
        request,
    )
    return BulkGeoAssignResult(
        upserted=upserted, failed=failed, errors=errors
    )


@router.get("/my/effective")
async def my_effective_config(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Convenience endpoint for the punch UI: returns the current
    employee's effective fences + mode + toggle. Useful for showing
    "you can punch from: HQ Kolkata, Client Site SPML" hints."""
    cfg = await _load_config(db, current_user.id)
    if cfg is None:
        return {
            "geo_enabled": False,
            "enforcement_mode": None,
            "fences": [],
        }
    return {
        "geo_enabled": cfg.geo_enabled,
        "enforcement_mode": cfg.enforcement_mode,
        "fences": [
            GeoFenceLocationRead.model_validate(link.fence)
            for link in cfg.fences if link.fence is not None
        ],
    }
