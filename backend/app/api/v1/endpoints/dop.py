"""/dop: admin API for manager kinds and assignments, posts, acting covers and
the approver check. Needs 'dop manage' (router level), not attendance-gated.

Every mutation is ONE retried transaction (see services/dop/assignments.py):
commit first, take the reporting lock, write through a service, commit. The
body returns plain values; the response is re-read afterwards with fresh
queries. Handlers capture the actor id before anything commits or rolls back
(an expired `current_user` cannot be read again)."""
import re
from datetime import date
from typing import Annotated, Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import (
    AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, StrictBool,
    StrictInt, StringConstraints, model_validator,
)
from sqlalchemy import or_, select

from app.api import deps
from app.api.v1.endpoints.roster_common import guard_conflicts, retry_on_lock
from app.models.approver_delegation import ApproverDelegation
from app.models.department import Department
from app.models.dop import (
    ActingAssignment, ManagerAssignment, ManagerKind, Post, PostHolder,
)
from app.models.employee import Employee
from app.models.user import Role, User
from app.services.approver_delegation import user_names
from app.services.dop import acting as AC
from app.services.dop import assignments as A
from app.services.dop import posts as PS
from app.services.dop import resolver as R
from app.services.dop import subdomains as S
from app.services.dop.world import load_people, load_world
from app.services.org_time import local_today

router = APIRouter(dependencies=[Depends(deps.check_permissions(["dop manage"]))])

# ------------------------------------------------------------------ schemas


def _str_date(v):
    if not isinstance(v, str):
        raise ValueError("Use a date written YYYY-MM-DD")
    return v


def _sane(d: date) -> date:
    if not date(2000, 1, 1) <= d <= date(2100, 12, 31):
        raise ValueError("Date must be between 2000 and 2100")
    return d


def _blank_none(v):
    return v or None


D = Annotated[date, BeforeValidator(_str_date), AfterValidator(_sane)]
Id = Annotated[StrictInt, Field(ge=1, le=2**31 - 1)]


def _no_ctl(v: str, keep="") -> str:
    """Free text may not carry NUL or other control characters (a note may
    keep newline, carriage return and tab)."""
    if any((ord(c) < 32 or ord(c) == 127) and c not in keep for c in v):
        raise ValueError("Control characters are not allowed")
    return v


def _text(n, min_length=0, keep=""):
    return Annotated[str, StringConstraints(
        strip_whitespace=True, min_length=min_length, max_length=n),
        AfterValidator(lambda v: _no_ctl(v, keep))]


def _clean_q(v: str) -> str:
    try:
        return _no_ctl(v)
    except ValueError as e:
        raise HTTPException(422, str(e))


Note = Annotated[Optional[_text(255, keep="\n\r\t")],
                 AfterValidator(_blank_none)]
Sub = _text(40)


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KindIn(_M):
    code: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,39}$")]
    name: _text(80, 1)
    sort_order: Annotated[StrictInt, Field(ge=0, le=10000)] = 0


class KindPatch(_M):
    name: Optional[_text(80, 1)] = None
    sort_order: Optional[Annotated[StrictInt, Field(ge=0, le=10000)]] = None
    is_active: Optional[StrictBool] = None


class BulkIn(_M):
    kind_id: Id
    user_ids: Optional[list[Id]] = Field(None, min_length=1, max_length=200)
    scope_type: Optional[Literal["department", "location", "company"]] = None
    scope_department_id: Optional[Id] = None
    scope_location: Optional[_text(100)] = None
    manager_user_id: Optional[Id] = None
    manager_post_id: Optional[Id] = None
    subdomains: list[Sub] = Field(default_factory=list, max_length=20)
    starts_on: D
    ends_on: Optional[D] = None
    note: Note = None
    replace: StrictBool = False

    @model_validator(mode="after")
    def _one_target(self):
        if (self.user_ids is None) == (self.scope_type is None):
            raise ValueError("Give either user_ids or a scope_type")
        if self.user_ids is not None and (
                self.scope_department_id or self.scope_location):
            raise ValueError("user_ids cannot be combined with a scope target")
        return self


class EndIn(_M):
    ends_on: D


class PostIn(_M):
    code: _text(40, 1)
    title: _text(120, 1)
    department_id: Optional[Id] = None
    location: Optional[_text(100)] = None
    parent_post_id: Optional[Id] = None
    heads_department_id: Optional[Id] = None
    is_active: StrictBool = True


