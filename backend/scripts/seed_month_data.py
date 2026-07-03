"""Seed ~30 days of realistic operational data into a LOCAL stack.

Section Q. Populates, idempotently:

- the `attendance edit` permission, attached to HR + admin roles
- 3 shift templates covering 24h (Morning / Evening / Night-overnight)
- shift assignments for the local test users
- ~30 days of attendance per user with realistic jitter: on-time days,
  late entries, early exits, and a few MISSING punch-outs (so the HR
  edit feature has real gaps to fix)
- an "Internal Operations" project + daily time entries matching the
  attendance days
- a couple of leave requests (approved + pending)

Safety: refuses to run unless ERP_LOCAL_SEED=1 and --yes-local is
passed — same contract as scripts/seed_local.py. Deterministic
(hash-based jitter), so re-runs add nothing and change nothing.

Run:
    docker compose -f docker-compose.local.yml exec -T \
        -e ERP_LOCAL_SEED=1 -e PYTHONPATH=/app \
        backend python -m scripts.seed_month_data --yes-local
"""
import asyncio
import hashlib
import os
import sys
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.attendance import Attendance
from app.models.hr import HolidayCalendar
from app.models.leave import LeaveRequest, LeaveStatus, LeaveType
from app.models.project import Project, ProjectMember
from app.models.shift import EmployeeShiftAssignment, ShiftTemplate
from app.models.timesheet import TimeEntry, TimeEntrySource
from app.models.user import Permission, Role, User

# Days of history to seed. Override with SEED_DAYS_BACK=95 for ~3
# months of payroll-testable attendance (idempotent — re-running with
# a larger window only adds the earlier days).
DAYS_BACK = int(os.environ.get("SEED_DAYS_BACK", "32"))

SHIFTS = [
    # name, start, end, overnight, break, grace_in, grace_out
    ("Morning (09:00-17:30)", time(9, 0), time(17, 30), False, 60, 10, 10),
    ("Evening (14:00-22:30)", time(14, 0), time(22, 30), False, 60, 10, 10),
    ("Night (22:00-06:30)", time(22, 0), time(6, 30), True, 60, 15, 15),
]

# email -> shift name (users missing locally are skipped)
USER_SHIFT = {
    "t1@example.com": "Morning (09:00-17:30)",
    "t2@example.com": "Evening (14:00-22:30)",
    "t3@example.com": "Night (22:00-06:30)",
    "employee@gmail.com": "Morning (09:00-17:30)",
    "pm@gmail.com": "Morning (09:00-17:30)",
    "hr@gmail.com": "Morning (09:00-17:30)",
}

# email -> list of (start_offset_days_ago, length, status, type_code)
LEAVE_PLAN = {
    "t1@example.com": [(12, 2, LeaveStatus.APPROVED, "PL")],
    "t2@example.com": [(-3, 1, LeaveStatus.SUBMITTED, "CL")],  # upcoming
}


def _guard() -> None:
    if os.environ.get("ERP_LOCAL_SEED") != "1" or "--yes-local" not in sys.argv:
        print(
            "REFUSING to run: set ERP_LOCAL_SEED=1 and pass --yes-local.\n"
            "This script writes a month of fake data — local stacks only."
        )
        sys.exit(1)


def _jitter(key: str, lo: int, hi: int) -> int:
    """Deterministic pseudo-random int in [lo, hi] from a string key."""
    h = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
    return lo + (h % (hi - lo + 1))


async def _ensure_permission(session: AsyncSession) -> None:
    perm = (await session.execute(
        select(Permission).where(Permission.name == "attendance edit")
    )).scalars().first()
    if not perm:
        perm = Permission(
            name="attendance edit",
            description="Directly edit/create employee punch records",
        )
        session.add(perm)
        await session.flush()
    for role_name in ("HR", "admin"):
        role = (await session.execute(
            select(Role).where(Role.name == role_name)
            .options()
        )).scalars().first()
        if role:
            await session.refresh(role, ["permissions"])
            if perm.name not in {p.name for p in role.permissions}:
                role.permissions.append(perm)
    await session.commit()
    print("  permission 'attendance edit' -> HR, admin")


