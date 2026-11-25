# DOP D1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let admin assign several managers per employee, maintain posts and acting covers, and check who would act on a request and why, without changing any live approval.

**Architecture:** A pure resolver (`services/dop/resolver.py`) answers "who acts" from an in-memory `World`; a loader builds the World from the DB. Write services own all validation and locking. `User.manager_id` becomes a mirror of the reporting assignment, so every existing reader is untouched. Live engines do not call the resolver until D2.

**Tech Stack:** FastAPI, async SQLAlchemy, MariaDB 11.8, Alembic; React (web).

Spec: `docs/superpowers/specs/2026-11-25-dop-delegation-of-powers-design.md`, sections 1, 2, 6 and 7. Branch `feature/dop-approvals` (off main e4079c2). Migration head at start: `a6b8d0f2c4e7`.

## D1 boundaries

- `ApproverDelegation` stays in charge of live out-of-office cover. The resolver **reads** live delegations as covers with `original_can_act=True`. Replacing the table moves to D2, together with enforcing `original_can_act=False`.
- Rules, step jobs, override and inbox are D2. Access control is A1.
- `manager_id` changes only when someone edits a manager or an assignment.

## Environment (all tasks)

- Tests: `docker exec erp-united-exploration-dev-backend-1 python -m pytest tests/<file> -q -p no:cacheprovider -W ignore`. They run on the real dev DB: teardown leaves zero rows; users end in `@test.com`.
- Tests **must be run live** in the task that writes them. 6A shipped 57 failing tests because they were not.
- Locking helpers are in `backend/app/api/v1/endpoints/roster_common.py` (`guard_conflicts`, `retry_on_lock`, `plain_actor`, `commit_or_409`). Never read `current_user` after `expire_all()` or a rollback; capture `plain_actor(current_user)` first.
- Do not use `hr.log_audit` inside a transaction (it commits). Add `AuditLog` rows directly.
- "Today" is `await local_today(db)` (guard test `tests/test_org_time_guard.py`).
- Frontend: pre-compiled CSS, so use only classes already in `frontend/src/index.css`. tsc baseline 164: `docker exec erp-united-exploration-dev-frontend-1 sh -c 'cd /app && npx -y -p typescript@5.6.3 tsc --noEmit -p . 2>&1 | grep -c "error TS"'`.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push. Test migrations on a cloned DB, never by downgrading the dev DB.

## File map

| Path | Responsibility |
|---|---|
| `backend/app/models/dop.py` | all D1 tables |
| `backend/alembic/versions/b7d9f1a3c5e8_dop_d1_foundation.py` | tables, seed kinds, backfill, permission |
| `backend/app/services/dop/__init__.py` | empty |
| `backend/app/services/dop/subdomains.py` | fixed subdomain list |
| `backend/app/services/dop/resolver.py` | pure resolution |
| `backend/app/services/dop/world.py` | DB → World |
| `backend/app/services/dop/assignments.py` | manager assignment writes, mirror sync |
| `backend/app/services/dop/posts.py` | posts and holders |
| `backend/app/services/dop/acting.py` | acting covers |
| `backend/app/api/v1/endpoints/dop.py` | `/dop` API |
| `backend/tests/test_dop_*.py`, `backend/tests/_dop_world.py` | tests, shared fixture |
| `frontend/src/components/dop/*` | Managers, Posts, Acting, Check tabs |

---

### Task 1: Subdomains and pure resolver

**Files:** Create `backend/app/services/dop/__init__.py`, `subdomains.py`, `resolver.py`; Test `backend/tests/test_dop_resolver.py`

- [ ] **Step 1: Write the failing tests**

```python
"""DOP D1: pure resolver. No DB."""
from datetime import date

import pytest

from app.services.dop import resolver as R

D = date(2030, 6, 10)
P = R.Person


def world(**kw):
    base = dict(
        people={i: P(i, True, "Eng", "Mumbai") for i in range(1, 10)},
        kinds={"reporting", "functional"}, assignments=[], posts={},
        holders=[], covers=[], heads={}, role_users={}, hr_ids=[9])
    base.update(kw)
    return R.World(**base)


def asg(id, mgr, scope="user", kind="reporting", user=1, dept=None, loc=None,
        post=None, start=date(2020, 1, 1), end=None, subs=()):
    return R.Assignment(id, kind, scope, user if scope == "user" else None,
                        dept, loc, mgr, post, start, end, frozenset(subs))


def cover(id, acting, user=None, post=None, subs=(), original=False,
          start=D, end=D):
    return R.Cover(id, user, post, acting, frozenset(subs), start, end, original)


REPORTING = R.Approver("manager_kind", "reporting")


def go(w, approver=REPORTING, fallback=None, sub="leave", on=D, requester=1):
    return R.resolve(w, approver, fallback, requester, sub, on)


def test_most_specific_scope_wins():
    a = [asg(1, 2, "company"), asg(2, 3, "location", loc="Mumbai"),
         asg(3, 4, "department", dept="Eng"), asg(4, 5)]
    for expected in (5, 4, 3, 2):
        assert go(world(assignments=a)).user_ids == [expected]
        a = a[:-1]


def test_named_subdomain_beats_all_at_same_scope():
    w = world(assignments=[asg(1, 2), asg(2, 3, subs={"expense"})])
    assert go(w, sub="expense").user_ids == [3]
    assert go(w, sub="leave").user_ids == [2]


def test_user_scope_all_beats_department_named():
    w = world(assignments=[asg(1, 2), asg(2, 3, "department", dept="Eng",
                                           subs={"leave"})])
    assert go(w).user_ids == [2]


def test_unrelated_subdomain_falls_through_to_wider_scope():
    w = world(assignments=[asg(1, 2, subs={"expense"}),
                           asg(2, 3, "company")])
    assert go(w, sub="leave").user_ids == [3]


def test_dates_are_inclusive():
    w = world(assignments=[asg(1, 2, start=D, end=D)])
    assert go(w).user_ids == [2]
    assert go(w, on=date(2030, 6, 11)).user_ids == [9]      # HR


def test_scope_text_ignores_case_and_spaces():
    w = world(assignments=[asg(1, 2, "location", loc="  mumBAI ")])
    assert go(w).user_ids == [2]


def test_post_manager_and_vacancy():
    posts = {7: R.Post(7, "HR Mgr", True, None)}
    w = world(assignments=[asg(1, None, post=7)], posts=posts,
              holders=[R.Holder(7, 4, date(2020, 1, 1), None)])
    assert go(w).user_ids == [4]
    vacant = world(assignments=[asg(1, None, post=7)], posts=posts)
    r = go(vacant)
    assert r.user_ids == [9] and r.via == "hr"


def test_acting_replaces_or_joins_original():
    base = dict(assignments=[asg(1, 2)])
    assert go(world(**base, covers=[cover(1, 3, user=2)])).user_ids == [3]
    r = go(world(**base, covers=[cover(1, 3, user=2, original=True)]))
    assert sorted(r.user_ids) == [2, 3]
    assert r.acting_for == {3: 2}


def test_acting_subdomain_and_no_chaining():
    w = world(assignments=[asg(1, 2)],
              covers=[cover(1, 3, user=2, subs={"expense"})])
    assert go(w, sub="leave").user_ids == [2]
    w = world(assignments=[asg(1, 2)],
              covers=[cover(1, 3, user=2), cover(2, 4, user=3)])
    assert go(w).user_ids == [3]


def test_post_cover_works_when_vacant():
    w = world(posts={7: R.Post(7, "HR Mgr", True, None)},
              covers=[cover(1, 5, post=7)])
    assert go(w, R.Approver("post", "7")).user_ids == [5]


def test_inactive_and_requester_are_dropped():
    people = {i: P(i, i != 2, "Eng", "Mumbai") for i in range(1, 10)}
    assert go(world(people=people, assignments=[asg(1, 2)])).via == "hr"
    assert go(world(assignments=[asg(1, 1)])).via == "hr"


def test_inactive_acting_keeps_original():
    people = {i: P(i, i != 3, "Eng", "Mumbai") for i in range(1, 10)}
    w = world(people=people, assignments=[asg(1, 2)],
              covers=[cover(1, 3, user=2)])
    assert go(w).user_ids == [2]


def test_fallback_then_hr_then_blocked():
    w = world(assignments=[asg(1, 4, kind="functional")])
    r = go(w, fallback=R.Approver("manager_kind", "functional"))
    assert (r.user_ids, r.via) == ([4], "fallback")
    assert go(world()).via == "hr"
    r = go(world(hr_ids=[1]))            # only HR is the requester
    assert r.via == "blocked" and r.user_ids == []


def test_department_head_post_then_head_then_deputy():
    w = world(heads={"eng": (3, 4)})
    assert go(w, R.Approver("dept_head_of_requester")).user_ids == [3]
    people = {i: P(i, i != 3, "Eng", "Mumbai") for i in range(1, 10)}
    w = world(people=people, heads={"eng": (3, 4)})
    assert go(w, R.Approver("dept_head_of_requester")).user_ids == [4]
    w = world(heads={"eng": (3, 4)}, posts={7: R.Post(7, "Head", True, "eng")},
              holders=[R.Holder(7, 5, D, None)])
    assert go(w, R.Approver("dept_head_of_requester")).user_ids == [5]


def test_person_and_role():
    assert go(world(), R.Approver("specific_user", "6")).user_ids == [6]
    w = world(role_users={"Finance": [5, 6, 1]})
    assert go(w, R.Approver("role", "Finance")).user_ids == [5, 6]


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        go(world(), R.Approver("nope"))


def test_explanation_is_readable():
    r = go(world(assignments=[asg(1, 2)], covers=[cover(1, 3, user=2)]))
    assert any("acting" in line for line in r.explanation)
```

