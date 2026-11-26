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


APPROVER_TYPES = ("specific_user", "role", "post", "manager_kind",
                  "reporting_manager", "dept_head_of_requester")


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
    # explanation lines name users as user_ref(<id>) and assignments as
    # "assignment #<id>": callers swap the token for the name.
    user_ids: list
    via: str                       # primary | fallback | hr | blocked
    acting_for: dict = field(default_factory=dict)  # user -> [users covered]
    via_post_id: Optional[int] = None
    explanation: list = field(default_factory=list)


def user_ref(uid) -> str:
    """Token for a user in an explanation line; callers swap it for the
    person's name. Control characters cannot occur in titles or names."""
    return f"\x02{uid}\x03"


def norm(text: Optional[str]) -> str:
    return " ".join((text or "").split()).casefold()


def live(row, on: date) -> bool:
    return row.starts_on <= on and (row.ends_on is None or on <= row.ends_on)


def base_index(w: World, on: date):
    """Fast lookup for the all-subdomain base manager: returns
    `lookup(kind, user_id)`, the same assignment `find_assignment(w, kind,
    user_id, "", on)` picks, in O(1) after one pass over the assignments."""
    idx: dict = {}
    for a in sorted(w.assignments, key=lambda a: a.id, reverse=True):
        if a.subdomains or not live(a, on):
            continue
        key = {"user": a.scope_user_id, "department": norm(a.department),
               "location": norm(a.location), "company": None}[a.scope]
        idx[(a.kind, a.scope, key)] = a        # lowest id ends up winning

    def lookup(kind, user_id):
        p = w.people.get(user_id)
        if p is None:
            return None
        dept, loc = norm(p.department), norm(p.location)
        for scope, key in (("user", user_id), ("department", dept or None),
                           ("location", loc or None), ("company", None)):
            if scope in ("department", "location") and key is None:
                continue
            a = idx.get((kind, scope, key))
            if a is not None:
                return a
        return None
    return lookup


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


def _cover_for(w, sub, on, requester, user_id=None, post_id=None):
    """A cover never applies to the acting person's own request."""
    post = w.posts.get(post_id) if post_id is not None else None
    post_ok = post is not None and post.is_active
    rows = [c for c in w.covers if live(c, on)
            and (not c.subdomains or sub in c.subdomains)
            and c.acting_user_id != requester
            and _active(w, c.acting_user_id)
            and ((post_ok and c.covers_post_id == post_id)
                 or (user_id is not None and c.covers_user_id == user_id))]
    # a cover of the post beats a cover of its holder; named beats all
    rows.sort(key=lambda c: (c.covers_post_id is None, not c.subdomains, c.id))
    return rows[0] if rows else None


def _ref_int(ap: Approver, log):
    try:
        return int(ap.ref)
    except (TypeError, ValueError):
        log.append(f"{ap.type}: invalid reference {ap.ref!r}")
        return None


def _candidates(w: World, ap: Approver, requester: int, sub: str, on: date,
                log):
    """Yield seat lists [(user_id | None, post_id | None)] before acting
    cover, in the order they are tried; the first that yields someone wins."""
    if ap.type == "specific_user":
        uid = _ref_int(ap, log)
        if uid is not None:
            log.append(f"Named person {user_ref(uid)}")
            yield [(uid, None)]
    elif ap.type == "role":
        ids = sorted(w.role_users.get(ap.ref or "", []))
        log.append(f"Role {ap.ref}: {len(ids)} user(s)")
        yield [(u, None) for u in ids]
    elif ap.type == "post":
        pid = _ref_int(ap, log)
        if pid is not None:
            uid = holder_of(w, pid, on)
            title = w.posts[pid].title if pid in w.posts else f"#{pid}"
            log.append(f"Post {title}: "
                       f"{'vacant' if uid is None else f'held by {user_ref(uid)}'}")
            yield [(uid, pid)]
    elif ap.type in ("manager_kind", "reporting_manager"):
        kind = "reporting" if ap.type == "reporting_manager" else ap.ref
        if kind not in w.kinds:
            log.append(f"Manager kind {kind} is unknown or inactive")
            return
        a = find_assignment(w, kind, requester, sub, on)
        if a is None:
            log.append(f"No {kind} manager assigned")
            return
        log.append(f"{kind} manager from the {a.scope} assignment #{a.id}")
        if a.manager_post_id is not None:
            uid = holder_of(w, a.manager_post_id, on)
            log.append("Post is vacant" if uid is None else f"Post held by {user_ref(uid)}")
            yield [(uid, a.manager_post_id)]
        else:
            yield [(a.manager_user_id, None)]
    elif ap.type == "dept_head_of_requester":
        p = w.people.get(requester)
        dept = norm(p.department) if p else ""
        if not dept:
            log.append("Requester has no department")
            return
        for post in sorted(w.posts.values(), key=lambda x: x.id):
            if norm(post.heads_department) == dept and post.is_active:
                uid = holder_of(w, post.id, on)
                if uid is not None or _cover_for(w, sub, on, requester,
                                                 post_id=post.id):
                    log.append(f"Head post {post.title}")
                    yield [(uid, post.id)]
        for label, uid in zip(("head", "deputy"), w.heads.get(dept, ())):
            if uid:
                log.append(f"Department {label} {user_ref(uid)}")
                yield [(uid, None)]
    else:
        raise ValueError(f"Unknown approver type: {ap.type}")


def _attempt(w, ap, requester, sub, on, log):
    for seats in _candidates(w, ap, requester, sub, on, log):
        ids, acting, post_id = [], {}, None
        for uid, pid in seats:
            c = _cover_for(w, sub, on, requester, user_id=uid, post_id=pid)
            picked = [uid] if uid is not None else []
            if c is not None:
                log.append(f"{user_ref(c.acting_user_id)} is acting for "
                           + (f"{user_ref(uid)}" if uid is not None
                              else "the vacant post"))
                if uid is not None:
                    acting.setdefault(c.acting_user_id, set()).add(uid)
                picked = [c.acting_user_id] + (picked if c.original_can_act
                                               else [])
            for x in picked:
                if x == requester:
                    log.append(f"{user_ref(x)} is the requester: skipped")
                elif not _active(w, x):
                    log.append(f"{user_ref(x)} is inactive: skipped")
                elif x not in ids:
                    ids.append(x)
            post_id = post_id or pid
        if ids:
            own = {u for u, _ in seats if u is not None}
            return (ids, {k: sorted(v) for k, v in acting.items()
                          if k in ids and k not in own}, post_id)
    return [], {}, None


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