async def _ensure_shifts(session: AsyncSession) -> dict[str, ShiftTemplate]:
    out: dict[str, ShiftTemplate] = {}
    for name, start, end, overnight, brk, gin, gout in SHIFTS:
        tpl = (await session.execute(
            select(ShiftTemplate).where(ShiftTemplate.name == name)
        )).scalars().first()
        if not tpl:
            tpl = ShiftTemplate(
                name=name, start_time=start, end_time=end,
                is_overnight=overnight, break_minutes=brk,
                grace_in_minutes=gin, grace_out_minutes=gout,
            )
            session.add(tpl)
            await session.flush()
            print(f"  shift created: {name}")
        out[name] = tpl
    await session.commit()
    return out


async def _ensure_assignments(
    session: AsyncSession,
    users: dict[str, User],
    shifts: dict[str, ShiftTemplate],
    start: date,
) -> None:
    for email, shift_name in USER_SHIFT.items():
        user = users.get(email)
        if not user:
            continue
        existing = (await session.execute(
            select(EmployeeShiftAssignment).where(
                EmployeeShiftAssignment.employee_id == user.id
            )
        )).scalars().first()
        if existing:
            continue
        session.add(EmployeeShiftAssignment(
            employee_id=user.id,
            shift_template_id=shifts[shift_name].id,
            effective_from=start,
            effective_to=None,
            note="seed_month_data",
        ))
        print(f"  shift assigned: {email} -> {shift_name}")
    await session.commit()


def _workdays(start: date, end: date, holidays: set[date]) -> list[date]:
    days, d = [], start
    while d <= end:
        if d.weekday() < 5 and d not in holidays:
            days.append(d)
        d += timedelta(days=1)
    return days


async def _seed_attendance(
    session: AsyncSession,
    users: dict[str, User],
    shifts: dict[str, ShiftTemplate],
    days: list[date],
    leave_days: dict[str, set[date]],
) -> dict[tuple[int, date], tuple[datetime, datetime | None]]:
    """Returns {(user_id, day): (punch_in, punch_out)} for timesheet gen."""
    created = 0
    punches: dict[tuple[int, date], tuple[datetime, datetime | None]] = {}
    for email, shift_name in USER_SHIFT.items():
        user = users.get(email)
        if not user:
            continue
        shift = shifts[shift_name]
        for i, day in enumerate(days):
            if day in leave_days.get(email, set()):
                continue
            key = f"{email}:{day.isoformat()}"
            # ~6% of days: fully absent (no record at all)
            if _jitter(key + ":absent", 0, 99) < 6:
                continue

            # Punch-in: -10..+25 min around shift start; every 9th day
            # very late (+35..+55) so late flags have real hits.
            in_off = _jitter(key + ":in", -10, 25)
            if i % 9 == 4:
                in_off = _jitter(key + ":verylate", 35, 55)
            punch_in = datetime.combine(
                day, shift.start_time, tzinfo=timezone.utc
            ) + timedelta(minutes=in_off)

            # Punch-out: -25..+40 min around shift end (next day for
            # overnight); every 11th day the punch-out is MISSING.
            out_day = day + timedelta(days=1) if shift.is_overnight else day
            punch_out = datetime.combine(
                out_day, shift.end_time, tzinfo=timezone.utc
            ) + timedelta(minutes=_jitter(key + ":out", -25, 40))
            if i % 11 == 7:
                punch_out = None

            exists = (await session.execute(
                select(Attendance.id).where(
                    Attendance.user_id == user.id,
                    Attendance.work_date == day,
                )
            )).scalars().first()
            if exists:
                punches[(user.id, day)] = (punch_in, punch_out)
                continue

            session.add(Attendance(
                user_id=user.id,
                mode="web" if _jitter(key + ":mode", 0, 1) else "mobile",
                captured_at=punch_in,
                punch_out_time=punch_out,
                work_date=day,
                shift_template_id=shift.id,
                is_cross_midnight=shift.is_overnight,
                attribution_flag=None,
            ))
            punches[(user.id, day)] = (punch_in, punch_out)
            created += 1
    await session.commit()
    print(f"  attendance rows created: {created}")
    return punches


