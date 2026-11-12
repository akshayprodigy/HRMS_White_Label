"""Roster publish lifecycle, copy and change history."""
from datetime import date as pydate, datetime, time, timedelta, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select

from app.api import deps
from app.api.v1.endpoints.hr import log_audit
from app.models.roster import (
    RosterEntry, RosterStatus, RosterEntryHistory, RosterPublishRequest,
)
from app.models.shift import ShiftTemplate
from app.models.user import User
from app.schemas.roster import (
    RosterBulkResult,
    RosterPublishBody, RosterPublishResult, PublishRequestCreate,
    PublishRequestDecision, PublishRequestRead, RosterCopyRequest,
    RosterHistoryRead,
)
from app.models.user import Role, Permission
from app.services import roster as roster_svc

from app.api.v1.endpoints.roster_common import (
    require_manage, require_admin, commit_or_409,
    write_cells, check_window,
)

router = APIRouter()


# ------------------- publish lifecycle, copy and history -------------------

async def _resolve_targets(
    db, user: User, employee_ids, department
) -> tuple:
    """(requested ids, in-scope ids)."""
    if employee_ids is not None:
        target = set(employee_ids)
    else:
        target = {
            e.user_id
            for e in await roster_svc.scoped_employees(db, user, department)
        }
    return target, await roster_svc.manageable_subset(db, user, target)


