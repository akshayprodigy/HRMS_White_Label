"""Asset register API (Roadmap v2 Phase 5, Task 4). Mounted at /assets, NOT
attendance-gated. Every route needs 'asset manage'.

Writes: lock asset row -> service call(s) -> commit_or_409 once. The service
writes the audit rows; do not call hr.log_audit here (it commits)."""
import io
import re
from datetime import date, timedelta
from typing import Any, Literal, Optional

import segno
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased

from app.services.org_time import local_today
from app.api import deps
from sqlalchemy.exc import IntegrityError

from app.api.v1.endpoints.roster_common import (
    _errno, commit_or_409, guard_conflicts, plain_actor, retry_on_lock,
)
from app.models.asset import (
    Asset, AssetCategory, AssetMaintenance, AssetStatus,
)
from app.models.employee import Employee
from app.models.geofence import GeoFenceLocation
from app.models.employee_asset import EmployeeAsset
from app.models.user import User
from app.services import assets as svc
from app.services.asset_depreciation import book_value

PERM_ASSET = "asset manage"
router = APIRouter(dependencies=[Depends(deps.check_permissions([PERM_ASSET]))])

MAX_PAISE = 2_000_000_000  # 32-bit INT column
_TAG_RE = re.compile(r"^[A-Z0-9-]{3,32}$")
_CODE_RE = re.compile(r"^[A-Z0-9]{2,10}$")
_MASTER = ("model", "serial_no", "location_id", "vendor", "invoice_no",
           "purchase_date", "purchase_cost_paise", "salvage_value_paise",
           "useful_life_months", "warranty_expiry", "amc_vendor", "amc_expiry",
           "notes", "name", "category_id")


def _iso(d) -> Optional[str]:
    return d.isoformat() if d else None


async def _check_location(db, location_id) -> None:
    if location_id is not None and (await db.execute(
            select(GeoFenceLocation.id).where(
                GeoFenceLocation.id == location_id))).first() is None:
        raise HTTPException(422, "Location not found")


def _nonblank(v):
    if v is None:
        return v
    v = v.strip()
    if not v:
        raise ValueError("must not be blank")
    return v


# ── schemas ──────────────────────────────────────────────────────────────
class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    code: str
    default_useful_life_months: Optional[int] = Field(default=None, gt=0)

    _strip_name = field_validator("name")(_nonblank)


class CategoryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    default_useful_life_months: Optional[int] = Field(default=None, gt=0)
    is_active: Optional[bool] = None

    _strip_name = field_validator("name")(_nonblank)


class AssetIn(BaseModel):
    category_id: int
    name: str = Field(min_length=1, max_length=150)
    model: Optional[str] = Field(default=None, max_length=150)
    serial_no: Optional[str] = Field(default=None, max_length=100)
    asset_tag: Optional[str] = None
    location_id: Optional[int] = None
    vendor: Optional[str] = Field(default=None, max_length=150)
    invoice_no: Optional[str] = Field(default=None, max_length=64)
    purchase_date: Optional[date] = None
    purchase_cost_paise: Optional[int] = Field(
        default=None, ge=0, le=MAX_PAISE)
    salvage_value_paise: int = Field(default=0, ge=0, le=MAX_PAISE)
    useful_life_months: Optional[int] = Field(default=None, gt=0)
    warranty_expiry: Optional[date] = None
    amc_vendor: Optional[str] = Field(default=None, max_length=150)
    amc_expiry: Optional[date] = None
    notes: Optional[str] = None

    _strip_name = field_validator("name")(_nonblank)


class AssetPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_id: Optional[int] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    model: Optional[str] = Field(default=None, max_length=150)
    serial_no: Optional[str] = Field(default=None, max_length=100)
    location_id: Optional[int] = None
    vendor: Optional[str] = Field(default=None, max_length=150)
    invoice_no: Optional[str] = Field(default=None, max_length=64)
    purchase_date: Optional[date] = None
    purchase_cost_paise: Optional[int] = Field(
        default=None, ge=0, le=MAX_PAISE)
    salvage_value_paise: Optional[int] = Field(
        default=None, ge=0, le=MAX_PAISE)
    useful_life_months: Optional[int] = Field(default=None, gt=0)
    warranty_expiry: Optional[date] = None
    amc_vendor: Optional[str] = Field(default=None, max_length=150)
    amc_expiry: Optional[date] = None
    notes: Optional[str] = None

    _strip_name = field_validator("name")(_nonblank)


class AllocateIn(BaseModel):
    employee_id: int
    issued_date: Optional[date] = None
    condition: Optional[str] = Field(default=None, max_length=50)
    remarks: Optional[str] = None


class ReturnIn(BaseModel):
    returned_date: Optional[date] = None
    condition: Optional[str] = Field(default=None, max_length=50)
    remarks: Optional[str] = None
    to_status: Literal["in_stock", "in_repair", "retired"] = "in_stock"


class LostIn(BaseModel):
    remarks: str = Field(min_length=3)


class StatusIn(BaseModel):
    to_status: Literal["in_stock", "in_repair", "retired"]
    remarks: Optional[str] = None


# ── serializers / loaders ────────────────────────────────────────────────
def _cat_out(c: AssetCategory) -> dict:
    return {"id": c.id, "name": c.name, "code": c.code,
            "default_useful_life_months": c.default_useful_life_months,
            "is_active": c.is_active}


def _life(a: Asset, cat: AssetCategory) -> Optional[int]:
    return a.useful_life_months or cat.default_useful_life_months


def _bv(a: Asset, cat: AssetCategory, today: date):
    return book_value(
        cost_paise=a.purchase_cost_paise, salvage_paise=a.salvage_value_paise,
        purchase_date=a.purchase_date, life_months=_life(a, cat),
        on=today)


def _life_info(a: Asset, cat: AssetCategory) -> tuple:
    from app.services.asset_depreciation import DEFAULT_LIFE_MONTHS
    if a.useful_life_months:
        return a.useful_life_months, "asset"
    if cat.default_useful_life_months:
        return cat.default_useful_life_months, "category"
    return DEFAULT_LIFE_MONTHS, "default"


def _asset_out(a: Asset, cat: AssetCategory, holder: Optional[dict],
               today: date) -> dict:
    bv = _bv(a, cat, today)
    eff, src = _life_info(a, cat)
    return {
        "id": a.id, "asset_tag": a.asset_tag, "name": a.name, "model": a.model,
        "serial_no": a.serial_no, "status": a.status,
        "category": {"id": cat.id, "name": cat.name, "code": cat.code},
        "location_id": a.location_id, "vendor": a.vendor,
        "invoice_no": a.invoice_no, "purchase_date": _iso(a.purchase_date),
        "purchase_cost_paise": a.purchase_cost_paise,
        "salvage_value_paise": a.salvage_value_paise,
        "useful_life_months": a.useful_life_months,
        "effective_useful_life_months": eff, "life_source": src,
        "warranty_expiry": _iso(a.warranty_expiry),
        "amc_vendor": a.amc_vendor, "amc_expiry": _iso(a.amc_expiry),
        "notes": a.notes, "created_at": _iso(a.created_at),
        "holder": holder,
        "book_value_paise": bv.book_value_paise if bv else None,
    }


async def _holder(db, asset_id: int) -> Optional[dict]:
    row = (await db.execute(
        select(Employee.id, Employee.employee_id, User.full_name)
        .select_from(EmployeeAsset)
        .join(Employee, Employee.id == EmployeeAsset.employee_id)
        .join(User, User.id == Employee.user_id)
        .where(EmployeeAsset.asset_id == asset_id,
               EmployeeAsset.status == "allocated")
        .order_by(EmployeeAsset.id.desc()).limit(1))).first()
    return ({"employee_id": row[0], "emp_code": row[1], "name": row[2]}
            if row else None)


