"""HR API for biometric devices, device users, PIN mappings, the raw punch
log and reprocess (Roadmap v2 Phase 4, Task 5). Mounted at /biometric and
NOT attendance-gated. Every route needs the 'biometric manage' permission
(superusers pass).

Back-fills (`apply_pending`) commit in their own sessions, so every endpoint
commits its own change first and back-fills afterwards."""
import ipaddress
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from app.api import deps
from app.api.v1.endpoints.roster_common import commit_or_409, lock_row
from app.core.datetime_utils import as_utc
from app.db.session import SessionLocal
from app.models.audit import AuditLog
from app.models.biometric import (
    BiometricDevice, BiometricDeviceStatus, BiometricDeviceUser,
    BiometricPunch, BiometricPunchState as S, BiometricUserMap,
)
from app.models.employee import Employee
from app.models.user import User
from app.services.adms_protocol import _PIN_RE
from app.services.biometric import PERM_BIOMETRIC, apply_pending
from app.services.time_rules import get_time_rules

router = APIRouter(dependencies=[Depends(deps.check_permissions([PERM_BIOMETRIC]))])

DEFAULT_OFFLINE_MINUTES = 30
# States that reflect real attendance decisions; a device holding any of
# them cannot be deleted (junk / held taps are removed with the device).
KEEP_STATES = (S.APPLIED, S.DUPLICATE, S.EDITED, S.LOCKED)


def _audit(db, me_id: int, action: str, rtype: str, rid, details: dict):
    db.add(AuditLog(user_id=me_id, action=action, resource_type=rtype,
                    resource_id=str(rid), details=details))


async def _offline_minutes(db) -> int:
    try:
        v = int((await get_time_rules(db)).get("biometric.offline_minutes",
                                               DEFAULT_OFFLINE_MINUTES))
        return v if v > 0 else DEFAULT_OFFLINE_MINUTES
    except (TypeError, ValueError):
        return DEFAULT_OFFLINE_MINUTES


def _health(d: BiometricDevice, now: datetime, offline_min: int) -> str:
    if d.status == BiometricDeviceStatus.DISABLED:
        return "disabled"
    seen = as_utc(d.last_seen_at)
    if seen is None:
        return "never"
    return "online" if now - seen <= timedelta(minutes=offline_min) else "offline"


def _dev_out(d: BiometricDevice, now, offline_min, counts=None) -> dict:
    c = counts or {}
    return {
        "id": d.id, "serial": d.serial, "name": d.name, "status": d.status,
        "utc_offset_minutes": d.utc_offset_minutes,
        "ip_allowlist": d.ip_allowlist, "location_note": d.location_note,
        "last_seen_at": as_utc(d.last_seen_at), "last_ip": d.last_ip,
        "firmware": d.firmware, "approved_at": as_utc(d.approved_at),
        "health": _health(d, now, offline_min),
        "pending_punches": c.get("pending", 0),
        "unmapped_pins": c.get("unmapped", 0),
        "enrolled_users": c.get("enrolled", 0),
    }


async def _get_device(db, device_id: int, lock: bool = False) -> BiometricDevice:
    stmt = select(BiometricDevice).where(BiometricDevice.id == device_id)
    d = (await lock_row(db, stmt, "Device is busy, retry")
         if lock else (await db.execute(stmt)).scalars().first())
    if d is None:
        raise HTTPException(404, "Device not found")
    return d


# ------------------------------ devices ------------------------------

@router.get("/devices")
async def list_devices(db: deps.DBDep):
    now = datetime.now(timezone.utc)
    offline_min = await _offline_minutes(db)
    devs = (await db.execute(
        select(BiometricDevice).order_by(BiometricDevice.id))).scalars().all()
    counts: dict[int, dict] = {d.id: {} for d in devs}
    for did, n in (await db.execute(
            select(BiometricPunch.device_id, func.count()).where(
                BiometricPunch.state == S.PENDING_DEVICE,
                BiometricPunch.device_id.is_not(None))
            .group_by(BiometricPunch.device_id))).all():
        counts.setdefault(did, {})["pending"] = n
    for did, n in (await db.execute(
            select(BiometricPunch.device_id,
                   func.count(func.distinct(BiometricPunch.pin))).where(
                BiometricPunch.state == S.UNMAPPED,
                BiometricPunch.device_id.is_not(None))
            .group_by(BiometricPunch.device_id))).all():
        counts.setdefault(did, {})["unmapped"] = n
    for did, n in (await db.execute(
            select(BiometricDeviceUser.device_id, func.count())
            .group_by(BiometricDeviceUser.device_id))).all():
        counts.setdefault(did, {})["enrolled"] = n
    return [_dev_out(d, now, offline_min, counts.get(d.id)) for d in devs]