class PostPatch(_M):
    code: Optional[_text(40, 1)] = None
    title: Optional[_text(120, 1)] = None
    department_id: Optional[Id] = None
    location: Optional[_text(100)] = None
    parent_post_id: Optional[Id] = None
    heads_department_id: Optional[Id] = None
    is_active: Optional[StrictBool] = None


class HolderIn(_M):
    user_id: Id
    starts_on: Optional[D] = None
    ends_on: Optional[D] = None


class RemoveHolderIn(_M):
    reopen_previous: StrictBool = False


class ActingIn(_M):
    acting_user_id: Id
    covers_user_id: Optional[Id] = None
    covers_post_id: Optional[Id] = None
    subdomains: list[Sub] = Field(default_factory=list, max_length=20)
    starts_on: Optional[D] = None
    ends_on: Optional[D] = None
    original_can_act: StrictBool = False
    only_when_on_leave: StrictBool = False
    reason: Note = None


class ActingPatch(_M):
    original_can_act: Optional[StrictBool] = None
    ends_on: Optional[D] = None
    reason: Note = None


class ApproverIn(_M):
    type: _text(40)
    ref: Optional[Union[_text(100), StrictInt]] = None


class CheckAllIn(_M):
    subdomain: _text(40)
    on_date: Optional[D] = None
    approver: ApproverIn
    fallback: Optional[ApproverIn] = None


class CheckIn(CheckAllIn):
    user_id: Id


# ------------------------------------------------------------------ plumbing

async def _tx(db, work):
    """The one shape every mutation takes (see the module docstring). `work`
    takes no arguments and returns plain values."""
    async def body():
        await db.commit()                 # fresh snapshot; locks come first
        await A.lock_reporting(db)
        return await work()
    try:
        return await retry_on_lock(db, body, commit=True)
    except HTTPException:
        await db.rollback()
        raise


def _iso(d):
    return d.isoformat() if d else None


def _status(starts_on, ends_on, today, *, revoked=False, cancelled=False):
    if cancelled:
        return "cancelled"
    if revoked:
        return "revoked"
    if ends_on is not None and ends_on < today:
        return "ended"
    return "scheduled" if starts_on > today else "live"


def _live_or_future(model, today):
    return or_(model.ends_on.is_(None), model.ends_on >= today)


async def _dept_names(db) -> dict:
    return dict((await db.execute(
        select(Department.id, Department.name))).all())


