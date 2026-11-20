"""Auto-fill preview (Roadmap v2 Phase 1B, Task 8). Read-only: nothing is
written; the client applies accepted suggestions through POST /roster/bulk
(status=draft, overwrite=False)."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.services.org_time import local_today
from app.api import deps
from app.api.v1.endpoints.roster_common import check_window
from app.models.coverage_requirement import CoverageRequirement
from app.models.shift import ShiftTemplate
from app.models.user import User
from app.schemas.roster import (
    AutofillPreviewRequest, AutofillPreviewResponse, AutofillSuggestionRead,
    AutofillUnfilledRead,
)
from app.services import autofill as autofill_svc
from app.services import roster as roster_svc
from app.services import schedule_rules
from app.services.availability import availability_by_day
from app.services.time_rules import get_schedule_rules

router = APIRouter()

MAX_DAYS = 31
MAX_EMPLOYEES = 500


@router.post("/autofill/preview", response_model=AutofillPreviewResponse)
async def autofill_preview(
    *,
    db: deps.DBDep,
    body: AutofillPreviewRequest,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    start, end, department = body.start, body.end, body.department
    check_window(start, end, MAX_DAYS - 1)
    admin = roster_svc.is_roster_admin(current_user)
    scoped = await roster_svc.scoped_employees(db, current_user)
    if not admin and not scoped:
        raise HTTPException(status_code=403, detail="You have no roster scope.")
    cand_all = [e for e in scoped if e.user_id is not None
                and (not department or e.department == department)]
    allowed = await roster_svc.manageable_subset(
        db, current_user, {e.user_id for e in cand_all})
    cands = [e for e in cand_all if e.user_id in allowed]
    if len(cands) > MAX_EMPLOYEES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many employees ({len(cands)}); filter by "
                   f"department (max {MAX_EMPLOYEES}).")

    reqs = roster_svc.visible_requirements(
        list((await db.execute(select(CoverageRequirement).where(
            CoverageRequirement.is_active.is_(True)))).scalars().all()),
        admin=admin, scoped_departments={e.department for e in scoped},
        department=department,
    )
    if not reqs or not cands:
        return AutofillPreviewResponse()

    rules = await get_schedule_rules(db)
    lookback = max(7, rules["max_consecutive_days"] + 1,
                   rules["max_consecutive_nights"] + 1)
    w_start = start - timedelta(days=lookback)
    w_end = end + timedelta(days=(6 - end.weekday()) + 1)
    templates = {t.id: t for t in (await db.execute(
        select(ShiftTemplate))).scalars().all()}
    meta = await roster_svc.coverage_meta(db, scoped, reqs)
    entries, asgs = await roster_svc.load_planner_cells(
        db, meta.keys(), w_start, w_end)
    spans = schedule_rules.build_spans(
        roster_svc.working_cells(entries, asgs, templates, meta, w_start, w_end),
        templates)

    today = await local_today(db)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)
            if start + timedelta(days=i) >= today]
    cov = schedule_rules.compute_coverage(
        [s for s in spans if start <= s.work_date <= end], reqs, meta, days)
    slots = [
        autofill_svc.Slot(c.date, c.shift_template_id, c.department,
                          c.location, c.required_min - c.scheduled)
        for c in cov if c.required_min > c.scheduled
    ]

    cand_ids = {e.user_id for e in cands}
    existing = {}
    weekly_off = set()
    for (uid, d), r in entries.items():
        if uid in cand_ids and start <= d <= end:
            existing[(uid, d)] = (r.shift_template_id, bool(r.is_week_off))
    for uid in cand_ids:
        for d in days:
            if (uid, d) in existing:
                continue
            a = roster_svc.active_assignment(asgs.get(uid, ()), d)
            t = templates.get(a.shift_template_id) if a else None
            if t is not None and d.weekday() in (t.weekly_offs or []):
                weekly_off.add((uid, d))
    leave = await roster_svc.approved_leave_days(db, cand_ids, start, end)
    avail = await availability_by_day(db, cand_ids, start, end)

    plain = [SimpleNamespace(user_id=e.user_id, department=e.department,
                             location=e.location) for e in cands]
    sugg, unfilled = await asyncio.to_thread(
        autofill_svc.suggest,
        employees=plain, days=days, templates=templates, slots=slots,
        existing_cells=existing, leave_days=leave, availability=avail,
        rules=rules, window_start=start,
        base_spans=[s for s in spans if s.user_id in cand_ids],
        weekly_off_days=weekly_off,
    )
    by_uid = {e.user_id: e for e in cands}

    def tname(tid):
        t = templates.get(tid)
        return t.name if t else None

    return AutofillPreviewResponse(
        suggestions=[AutofillSuggestionRead(
            employee_id=s.user_id,
            employee_name=(by_uid[s.user_id].user.full_name
                           if by_uid[s.user_id].user else None),
            work_date=s.day, shift_template_id=s.template_id,
            shift_name=tname(s.template_id),
            department=by_uid[s.user_id].department,
            reasons=list(s.reasons),
        ) for s in sugg],
        unfilled=[AutofillUnfilledRead(
            work_date=u.day, shift_template_id=u.template_id,
            shift_name=tname(u.template_id), department=u.department,
            location=u.location, missing=u.need,
        ) for u in unfilled],
    )