@router.post("/publish", response_model=RosterPublishResult)
async def publish_roster(
    *,
    db: deps.DBDep,
    request: Request,
    body: RosterPublishBody,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    check_window(body.start, body.end)
    _target, allowed = await _resolve_targets(
        db, current_user, body.employee_ids, body.department
    )
    if not allowed:
        return RosterPublishResult()
    res = await roster_svc.publish_drafts(
        db, current_user, allowed, body.start, body.end
    )
    await commit_or_409(db)
    if res["published"]:
        await log_audit(
            db, current_user.id, "roster.publish", "roster_entry", None,
            {**res, "start": body.start.isoformat(),
             "end": body.end.isoformat()},
            request,
        )
    return RosterPublishResult(**res)


async def _names(db, ids) -> dict:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return {
        u.id: (u.full_name or u.email) for u in (await db.execute(
            select(User).where(User.id.in_(ids))
        )).scalars().all()
    }


async def _draft_counts(db, reqs) -> dict:
    """req.id -> number of DRAFT entries for its ids in its window. One
    query for the whole list; counted in memory."""
    if not reqs:
        return {}
    all_ids = sorted({i for r in reqs for i in (r.employee_ids or [])})
    out = {r.id: 0 for r in reqs}
    if not all_ids:
        return out
    rows = (await db.execute(
        select(RosterEntry.employee_id, RosterEntry.work_date).where(
            RosterEntry.employee_id.in_(all_ids),
            RosterEntry.status == RosterStatus.DRAFT,
            RosterEntry.work_date >= min(r.start for r in reqs),
            RosterEntry.work_date <= max(r.end for r in reqs),
        )
    )).all()
    for r in reqs:
        ids = set(r.employee_ids or [])
        out[r.id] = sum(
            1 for (uid, wd) in rows if uid in ids and r.start <= wd <= r.end
        )
    return out


def _pr_read(r: RosterPublishRequest, names: dict, counts: dict) -> PublishRequestRead:
    out = PublishRequestRead.model_validate(r, from_attributes=True)
    out.requester_name = names.get(r.requested_by_id)
    out.draft_count = counts.get(r.id)
    return out


async def _roster_admin_ids(db, exclude: int, cap: int = 20) -> List[int]:
    rows = (await db.execute(
        select(User.id).where(
            User.is_active.is_(True),
            User.id != exclude,
            or_(
                User.is_superuser.is_(True),
                User.roles.any(Role.permissions.any(
                    Permission.name == roster_svc.PERM_ROSTER)),
            ),
        ).order_by(User.id).limit(cap)
    )).scalars().all()
    return list(rows)


@router.post("/publish-requests", response_model=PublishRequestRead)
async def create_publish_request(
    *,
    db: deps.DBDep,
    request: Request,
    body: PublishRequestCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    check_window(body.start, body.end)
    _target, allowed = await _resolve_targets(
        db, current_user, body.employee_ids, body.department
    )
    if not allowed:
        raise HTTPException(
            status_code=422, detail="No employees in your roster scope."
        )
    dept_cond = (
        RosterPublishRequest.department.is_(None) if body.department is None
        else RosterPublishRequest.department == body.department
    )
    dup = (await db.execute(
        select(RosterPublishRequest.id).where(
            RosterPublishRequest.requested_by_id == current_user.id,
            RosterPublishRequest.status == "pending",
            RosterPublishRequest.start == body.start,
            RosterPublishRequest.end == body.end,
            dept_cond,
        )
    )).first()
    if dup is not None:
        raise HTTPException(
            status_code=409,
            detail="An identical publish request is already pending",
        )
    pr = RosterPublishRequest(
        requested_by_id=current_user.id, start=body.start, end=body.end,
        department=body.department, employee_ids=sorted(allowed),
        note=body.note, status="pending",
    )
    db.add(pr)
    await db.flush()
    who = current_user.full_name or current_user.email
    await roster_svc.notify_many(db, [
        (aid, "Roster publish request",
         f"{who} asked to publish the schedule for "
         f"{body.start.isoformat()}–{body.end.isoformat()}.",
         "roster_publish_request", str(pr.id))
        for aid in await _roster_admin_ids(db, current_user.id)
    ])
    await commit_or_409(db)
    return _pr_read(
        pr, {current_user.id: current_user.full_name or current_user.email},
        await _draft_counts(db, [pr]),
    )


@router.get("/publish-requests", response_model=List[PublishRequestRead])
async def list_publish_requests(
    db: deps.DBDep,
    status: str = Query("pending", pattern="^(pending|approved|rejected|cancelled|all)$"),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    q = select(RosterPublishRequest).order_by(
        RosterPublishRequest.created_at.desc(), RosterPublishRequest.id.desc()
    )
    if not roster_svc.is_roster_admin(current_user):
        q = q.where(RosterPublishRequest.requested_by_id == current_user.id)
    if status != "all":
        q = q.where(RosterPublishRequest.status == status)
    rows = list((await db.execute(q.limit(500))).scalars().all())
    names = await _names(db, {r.requested_by_id for r in rows})
    counts = await _draft_counts(db, rows)
    return [_pr_read(r, names, counts) for r in rows]


@router.post(
    "/publish-requests/{req_id}/decide", response_model=PublishRequestRead
)
async def decide_publish_request(
    *,
    db: deps.DBDep,
    request: Request,
    req_id: int,
    body: PublishRequestDecision,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    require_admin(current_user)
    pr = (await db.execute(
        select(RosterPublishRequest)
        .where(RosterPublishRequest.id == req_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )).scalars().first()
    if not pr:
        raise HTTPException(status_code=404, detail="Request not found")
    if pr.status != "pending":
        raise HTTPException(status_code=409, detail="Request already decided")
    note = (body.note or "").strip() or None
    if not body.approve and note is None:
        raise HTTPException(
            status_code=422, detail="A note is required to reject"
        )
    span = f"{pr.start.isoformat()}–{pr.end.isoformat()}"
    res = None
    if body.approve:
        res = await roster_svc.publish_drafts(
            db, current_user, pr.employee_ids or [], pr.start, pr.end
        )
        pr.status = "approved"
        await roster_svc.notify(
            db, pr.requested_by_id, "Publish request approved",
            f"Your request to publish {span} was approved "
            f"({res['published']} shift(s) published).",
            "roster_publish_request", str(pr.id),
        )
    else:
        pr.status = "rejected"
        await roster_svc.notify(
            db, pr.requested_by_id, "Publish request rejected",
            f"Your request to publish {span} was rejected: {note}",
            "roster_publish_request", str(pr.id),
        )
    pr.decided_by_id = current_user.id
    pr.decided_at = datetime.now(timezone.utc)
    pr.decision_note = note
    await commit_or_409(db)
    await log_audit(
        db, current_user.id, "roster.publish_request.decide",
        "roster_publish_request", str(pr.id),
        {"approve": body.approve, **(res or {})}, request,
    )
    names = await _names(db, {pr.requested_by_id})
    out = _pr_read(pr, names, {})
    if res is not None:
        out.publish_result = RosterPublishResult(**res)
        if res["published"] == 0:
            out.message = "No drafts published: already published or removed"
    return out


@router.post(
    "/publish-requests/{req_id}/cancel", response_model=PublishRequestRead
)
async def cancel_publish_request(
    *,
    db: deps.DBDep,
    request: Request,
    req_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    pr = (await db.execute(
        select(RosterPublishRequest)
        .where(RosterPublishRequest.id == req_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )).scalars().first()
    if not pr:
        raise HTTPException(status_code=404, detail="Request not found")
    if pr.requested_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your request")
    if pr.status != "pending":
        raise HTTPException(
            status_code=409, detail="Only pending requests can be cancelled"
        )
    pr.status = "cancelled"
    await db.commit()
    await log_audit(
        db, current_user.id, "roster.publish_request.cancel",
        "roster_publish_request", str(pr.id), {}, request,
    )
    return _pr_read(pr, await _names(db, {pr.requested_by_id}), {})


@router.post("/copy", response_model=RosterBulkResult)
async def copy_roster(
    *,
    db: deps.DBDep,
    request: Request,
    body: RosterCopyRequest,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Copy cells from the source window into the target window as DRAFT.
    Existing PUBLISHED target cells are never touched."""
    check_window(body.source_start, body.source_end, 30)
    span = (body.source_end - body.source_start).days
    target_end = body.target_start + timedelta(days=span)
    if body.target_start <= body.source_end and target_end >= body.source_start:
        raise HTTPException(
            status_code=422,
            detail="Target window must not overlap the source window",
        )
    result = RosterBulkResult()
    target, allowed = await _resolve_targets(
        db, current_user, body.employee_ids, body.department
    )
    result.out_of_scope.extend(sorted(target - allowed))
    if not allowed:
        return result
    delta = body.target_start - body.source_start
    src = await roster_svc.prefetch_entries(
        db, allowed, body.source_start, body.source_end
    )
    cells = [
        (uid, wd + delta, e.shift_template_id, e.is_week_off)
        for (uid, wd), e in sorted(src.items())
        if e.shift_template_id is not None or e.is_week_off
    ]
    await write_cells(
        db, current_user, allowed, cells, RosterStatus.DRAFT,
        body.overwrite, result, protect_all_published=True,
    )
    await commit_or_409(db)
    if result.created or result.updated:
        await log_audit(
            db, current_user.id, "roster.copy", "roster_entry", None,
            {
                "created": result.created, "updated": result.updated,
                "skipped": result.skipped,
                "source_start": body.source_start.isoformat(),
                "source_end": body.source_end.isoformat(),
                "target_start": body.target_start.isoformat(),
            },
            request,
        )
    return result


async def _history_rows(db, q) -> List[RosterHistoryRead]:
    rows = list((await db.execute(
        q.order_by(
            RosterEntryHistory.changed_at.desc(), RosterEntryHistory.id.desc()
        ).limit(500)
    )).scalars().all())
    names = await _names(
        db, {r.employee_id for r in rows} | {r.changed_by_id for r in rows}
    )
    tids = {
        t for r in rows
        for t in (r.old_shift_template_id, r.new_shift_template_id)
        if t is not None
    }
    tpl = {}
    if tids:
        tpl = {
            t.id: t.name for t in (await db.execute(
                select(ShiftTemplate).where(ShiftTemplate.id.in_(tids))
            )).scalars().all()
        }
    return [
        RosterHistoryRead(
            id=r.id, employee_id=r.employee_id,
            employee_name=names.get(r.employee_id), work_date=r.work_date,
            old_shift_template_id=r.old_shift_template_id,
            old_shift_name=tpl.get(r.old_shift_template_id),
            old_is_week_off=r.old_is_week_off,
            new_shift_template_id=r.new_shift_template_id,
            new_shift_name=tpl.get(r.new_shift_template_id),
            new_is_week_off=r.new_is_week_off, action=r.action,
            reason=r.reason, changed_by_id=r.changed_by_id,
            changed_by_name=names.get(r.changed_by_id),
            changed_at=r.changed_at,
        ) for r in rows
    ]


def _history_filter(q, start, end, work_start, work_end):
    """Window on WHEN the change happened (changed_at, UTC days; default the
    last 30 days, max 92); optional work_start/work_end narrow by the
    affected work date."""
    end = end or datetime.now(timezone.utc).date()
    start = start or (end - timedelta(days=30))
    check_window(start, end, 92)
    q = q.where(
        RosterEntryHistory.changed_at >= datetime.combine(
            start, time.min, tzinfo=timezone.utc),
        RosterEntryHistory.changed_at < datetime.combine(
            end + timedelta(days=1), time.min, tzinfo=timezone.utc),
    )
    if work_start is not None:
        q = q.where(RosterEntryHistory.work_date >= work_start)
    if work_end is not None:
        q = q.where(RosterEntryHistory.work_date <= work_end)
    return q


@router.get("/history", response_model=List[RosterHistoryRead])
async def roster_history(
    db: deps.DBDep,
    employee_id: Optional[int] = Query(None),
    start: Optional[pydate] = Query(None),
    end: Optional[pydate] = Query(None),
    work_start: Optional[pydate] = Query(None),
    work_end: Optional[pydate] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    q = _history_filter(
        select(RosterEntryHistory), start, end, work_start, work_end
    )
    if employee_id is not None:
        await require_manage(db, current_user, employee_id)
        q = q.where(RosterEntryHistory.employee_id == employee_id)
    elif not roster_svc.is_roster_admin(current_user):
        ids = [e.user_id for e in await roster_svc.scoped_employees(
            db, current_user)]
        if not ids:
            raise HTTPException(status_code=403, detail="You have no roster scope.")
        q = q.where(RosterEntryHistory.employee_id.in_(ids))
    return await _history_rows(db, q)


@router.get("/my/history", response_model=List[RosterHistoryRead])
async def my_roster_history(
    db: deps.DBDep,
    start: Optional[pydate] = Query(None),
    end: Optional[pydate] = Query(None),
    work_start: Optional[pydate] = Query(None),
    work_end: Optional[pydate] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    return await _history_rows(db, _history_filter(
        select(RosterEntryHistory).where(
            RosterEntryHistory.employee_id == current_user.id),
        start, end, work_start, work_end,
    ))