- [ ] **Step 2: Run it.** `pytest tests/test_dop_resolver.py`. Expected: collection error, `No module named 'app.services.dop'`.

- [ ] **Step 3: Implement**

`subdomains.py`:

```python
"""Fixed areas of authority a manager or cover can be limited to."""
SUBDOMAINS = {
    "leave": "Leave", "attendance": "Attendance", "roster": "Roster",
    "expense": "Expenses and travel", "asset": "Assets", "pay": "Pay",
    "people": "People", "business": "Business",
}


def validate(values) -> frozenset:
    bad = sorted(set(values or ()) - set(SUBDOMAINS))
    if bad:
        raise ValueError(f"Unknown subdomain: {', '.join(bad)}")
    return frozenset(values or ())
```

`resolver.py`:

```python
"""Who acts on a request? Pure: no DB, no clock."""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class Person:
    id: int
    active: bool
    department: Optional[str]
    location: Optional[str]


@dataclass(frozen=True)
class Assignment:
    id: int
    kind: str
    scope: str                     # user | department | location | company
    scope_user_id: Optional[int]
    department: Optional[str]
    location: Optional[str]
    manager_user_id: Optional[int]
    manager_post_id: Optional[int]
    starts_on: date
    ends_on: Optional[date]
    subdomains: frozenset          # empty = all


@dataclass(frozen=True)
class Post:
    id: int
    title: str
    is_active: bool
    heads_department: Optional[str]


@dataclass(frozen=True)
class Holder:
    post_id: int
    user_id: int
    starts_on: date
    ends_on: Optional[date]


@dataclass(frozen=True)
class Cover:
    id: int
    covers_user_id: Optional[int]
    covers_post_id: Optional[int]
    acting_user_id: int
    subdomains: frozenset
    starts_on: date
    ends_on: Optional[date]
    original_can_act: bool


@dataclass(frozen=True)
class Approver:
    type: str
    ref: Optional[str] = None


@dataclass
class World:
    people: dict
    kinds: set
    assignments: list
    posts: dict
    holders: list
    covers: list
    heads: dict                    # norm(department) -> (head, deputy)
    role_users: dict
    hr_ids: list


@dataclass
class Resolution:
    user_ids: list
    via: str                       # primary | fallback | hr | blocked
    acting_for: dict = field(default_factory=dict)
    via_post_id: Optional[int] = None
    explanation: list = field(default_factory=list)


def norm(text: Optional[str]) -> str:
    return " ".join((text or "").split()).casefold()


def live(row, on: date) -> bool:
    return row.starts_on <= on and (row.ends_on is None or on <= row.ends_on)


def find_assignment(w: World, kind: str, user_id: int, sub: str, on: date):
    """Most specific scope first; within a scope a named subdomain beats
    'all'. None when nothing applies."""
    p = w.people.get(user_id)
    if p is None:
        return None
    dept, loc = norm(p.department), norm(p.location)
    tests = (
        lambda a: a.scope == "user" and a.scope_user_id == user_id,
        lambda a: a.scope == "department" and dept and norm(a.department) == dept,
        lambda a: a.scope == "location" and loc and norm(a.location) == loc,
        lambda a: a.scope == "company",
    )
    cands = [a for a in w.assignments if a.kind == kind and live(a, on)]
    for matches in tests:
        hit = [a for a in cands if matches(a)
               and (not a.subdomains or sub in a.subdomains)]
        if hit:
            return sorted(hit, key=lambda a: (not a.subdomains, a.id))[0]
    return None


def holder_of(w: World, post_id: int, on: date) -> Optional[int]:
    post = w.posts.get(post_id)
    if post is None or not post.is_active:
        return None
    return next((h.user_id for h in w.holders
                 if h.post_id == post_id and live(h, on)), None)


def _active(w: World, uid) -> bool:
    p = w.people.get(uid)
    return bool(p and p.active)


def _cover_for(w, sub, on, user_id=None, post_id=None):
    rows = [c for c in w.covers if live(c, on)
            and (not c.subdomains or sub in c.subdomains)
            and _active(w, c.acting_user_id)
            and ((post_id is not None and c.covers_post_id == post_id)
                 or (user_id is not None and c.covers_user_id == user_id))]
    # a cover of the post beats a cover of its holder; named beats all
    rows.sort(key=lambda c: (c.covers_post_id is None, not c.subdomains, c.id))
    return rows[0] if rows else None


def _seats(w: World, ap: Approver, requester: int, sub: str, on: date, log):
    """[(user_id | None, post_id | None)] before acting cover."""
    if ap.type == "specific_user":
        log.append(f"Named person #{ap.ref}")
        return [(int(ap.ref), None)]
    if ap.type == "role":
        ids = sorted(w.role_users.get(ap.ref or "", []))
        log.append(f"Role {ap.ref}: {len(ids)} user(s)")
        return [(u, None) for u in ids]
    if ap.type == "post":
        pid = int(ap.ref)
        uid = holder_of(w, pid, on)
        title = w.posts[pid].title if pid in w.posts else f"#{pid}"
        log.append(f"Post {title}: {'vacant' if uid is None else f'held by #{uid}'}")
        return [(uid, pid)]
    if ap.type in ("manager_kind", "reporting_manager"):
        kind = "reporting" if ap.type == "reporting_manager" else ap.ref
        a = find_assignment(w, kind, requester, sub, on)
        if a is None:
            log.append(f"No {kind} manager assigned")
            return []
        log.append(f"{kind} manager from the {a.scope} assignment #{a.id}")
        if a.manager_post_id is not None:
            uid = holder_of(w, a.manager_post_id, on)
            log.append("Post is vacant" if uid is None else f"Post held by #{uid}")
            return [(uid, a.manager_post_id)]
        return [(a.manager_user_id, None)]
    if ap.type == "dept_head_of_requester":
        p = w.people.get(requester)
        dept = norm(p.department) if p else ""
        for post in sorted(w.posts.values(), key=lambda x: x.id):
            if dept and norm(post.heads_department) == dept and post.is_active:
                uid = holder_of(w, post.id, on)
                if uid is not None or _cover_for(w, sub, on, post_id=post.id):
                    log.append(f"Head post {post.title}")
                    return [(uid, post.id)]
        for uid in w.heads.get(dept, ()):
            if uid and _active(w, uid):
                log.append(f"Department head/deputy #{uid}")
                return [(uid, None)]
        log.append("Department has no active head")
        return []
    raise ValueError(f"Unknown approver type: {ap.type}")


def _attempt(w, ap, requester, sub, on, log):
    ids, acting, post_id = [], {}, None
    for uid, pid in _seats(w, ap, requester, sub, on, log):
        c = _cover_for(w, sub, on, user_id=uid, post_id=pid)
        picked = [uid] if uid is not None else []
        if c is not None:
            log.append(f"#{c.acting_user_id} is acting for "
                       + (f"#{uid}" if uid is not None else "the vacant post"))
            if uid is not None:
                acting[c.acting_user_id] = uid
            picked = [c.acting_user_id] + (picked if c.original_can_act else [])
        for x in picked:
            if x == requester:
                log.append(f"#{x} is the requester: skipped")
            elif not _active(w, x):
                log.append(f"#{x} is inactive: skipped")
            elif x not in ids:
                ids.append(x)
        post_id = post_id or pid
    return ids, {k: v for k, v in acting.items() if k in ids}, post_id


def resolve(w: World, approver: Approver, fallback: Optional[Approver],
            requester: int, sub: str, on: date) -> Resolution:
    log: list = []
    for via, ap in (("primary", approver), ("fallback", fallback)):
        if ap is None:
            continue
        if via == "fallback":
            log.append("Using the fallback")
        ids, acting, post_id = _attempt(w, ap, requester, sub, on, log)
        if ids:
            return Resolution(ids, via, acting, post_id, log)
    hr = [u for u in sorted(set(w.hr_ids)) if u != requester and _active(w, u)]
    if hr:
        log.append("Nobody found: goes to HR")
        return Resolution(hr, "hr", explanation=log)
    log.append("Nobody can act: blocked, admin must fix the route")
    return Resolution([], "blocked", explanation=log)
```

- [ ] **Step 4: Run it.** Expected: 17 passed.
- [ ] **Step 5: Commit** `feat(dop): pure approver resolver`.

### Task 2: Models and migration

**Files:** Create `backend/app/models/dop.py`, migration `b7d9f1a3c5e8`; Modify `backend/app/models/__init__.py` (append import)