async def _detail(db, asset_id: int) -> dict:
    db.expire_all()
    a = (await db.execute(select(Asset).where(Asset.id == asset_id)
                          .execution_options(populate_existing=True))
         ).scalars().first()
    if a is None:
        raise HTTPException(404, "Asset not found")
    cat = await db.get(AssetCategory, a.category_id)
    today = await local_today(db)
    out = _asset_out(a, cat, await _holder(db, a.id), today)
    bv = _bv(a, cat, today)
    out["depreciation"] = (
        {"cost_paise": bv.cost_paise, "salvage_paise": bv.salvage_paise,
         "life_months": bv.life_months, "months_elapsed": bv.months_elapsed,
         "accumulated_paise": bv.accumulated_paise,
         "book_value_paise": bv.book_value_paise,
         "fully_depreciated": bv.fully_depreciated} if bv else None)
    emp_user = aliased(User)
    by_user = aliased(User)
    ret_user = aliased(User)
    rows = (await db.execute(
        select(EmployeeAsset, Employee.employee_id, emp_user.full_name,
               by_user.full_name, ret_user.full_name)
        .join(Employee, Employee.id == EmployeeAsset.employee_id)
        .join(emp_user, emp_user.id == Employee.user_id)
        .outerjoin(by_user, by_user.id == EmployeeAsset.allocated_by_id)
        .outerjoin(ret_user, ret_user.id == EmployeeAsset.returned_to_id)
        .where(EmployeeAsset.asset_id == a.id)
        .order_by(EmployeeAsset.id.desc()))).all()
    out["history"] = [{
        "id": al.id, "employee_id": al.employee_id, "emp_code": code,
        "employee_name": ename, "issued_date": _iso(al.issued_date),
        "returned_date": _iso(al.returned_date), "status": al.status,
        "condition": al.condition, "returned_condition": al.returned_condition,
        "remarks": al.remarks, "allocated_by": bname, "returned_to": rname,
    } for al, code, ename, bname, rname in rows]
    ms = (await db.execute(
        select(AssetMaintenance).where(AssetMaintenance.asset_id == a.id)
        .order_by(AssetMaintenance.started_on.desc(),
                  AssetMaintenance.id.desc()))).scalars().all()
    out["maintenance"] = [{
        "id": m.id, "kind": m.kind, "description": m.description,
        "vendor": m.vendor, "cost_paise": m.cost_paise,
        "started_on": _iso(m.started_on), "completed_on": _iso(m.completed_on),
    } for m in ms]
    out["maintenance_cost_total_paise"] = sum(m.cost_paise or 0 for m in ms)
    return out


async def _lock(db, asset_id: int) -> Asset:
    try:
        return await svc.get_asset_for_update(db, asset_id)
    except LookupError:
        raise HTTPException(404, "Asset not found")


async def _active_category(db, category_id: int) -> AssetCategory:
    cat = await db.get(AssetCategory, category_id)
    if cat is None or not cat.is_active:
        raise HTTPException(422, "Category must exist and be active")
    return cat


async def _name_or_code_taken(db, name=None, code=None, exclude_id=None) -> bool:
    conds = []
    if name is not None:
        conds.append(func.lower(AssetCategory.name) == name.lower())
    if code is not None:
        conds.append(func.lower(AssetCategory.code) == code.lower())
    q = select(AssetCategory.id).where(or_(*conds))
    if exclude_id:
        q = q.where(AssetCategory.id != exclude_id)
    return (await db.execute(q.limit(1))).first() is not None


# ── categories ───────────────────────────────────────────────────────────
@router.get("/categories")
async def list_categories(db: deps.DBDep) -> Any:
    rows = (await db.execute(
        select(AssetCategory).order_by(AssetCategory.name))).scalars().all()
    return [_cat_out(c) for c in rows]


