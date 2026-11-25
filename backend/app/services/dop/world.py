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


async def load_people(db) -> dict:
    """Department and location exactly as the resolver sees them: the
    employee's, falling back to the user's. Shared with the assignment
    service so both agree on who a scope matches."""
    return {
        i: R.Person(i, bool(act), dept, loc or uloc)
        for i, act, uloc, dept, loc in (await db.execute(
            select(User.id, User.is_active, User.location,
                   Employee.department, Employee.location)
            .outerjoin(Employee, Employee.user_id == User.id))).all()}


async def load_world(db, on: date) -> R.World:
    """Everything needed to resolve on date `on` (about 10 queries,
    independent of employee count). Plain reads only: writers serialise on
    the manager_kind lock instead (see services/dop/assignments.py)."""
    people = await load_people(db)
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