- [ ] **Step 1: Models**

```python
"""Delegation of Powers (D1): manager kinds and assignments, posts, acting."""
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

CASCADE, SET_NULL, RESTRICT = "CASCADE", "SET NULL", "RESTRICT"


def _now():
    return datetime.now(timezone.utc)


class ManagerKind(Base):
    __tablename__ = "manager_kind"  # type: ignore[assignment]
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


class Post(Base):
    __tablename__ = "post"  # type: ignore[assignment]
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    department_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("department.id", ondelete=SET_NULL))
    location: Mapped[Optional[str]] = mapped_column(String(100))
    parent_post_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("post.id", ondelete=SET_NULL))
    heads_department_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("department.id", ondelete=SET_NULL), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now)


class PostHolder(Base):
    __tablename__ = "post_holder"  # type: ignore[assignment]
    __table_args__ = (Index("ix_post_holder_post", "post_id", "starts_on"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("post.id", ondelete=CASCADE))
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=CASCADE), index=True)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[Optional[date]] = mapped_column(Date)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=SET_NULL))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now)


class ManagerAssignment(Base):
    __tablename__ = "manager_assignment"  # type: ignore[assignment]
    __table_args__ = (
        Index("ix_mgr_asg_kind_scope", "manager_kind_id", "scope_type"),
        Index("ix_mgr_asg_user", "scope_user_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    manager_kind_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("manager_kind.id", ondelete=RESTRICT))
    scope_type: Mapped[str] = mapped_column(String(16))
    scope_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=CASCADE))
    scope_department_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("department.id", ondelete=CASCADE))
    scope_location: Mapped[Optional[str]] = mapped_column(String(100))
    manager_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=CASCADE), index=True)
    manager_post_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("post.id", ondelete=CASCADE), index=True)
    # JSON list of codes; [] = all. Replaces the spec's child table: rows are
    # always read whole.
    subdomains: Mapped[list] = mapped_column(JSON, default=list)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[Optional[date]] = mapped_column(Date)
    note: Mapped[Optional[str]] = mapped_column(String(255))
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=SET_NULL))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now)
    # removed before it ever started
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True))


class ActingAssignment(Base):
    __tablename__ = "acting_assignment"  # type: ignore[assignment]
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    covers_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=CASCADE), index=True)
    covers_post_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("post.id", ondelete=CASCADE), index=True)
    acting_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=CASCADE), index=True)
    subdomains: Mapped[list] = mapped_column(JSON, default=list)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[Optional[date]] = mapped_column(Date)
    original_can_act: Mapped[bool] = mapped_column(Boolean, default=False)
    only_when_on_leave: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255))
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=SET_NULL))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True))
    revoked_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=SET_NULL))
```

Append to `models/__init__.py`:
```python
from .dop import (
    ManagerKind, Post, PostHolder, ManagerAssignment, ActingAssignment,
)
```

- [ ] **Step 2: Migration** (`revision = "b7d9f1a3c5e8"`, `down_revision = "a6b8d0f2c4e7"`). Create the five tables in the order above with the same columns, FKs and indexes; server defaults `"1"`/`"0"` for booleans and `sa.func.now()` for `created_at`. Then:

```python
    op.execute("INSERT INTO manager_kind (code, name, sort_order, is_active, "
               "is_system) VALUES ('reporting','Reporting manager',0,1,1),"
               "('functional','Functional manager',1,1,0),"
               "('project','Project manager',2,1,0)")
    op.execute(
        "INSERT INTO manager_assignment (manager_kind_id, scope_type, "
        "scope_user_id, manager_user_id, subdomains, starts_on, note, "
        "created_at) SELECT k.id, 'user', u.id, u.manager_id, '[]', "
        "'2000-01-01', 'Copied from reporting manager', UTC_TIMESTAMP() "
        "FROM user u JOIN manager_kind k ON k.code = 'reporting' "
        "WHERE u.manager_id IS NOT NULL AND u.manager_id <> u.id")
    op.execute("INSERT INTO permission (name, description) SELECT "
               "'dop manage', 'Manage managers, posts and acting covers' "
               "FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM permission "
               "WHERE name = 'dop manage')")
    op.execute("INSERT IGNORE INTO role_permissions (role_id, permission_id) "
               "SELECT r.id, p.id FROM role r, permission p WHERE "
               "r.name = 'Super Admin' AND p.name = 'dop manage'")
```

Downgrade: delete role_permissions and permission for `dop manage`, then drop `acting_assignment`, `manager_assignment`, `post_holder`, `post`, `manager_kind`.

- [ ] **Step 3: Verify on a clone.** Dump `erp_db`, load into `mig_dop1`, grant to `erp_user`, then `docker exec -e MARIADB_DB=mig_dop1 erp-united-exploration-dev-backend-1 sh -c 'cd /app && alembic upgrade head && alembic downgrade -1 && alembic upgrade head'`. Expect: `SELECT COUNT(*) FROM manager_assignment` equals `SELECT COUNT(*) FROM user WHERE manager_id IS NOT NULL AND manager_id <> id`. Drop the clone, then `alembic upgrade head` on dev.
- [ ] **Step 4: Commit** `feat(db): DOP manager assignments, posts, acting covers`.

### Task 3: World loader

**Files:** Create `backend/app/services/dop/world.py`, `backend/tests/_dop_world.py`; Test `backend/tests/test_dop_world.py`

- [ ] **Step 1: Fixture** `_dop_world.py`: async fixture `dop` creating, with a uuid suffix, a Department `DOP{sfx}` and active users `emp, mgr, mgr2, act, hr, admin, off` (emails `dop_<n>_<sfx>@test.com`, password `x`; `off` inactive; `admin.is_superuser=True`; `hr` in role HR), with an `Employee` for each (`department=DOP{sfx}`, `location=Mumbai{sfx}`, `date_of_joining=date(2020,1,1)`, `designation="T"`, `employee_id=f"D{n}{sfx}"`). It yields `{"sfx","dept","dept_id","loc","uid"}`. Teardown deletes, in order: ActingAssignment, ManagerAssignment, PostHolder and Post (code like `%{sfx}%`), ApproverDelegation, AuditLog and Notification by user, Employee, user_roles, User, Department. Follow `world()` in `tests/test_optional_holidays.py` for the pattern.

- [ ] **Step 2: Failing test**

```python
from datetime import date, timedelta

from _dop_world import dop  # noqa: F401
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.approver_delegation import ApproverDelegation
from app.models.dop import ManagerAssignment, ManagerKind
from app.services.dop import resolver as R
from app.services.dop.world import load_world
from app.services.org_time import local_today


async def test_loads_assignment_and_live_delegation(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        today = await local_today(db)
        kind = (await db.execute(select(ManagerKind).where(
            ManagerKind.code == "reporting"))).scalar_one()
        db.add(ManagerAssignment(
            manager_kind_id=kind.id, scope_type="department",
            scope_department_id=dop["dept_id"], manager_user_id=u["mgr"],
            subdomains=[], starts_on=date(2020, 1, 1)))
        db.add(ApproverDelegation(
            user_id=u["mgr"], delegate_id=u["act"], starts_on=today,
            ends_on=today + timedelta(days=1)))
        await db.commit()
        w = await load_world(db, today)
        r = R.resolve(w, R.Approver("manager_kind", "reporting"), None,
                      u["emp"], "leave", today)
    assert sorted(r.user_ids) == sorted([u["mgr"], u["act"]])
    assert r.acting_for == {u["act"]: u["mgr"]}


async def test_cancelled_rows_are_ignored(dop):
    from datetime import datetime, timezone
    u = dop["uid"]
    async with SessionLocal() as db:
        today = await local_today(db)
        kind = (await db.execute(select(ManagerKind).where(
            ManagerKind.code == "reporting"))).scalar_one()
        db.add(ManagerAssignment(
            manager_kind_id=kind.id, scope_type="user",
            scope_user_id=u["emp"], manager_user_id=u["mgr"], subdomains=[],
            starts_on=today, cancelled_at=datetime.now(timezone.utc)))
        await db.commit()
        w = await load_world(db, today)
    assert R.find_assignment(w, "reporting", u["emp"], "leave", today) is None
```

- [ ] **Step 3: Implement**