async def _post_titles(db, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict((await db.execute(select(Post.id, Post.title).where(
        Post.id.in_(ids)))).all())


def _nm(names, uid):
    return names.get(uid, f"User {uid}") if uid else None


# ---------------------------------------------------------------------- meta

@router.get("/meta")
async def meta(db: deps.DBDep):
    kinds = (await db.execute(select(ManagerKind).order_by(
        ManagerKind.sort_order, ManagerKind.id))).scalars().all()
    depts = (await db.execute(select(Department.id, Department.name).where(
        Department.is_active.is_(True)).order_by(Department.name))).all()
    locs = set((await db.execute(select(Employee.location).distinct())
                ).scalars().all())
    locs |= set((await db.execute(select(User.location).distinct())
                 ).scalars().all())
    roles = (await db.execute(select(Role.name).order_by(Role.name))
             ).scalars().all()
    return {
        "kinds": [_kind_dict(k) for k in kinds],
        "subdomains": [{"code": c, "name": n} for c, n in S.SUBDOMAINS.items()],
        "scopes": list(A.SCOPES),
        "departments": [{"id": i, "name": n} for i, n in depts],
        "locations": sorted(x.strip() for x in locs if x and x.strip()),
        "roles": list(roles),
        "approver_types": list(R.APPROVER_TYPES),
    }


@router.get("/people")
async def people(db: deps.DBDep, q: str = Query("", max_length=100)):
    stmt = select(User.id, User.full_name, User.email).where(
        User.is_active.is_(True))
    q = _clean_q(q).strip()
    if q:
        stmt = stmt.where(or_(User.full_name.contains(q, autoescape=True),
                              User.email.contains(q, autoescape=True)))
    rows = (await db.execute(stmt.order_by(User.full_name, User.id).limit(20))
            ).all()
    return [{"id": i, "name": n or e, "email": e} for i, n, e in rows]


# --------------------------------------------------------------------- kinds

def _kind_dict(k) -> dict:
    return {"id": k.id, "code": k.code, "name": k.name,
            "sort_order": k.sort_order, "is_active": bool(k.is_active),
            "is_system": bool(k.is_system)}


async def _kind_out(db, kind_id) -> dict:
    k = (await db.execute(select(ManagerKind).where(
        ManagerKind.id == kind_id).execution_options(populate_existing=True)
    )).scalars().one()
    return _kind_dict(k)


@router.post("/kinds")
@guard_conflicts
async def create_kind(payload: KindIn, db: deps.DBDep,
                      current_user: User = Depends(deps.get_current_user)):
    aid = current_user.id
    data = payload.model_dump()

    async def work() -> int:
        if (await db.execute(select(ManagerKind.id).where(
                ManagerKind.code == data["code"]))).first():
            raise HTTPException(409, "That code is already used")
        k = ManagerKind(**data, is_active=True, is_system=False)
        db.add(k)
        await db.flush()
        A.audit(db, aid, "dop.kind.create", "manager_kind", k.id, data)
        return k.id
    return await _kind_out(db, await _tx(db, work))


@router.patch("/kinds/{kind_id}")
@guard_conflicts
async def patch_kind(kind_id: int, payload: KindPatch, db: deps.DBDep,
                     current_user: User = Depends(deps.get_current_user)):
    aid = current_user.id
    ch = payload.model_dump(exclude_unset=True)
    if any(v is None for v in ch.values()):
        raise HTTPException(422, "A field cannot be null")

    async def work() -> int:
        k = (await db.execute(
            select(ManagerKind).where(ManagerKind.id == kind_id)
            .with_for_update().execution_options(populate_existing=True)
        )).scalars().first()
        if k is None:
            raise HTTPException(404, "Manager kind not found")
        if ch.get("is_active") is False and k.is_active:
            if k.is_system:
                raise HTTPException(
                    422, "System manager kinds cannot be deactivated")
            today = await local_today(db)
            if (await db.execute(select(ManagerAssignment.id).where(
                    ManagerAssignment.manager_kind_id == k.id,
                    ManagerAssignment.cancelled_at.is_(None),
                    _live_or_future(ManagerAssignment, today)).limit(1)
            )).first():
                raise HTTPException(
                    409, "The kind has live or future assignments: end them "
                         "first")
        before = {f: getattr(k, f) for f in ch}
        for f, v in ch.items():
            setattr(k, f, v)
        await db.flush()
        A.audit(db, aid, "dop.kind.update", "manager_kind", k.id,
                {"before": before, "after": ch})
        return k.id
    return await _kind_out(db, await _tx(db, work))


# --------------------------------------------------------------- assignments

async def _assignment_items(db, rows, today) -> list:
    users = {x for r in rows for x in (
        r.scope_user_id, r.manager_user_id, r.created_by_id) if x}
    names = await user_names(db, users)
    depts, titles = await _dept_names(db), await _post_titles(
        db, [r.manager_post_id for r in rows])
    kinds = {k.id: k for k in (await db.execute(select(ManagerKind))
                               ).scalars().all()}
    return [{
        "id": r.id, "kind_id": r.manager_kind_id,
        "kind_code": kinds[r.manager_kind_id].code,
        "kind_name": kinds[r.manager_kind_id].name,
        "scope_type": r.scope_type,
        "scope_user_id": r.scope_user_id,
        "scope_user_name": _nm(names, r.scope_user_id),
        "scope_department_id": r.scope_department_id,
        "scope_department_name": depts.get(r.scope_department_id),
        "scope_location": r.scope_location,
        "manager_user_id": r.manager_user_id,
        "manager_user_name": _nm(names, r.manager_user_id),
        "manager_post_id": r.manager_post_id,
        "manager_post_title": titles.get(r.manager_post_id),
        "subdomains": list(r.subdomains or []),
        "starts_on": _iso(r.starts_on), "ends_on": _iso(r.ends_on),
        "note": r.note,
        "status": _status(r.starts_on, r.ends_on, today,
                          cancelled=r.cancelled_at is not None),
        "created_by_id": r.created_by_id,
        "created_by_name": _nm(names, r.created_by_id)} for r in rows]


async def _assignments_by_ids(db, ids) -> list:
    rows = (await db.execute(
        select(ManagerAssignment).where(ManagerAssignment.id.in_(ids))
        .order_by(ManagerAssignment.id)
        .execution_options(populate_existing=True))).scalars().all()
    return await _assignment_items(db, rows, await local_today(db))


@router.get("/assignments")
async def list_assignments(
        db: deps.DBDep, user_id: Optional[int] = Query(None, ge=1),
        kind_id: Optional[int] = Query(None, ge=1), history: bool = False,
        manager_user_id: Optional[int] = Query(None, ge=1),
        limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0)):
    """Live and future rows (history=true: also ended and cancelled). With
    user_id: the rows that apply to that employee (their own, their
    department's, their location's, company-wide)."""
    today = await local_today(db)
    stmt = select(ManagerAssignment)
    if kind_id:
        stmt = stmt.where(ManagerAssignment.manager_kind_id == kind_id)
    if manager_user_id:
        posts = (await db.execute(select(PostHolder.post_id).where(
            PostHolder.user_id == manager_user_id,
            _live_or_future(PostHolder, today)))).scalars().all()
        stmt = stmt.where(or_(
            ManagerAssignment.manager_user_id == manager_user_id,
            ManagerAssignment.manager_post_id.in_(posts or [-1])))
    if not history:
        stmt = stmt.where(ManagerAssignment.cancelled_at.is_(None),
                          _live_or_future(ManagerAssignment, today))
    rows = (await db.execute(stmt.order_by(
        ManagerAssignment.id.desc()).execution_options(
        populate_existing=True))).scalars().all()
    if user_id:
        p = (await load_people(db)).get(user_id)
        dnames = await _dept_names(db)
        dept, loc = R.norm(p.department) if p else "", (
            R.norm(p.location) if p else "")

        def applies(r):
            return (
                (r.scope_type == "user" and r.scope_user_id == user_id)
                or (r.scope_type == "department" and dept
                    and R.norm(dnames.get(r.scope_department_id)) == dept)
                or (r.scope_type == "location" and loc
                    and R.norm(r.scope_location) == loc)
                or r.scope_type == "company")
        rows = [r for r in rows if applies(r)]
    return {"items": await _assignment_items(
        db, rows[offset:offset + limit], today), "total": len(rows),
        "limit": limit, "offset": offset}