async def _ensure_project(
    session: AsyncSession, users: dict[str, User]
) -> Project:
    proj = (await session.execute(
        select(Project).where(Project.code == "INT-OPS")
    )).scalars().first()
    if not proj:
        proj = Project(
            name="Internal Operations",
            code="INT-OPS",
            description="Seeded internal project for timesheet data",
            status="active",
        )
        session.add(proj)
        await session.flush()
        print("  project created: Internal Operations (INT-OPS)")
    for user in users.values():
        member = (await session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == proj.id,
                ProjectMember.user_id == user.id,
            )
        )).scalars().first()
        if not member:
            session.add(ProjectMember(
                project_id=proj.id, user_id=user.id, role="member",
            ))
    await session.commit()
    return proj


async def _seed_time_entries(
    session: AsyncSession,
    proj: Project,
    punches: dict[tuple[int, date], tuple[datetime, datetime | None]],
) -> None:
    created = 0
    for (user_id, day), (punch_in, punch_out) in punches.items():
        start_at = punch_in + timedelta(minutes=15)
        if punch_out is not None:
            end_at = punch_out - timedelta(minutes=45)
        else:
            end_at = start_at + timedelta(hours=7, minutes=30)
        if end_at <= start_at:
            continue
        exists = (await session.execute(
            select(TimeEntry.id).where(
                TimeEntry.user_id == user_id,
                TimeEntry.start_at >= datetime.combine(
                    day, time(0, 0), tzinfo=timezone.utc
                ),
                TimeEntry.start_at < datetime.combine(
                    day + timedelta(days=1), time(0, 0), tzinfo=timezone.utc
                ),
            )
        )).scalars().first()
        if exists:
            continue
        session.add(TimeEntry(
            user_id=user_id,
            project_id=proj.id,
            start_at=start_at,
            end_at=end_at,
            duration_seconds=int((end_at - start_at).total_seconds()),
            source=TimeEntrySource.TIMER,
            created_by_user_id=user_id,
        ))
        created += 1
    await session.commit()
    print(f"  time entries created: {created}")


async def _seed_leaves(
    session: AsyncSession, users: dict[str, User], today: date
) -> dict[str, set[date]]:
    """Create planned leave requests; return {email: leave dates} so the
    attendance generator skips those days."""
    leave_days: dict[str, set[date]] = {}
    types = {
        t.code: t for t in (await session.execute(
            select(LeaveType).where(LeaveType.code.is_not(None))
        )).scalars().all()
    }
    for email, plans in LEAVE_PLAN.items():
        user = users.get(email)
        if not user:
            continue
        for days_ago, length, status, code in plans:
            ltype = types.get(code)
            if not ltype:
                continue
            start = today - timedelta(days=days_ago)
            end = start + timedelta(days=length - 1)
            if status == LeaveStatus.APPROVED:
                dates = leave_days.setdefault(email, set())
                d = start
                while d <= end:
                    dates.add(d)
                    d += timedelta(days=1)
            exists = (await session.execute(
                select(LeaveRequest.id).where(
                    LeaveRequest.employee_id == user.id,
                    LeaveRequest.start_date == start,
                )
            )).scalars().first()
            if exists:
                continue
            session.add(LeaveRequest(
                employee_id=user.id,
                leave_type_id=ltype.id,
                start_date=start,
                end_date=end,
                reason="Seeded leave (seed_month_data)",
                status=status,
                created_by_user_id=user.id,
            ))
            print(f"  leave: {email} {start} +{length}d [{status.value}]")
    await session.commit()
    return leave_days