```python
"""Build the resolver's World from the DB."""
from datetime import date

from sqlalchemy import or_, select

from app.models.approver_delegation import ApproverDelegation
from app.models.department import Department
from app.models.dop import (
    ActingAssignment, ManagerAssignment, ManagerKind, Post, PostHolder,
)
from app.models.employee import Employee
from app.models.leave import LeaveRequest, LeaveStatus
from app.models.user import Permission, Role, User
from app.services.dop import resolver as R

HR_PERM = "hr employee write"


async def load_world(db, on: date) -> R.World:
    """Everything needed to resolve on date `on` (about 10 queries,
    independent of employee count)."""
    people = {
        i: R.Person(i, bool(act), dept, loc or uloc)
        for i, act, uloc, dept, loc in (await db.execute(
            select(User.id, User.is_active, User.location,
                   Employee.department, Employee.location)
            .outerjoin(Employee, Employee.user_id == User.id))).all()}
    depts = {d.id: d for d in (await db.execute(
        select(Department))).scalars().all()}

    def dname(i):
        return depts[i].name if i in depts else None

    kinds = {k.id: k.code for k in (await db.execute(
        select(ManagerKind).where(ManagerKind.is_active.is_(True))
    )).scalars().all()}

    def window(m):
        return (m.starts_on <= on, or_(m.ends_on.is_(None), m.ends_on >= on))

    asgs = [R.Assignment(
        a.id, kinds[a.manager_kind_id], a.scope_type, a.scope_user_id,
        dname(a.scope_department_id), a.scope_location, a.manager_user_id,
        a.manager_post_id, a.starts_on, a.ends_on, frozenset(a.subdomains or ()))
        for a in (await db.execute(select(ManagerAssignment).where(
            *window(ManagerAssignment),
            ManagerAssignment.cancelled_at.is_(None)))).scalars().all()
        if a.manager_kind_id in kinds]
    posts = {p.id: R.Post(p.id, p.title, p.is_active,
                          dname(p.heads_department_id))
             for p in (await db.execute(select(Post))).scalars().all()}
    holders = [R.Holder(h.post_id, h.user_id, h.starts_on, h.ends_on)
               for h in (await db.execute(select(PostHolder).where(
                   *window(PostHolder)))).scalars().all()]

    acting = (await db.execute(select(ActingAssignment).where(
        *window(ActingAssignment),
        ActingAssignment.revoked_at.is_(None)))).scalars().all()
    delegs = (await db.execute(select(ApproverDelegation).where(
        *window(ApproverDelegation),
        ApproverDelegation.revoked_at.is_(None)))).scalars().all()
    holder_by_post = {h.post_id: h.user_id for h in holders}
    need = {(a.covers_user_id or holder_by_post.get(a.covers_post_id))
            for a in acting if a.only_when_on_leave}
    need |= {d.user_id for d in delegs if d.only_when_on_leave}
    need.discard(None)
    away = set((await db.execute(select(LeaveRequest.employee_id).where(
        LeaveRequest.employee_id.in_(need),
        LeaveRequest.status == LeaveStatus.APPROVED,
        LeaveRequest.start_date <= on, LeaveRequest.end_date >= on))
    ).scalars().all()) if need else set()
    covers = [R.Cover(a.id, a.covers_user_id, a.covers_post_id,
                      a.acting_user_id, frozenset(a.subdomains or ()),
                      a.starts_on, a.ends_on, a.original_can_act)
              for a in acting if not a.only_when_on_leave
              or (a.covers_user_id
                  or holder_by_post.get(a.covers_post_id)) in away]
    # Live out-of-office delegations (replaced in D2). The high id makes an
    # explicit acting cover win.
    covers += [R.Cover(10**9 + d.id, d.user_id, None, d.delegate_id,
                       frozenset(), d.starts_on, d.ends_on, True)
               for d in delegs if not d.only_when_on_leave
               or d.user_id in away]

    roles: dict = {}
    for name, uid in (await db.execute(
            select(Role.name, User.id).join(User.roles))).all():
        roles.setdefault(name, []).append(uid)
    hr = set((await db.execute(
        select(User.id).join(User.roles).join(Role.permissions)
        .where(Permission.name == HR_PERM))).scalars().all())
    hr |= set((await db.execute(select(User.id).where(
        User.is_superuser.is_(True)))).scalars().all())
    return R.World(
        people=people, kinds=set(kinds.values()), assignments=asgs,
        posts=posts, holders=holders, covers=covers,
        heads={R.norm(d.name): (d.head_user_id, d.deputy_head_user_id)
               for d in depts.values()},
        role_users=roles, hr_ids=sorted(hr))
```

- [ ] **Step 4: Run; expect 2 passed. Commit** `feat(dop): load resolver world`.

### Task 4: Manager assignment service and mirror

**Files:** Create `backend/app/services/dop/assignments.py`; Test `backend/tests/test_dop_assignments.py`

Interface (services never commit):

```python
async def create(db, *, actor_id, kind_id, scope_type, scope_user_id=None,
                 scope_department_id=None, scope_location=None,
                 manager_user_id=None, manager_post_id=None, subdomains=(),
                 starts_on, ends_on=None, note=None) -> ManagerAssignment
async def end(db, *, actor_id, assignment_id, ends_on) -> ManagerAssignment
async def set_reporting_manager(db, *, actor_id, user_id, manager_id) -> None
async def sync_mirror(db, user_ids=None) -> int
```

- [ ] **Step 1: Failing tests**

```python
from datetime import timedelta

import pytest
from _dop_world import dop  # noqa: F401
from fastapi import HTTPException
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.audit import AuditLog
from app.models.dop import ManagerAssignment, ManagerKind
from app.models.user import User
from app.services.dop import assignments as A
from app.services.org_time import local_today


async def _kind(db, code="reporting"):
    return (await db.execute(select(ManagerKind.id).where(
        ManagerKind.code == code))).scalar_one()


async def _mk(db, dop, mgr="mgr", **kw):
    today = await local_today(db)
    kw.setdefault("starts_on", today)
    kw.setdefault("scope_type", "user")
    if kw["scope_type"] == "user":
        kw.setdefault("scope_user_id", dop["uid"]["emp"])
    return await A.create(db, actor_id=dop["uid"]["admin"],
                          kind_id=await _kind(db),
                          manager_user_id=dop["uid"][mgr], **kw)


async def _manager_of(uid):
    async with SessionLocal() as db:
        return (await db.execute(select(User.manager_id).where(
            User.id == uid))).scalar_one()


async def test_create_mirrors_and_audits(dop):
    async with SessionLocal() as db:
        a = await _mk(db, dop)
        await db.commit()
        aid = a.id
    assert await _manager_of(dop["uid"]["emp"]) == dop["uid"]["mgr"]
    async with SessionLocal() as db:
        assert (await db.execute(select(AuditLog).where(
            AuditLog.action == "dop.assignment.create",
            AuditLog.resource_id == str(aid)))).scalars().first()


async def test_overlap_refused_but_named_and_all_coexist(dop):
    async with SessionLocal() as db:
        await _mk(db, dop)
        await _mk(db, dop, mgr="mgr2", subdomains=["expense"])
        for subs in ([], ["expense", "leave"]):
            with pytest.raises(HTTPException) as e:
                await _mk(db, dop, mgr="act", subdomains=subs)
            assert e.value.status_code == 409
        await db.rollback()


@pytest.mark.parametrize("bad", [
    {"scope_type": "nope"}, {"subdomains": ["zzz"]},
    {"mgr": "emp"},                       # own manager
    {"mgr": "off"},                       # inactive
])
async def test_validation(dop, bad):
    async with SessionLocal() as db:
        with pytest.raises(HTTPException) as e:
            await _mk(db, dop, **bad)
        assert e.value.status_code == 422
        await db.rollback()


async def test_end_before_start_refused(dop):
    async with SessionLocal() as db:
        today = await local_today(db)
        with pytest.raises(HTTPException) as e:
            await _mk(db, dop, ends_on=today - timedelta(days=1))
        assert e.value.status_code == 422
        await db.rollback()


async def test_department_scope_mirrors_only_people_without_their_own(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        await _mk(db, dop, mgr="mgr2", scope_user_id=u["emp"])
        await _mk(db, dop, mgr="mgr", scope_type="department",
                  scope_department_id=dop["dept_id"])
        await db.commit()
    assert await _manager_of(u["emp"]) == u["mgr2"]
    assert await _manager_of(u["act"]) == u["mgr"]
    assert await _manager_of(u["mgr"]) is None        # never own manager


async def test_set_reporting_manager_replaces_and_clears(dop):
    u = dop["uid"]
    for mgr in ("mgr", "mgr2", "mgr2", None):
        async with SessionLocal() as db:
            await A.set_reporting_manager(
                db, actor_id=u["admin"], user_id=u["emp"],
                manager_id=u[mgr] if mgr else None)
            await db.commit()
        assert await _manager_of(u["emp"]) == (u[mgr] if mgr else None)
    async with SessionLocal() as db:
        today = await local_today(db)
        rows = (await db.execute(select(ManagerAssignment).where(
            ManagerAssignment.scope_user_id == u["emp"],
            ManagerAssignment.cancelled_at.is_(None)))).scalars().all()
        assert not [r for r in rows
                    if r.ends_on is None or r.ends_on >= today]


async def test_full_sync_leaves_ungoverned_managers_alone(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        (await db.get(User, u["emp"])).manager_id = u["mgr"]
        await db.commit()
        await A.sync_mirror(db, [u["emp"]])
        await db.commit()
    assert await _manager_of(u["emp"]) == u["mgr"]


async def test_cycle_refused(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        await A.set_reporting_manager(db, actor_id=u["admin"],
                                      user_id=u["emp"], manager_id=u["mgr"])
        with pytest.raises(HTTPException) as e:
            await A.set_reporting_manager(
                db, actor_id=u["admin"], user_id=u["mgr"],
                manager_id=u["emp"])
        assert e.value.status_code == 422
        await db.rollback()
```