@router.post("/assignments/bulk")
@guard_conflicts
async def bulk_assign(payload: BulkIn, db: deps.DBDep,
                      current_user: User = Depends(deps.get_current_user)):
    aid = current_user.id
    kw = payload.model_dump(exclude={"user_ids", "replace", "scope_type"})

    async def work() -> dict:
        if payload.user_ids is not None:
            ids, replaced, continued = await A.create_many(
                db, actor_id=aid, user_ids=payload.user_ids,
                replace=payload.replace,
                **{k: v for k, v in kw.items()
                   if k not in ("scope_department_id", "scope_location")})
        else:
            t = {**kw, "scope_type": payload.scope_type}
            replaced, continued = (
                await A.replace_overlaps(db, actor_id=aid, **t)
                if payload.replace else (0, 0))
            ids = [(await A.create(db, actor_id=aid, **t)).id]
        return {"created": len(ids), "replaced": replaced,
                "continued": continued, "assignment_ids": ids}
    return await _tx(db, work)


@router.post("/assignments/{assignment_id}/end")
@guard_conflicts
async def end_assignment(assignment_id: int, payload: EndIn, db: deps.DBDep,
                         current_user: User = Depends(deps.get_current_user)):
    aid = current_user.id

    async def work() -> int:
        return (await A.end(db, actor_id=aid, assignment_id=assignment_id,
                            ends_on=payload.ends_on)).id
    return (await _assignments_by_ids(db, [await _tx(db, work)]))[0]


# ------------------------------------------------------------------ managers