class DevicePatch(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    utc_offset_minutes: Optional[int] = Field(None, ge=-720, le=840)
    ip_allowlist: Union[str, list[str], None] = None
    location_note: Optional[str] = Field(None, max_length=200)


def _norm_allowlist(raw: Union[str, list[str], None]) -> Optional[str]:
    if raw is None:
        return None
    items = (raw.replace(",", " ").split() if isinstance(raw, str)
             else [str(x).strip() for x in raw])
    out: list[str] = []
    for e in items:
        if not e:
            continue
        try:
            net = str(ipaddress.ip_network(e, strict=False))
        except ValueError:
            raise HTTPException(422, f"Invalid IP or CIDR: {e}")
        if net not in out:
            out.append(net)
    s = ",".join(out)
    if len(s) > 500:
        raise HTTPException(422, "IP allow-list is too long (max 500 chars)")
    return s or None


@router.patch("/devices/{device_id}")
async def update_device(device_id: int, body: DevicePatch, db: deps.DBDep,
                        me: deps.CurrentUser):
    """Partial update; only fields present in the body change. Empty
    ip_allowlist (or null) clears it. ip_allowlist is a comma-joined string
    on read; write accepts a string or a list."""
    me_id = me.id
    sent = body.model_fields_set
    new_ips = _norm_allowlist(body.ip_allowlist) if "ip_allowlist" in sent else None
    d = await _get_device(db, device_id, lock=True)
    changes: dict[str, Any] = {}
    if "name" in sent:
        d.name = (body.name or "").strip() or None
        changes["name"] = d.name
    if "utc_offset_minutes" in sent:
        if body.utc_offset_minutes is None:
            raise HTTPException(422, "utc_offset_minutes cannot be null")
        d.utc_offset_minutes = body.utc_offset_minutes
        changes["utc_offset_minutes"] = d.utc_offset_minutes
    if "ip_allowlist" in sent:
        d.ip_allowlist = new_ips
        changes["ip_allowlist"] = new_ips
    if "location_note" in sent:
        d.location_note = (body.location_note or "").strip() or None
        changes["location_note"] = d.location_note
    _audit(db, me_id, "BIOMETRIC_DEVICE_UPDATED", "biometric_device",
           device_id, changes)
    await commit_or_409(db)
    await db.refresh(d)
    return _dev_out(d, datetime.now(timezone.utc), await _offline_minutes(db))


@router.post("/devices/{device_id}/approve")
async def approve_device(device_id: int, db: deps.DBDep, me: deps.CurrentUser):
    """pending/disabled -> active, then back-fills held taps. Approving an
    already-active device is a 400. Returns {device, backfill: counts}."""
    me_id = me.id
    d = await _get_device(db, device_id, lock=True)
    if d.status == BiometricDeviceStatus.ACTIVE:
        raise HTTPException(400, "Device is already active")
    prev = d.status
    d.status = BiometricDeviceStatus.ACTIVE
    d.approved_by_id = me_id
    d.approved_at = datetime.now(timezone.utc)
    _audit(db, me_id, "BIOMETRIC_DEVICE_APPROVED", "biometric_device",
           device_id, {"serial": d.serial, "from": prev})
    await commit_or_409(db)
    counts = await apply_pending(SessionLocal, device_id=device_id)
    await db.refresh(d)
    return {"device": _dev_out(d, datetime.now(timezone.utc),
                               await _offline_minutes(db)),
            "backfill": counts}


@router.post("/devices/{device_id}/disable")
async def disable_device(device_id: int, db: deps.DBDep, me: deps.CurrentUser):
    """-> disabled. Its traffic is acknowledged and dropped by /iclock."""
    me_id = me.id
    d = await _get_device(db, device_id, lock=True)
    if d.status == BiometricDeviceStatus.DISABLED:
        raise HTTPException(400, "Device is already disabled")
    prev = d.status
    d.status = BiometricDeviceStatus.DISABLED
    _audit(db, me_id, "BIOMETRIC_DEVICE_DISABLED", "biometric_device",
           device_id, {"serial": d.serial, "from": prev})
    await commit_or_409(db)
    await db.refresh(d)
    return _dev_out(d, datetime.now(timezone.utc), await _offline_minutes(db))


@router.delete("/devices/{device_id}")
async def delete_device(device_id: int, db: deps.DBDep, me: deps.CurrentUser):
    """409 when the device has any applied / duplicate / edited / locked
    taps (they back real attendance). Otherwise deletes the device with its
    held raw taps (pending_device, unmapped, error, ignored), enrolled users
    and device-specific mappings."""
    me_id = me.id
    d = await _get_device(db, device_id, lock=True)
    kept = (await db.execute(select(func.count()).select_from(BiometricPunch)
            .where(BiometricPunch.device_id == device_id,
                   BiometricPunch.state.in_(KEEP_STATES)))).scalar_one()
    if kept:
        raise HTTPException(
            409, "Device has punches that were applied to attendance; "
                 "disable it instead of deleting")
    serial = d.serial
    await db.execute(delete(BiometricPunch).where(
        BiometricPunch.device_id == device_id))
    await db.delete(d)
    _audit(db, me_id, "BIOMETRIC_DEVICE_DELETED", "biometric_device",
           device_id, {"serial": serial})
    await commit_or_409(db)
    return {"deleted": True}


# ---------------------- device users / suggestions ----------------------

def _scope_maps(maps: list[BiometricUserMap], device_id: int) -> dict[str, BiometricUserMap]:
    """Effective mapping per pin for a device (specific beats global)."""
    out: dict[str, BiometricUserMap] = {}
    for m in maps:
        if m.device_id is None:
            out.setdefault(m.pin, m)
    for m in maps:
        if m.device_id == device_id:
            out[m.pin] = m
    return out


async def _suggest(db, device_users, maps) -> dict[str, int]:
    """pin -> user_id for UNMAPPED device users with a unique match.
    Employee code == pin first, else unique case-insensitive full-name
    match among active users. Users already mapped in scope, or suggested
    for more than one pin, are never suggested."""
    taken = {m.user_id for m in maps}
    mapped_pins = {m.pin for m in maps}
    todo = [u for u in device_users if u.pin not in mapped_pins]
    if not todo:
        return {}
    pins = [u.pin for u in todo]
    by_code: dict[str, list[int]] = {}
    for code, uid in (await db.execute(
            select(Employee.employee_id, Employee.user_id)
            .join(User, User.id == Employee.user_id)
            .where(Employee.employee_id.in_(pins),
                   User.is_active.is_(True)))).all():
        by_code.setdefault(code.lower(), []).append(uid)
    names = {(u.name or "").strip().lower() for u in todo if (u.name or "").strip()}
    by_name: dict[str, list[int]] = {}
    if names:
        for uid, fn in (await db.execute(
                select(User.id, User.full_name).where(
                    User.is_active.is_(True),
                    func.lower(func.trim(User.full_name)).in_(names)))).all():
            by_name.setdefault((fn or "").strip().lower(), []).append(uid)
    sug: dict[str, int] = {}
    for u in todo:
        cands = by_code.get(u.pin.lower())
        if not cands:
            cands = by_name.get((u.name or "").strip().lower())
        if cands and len(cands) == 1 and cands[0] not in taken:
            sug[u.pin] = cands[0]
    # one user suggested for several pins is ambiguous
    counts: dict[int, int] = {}
    for uid in sug.values():
        counts[uid] = counts.get(uid, 0) + 1
    return {p: uid for p, uid in sug.items() if counts[uid] == 1}


async def _user_info(db, user_ids) -> dict[int, dict]:
    ids = list({i for i in user_ids if i is not None})
    if not ids:
        return {}
    rows = (await db.execute(
        select(User.id, User.full_name, Employee.employee_id)
        .outerjoin(Employee, Employee.user_id == User.id)
        .where(User.id.in_(ids)))).all()
    return {i: {"user_name": n, "employee_code": c} for i, n, c in rows}


def _map_out(m: BiometricUserMap, info: dict) -> dict:
    i = info.get(m.user_id, {})
    return {"id": m.id, "device_id": m.device_id, "pin": m.pin,
            "user_id": m.user_id, "user_name": i.get("user_name"),
            "employee_code": i.get("employee_code"),
            "created_at": as_utc(m.created_at)}


@router.get("/devices/{device_id}/users")
async def device_users(device_id: int, db: deps.DBDep):
    """Enrolled users with the effective mapping (`mapping`, scope device or
    global) and `suggested_user_id` / `suggested_user_name`."""
    await _get_device(db, device_id)
    dus = (await db.execute(select(BiometricDeviceUser).where(
        BiometricDeviceUser.device_id == device_id)
        .order_by(BiometricDeviceUser.pin))).scalars().all()
    maps = (await db.execute(select(BiometricUserMap).where(
        (BiometricUserMap.device_id == device_id)
        | BiometricUserMap.device_id.is_(None)))).scalars().all()
    eff = _scope_maps(maps, device_id)
    sug = await _suggest(db, dus, maps)
    info = await _user_info(db, [m.user_id for m in eff.values()] + list(sug.values()))
    out = []
    for u in dus:
        m = eff.get(u.pin)
        s = sug.get(u.pin)
        out.append({
            "pin": u.pin, "name": u.name,
            "mapping": ({**_map_out(m, info),
                         "scope": "global" if m.device_id is None else "device"}
                        if m else None),
            "suggested_user_id": s,
            "suggested_user_name": info.get(s, {}).get("user_name") if s else None,
            "suggested_employee_code": info.get(s, {}).get("employee_code") if s else None,
        })
    return out


# ------------------------------ mappings ------------------------------

@router.get("/mappings")
async def list_mappings(db: deps.DBDep, device_id: Optional[int] = None,
                        q: Optional[str] = Query(None, max_length=100)):
    """Mappings with user name and employee code. `device_id` filters to that
    device's mappings; `q` matches pin, user name or employee code."""
    stmt = (select(BiometricUserMap)
            .join(User, User.id == BiometricUserMap.user_id)
            .outerjoin(Employee, Employee.user_id == User.id)
            .order_by(BiometricUserMap.id))
    if device_id is not None:
        stmt = stmt.where(BiometricUserMap.device_id == device_id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            BiometricUserMap.pin.ilike(like) | User.full_name.ilike(like)
            | Employee.employee_id.ilike(like))
    maps = (await db.execute(stmt.limit(1000))).scalars().all()
    info = await _user_info(db, [m.user_id for m in maps])
    return [_map_out(m, info) for m in maps]


class MappingIn(BaseModel):
    device_id: Optional[int] = None
    pin: str = Field(..., min_length=1, max_length=32)
    user_id: int
    replace: bool = False


@router.put("/mappings")
async def put_mapping(body: MappingIn, db: deps.DBDep, me: deps.CurrentUser):
    """Upsert a mapping (device_id null = every device). 409 if the pin is
    already mapped to a different user in that scope unless replace=true.
    Back-fills held taps for the pin (all devices for a global mapping, plus
    imports). Returns {mapping, backfill: counts}."""
    me_id = me.id
    pin = body.pin.strip()
    if not _PIN_RE.match(pin):
        raise HTTPException(400, "Invalid PIN (letters, digits, _ and - only)")
    if body.device_id is not None:
        await _get_device(db, body.device_id)
    user = (await db.execute(select(User).where(
        User.id == body.user_id))).scalars().first()
    if user is None or not user.is_active:
        raise HTTPException(400, "User not found or inactive")
    key = body.device_id or 0
    existing = await lock_row(db, select(BiometricUserMap).where(
        BiometricUserMap.device_key == key, BiometricUserMap.pin == pin),
        "Mapping is being changed, retry")
    prev_user = None
    if existing is not None:
        if existing.user_id != body.user_id:
            if not body.replace:
                raise HTTPException(
                    409, "PIN is already mapped to another user; "
                         "send replace=true to change it")
            prev_user = existing.user_id
            existing.user_id = body.user_id
            existing.created_by_id = me_id
        m = existing
    else:
        m = BiometricUserMap(device_id=body.device_id, pin=pin,
                             user_id=body.user_id, created_by_id=me_id)
        db.add(m)
    _audit(db, me_id, "BIOMETRIC_MAPPING_SET", "biometric_user_map",
           existing.id if existing else "new",
           {"device_id": body.device_id, "pin": pin, "user_id": body.user_id,
            "replaced_user_id": prev_user})
    await commit_or_409(db, "Mapping was changed by someone else, retry")
    counts = await apply_pending(SessionLocal, pin=pin, device_id=body.device_id)
    await db.refresh(m)
    info = await _user_info(db, [m.user_id])
    return {"mapping": _map_out(m, info), "backfill": counts}


@router.delete("/mappings/{map_id}")
async def delete_mapping(map_id: int, db: deps.DBDep, me: deps.CurrentUser):
    """Removes the mapping. Attendance already applied from its taps is NOT
    reverted; only future taps become unmapped."""
    me_id = me.id
    m = await lock_row(db, select(BiometricUserMap).where(
        BiometricUserMap.id == map_id))
    if m is None:
        raise HTTPException(404, "Mapping not found")
    info = {"device_id": m.device_id, "pin": m.pin, "user_id": m.user_id}
    await db.delete(m)
    _audit(db, me_id, "BIOMETRIC_MAPPING_DELETED", "biometric_user_map",
           map_id, info)
    await commit_or_409(db)
    return {"deleted": True}


class AutoIn(BaseModel):
    device_id: int


@router.post("/mappings/auto")
async def auto_map(body: AutoIn, db: deps.DBDep, me: deps.CurrentUser):
    """Creates device-specific mappings for every enrolled, not yet mapped
    device user with a unique suggestion (employee code, else full name),
    then back-fills the device. Returns {created, backfill}."""
    me_id = me.id
    await _get_device(db, body.device_id)
    dus = (await db.execute(select(BiometricDeviceUser).where(
        BiometricDeviceUser.device_id == body.device_id))).scalars().all()
    maps = (await db.execute(select(BiometricUserMap).where(
        (BiometricUserMap.device_id == body.device_id)
        | BiometricUserMap.device_id.is_(None)))).scalars().all()
    sug = await _suggest(db, dus, maps)
    for pin, uid in sug.items():
        db.add(BiometricUserMap(device_id=body.device_id, pin=pin,
                                user_id=uid, created_by_id=me_id))
    if sug:
        _audit(db, me_id, "BIOMETRIC_MAPPING_AUTO", "biometric_device",
               body.device_id, {"created": len(sug), "pins": sorted(sug)})
        await commit_or_409(db, "Mappings changed concurrently, retry")
    counts = (await apply_pending(SessionLocal, device_id=body.device_id)
              if sug else {})
    return {"created": len(sug), "backfill": counts}


# ------------------------------ punch log ------------------------------

@router.get("/punches")
async def list_punches(
    db: deps.DBDep, state: Optional[str] = None,
    device_id: Optional[int] = None, pin: Optional[str] = None,
    user_id: Optional[int] = None,
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = None,
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
):
    """Raw tap log, newest first. Returns {items, total}. `from` / `to` are
    punch_time bounds (naive values are UTC; from inclusive, to exclusive)."""
    conds = []
    if state:
        conds.append(BiometricPunch.state == state)
    if device_id is not None:
        conds.append(BiometricPunch.device_id == device_id)
    if pin:
        conds.append(BiometricPunch.pin == pin)
    if user_id is not None:
        conds.append(BiometricPunch.user_id == user_id)
    if from_ is not None:
        conds.append(BiometricPunch.punch_time >= as_utc(from_))
    if to is not None:
        conds.append(BiometricPunch.punch_time < as_utc(to))
    total = (await db.execute(select(func.count()).select_from(BiometricPunch)
             .where(*conds))).scalar_one()
    rows = (await db.execute(
        select(BiometricPunch, BiometricDevice.serial, User.full_name,
               Employee.employee_id)
        .outerjoin(BiometricDevice, BiometricDevice.id == BiometricPunch.device_id)
        .outerjoin(User, User.id == BiometricPunch.user_id)
        .outerjoin(Employee, Employee.user_id == BiometricPunch.user_id)
        .where(*conds)
        .order_by(BiometricPunch.punch_time.desc(), BiometricPunch.id.desc())
        .limit(limit).offset(offset))).all()
    items = [{
        "id": p.id, "source": p.source, "device_id": p.device_id,
        "device_serial": serial, "import_batch": p.import_batch,
        "pin": p.pin, "punch_time": as_utc(p.punch_time),
        "device_status": p.device_status, "verify_type": p.verify_type,
        "state": p.state, "user_id": p.user_id, "user_name": uname,
        "employee_code": code, "attendance_id": p.attendance_id,
        "error": p.error, "created_at": as_utc(p.created_at),
        "applied_at": as_utc(p.applied_at),
    } for p, serial, uname, code in rows]
    return {"items": items, "total": total}


class ReprocessIn(BaseModel):
    state: Literal["error", "unmapped", "locked"]
    device_id: Optional[int] = None


@router.post("/punches/reprocess")
async def reprocess(body: ReprocessIn, db: deps.DBDep, me: deps.CurrentUser):
    """Re-runs the apply step for taps in the given state (locked taps are
    retried for when payroll was unlocked). Returns {backfill: counts}."""
    me_id = me.id
    if body.device_id is not None:
        await _get_device(db, body.device_id)
    counts = await apply_pending(SessionLocal, device_id=body.device_id,
                                 states={body.state})
    _audit(db, me_id, "BIOMETRIC_REPROCESS", "biometric_punch", body.state,
           {"state": body.state, "device_id": body.device_id, "counts": counts})
    await commit_or_409(db)
    return {"backfill": counts}