- [ ] **Step 2: Run; expect ImportError.**
- [ ] **Step 3: Implement**

```python
"""Manager assignment writes. Never commits. All writes of one kind are
serialised by locking its manager_kind row (cheap: admin-only, rare)."""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.department import Department
from app.models.dop import ManagerAssignment, ManagerKind, Post
from app.models.user import User
from app.services.dop import resolver as R
from app.services.dop import subdomains as S
from app.services.dop.world import load_world
from app.services.org_time import local_today

SCOPES = ("user", "department", "location", "company")


def audit(db, actor_id, action, rtype, rid, details):
    db.add(AuditLog(user_id=actor_id, action=action, resource_type=rtype,
                    resource_id=str(rid), details=details))


def snapshot(a: ManagerAssignment) -> dict:
    return {
        "kind_id": a.manager_kind_id, "scope_type": a.scope_type,
        "scope_user_id": a.scope_user_id,
        "scope_department_id": a.scope_department_id,
        "scope_location": a.scope_location,
        "manager_user_id": a.manager_user_id,
        "manager_post_id": a.manager_post_id,
        "subdomains": list(a.subdomains or []),
        "starts_on": a.starts_on.isoformat(),
        "ends_on": a.ends_on.isoformat() if a.ends_on else None}


def dates_overlap(s1, e1, s2, e2) -> bool:
    return (e2 is None or s1 <= e2) and (e1 is None or s2 <= e1)


def subs_clash(a, b) -> bool:
    """Two 'all' rows clash, two named rows clash when they share one;
    'all' and named coexist (named wins)."""
    a, b = set(a or ()), set(b or ())
    return (not a and not b) or bool(a & b)


async def _lock_kind(db, kind_id) -> ManagerKind:
    kind = (await db.execute(
        select(ManagerKind).where(ManagerKind.id == kind_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().first()
    if kind is None or not kind.is_active:
        raise HTTPException(422, "Unknown or inactive manager kind")
    return kind


async def _active_user(db, uid, what):
    u = (await db.execute(select(User.id, User.is_active).where(
        User.id == uid))).first()
    if u is None or not u.is_active:
        raise HTTPException(422, f"{what} not found or inactive")


async def _same_scope(db, kind_id, scope_type, user_id, dept_id, loc):
    rows = (await db.execute(
        select(ManagerAssignment).where(
            ManagerAssignment.manager_kind_id == kind_id,
            ManagerAssignment.scope_type == scope_type,
            ManagerAssignment.cancelled_at.is_(None))
        # locking read: HR edits reach here mid-transaction, and a plain read
        # would use their older snapshot (writers hold the kind row, so no
        # gap-lock deadlock between them)
        .with_for_update()
        .execution_options(populate_existing=True))).scalars().all()
    return [r for r in rows
            if r.scope_user_id == user_id and r.scope_department_id == dept_id
            and R.norm(r.scope_location) == R.norm(loc)]


async def _assert_no_cycle(db, user_id, manager_id):
    seen, cur = {user_id}, manager_id
    while cur is not None:
        if cur in seen:
            raise HTTPException(
                422, "This would make a reporting loop (the manager reports "
                     "to this employee)")
        seen.add(cur)
        cur = (await db.execute(select(User.manager_id).where(
            User.id == cur))).scalar_one_or_none()


async def create(db, *, actor_id, kind_id, scope_type, scope_user_id=None,
                 scope_department_id=None, scope_location=None,
                 manager_user_id=None, manager_post_id=None, subdomains=(),
                 starts_on, ends_on=None, note=None) -> ManagerAssignment:
    if scope_type not in SCOPES:
        raise HTTPException(422, "Unknown scope")
    scope_location = (scope_location or "").strip() or None
    given = {"user": scope_user_id, "department": scope_department_id,
             "location": scope_location}
    if [k for k, v in given.items() if v is not None] != (
            [] if scope_type == "company" else [scope_type]):
        raise HTTPException(422, f"Scope '{scope_type}' needs exactly its own target")
    if (manager_user_id is None) == (manager_post_id is None):
        raise HTTPException(422, "Choose a person or a post as the manager")
    if ends_on is not None and ends_on < starts_on:
        raise HTTPException(422, "End date is before the start date")
    try:
        subs = sorted(S.validate(subdomains))
    except ValueError as e:
        raise HTTPException(422, str(e))
    kind = await _lock_kind(db, kind_id)
    if scope_user_id is not None:
        await _active_user(db, scope_user_id, "Employee")
        if scope_user_id == manager_user_id:
            raise HTTPException(422, "An employee cannot be their own manager")
    if scope_department_id is not None and (
            await db.get(Department, scope_department_id)) is None:
        raise HTTPException(422, "Department not found")
    if manager_user_id is not None:
        await _active_user(db, manager_user_id, "Manager")
    else:
        post = await db.get(Post, manager_post_id)
        if post is None or not post.is_active:
            raise HTTPException(422, "Post not found or inactive")
    if kind.code == "reporting" and scope_type == "user" and manager_user_id:
        await _assert_no_cycle(db, scope_user_id, manager_user_id)
    for r in await _same_scope(db, kind_id, scope_type, scope_user_id,
                               scope_department_id, scope_location):
        if subs_clash(r.subdomains, subs) and dates_overlap(
                r.starts_on, r.ends_on, starts_on, ends_on):
            raise HTTPException(
                409, f"Overlaps assignment #{r.id}: end that one first")
    a = ManagerAssignment(
        manager_kind_id=kind_id, scope_type=scope_type,
        scope_user_id=scope_user_id, scope_department_id=scope_department_id,
        scope_location=scope_location, manager_user_id=manager_user_id,
        manager_post_id=manager_post_id, subdomains=subs,
        starts_on=starts_on, ends_on=ends_on, note=note,
        created_by_id=actor_id)
    db.add(a)
    await db.flush()
    audit(db, actor_id, "dop.assignment.create", "manager_assignment", a.id,
          snapshot(a))
    if kind.code == "reporting":
        await sync_mirror(db, await affected_users(db, a))
    return a


async def end(db, *, actor_id, assignment_id, ends_on) -> ManagerAssignment:
    kind_id = (await db.execute(select(ManagerAssignment.manager_kind_id)
               .where(ManagerAssignment.id == assignment_id))
               ).scalar_one_or_none()
    if kind_id is None:
        raise HTTPException(404, "Assignment not found")
    kind = (await db.execute(select(ManagerKind).where(
        ManagerKind.id == kind_id).with_for_update())).scalars().one()
    a = (await db.execute(
        select(ManagerAssignment).where(ManagerAssignment.id == assignment_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().one()
    if a.cancelled_at is not None:
        raise HTTPException(409, "Assignment was already removed")
    if a.ends_on is not None and ends_on > a.ends_on:
        raise HTTPException(
            422, "It already ends earlier: create a new assignment instead")
    before = snapshot(a)
    if ends_on < a.starts_on:
        a.cancelled_at = datetime.now(timezone.utc)
    else:
        a.ends_on = ends_on
    await db.flush()
    audit(db, actor_id, "dop.assignment.end", "manager_assignment", a.id,
          {"before": before, "ends_on": ends_on.isoformat(),
           "cancelled": a.cancelled_at is not None})
    if kind.code == "reporting":
        await sync_mirror(db, await affected_users(db, a))
    return a


async def affected_users(db, a) -> list:
    from app.models.employee import Employee
    if a.scope_type == "user":
        return [a.scope_user_id]
    q = select(User.id).outerjoin(Employee, Employee.user_id == User.id)
    rows = (await db.execute(q.add_columns(
        Employee.department, Employee.location, User.location))).all()
    if a.scope_type == "company":
        return [r[0] for r in rows]
    if a.scope_type == "department":
        d = await db.get(Department, a.scope_department_id)
        return [r[0] for r in rows if R.norm(r[1]) == R.norm(d.name)]
    return [r[0] for r in rows
            if R.norm(r[2] or r[3]) == R.norm(a.scope_location)]


async def set_reporting_manager(db, *, actor_id, user_id, manager_id) -> None:
    """HR/admin edits of one employee's manager: end the current user-scoped
    all-subdomain reporting row and start a new one today."""
    today = await local_today(db)
    kind_id = (await db.execute(select(ManagerKind.id).where(
        ManagerKind.code == "reporting"))).scalar_one()
    await _lock_kind(db, kind_id)
    for r in await _same_scope(db, kind_id, "user", user_id, None, None):
        if r.subdomains or (r.ends_on is not None and r.ends_on < today):
            continue
        if r.manager_user_id == manager_id and manager_id is not None \
                and r.starts_on <= today and r.ends_on is None:
            await sync_mirror(db, [user_id])
            return
        await end(db, actor_id=actor_id, assignment_id=r.id,
                  ends_on=today - timedelta(days=1))
    if manager_id is not None:
        await create(db, actor_id=actor_id, kind_id=kind_id,
                     scope_type="user", scope_user_id=user_id,
                     manager_user_id=manager_id, starts_on=today)
    else:
        await sync_mirror(db, [user_id])


async def sync_mirror(db, user_ids=None) -> int:
    """Set User.manager_id to the base reporting manager (no acting cover).
    Returns how many users changed."""
    await db.flush()
    today = await local_today(db)
    w = await load_world(db, today)
    q = select(User).order_by(User.id)
    if user_ids is not None:
        q = q.where(User.id.in_(list(user_ids)))
    # Never clear a manager the assignments never governed (seeds, scripts).
    governed: set = set()
    for row in (await db.execute(
            select(ManagerAssignment).join(
                ManagerKind, ManagerKind.id == ManagerAssignment.manager_kind_id)
            .where(ManagerKind.code == "reporting"))).scalars().all():
        if row.scope_type == "user":
            governed.add(row.scope_user_id)
        else:
            governed |= set(await affected_users(db, row))
    changed = 0
    for u in (await db.execute(q)).scalars().all():
        a = R.find_assignment(w, "reporting", u.id, "", today)
        if a is None and u.id not in governed:
            continue
        mgr = None
        if a is not None:
            mgr = (R.holder_of(w, a.manager_post_id, today)
                   if a.manager_post_id else a.manager_user_id)
        if mgr == u.id:
            mgr = None
        if u.manager_id != mgr:
            u.manager_id = mgr
            changed += 1
    await db.flush()
    return changed
```