@router.get("/managers")
async def managers(
        db: deps.DBDep, q: str = Query("", max_length=100),
        department: str = Query("", max_length=100),
        missing: Optional[str] = Query(None, max_length=40),
        managed_by: Optional[int] = Query(None, ge=1),
        include_inactive: bool = False,
        limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    """Per employee, the base manager of every active kind today (all
    subdomains, no acting cover), computed from one loaded world."""
    today = await local_today(db)
    w = await load_world(db, today)
    kinds = (await db.execute(select(ManagerKind).where(
        ManagerKind.is_active.is_(True)).order_by(
        ManagerKind.sort_order, ManagerKind.id))).scalars().all()
    if missing and missing not in {k.code for k in kinds}:
        raise HTTPException(422, "Unknown manager kind")
    emp = set((await db.execute(select(Employee.user_id))).scalars().all())
    ident = {i: (n or e, e) for i, n, e in (await db.execute(
        select(User.id, User.full_name, User.email))).all()}
    lookup = R.base_index(w, today)
    holder: dict = {}
    for h in w.holders:
        post = w.posts.get(h.post_id)
        if post and post.is_active and R.live(h, today):
            holder.setdefault(h.post_id, h.user_id)
    qn, dn = _clean_q(q).strip().casefold(), R.norm(_clean_q(department))
    named: set = set()          # people a live or future row of ANY areas
    if managed_by:              # names `managed_by`, directly or by a post
        posts = (await db.execute(select(PostHolder.post_id).where(
            PostHolder.user_id == managed_by,
            _live_or_future(PostHolder, today)))).scalars().all()
        dn_by_id = await _dept_names(db)
        for a in (await db.execute(select(ManagerAssignment).where(
                ManagerAssignment.cancelled_at.is_(None),
                _live_or_future(ManagerAssignment, today),
                or_(ManagerAssignment.manager_user_id == managed_by,
                    ManagerAssignment.manager_post_id.in_(posts or [-1])))
                )).scalars().all():
            named |= set(A._matching(
                w.people, a, dn_by_id.get(a.scope_department_id)))

    def cell(kind, uid):
        a = lookup(kind, uid)
        if a is None:
            return None
        post = w.posts.get(a.manager_post_id)
        held = (holder.get(a.manager_post_id) if post else None) \
            if a.manager_post_id else a.manager_user_id
        own = held == uid
        mgr = None if own else held
        return {"assignment_id": a.id, "source": a.scope,
                "manager_user_id": mgr,
                "manager_name": ident[mgr][0] if mgr in ident else None,
                "manager_active": (bool(w.people[mgr].active)
                                   if mgr in w.people else None),
                "post_id": a.manager_post_id,
                "post_title": post.title if post else None,
                "vacant": a.manager_post_id is not None and held is None,
                "self_managed": own}

    def has_manager(c):
        return bool(c and c["manager_user_id"] and c["manager_active"])

    out = []
    for uid, p in w.people.items():
        if uid not in emp or uid not in ident or (
                not p.active and not include_inactive):
            continue
        name, email = ident[uid]
        if qn and qn not in name.casefold() and qn not in email.casefold():
            continue
        if dn and R.norm(p.department) != dn:
            continue
        cells = {k.code: cell(k.code, uid) for k in kinds}
        if managed_by and uid != managed_by and uid not in named and not any(
                c and c["manager_user_id"] == managed_by
                for c in cells.values()):
            continue
        if managed_by and uid == managed_by:
            continue
        if missing and has_manager(cells[missing]):
            continue
        out.append({"user_id": uid, "name": name, "email": email,
                    "is_active": p.active, "department": p.department,
                    "location": p.location, "managers": cells})
    out.sort(key=lambda x: (x["name"].casefold(), x["user_id"]))
    return {"kinds": [{"id": k.id, "code": k.code, "name": k.name}
                      for k in kinds],
            "items": out[offset:offset + limit], "total": len(out),
            "limit": limit, "offset": offset}


# --------------------------------------------------------------------- posts

def _holder_dict(h, names) -> dict:
    return {"id": h.id, "holder_id": h.id, "user_id": h.user_id,
            "user_name": _nm(names, h.user_id),
            "starts_on": _iso(h.starts_on), "ends_on": _iso(h.ends_on)}


def _cover_dict(c, names, titles, today, source="acting") -> dict:
    return {
        "id": c.id, "key": f"{source}-{c.id}", "source": source,
        "read_only": False,
        "covers_user_id": c.covers_user_id,
        "covers_user_name": _nm(names, c.covers_user_id),
        "covers_post_id": c.covers_post_id,
        "covers_post_title": titles.get(c.covers_post_id),
        "acting_user_id": c.acting_user_id,
        "acting_user_name": _nm(names, c.acting_user_id),
        "subdomains": list(c.subdomains or []),
        "starts_on": _iso(c.starts_on), "ends_on": _iso(c.ends_on),
        "original_can_act": bool(c.original_can_act),
        "only_when_on_leave": bool(c.only_when_on_leave),
        "reason": c.reason,
        "status": _status(c.starts_on, c.ends_on, today,
                          revoked=c.revoked_at is not None)}


async def _post_items(db, post_ids=None, include_inactive=True) -> list:
    today = await local_today(db)
    stmt = select(Post).order_by(Post.title, Post.id).execution_options(
        populate_existing=True)
    if post_ids is not None:
        stmt = stmt.where(Post.id.in_(post_ids))
    if not include_inactive:
        stmt = stmt.where(Post.is_active.is_(True))
    posts = (await db.execute(stmt)).scalars().all()
    ids = [p.id for p in posts]
    holders = (await db.execute(
        select(PostHolder).where(
            PostHolder.post_id.in_(ids),
            _live_or_future(PostHolder, today))
        .order_by(PostHolder.starts_on, PostHolder.id)
        .execution_options(populate_existing=True))).scalars().all() \
        if ids else []
    covers = (await db.execute(
        select(ActingAssignment).where(
            ActingAssignment.covers_post_id.in_(ids),
            ActingAssignment.revoked_at.is_(None),
            _live_or_future(ActingAssignment, today))
        .order_by(ActingAssignment.id)
        .execution_options(populate_existing=True))).scalars().all() \
        if ids else []
    names = await user_names(db, {h.user_id for h in holders} | {
        x for c in covers for x in (c.acting_user_id, c.covers_user_id)})
    depts = await _dept_names(db)
    titles = dict((await db.execute(select(Post.id, Post.title))).all())
    out = []
    for p in posts:
        mine = [h for h in holders if h.post_id == p.id]
        cur = next((h for h in mine if h.starts_on <= today), None)
        nxt = next((h for h in mine if h.starts_on > today), None)
        out.append({
            "id": p.id, "code": p.code, "title": p.title,
            "department_id": p.department_id,
            "department_name": depts.get(p.department_id),
            "location": p.location, "parent_post_id": p.parent_post_id,
            "parent_post_title": titles.get(p.parent_post_id),
            "heads_department_id": p.heads_department_id,
            "heads_department_name": depts.get(p.heads_department_id),
            "is_active": bool(p.is_active),
            "holder": _holder_dict(cur, names) if cur else None,
            "next_holder": _holder_dict(nxt, names) if nxt else None,
            "acting": [_cover_dict(c, names, titles, today)
                       for c in covers if c.covers_post_id == p.id]})
    return out


async def _post_out(db, post_id) -> dict:
    rows = await _post_items(db, [post_id])
    if not rows:
        raise HTTPException(404, "Post not found")
    return rows[0]


async def _holders_out(db, post_id) -> dict:
    post = await _post_out(db, post_id)
    hist = await PS.history(db, post_id)
    names = await user_names(db, {h.user_id for h in hist})
    return {"post": post, "holders": [_holder_dict(h, names) for h in hist]}


@router.get("/posts")
async def list_posts(db: deps.DBDep, include_inactive: bool = True):
    return await _post_items(db, None, include_inactive)


@router.post("/posts")
@guard_conflicts
async def create_post(payload: PostIn, db: deps.DBDep,
                      current_user: User = Depends(deps.get_current_user)):
    aid = current_user.id
    data = payload.model_dump()

    async def work() -> int:
        return (await PS.create(db, actor_id=aid, **data)).id
    return await _post_out(db, await _tx(db, work))


@router.patch("/posts/{post_id}")
@guard_conflicts
async def patch_post(post_id: int, payload: PostPatch, db: deps.DBDep,
                     current_user: User = Depends(deps.get_current_user)):
    aid = current_user.id
    ch = payload.model_dump(exclude_unset=True)

    async def work() -> int:
        return (await PS.update(db, actor_id=aid, post_id=post_id,
                                changes=ch)).id
    return await _post_out(db, await _tx(db, work))


@router.get("/posts/{post_id}/holders")
async def post_holders(post_id: int, db: deps.DBDep):
    return await _holders_out(db, post_id)


@router.post("/posts/{post_id}/holders")
@guard_conflicts
async def add_holder(post_id: int, payload: HolderIn, db: deps.DBDep,
                     current_user: User = Depends(deps.get_current_user)):
    aid = current_user.id

    async def work() -> int:
        start = payload.starts_on or await local_today(db)
        return (await PS.assign_holder(
            db, actor_id=aid, post_id=post_id, user_id=payload.user_id,
            starts_on=start, ends_on=payload.ends_on)).post_id
    return await _holders_out(db, await _tx(db, work))


@router.post("/posts/{post_id}/holders/{holder_id}/end")
@guard_conflicts
async def end_holder(post_id: int, holder_id: int, payload: EndIn,
                     db: deps.DBDep,
                     current_user: User = Depends(deps.get_current_user)):
    aid = current_user.id

    async def work() -> int:
        return (await PS.end_holder(
            db, actor_id=aid, post_id=post_id, holder_id=holder_id,
            ends_on=payload.ends_on)).post_id
    return await _holders_out(db, await _tx(db, work))


@router.post("/posts/{post_id}/holders/{holder_id}/remove")
@guard_conflicts
async def remove_holder(post_id: int, holder_id: int,
                        db: deps.DBDep,
                        payload: Optional[RemoveHolderIn] = None,
                        current_user: User = Depends(deps.get_current_user)):
    aid = current_user.id

    async def work() -> int:
        await PS.remove_holder(
            db, actor_id=aid, post_id=post_id, holder_id=holder_id,
            reopen_previous=bool(payload and payload.reopen_previous))
        return post_id
    return await _holders_out(db, await _tx(db, work))


# -------------------------------------------------------------------- acting

async def _acting_items(db, ids=None, include_ended=False) -> list:
    today = await local_today(db)
    stmt = select(ActingAssignment).order_by(
        ActingAssignment.id.desc()).execution_options(populate_existing=True)
    dstmt = select(ApproverDelegation).order_by(
        ApproverDelegation.id.desc()).execution_options(
        populate_existing=True)
    if ids is not None:
        stmt = stmt.where(ActingAssignment.id.in_(ids))
    if ids is None and not include_ended:
        stmt = stmt.where(ActingAssignment.revoked_at.is_(None),
                          _live_or_future(ActingAssignment, today))
        dstmt = dstmt.where(ApproverDelegation.revoked_at.is_(None),
                            _live_or_future(ApproverDelegation, today))
    covers = (await db.execute(stmt)).scalars().all()
    delegs = [] if ids is not None else (
        await db.execute(dstmt)).scalars().all()
    names = await user_names(db, {
        x for c in covers for x in (c.acting_user_id, c.covers_user_id)
    } | {x for d in delegs for x in (d.user_id, d.delegate_id)})
    titles = await _post_titles(db, [c.covers_post_id for c in covers])
    out = [_cover_dict(c, names, titles, today) for c in covers]
    out += [{
        "id": d.id, "key": f"ooo-{d.id}", "source": "out_of_office",
        "read_only": True,
        "covers_user_id": d.user_id,
        "covers_user_name": _nm(names, d.user_id),
        "covers_post_id": None, "covers_post_title": None,
        "acting_user_id": d.delegate_id,
        "acting_user_name": _nm(names, d.delegate_id),
        "subdomains": [], "starts_on": _iso(d.starts_on),
        "ends_on": _iso(d.ends_on), "original_can_act": True,
        "only_when_on_leave": bool(d.only_when_on_leave), "reason": d.note,
        "status": _status(d.starts_on, d.ends_on, today,
                          revoked=d.revoked_at is not None)} for d in delegs]
    return out


@router.get("/acting")
async def list_acting(db: deps.DBDep, include_ended: bool = False):
    return await _acting_items(db, None, include_ended)


@router.post("/acting")
@guard_conflicts
async def create_acting(payload: ActingIn, db: deps.DBDep,
                        current_user: User = Depends(deps.get_current_user)):
    aid = current_user.id
    kw = payload.model_dump(exclude={"starts_on"})

    async def work() -> int:
        start = payload.starts_on or await local_today(db)
        return (await AC.create(db, actor_id=aid, starts_on=start, **kw)).id
    return (await _acting_items(db, [await _tx(db, work)]))[0]


@router.patch("/acting/{cover_id}")
@guard_conflicts
async def patch_acting(cover_id: int, payload: ActingPatch, db: deps.DBDep,
                       current_user: User = Depends(deps.get_current_user)):
    aid = current_user.id
    ch = payload.model_dump(exclude_unset=True)
    if ch.get("original_can_act", True) is None:
        raise HTTPException(422, "original_can_act must be true or false")

    async def work() -> int:
        return (await AC.update(db, actor_id=aid, cover_id=cover_id,
                                **ch)).id
    return (await _acting_items(db, [await _tx(db, work)]))[0]


@router.post("/acting/{cover_id}/revoke")
@guard_conflicts
async def revoke_acting(cover_id: int, db: deps.DBDep,
                        current_user: User = Depends(deps.get_current_user)):
    aid = current_user.id

    async def work() -> int:
        return (await AC.revoke(db, actor_id=aid, cover_id=cover_id)).id
    return (await _acting_items(db, [await _tx(db, work)]))[0]


# --------------------------------------------------------------------- check

async def _approver(db, ap: ApproverIn, what: str) -> R.Approver:
    """Validate a route's approver: a malformed or unknown reference is a
    422 here instead of a silent trip to HR."""
    if ap.type not in R.APPROVER_TYPES:
        raise HTTPException(422, f"{what}: unknown approver type")
    if ap.type in ("reporting_manager", "dept_head_of_requester"):
        return R.Approver(ap.type, None)
    ref = ap.ref if ap.ref is None else str(ap.ref).strip()
    if not ref:
        raise HTTPException(422, f"{what}: a reference is needed")
    if ap.type in ("specific_user", "post"):
        if not re.fullmatch(r"[0-9]{1,10}", ref):
            raise HTTPException(422, f"{what}: reference must be an id")
        model = User if ap.type == "specific_user" else Post
        if (await db.execute(select(model.id).where(
                model.id == int(ref)))).first() is None:
            raise HTTPException(422, f"{what}: person or post not found")
        ref = str(int(ref))
    elif ap.type == "role":
        if (await db.execute(select(Role.id).where(
                Role.name == ref))).first() is None:
            raise HTTPException(422, f"{what}: role not found")
    else:
        if (await db.execute(select(ManagerKind.id).where(
                ManagerKind.code == ref))).first() is None:
            raise HTTPException(422, f"{what}: manager kind not found")
    return R.Approver(ap.type, ref)


async def _check_args(db, p: CheckAllIn):
    if p.subdomain not in S.SUBDOMAINS:
        raise HTTPException(422, "Unknown subdomain")
    ap = await _approver(db, p.approver, "Approver")
    fb = await _approver(db, p.fallback, "Fallback") if p.fallback else None
    on = p.on_date or await local_today(db)
    return ap, fb, on


_REF = re.compile(r"\x02(\d+)\x03")


def _ids_in(lines) -> set:
    return {int(m) for line in lines for m in _REF.findall(line)}


def _named(line, names) -> str:
    return _REF.sub(lambda m: _nm(names, int(m.group(1))), line)


@router.post("/check")
async def check(payload: CheckIn, db: deps.DBDep):
    ap, fb, on = await _check_args(db, payload)
    if (await db.execute(select(User.id).where(
            User.id == payload.user_id))).first() is None:
        raise HTTPException(422, "Employee not found")
    w = await load_world(db, on)
    try:
        res = R.resolve(w, ap, fb, payload.user_id, payload.subdomain, on)
    except ValueError as e:
        raise HTTPException(422, str(e))
    names = await user_names(db, {payload.user_id, *res.user_ids,
                                  *res.acting_for,
                                  *(x for v in res.acting_for.values()
                                    for x in v)} | _ids_in(res.explanation))
    return {
        "user_id": payload.user_id, "user_name": _nm(names, payload.user_id),
        "subdomain": payload.subdomain, "on_date": _iso(on), "via": res.via,
        "approvers": [{"user_id": i, "name": _nm(names, i)}
                      for i in res.user_ids],
        "acting_for": [{"user_id": a, "name": _nm(names, a), "covers": [
            {"user_id": c, "name": _nm(names, c)} for c in cov]}
            for a, cov in res.acting_for.items()],
        "via_post": ({"id": res.via_post_id,
                      "title": w.posts[res.via_post_id].title}
                     if res.via_post_id in w.posts else None),
        "explanation": [_named(x, names) for x in res.explanation]}


@router.post("/check/all")
async def check_all(payload: CheckAllIn, db: deps.DBDep):
    """Resolve the route for every active employee from one world."""
    ap, fb, on = await _check_args(db, payload)
    w = await load_world(db, on)
    emp = set((await db.execute(select(Employee.user_id))).scalars().all())
    ident = {i: (n or e) for i, n, e in (await db.execute(
        select(User.id, User.full_name, User.email))).all()}
    checked, hits = 0, {"blocked": [], "hr": []}
    for uid, p in w.people.items():
        if uid not in emp or not p.active:
            continue
        checked += 1
        try:
            res = R.resolve(w, ap, fb, uid, payload.subdomain, on)
        except ValueError as e:
            raise HTTPException(422, str(e))
        if res.via in hits:
            hits[res.via].append((ident.get(uid, str(uid)).casefold(), uid,
                                  p.department, res.explanation))
    out = {"checked": checked, "on_date": _iso(on)}
    shown = {}
    for key, rows in hits.items():
        rows.sort(key=lambda r: (r[0], r[1]))
        shown[key] = rows[:200]
    names = await user_names(db, _ids_in(
        line for rows in shown.values() for r in rows for line in r[3]))
    for key, label in (("blocked", "blocked"), ("hr", "via_hr")):
        out[f"{label}_count"] = len(hits[key])
        out[label] = [{
            "user_id": uid, "name": ident.get(uid, str(uid)),
            "department": dept,
            "reason": "; ".join(_named(x, names) for x in log)}
            for _, uid, dept, log in shown[key]]
    out["truncated"] = any(len(hits[k]) > 200 for k in hits)
    return out