@router.post("/categories")
@guard_conflicts
async def create_category(db: deps.DBDep, body: CategoryIn) -> Any:
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Name is required")
    if not _CODE_RE.match(body.code):
        raise HTTPException(422, "Code must be 2-10 characters of A-Z and 0-9")
    if await _name_or_code_taken(db, name, body.code):
        raise HTTPException(409, "A category with this name or code exists")
    c = AssetCategory(name=name, code=body.code,
                      default_useful_life_months=body.default_useful_life_months)
    db.add(c)
    await commit_or_409(db, "A category with this name or code exists")
    return _cat_out(c)


@router.patch("/categories/{category_id}")
@guard_conflicts
async def patch_category(db: deps.DBDep, category_id: int,
                         body: CategoryPatch) -> Any:
    c = (await db.execute(select(AssetCategory).where(
        AssetCategory.id == category_id).with_for_update())).scalars().first()
    if c is None:
        raise HTTPException(404, "Category not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data:
        data["name"] = (data["name"] or "").strip()
        if not data["name"]:
            raise HTTPException(422, "Name is required")
        if await _name_or_code_taken(db, name=data["name"], exclude_id=c.id):
            raise HTTPException(409, "A category with this name exists")
    if data.get("is_active") is None:
        data.pop("is_active", None)
    for k, v in data.items():
        setattr(c, k, v)
    await commit_or_409(db, "A category with this name exists")
    return _cat_out(c)


# ── summary / by-tag (static, before /{asset_id}) ────────────────────────
@router.get("/summary")
async def summary(db: deps.DBDep) -> Any:
    today = await local_today(db)
    by_status = {s: 0 for s in (
        AssetStatus.IN_STOCK, AssetStatus.ALLOCATED, AssetStatus.IN_REPAIR,
        AssetStatus.RETIRED, AssetStatus.LOST)}
    for st, n in (await db.execute(
            select(Asset.status, func.count()).group_by(Asset.status))).all():
        by_status[st] = n
    by_cat = [{"id": i, "name": n, "count": c} for i, n, c in (await db.execute(
        select(AssetCategory.id, AssetCategory.name, func.count(Asset.id))
        .outerjoin(Asset, Asset.category_id == AssetCategory.id)
        .group_by(AssetCategory.id, AssetCategory.name)
        .order_by(AssetCategory.name))).all()]
    end = today + timedelta(days=30)
    live = Asset.status.notin_([AssetStatus.RETIRED, AssetStatus.LOST])
    expiring = (await db.execute(
        select(func.count()).select_from(Asset).where(
            live, or_(Asset.warranty_expiry.between(today, end),
                      Asset.amc_expiry.between(today, end))))).scalar_one()
    total_cost = (await db.execute(select(func.coalesce(
        func.sum(Asset.purchase_cost_paise), 0)))).scalar_one()
    book_total = 0
    for a, cat in (await db.execute(
            select(Asset, AssetCategory).join(
                AssetCategory, AssetCategory.id == Asset.category_id)
            .where(Asset.purchase_cost_paise.is_not(None),
                   Asset.purchase_date.is_not(None)))).all():
        bv = _bv(a, cat, today)
        if bv:
            book_total += bv.book_value_paise
    return {"by_status": by_status, "by_category": by_cat,
            "expiring_30d": expiring, "total_cost_paise": int(total_cost),
            "total_book_value_paise": book_total}


@router.get("/by-tag/{tag}")
async def by_tag(db: deps.DBDep, tag: str) -> Any:
    aid = (await db.execute(select(Asset.id).where(
        func.upper(Asset.asset_tag) == tag.strip().upper()))).scalar()
    if aid is None:
        raise HTTPException(404, "Asset not found")
    return await _detail(db, aid)


# ── list / create ────────────────────────────────────────────────────────
@router.get("")
async def list_assets(
    db: deps.DBDep,
    status: Optional[Literal[
        "in_stock", "allocated", "in_repair", "retired", "lost"]] = None,
    category_id: Optional[int] = None,
    location_id: Optional[int] = None,
    q: Optional[str] = None,
    expiring_within_days: Optional[int] = Query(default=None, ge=0, le=3650),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Any:
    alloc_join = and_(EmployeeAsset.asset_id == Asset.id,
                      EmployeeAsset.status == "allocated")
    base = (select(Asset, AssetCategory, Employee.id, Employee.employee_id,
                   User.full_name)
            .join(AssetCategory, AssetCategory.id == Asset.category_id)
            .outerjoin(EmployeeAsset, alloc_join)
            .outerjoin(Employee, Employee.id == EmployeeAsset.employee_id)
            .outerjoin(User, User.id == Employee.user_id))
    conds = []
    if status:
        conds.append(Asset.status == status)
    if category_id:
        conds.append(Asset.category_id == category_id)
    if location_id:
        conds.append(Asset.location_id == location_id)
    if q and q.strip():
        like = "%" + q.strip().replace("\\", "\\\\").replace(
            "%", "\\%").replace("_", "\\_") + "%"
        conds.append(or_(
            Asset.asset_tag.ilike(like, escape="\\"),
            Asset.name.ilike(like, escape="\\"),
            Asset.serial_no.ilike(like, escape="\\"),
            User.full_name.ilike(like, escape="\\")))
    if expiring_within_days is not None:
        today = await local_today(db)
        end = today + timedelta(days=expiring_within_days)
        conds.append(Asset.status.notin_(
            [AssetStatus.RETIRED, AssetStatus.LOST]))
        conds.append(or_(Asset.warranty_expiry.between(today, end),
                         Asset.amc_expiry.between(today, end)))
    total = (await db.execute(
        select(func.count(func.distinct(Asset.id)))
        .select_from(Asset)
        .join(AssetCategory, AssetCategory.id == Asset.category_id)
        .outerjoin(EmployeeAsset, alloc_join)
        .outerjoin(Employee, Employee.id == EmployeeAsset.employee_id)
        .outerjoin(User, User.id == Employee.user_id)
        .where(*conds))).scalar_one()
    rows = (await db.execute(
        base.where(*conds).order_by(Asset.id.desc())
        .limit(limit).offset(offset))).all()
    today = await local_today(db)
    items = [_asset_out(a, cat, {"employee_id": eid, "emp_code": code,
                                 "name": name} if eid else None, today)
             for a, cat, eid, code, name in rows]
    return {"items": items, "total": total}


@router.post("")
@guard_conflicts
async def create_asset(db: deps.DBDep, current_user: deps.CurrentUser,
                       body: AssetIn) -> Any:
    actor = plain_actor(current_user)

    async def fn():
        explicit = (body.asset_tag or "").strip().upper()
        if not explicit:
            # First statement of the attempt: take the category lock before
            # any consistent read so the snapshot is taken after the wait.
            await db.execute(select(AssetCategory.id).where(
                AssetCategory.id == body.category_id).with_for_update())
        cat = await _active_category(db, body.category_id)
        if body.purchase_date and body.purchase_date > await local_today(db):
            raise HTTPException(422, "Purchase date cannot be in the future")
        await _check_location(db, body.location_id)
        tag = explicit
        if tag:
            if not _TAG_RE.match(tag):
                raise HTTPException(
                    422, "Asset tag must be 3-32 characters of A-Z, 0-9, -")
            if (await db.execute(select(Asset.id).where(
                    func.upper(Asset.asset_tag) == tag))).first():
                raise HTTPException(409, "Asset tag already exists")
        else:
            tag = await svc.next_asset_tag(db, cat)
        data = body.model_dump(exclude={"asset_tag", "category_id"})
        a = Asset(asset_tag=tag, category_id=cat.id,
                  status=AssetStatus.IN_STOCK, created_by_id=actor.id, **data)
        db.add(a)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            if _errno(exc) == 1062:
                raise HTTPException(409, "Asset tag already exists")
            raise
        return a.id

    new_id = await retry_on_lock(db, fn, commit=True)
    return await _detail(db, new_id)


# ── detail / patch ───────────────────────────────────────────────────────
@router.get("/{asset_id}/qr.svg")
async def qr_svg(db: deps.DBDep, asset_id: int) -> Response:
    tag = (await db.execute(select(Asset.asset_tag).where(
        Asset.id == asset_id))).scalar()
    if tag is None:
        raise HTTPException(404, "Asset not found")
    buf = io.BytesIO()
    segno.make(tag, error="m").save(buf, kind="svg", scale=4, border=2)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")


@router.get("/{asset_id}")
async def get_asset(db: deps.DBDep, asset_id: int) -> Any:
    return await _detail(db, asset_id)


@router.patch("/{asset_id}")
@guard_conflicts
async def patch_asset(db: deps.DBDep, asset_id: int, body: AssetPatch) -> Any:
    a = await _lock(db, asset_id)
    data = body.model_dump(exclude_unset=True)
    if "category_id" in data:
        if data["category_id"] is None:
            raise HTTPException(422, "category_id cannot be null")
        if data["category_id"] != a.category_id:
            await _active_category(db, data["category_id"])
    if data.get("name") is None:
        data.pop("name", None)
    if data.get("salvage_value_paise") is None:
        data.pop("salvage_value_paise", None)
    if data.get("location_id") is not None:
        await _check_location(db, data["location_id"])
    pd = data.get("purchase_date")
    if pd and pd > await local_today(db):
        raise HTTPException(422, "Purchase date cannot be in the future")
    for k, v in data.items():
        setattr(a, k, v)
    await commit_or_409(db)
    return await _detail(db, asset_id)


# ── state transitions ────────────────────────────────────────────────────
async def _transition(db, asset_id: int, fn) -> dict:
    """Lock the asset, apply fn, commit. A lock conflict retries on a fresh
    snapshot, so the business state is re-evaluated (second allocate of the
    same asset gets the proper 409, never a second success)."""
    async def attempt():
        a = await _lock(db, asset_id)
        try:
            await fn(a)
        except svc.AssetStateError as e:
            await db.rollback()
            raise HTTPException(409, str(e))
        except LookupError as e:
            await db.rollback()
            raise HTTPException(404, str(e))

    await retry_on_lock(db, attempt, commit=True)
    return await _detail(db, asset_id)


@router.post("/{asset_id}/allocate")
@guard_conflicts
async def allocate(db: deps.DBDep, current_user: deps.CurrentUser,
                   asset_id: int, body: AllocateIn) -> Any:
    actor = plain_actor(current_user)

    async def go(a):
        emp = await db.get(Employee, body.employee_id)
        if emp is None:
            raise LookupError("Employee not found")
        await svc.allocate(db, asset=a, employee=emp, actor=actor,
                           issued_date=body.issued_date,
                           condition=body.condition, remarks=body.remarks)
    return await _transition(db, asset_id, go)


@router.post("/{asset_id}/return")
@guard_conflicts
async def return_(db: deps.DBDep, current_user: deps.CurrentUser,
                  asset_id: int, body: ReturnIn) -> Any:
    actor = plain_actor(current_user)

    async def go(a):
        await svc.return_asset(
            db, asset=a, actor=actor, returned_date=body.returned_date,
            condition=body.condition, remarks=body.remarks,
            to_status=body.to_status)
    return await _transition(db, asset_id, go)


@router.post("/{asset_id}/lost")
@guard_conflicts
async def lost(db: deps.DBDep, current_user: deps.CurrentUser,
               asset_id: int, body: LostIn) -> Any:
    actor = plain_actor(current_user)

    async def go(a):
        await svc.mark_lost(db, asset=a, actor=actor,
                            remarks=body.remarks)
    return await _transition(db, asset_id, go)


@router.post("/{asset_id}/status")
@guard_conflicts
async def set_status(db: deps.DBDep, current_user: deps.CurrentUser,
                     asset_id: int, body: StatusIn) -> Any:
    actor = plain_actor(current_user)

    async def go(a):
        await svc.set_status(db, asset=a, actor=actor,
                             to_status=body.to_status, remarks=body.remarks)
    return await _transition(db, asset_id, go)