(`sub=""` matches only all-subdomain rows, which is what the mirror wants.)

- [ ] **Step 4: Run; expect 11 new tests passed.** `pytest tests/test_dop_assignments.py tests/test_dop_resolver.py`
- [ ] **Step 5: Commit** `feat(dop): manager assignments with manager_id mirror`.

### Task 5: Route existing manager edits through the service

**Files:** Modify `backend/app/api/v1/endpoints/hr.py` (~806-826, ~1081, ~1126-1140, ~1425), `backend/app/api/v1/endpoints/admin.py` (~550), `backend/app/services/scheduler.py`; Test `backend/tests/test_dop_mirror_writers.py`

- [ ] **Step 1: Failing guard test**

```python
"""Only the DOP service may write User.manager_id."""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
OK = {"services/dop/assignments.py"}


def _writes(tree):
    for n in ast.walk(tree):
        if isinstance(n, (ast.Assign, ast.AugAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                if isinstance(t, ast.Attribute) and t.attr == "manager_id":
                    yield n.lineno
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                and n.func.id == "User" \
                and any(k.arg == "manager_id" for k in n.keywords):
            yield n.lineno


def test_no_direct_manager_id_writes():
    bad = []
    for f in APP.rglob("*.py"):
        rel = f.relative_to(APP).as_posix()
        if rel in OK:
            continue
        bad += [f"{rel}:{ln}" for ln in _writes(ast.parse(f.read_text()))]
    assert bad == []
```

- [ ] **Step 2: Run; expect FAIL listing five locations** in `hr.py` and `admin.py`.
- [ ] **Step 3: Implement.** In each place remove the direct write and, after the user is flushed and **before** the existing commit, call:

```python
from app.services.dop.assignments import set_reporting_manager, sync_mirror
```

  - bulk import (~820): drop `manager_id=manager_id` from `User(...)`; after `await db.flush()`:
    `if manager_id is not None: await set_reporting_manager(db, actor_id=None, user_id=user.id, manager_id=manager_id)`
    (bulk import runs inside a per-row helper without the acting user; pass its `current_user.id` if the helper already receives it).
  - create employee (~1081): after `db.add(db_obj)` add `await db.flush()`, then `if obj_in.manager_id is not None: await set_reporting_manager(db, actor_id=current_user.id, user_id=user.id, manager_id=obj_in.manager_id)`.
  - create with user (~1136): the same after the flush, with `new_user.id` and `obj_in.user.manager_id`.
  - update employee (~1425): `actor_id = current_user.id` before the loop; in the `manager_id` branch call `await set_reporting_manager(db, actor_id=actor_id, user_id=db_obj.user_id, manager_id=value)`; after the loop, `if {"department", "location"} & set(update_data): await sync_mirror(db, [db_obj.user_id])`.
  - admin (~550): `await set_reporting_manager(db, actor_id=current_user.id, user_id=user.id, manager_id=user_in.manager_id)`.

Scheduler job (dated assignments start and end by themselves):

```python
async def _job_dop_manager_mirror(session: AsyncSession) -> Dict[str, Any]:
    from app.services.dop.assignments import sync_mirror
    out = {"changed": await sync_mirror(session)}
    await session.commit()
    return out


register_job(JobSpec(
    name="dop_manager_mirror",
    display_name="Reporting manager refresh",
    description=(
        "Daily 00:10 IST: applies manager assignments and post holders that "
        "start or end today to each employee's reporting manager."
    ),
    default_cadence_cron="40 18 * * *",
    fn=_job_dop_manager_mirror,
))
```

- [ ] **Step 4: Run** the guard test plus `tests/test_hr_features.py tests/test_approval_concurrency.py tests/test_work_location.py tests/test_optional_holidays.py`. Expected: all pass. Tests that set `manager_id` directly on fixtures remain valid: the mirror only touches rows when someone edits an assignment.
- [ ] **Step 5: Commit** `refactor(dop): manager edits go through the assignment service`.

### Task 6: Posts and acting services

**Files:** Create `backend/app/services/dop/posts.py`, `acting.py`; Test `backend/tests/test_dop_posts_acting.py`

- [ ] **Step 1: Failing tests**

```python
from datetime import timedelta

import pytest
from _dop_world import dop  # noqa: F401
from fastapi import HTTPException

from app.db.session import SessionLocal
from app.services.dop import acting as AC
from app.services.dop import posts as PS
from app.services.org_time import local_today


async def _post(db, dop, code="P", **kw):
    return await PS.create(db, actor_id=dop["uid"]["admin"],
                           code=f"{code}{dop['sfx']}", title="HR Manager", **kw)


async def _raises(code, coro):
    with pytest.raises(HTTPException) as e:
        await coro
    assert e.value.status_code == code


async def test_one_holder_at_a_time_and_handover(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        t = await local_today(db)
        p = await _post(db, dop)
        await PS.assign_holder(db, actor_id=u["admin"], post_id=p.id,
                               user_id=u["mgr"], starts_on=t)
        await PS.assign_holder(db, actor_id=u["admin"], post_id=p.id,
                               user_id=u["mgr2"],
                               starts_on=t + timedelta(days=5))
        hist = await PS.history(db, p.id)
        assert [(h.user_id, h.starts_on, h.ends_on) for h in hist] == [
            (u["mgr"], t, t + timedelta(days=4)),
            (u["mgr2"], t + timedelta(days=5), None)]
        await _raises(409, PS.assign_holder(
            db, actor_id=u["admin"], post_id=p.id, user_id=u["act"],
            starts_on=t + timedelta(days=2)))
        await db.rollback()


async def test_post_validation(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        t = await local_today(db)
        p = await _post(db, dop, heads_department_id=dop["dept_id"])
        await _raises(409, _post(db, dop))
        await _raises(409, _post(db, dop, code="Q",
                                 heads_department_id=dop["dept_id"]))
        await _raises(422, PS.assign_holder(
            db, actor_id=u["admin"], post_id=p.id, user_id=u["off"],
            starts_on=t))
        await _raises(422, PS.update(db, actor_id=u["admin"], post_id=p.id,
                                     changes={"parent_post_id": p.id}))
        await db.rollback()


async def test_acting_rules(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        t = await local_today(db)

        async def mk(**kw):
            base = dict(actor_id=u["admin"], covers_user_id=u["mgr"],
                        acting_user_id=u["act"], starts_on=t,
                        ends_on=t + timedelta(days=3))
            base.update(kw)
            return await AC.create(db, **base)
        c = await mk()
        assert c.original_can_act is False
        await _raises(409, mk(acting_user_id=u["mgr2"]))
        await mk(acting_user_id=u["mgr2"], subdomains=["expense"])
        await _raises(422, mk(acting_user_id=u["mgr"]))
        await _raises(422, mk(acting_user_id=u["off"]))
        await _raises(422, mk(covers_user_id=None))
        await AC.update(db, actor_id=u["admin"], cover_id=c.id,
                        original_can_act=True, ends_on=t)
        assert c.original_can_act is True
        await AC.revoke(db, actor_id=u["admin"], cover_id=c.id)
        await _raises(409, AC.revoke(db, actor_id=u["admin"], cover_id=c.id))
        await mk(acting_user_id=u["hr"])          # free again
        await db.rollback()
```

- [ ] **Step 2: Implement `posts.py`**