# ---------------------------------------------------------------------------
# Section R additions: reporting managers + the Shift Change chain
# ---------------------------------------------------------------------------

async def ensure_managers(session: AsyncSession) -> None:
    """Point the test employees at PM as reporting manager (and PM at
    CEO) so the REPORTING_MANAGER chain step resolves."""
    emails = [
        "t1@example.com", "t2@example.com", "t3@example.com",
        "employee@gmail.com", "pm@gmail.com", "hr@gmail.com",
        "ceo@gmail.com",
    ]
    users = {
        u.email: u for u in (await session.execute(
            select(User).where(User.email.in_(emails))
        )).scalars().all()
    }
    pm = users.get("pm@gmail.com")
    ceo = users.get("ceo@gmail.com")
    changed = 0
    for email in ("t1@example.com", "t2@example.com", "t3@example.com",
                  "employee@gmail.com", "hr@gmail.com"):
        u = users.get(email)
        if u and pm and not u.manager_id:
            u.manager_id = pm.id
            changed += 1
    if pm and ceo and not pm.manager_id:
        pm.manager_id = ceo.id
        changed += 1
    await session.commit()
    print(f"  managers wired: {changed}")


async def ensure_shift_change_chain(session: AsyncSession) -> None:
    from datetime import date as _date

    from app.models.approval_chain import (
        ApprovalChain, ApprovalChainStep, ApproverType, ChainEntityType,
    )

    existing = (await session.execute(
        select(ApprovalChain).where(
            ApprovalChain.entity_type == ChainEntityType.SHIFT_CHANGE,
        )
    )).scalars().first()
    if existing:
        print("  shift-change chain exists")
        return
    chain = ApprovalChain(
        name="Shift Change (Manager -> HR)",
        entity_type=ChainEntityType.SHIFT_CHANGE,
        is_active=True,
        effective_from=_date(2026, 1, 1),
        notes="Seeded by seed_month_data",
    )
    session.add(chain)
    await session.flush()
    session.add(ApprovalChainStep(
        chain_id=chain.id, step_order=1,
        approver_type=ApproverType.REPORTING_MANAGER,
        label="Reporting Manager",
    ))
    session.add(ApprovalChainStep(
        chain_id=chain.id, step_order=2,
        approver_type=ApproverType.ROLE, approver_ref="HR",
        label="HR",
    ))
    await session.commit()
    print("  shift-change chain created (Manager -> HR)")


async def main() -> None:
    _guard()
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=DAYS_BACK)

    async with Session() as session:
        emails = set(USER_SHIFT) | set(LEAVE_PLAN)
        users = {
            u.email: u for u in (await session.execute(
                select(User).where(User.email.in_(emails))
            )).scalars().all()
        }
        print(f"[1/6] users found: {sorted(users)}")

        print("[2/6] permission")
        await _ensure_permission(session)

        print("[3/6] shifts + assignments")
        shifts = await _ensure_shifts(session)
        await _ensure_assignments(session, users, shifts, start)

        print("[4/6] leaves")
        leave_days = await _seed_leaves(session, users, today)

        print("[5/6] attendance")
        holidays = {
            h.date for h in (await session.execute(
                select(HolidayCalendar)
            )).scalars().all()
        }
        days = _workdays(start, today - timedelta(days=1), holidays)
        punches = await _seed_attendance(
            session, users, shifts, days, leave_days
        )

        print("[6/6] project + time entries")
        proj = await _ensure_project(session, users)
        await _seed_time_entries(session, proj, punches)

        print("[7] managers + shift-change chain (Section R)")
        await ensure_managers(session)
        await ensure_shift_change_chain(session)

    await engine.dispose()
    print("\nDone. A month of attendance/timesheets/leaves is seeded.")


if __name__ == "__main__":
    asyncio.run(main())
