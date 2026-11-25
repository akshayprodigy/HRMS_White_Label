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