```python
"""Posts and their holders. Never commits. Holder writes lock the post row."""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.models.department import Department
from app.models.dop import ManagerAssignment, Post, PostHolder
from app.services.dop.assignments import (
    _active_user, affected_users, audit, dates_overlap, sync_mirror,
)
from app.services.org_time import local_today

FIELDS = ("code", "title", "department_id", "location", "parent_post_id",
          "heads_department_id", "is_active")


async def _lock(db, post_id) -> Post:
    p = (await db.execute(select(Post).where(Post.id == post_id)
         .with_for_update().execution_options(populate_existing=True)
         )).scalars().first()
    if p is None:
        raise HTTPException(404, "Post not found")
    return p


async def _validate(db, data, post_id=None):
    if "code" in data and (await db.execute(select(Post.id).where(
            Post.code == data["code"], Post.id != (post_id or 0))
            )).first():
        raise HTTPException(409, "Post code already exists")
    for f in ("department_id", "heads_department_id"):
        if data.get(f) and await db.get(Department, data[f]) is None:
            raise HTTPException(422, "Department not found")
    if data.get("heads_department_id") and (await db.execute(
            select(Post.id).where(
                Post.heads_department_id == data["heads_department_id"],
                Post.id != (post_id or 0)))).first():
        raise HTTPException(409, "That department already has a head post")
    cur, seen = data.get("parent_post_id"), {post_id}
    while cur is not None:
        if cur in seen:
            raise HTTPException(422, "Posts cannot report in a loop")
        seen.add(cur)
        row = (await db.execute(select(Post.id, Post.parent_post_id).where(
            Post.id == cur))).first()
        if row is None:
            raise HTTPException(422, "Parent post not found")
        cur = row.parent_post_id


async def create(db, *, actor_id, code, title, **kw) -> Post:
    data = {"code": code.strip(), "title": title.strip(), **kw}
    await _validate(db, data)
    p = Post(**data)
    db.add(p)
    await db.flush()
    audit(db, actor_id, "dop.post.create", "post", p.id, data)
    return p


async def update(db, *, actor_id, post_id, changes) -> Post:
    p = await _lock(db, post_id)
    changes = {k: v for k, v in changes.items() if k in FIELDS}
    await _validate(db, changes, post_id)
    today = await local_today(db)
    if changes.get("is_active") is False and (await db.execute(
            select(ManagerAssignment.id).where(
                ManagerAssignment.manager_post_id == post_id,
                ManagerAssignment.cancelled_at.is_(None),
                or_(ManagerAssignment.ends_on.is_(None),
                    ManagerAssignment.ends_on >= today)))).first():
        raise HTTPException(
            409, "Post is used as a manager: end those assignments first")
    before = {k: getattr(p, k) for k in changes}
    for k, v in changes.items():
        setattr(p, k, v)
    await db.flush()
    audit(db, actor_id, "dop.post.update", "post", p.id,
          {"before": before, "after": changes})
    return p


async def history(db, post_id) -> list:
    return list((await db.execute(
        select(PostHolder).where(PostHolder.post_id == post_id)
        .order_by(PostHolder.starts_on, PostHolder.id)
        .execution_options(populate_existing=True))).scalars().all())


async def _sync(db, post_id):
    ids: set = set()
    for a in (await db.execute(select(ManagerAssignment).where(
            ManagerAssignment.manager_post_id == post_id,
            ManagerAssignment.cancelled_at.is_(None)))).scalars().all():
        ids |= set(await affected_users(db, a))
    if ids:
        await sync_mirror(db, ids)


async def assign_holder(db, *, actor_id, post_id, user_id, starts_on,
                        ends_on=None) -> PostHolder:
    """Start a holder. An open-ended current holder ends the day before."""
    if ends_on is not None and ends_on < starts_on:
        raise HTTPException(422, "End date is before the start date")
    p = await _lock(db, post_id)
    if not p.is_active:
        raise HTTPException(422, "Post is inactive")
    await _active_user(db, user_id, "Holder")
    for h in await history(db, post_id):
        if h.ends_on is None and h.starts_on < starts_on:
            h.ends_on = starts_on - timedelta(days=1)
        elif dates_overlap(h.starts_on, h.ends_on, starts_on, ends_on):
            raise HTTPException(409, "Someone already holds the post then")
    h = PostHolder(post_id=post_id, user_id=user_id, starts_on=starts_on,
                   ends_on=ends_on, created_by_id=actor_id)
    db.add(h)
    await db.flush()
    audit(db, actor_id, "dop.post.holder", "post", post_id,
          {"user_id": user_id, "starts_on": starts_on.isoformat(),
           "ends_on": ends_on.isoformat() if ends_on else None})
    await _sync(db, post_id)
    return h


async def end_holder(db, *, actor_id, post_id, holder_id, ends_on):
    await _lock(db, post_id)
    h = next((x for x in await history(db, post_id) if x.id == holder_id), None)
    if h is None:
        raise HTTPException(404, "Holder not found")
    if ends_on < h.starts_on or (h.ends_on and ends_on > h.ends_on):
        raise HTTPException(422, "End date is outside the holding period")
    h.ends_on = ends_on
    await db.flush()
    audit(db, actor_id, "dop.post.holder_end", "post", post_id,
          {"holder_id": holder_id, "ends_on": ends_on.isoformat()})
    await _sync(db, post_id)
    return h
```

- [ ] **Step 3: Implement `acting.py`**

```python
"""Acting covers. Never commits. Writes lock the covered user or post row."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.models.dop import ActingAssignment, Post
from app.models.user import User
from app.services.dop import subdomains as S
from app.services.dop.assignments import (
    _active_user, audit, dates_overlap, subs_clash,
)


def snapshot(c) -> dict:
    return {"covers_user_id": c.covers_user_id,
            "covers_post_id": c.covers_post_id,
            "acting_user_id": c.acting_user_id,
            "subdomains": list(c.subdomains or []),
            "starts_on": c.starts_on.isoformat(),
            "ends_on": c.ends_on.isoformat() if c.ends_on else None,
            "original_can_act": c.original_can_act,
            "only_when_on_leave": c.only_when_on_leave}


async def _lock_target(db, user_id, post_id):
    model, key = (User, user_id) if user_id is not None else (Post, post_id)
    if (await db.execute(select(model.id).where(model.id == key)
                         .with_for_update())).first() is None:
        raise HTTPException(422, "Covered person or post not found")


async def _siblings(db, user_id, post_id, skip=0):
    return (await db.execute(
        select(ActingAssignment).where(
            ActingAssignment.covers_user_id.is_(None) if user_id is None
            else ActingAssignment.covers_user_id == user_id,
            ActingAssignment.covers_post_id.is_(None) if post_id is None
            else ActingAssignment.covers_post_id == post_id,
            ActingAssignment.revoked_at.is_(None),
            ActingAssignment.id != skip)
        .execution_options(populate_existing=True))).scalars().all()


def _check_overlap(rows, subs, starts_on, ends_on):
    for r in rows:
        if subs_clash(r.subdomains, subs) and dates_overlap(
                r.starts_on, r.ends_on, starts_on, ends_on):
            raise HTTPException(409, f"Overlaps acting cover #{r.id}")


async def create(db, *, actor_id, acting_user_id, starts_on, ends_on=None,
                 covers_user_id=None, covers_post_id=None, subdomains=(),
                 original_can_act=False, only_when_on_leave=False,
                 reason=None) -> ActingAssignment:
    if (covers_user_id is None) == (covers_post_id is None):
        raise HTTPException(422, "Choose the person or the post to cover")
    if covers_user_id == acting_user_id:
        raise HTTPException(422, "A person cannot act for themselves")
    if ends_on is not None and ends_on < starts_on:
        raise HTTPException(422, "End date is before the start date")
    try:
        subs = sorted(S.validate(subdomains))
    except ValueError as e:
        raise HTTPException(422, str(e))
    await _lock_target(db, covers_user_id, covers_post_id)
    await _active_user(db, acting_user_id, "Acting person")
    _check_overlap(await _siblings(db, covers_user_id, covers_post_id), subs,
                   starts_on, ends_on)
    c = ActingAssignment(
        covers_user_id=covers_user_id, covers_post_id=covers_post_id,
        acting_user_id=acting_user_id, subdomains=subs, starts_on=starts_on,
        ends_on=ends_on, original_can_act=original_can_act,
        only_when_on_leave=only_when_on_leave, reason=reason,
        created_by_id=actor_id)
    db.add(c)
    await db.flush()
    audit(db, actor_id, "dop.acting.create", "acting_assignment", c.id,
          snapshot(c))
    return c


async def _locked(db, cover_id) -> ActingAssignment:
    row = (await db.execute(select(
        ActingAssignment.covers_user_id, ActingAssignment.covers_post_id)
        .where(ActingAssignment.id == cover_id))).first()
    if row is None:
        raise HTTPException(404, "Acting cover not found")
    await _lock_target(db, row[0], row[1])
    c = (await db.execute(select(ActingAssignment).where(
        ActingAssignment.id == cover_id).with_for_update()
        .execution_options(populate_existing=True))).scalars().one()
    if c.revoked_at is not None:
        raise HTTPException(409, "Acting cover was already ended")
    return c


async def update(db, *, actor_id, cover_id, **changes) -> ActingAssignment:
    """Only original_can_act, ends_on and reason can change."""
    c = await _locked(db, cover_id)
    before = snapshot(c)
    changes = {k: v for k, v in changes.items()
               if k in ("original_can_act", "ends_on", "reason")}
    if "ends_on" in changes:
        e = changes["ends_on"]
        if e is not None and e < c.starts_on:
            raise HTTPException(422, "End date is before the start date")
        _check_overlap(await _siblings(db, c.covers_user_id,
                                       c.covers_post_id, c.id),
                       c.subdomains, c.starts_on, e)
    for k, v in changes.items():
        setattr(c, k, v)
    await db.flush()
    audit(db, actor_id, "dop.acting.update", "acting_assignment", c.id,
          {"before": before, "after": snapshot(c)})
    return c


async def revoke(db, *, actor_id, cover_id) -> ActingAssignment:
    c = await _locked(db, cover_id)
    c.revoked_at = datetime.now(timezone.utc)
    c.revoked_by_id = actor_id
    await db.flush()
    audit(db, actor_id, "dop.acting.revoke", "acting_assignment", c.id,
          snapshot(c))
    return c
```

- [ ] **Step 4: Run; expect 3 passed. Commit** `feat(dop): posts and acting covers`.

### Task 7: API

**Files:** Create `backend/app/api/v1/endpoints/dop.py`; Modify `backend/app/api/v1/api.py` (import; `api_router.include_router(dop.router, prefix="/dop", tags=["dop"])`, not attendance-gated); Test `backend/tests/test_dop_api.py`

Routes, all requiring `deps.check_permissions(["dop manage"])` at router level:

| Method, path | Body / query | Returns |
|---|---|---|
| GET `/meta` | | kinds, subdomains, scopes, departments, locations |
| GET `/people?q=` | name/email search, max 20, active | id, name, email |
| POST, PATCH `/kinds[/{id}]` | code (create only), name, sort_order, is_active | kind; system kinds cannot be deactivated (422) |
| GET `/managers?q&department&missing&limit&offset` | page ≤ 100 | per employee: resolved base manager per kind with scope source |
| GET `/assignments?user_id&kind_id&history` | | rows with names |
| POST `/assignments/bulk` | `{user_ids: [1..200] or scope…, kind_id, manager…, subdomains, starts_on, ends_on, note, replace}` | `{created, replaced}`, all or nothing |
| POST `/assignments/{id}/end` | `{ends_on}` | row |
| GET, POST `/posts`; PATCH `/posts/{id}` | | post with holder, acting |
| GET, POST `/posts/{id}/holders`; POST `/posts/{id}/holders/{hid}/end` | | history |
| GET, POST `/acting`; PATCH `/acting/{id}`; POST `/acting/{id}/revoke` | | cover |
| POST `/check` | `{user_id, subdomain, on_date?, approver:{type,ref}, fallback?}` | resolution with names |
| POST `/check/all` | same without user_id | `{checked, blocked:[…], via_hr:[…]}` (lists capped at 200, totals exact) |

- [ ] **Step 1: Failing tests.** `api` fixture logs in `admin`, `hr`, `emp` through `/auth/login` with `create_app()` and `ASGITransport` (as in `test_optional_holidays.py`). Assert: `hr` and `emp` get 403 on GET `/meta`; bulk assign of `emp`+`act` to `mgr` returns `created == 2` and both `manager_id`s change; the same call again is 409 and changes nothing; with `replace=true` and `mgr2` it returns `replaced == 2`; one bad id among good ones rolls everything back (422, no rows); `/managers?missing=reporting` contains `mgr` and not `emp`; a post with a holder used as functional manager is returned by `/check` with `via == "primary"` and the holder's name; after POST `/acting` covering that post, `/check` returns the acting user with `acting_for`; `/check` with an unknown subdomain is 422; two concurrent identical bulk posts give exactly one 200 and one 409.
- [ ] **Step 2: Run; expect 404s.**
- [ ] **Step 3: Implement.** Every mutation follows this shape; `_out` helpers take plain rows and a name map from `services.approver_delegation.user_names`:

```python
@router.post("/assignments/bulk")
@guard_conflicts
async def bulk_assign(payload: BulkIn, db: deps.DBDep,
                      current_user: User = Depends(deps.get_current_user)):
    aid = current_user.id

    async def body() -> dict:
        await db.commit()              # fresh snapshot; locks come first
        created = replaced = 0
        base = payload.model_dump(exclude={"user_ids", "replace"})
        targets = ([{**base, "scope_type": "user", "scope_user_id": u}
                    for u in sorted(set(payload.user_ids))]
                   if payload.user_ids else [base])
        for kw in targets:
            if payload.replace:
                replaced += await svc.replace_overlaps(db, actor_id=aid, **kw)
            await svc.create(db, actor_id=aid, **kw)
            created += 1
        return {"created": created, "replaced": replaced}

    return await retry_on_lock(db, body, commit=True)
```

Add to `assignments.py`:

```python
async def replace_overlaps(db, *, actor_id, kind_id, scope_type, starts_on,
                           subdomains=(), scope_user_id=None,
                           scope_department_id=None, scope_location=None,
                           ends_on=None, **_) -> int:
    """End rows the new assignment would clash with, the day before it
    starts (rows that start on or after it are cancelled)."""
    await _lock_kind(db, kind_id)
    n = 0
    for r in await _same_scope(db, kind_id, scope_type, scope_user_id,
                               scope_department_id, scope_location):
        if subs_clash(r.subdomains, subdomains) and dates_overlap(
                r.starts_on, r.ends_on, starts_on, ends_on):
            await end(db, actor_id=actor_id, assignment_id=r.id,
                      ends_on=starts_on - timedelta(days=1))
            n += 1
    return n
```

`/check` uses `load_world(db, on)` then `resolve`; a `ValueError` becomes 422. `_retry` bodies return plain values only, and responses are re-read with fresh queries that never touch `current_user`.
- [ ] **Step 4: Run; all pass. Commit** `feat(dop): admin API`.

### Task 8: Web screens

**Files:** Create `frontend/src/components/dop/{dop-admin,managers-tab,assign-dialog,posts-tab,post-dialog,acting-tab,acting-dialog,check-tab,person-picker,dop-utils}.tsx`; Modify `frontend/src/api/endpoints.ts`, `App.tsx`, `sidebar.tsx`

- [ ] **Step 1:** `ENDPOINTS.DOP` with one entry per route in Task 7.
- [ ] **Step 2:** `dop-admin.tsx` mirrors `assets/asset-management.tsx` (tab strip, `Card`, `errMsg`); tabs Managers, Posts, Acting, Check. Banner: "Setting up only: live approvals keep their current routes until the next release. Changing a reporting manager takes effect immediately." Reuse `assets/modal.tsx`.
- [ ] **Step 3: Managers:** search, department filter, "Missing manager" filter by kind, one column per active kind showing name and source ("department", "company"), row checkboxes, **Assign** dialog (kind, person or post, whole scope or selected employees, subdomain checkboxes with "Everything" default, dates, note, "Replace existing"), history drawer with End. **Manage kinds** dialog.
- [ ] **Step 4: Posts:** list with holder, acting and vacant badge, indented by parent; create/edit; hand over (person, date); history.
- [ ] **Step 5: Acting:** list with status; create (person or post, acting person, subdomains, dates, only-when-on-leave, reason); switch **"Original can also act"** saved by PATCH after an in-page confirm; End.
- [ ] **Step 6: Check:** employee, subdomain, date, approver, optional fallback; result shows person(s), capacity, and the explanation lines with `#id` replaced by names; **Check all employees** lists blocked and HR-routed people.
- [ ] **Step 7:** sidebar entry `{ id: "dop-admin", label: "Delegation of Powers", icon: Network, roles: ["admin", "super admin"], group: "Administration" }`, lazy case and title in `App.tsx` as for `asset-management`. A 403 shows "You need the 'dop manage' permission".
- [ ] **Step 8:** tsc 164; `npx vite build --outDir /tmp/build` passes; every class exists in `index.css`. Commit `feat(web): delegation of powers setup`.

### Task 9: Verification

- [ ] Full backend suite live: `pytest tests app/tests --ignore=tests/test_admin_auth.py --ignore=tests/test_leave_flows.py`. Expected: only the 2 known `test_hr_employees` failures.
- [ ] **Parity:** on a clone of the dev DB, record `(id, manager_id)` before the migration; after it run `sync_mirror(db)` for everyone; expect 0 differences apart from self-managed users.
- [ ] Live API end-to-end against :8005, including races (bulk vs bulk, holder vs holder, acting vs acting): no 5xx.
- [ ] Browser: each tab, one full flow (assign, hand over post, act, check), plus a WFH request still approved by the employee's manager.
- [ ] Final whole-branch review; `DEPLOYMENT.md` section (migration, permission, daily job needs `ENABLE_SCHEDULER=1`, mirror behaviour); update the memory file.

## Spec coverage

| Spec | Task |
|---|---|
| Kinds, subdomains, assignments | 1, 2, 4, 7 |
| Posts, holders, head posts | 2, 6, 7 |
| Acting, original switch, only on leave | 2, 3, 6, 7 |
| Resolver order, fallback, HR, blocked | 1 |
| Reporting mirror | 4, 5 |
| Managers / Posts / Acting / Check screens | 8 |
| CSV import of managers | existing employee bulk import, routed in 5 |
| Repeat approver, verifier ≠ approver, re-resolve, override, rules, inbox, replacing ApproverDelegation | D2 |
