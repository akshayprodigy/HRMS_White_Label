"""
Employee Exit Management API

Workflow:
  Employee submits resignation → HR accepts → Notice period →
  Exit interview → HR initiates clearance → Departments clear →
  HR final release (deactivates user)

Employee can withdraw before HR accepts.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.models.audit import AuditLog
from app.models.employee import Employee
from app.models.user import User
from app.models.notification import Notification
from app.models.exit_management import (
    Resignation, ResignationStatus,
    ExitInterview,
    ClearanceRequest, ClearanceItem, ClearanceStatus,
)
from app.schemas.exit_management import (
    ResignationSubmit, ResignationAccept, ResignationRead,
    ExitInterviewSubmit, ExitInterviewHRRemarks, ExitInterviewRead,
    ClearanceRequestCreate, ClearanceRequestRead,
    ClearanceAction, InitiateClearance,
    ExitDetailsRead, ClearanceItemRead,
)

router = APIRouter()

HR_WRITE = "hr employee write"
HR_READ = "hr employee read"


# ─── Helpers ──────────────────────────────────────────────────

def _resignation_to_read(r: Resignation) -> ResignationRead:
    data = ResignationRead.model_validate(r, from_attributes=True)
    if r.employee:
        data.employee_name = r.employee.user.full_name if r.employee.user else None
        data.employee_emp_id = r.employee.employee_id
        data.department = r.employee.department
        data.designation = r.employee.designation
    if r.accepted_by:
        data.accepted_by_name = r.accepted_by.full_name
    if r.released_by:
        data.released_by_name = r.released_by.full_name
    return data


def _clearance_to_read(c: ClearanceRequest) -> ClearanceRequestRead:
    data = ClearanceRequestRead.model_validate(c, from_attributes=True)
    if c.assigned_to:
        data.assigned_to_name = c.assigned_to.full_name
    data.items = [
        ClearanceItemRead.model_validate(i, from_attributes=True)
        for i in (c.items or [])
    ]
    return data


async def _get_employee_for_user(db, user_id: int) -> Employee:
    result = await db.execute(
        select(Employee)
        .options(selectinload(Employee.user))
        .where(Employee.user_id == user_id)
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    return emp


async def _get_resignation(db, resignation_id: int) -> Resignation:
    result = await db.execute(
        select(Resignation)
        .options(
            selectinload(Resignation.employee).selectinload(Employee.user),
            selectinload(Resignation.accepted_by),
            selectinload(Resignation.released_by),
            selectinload(Resignation.exit_interview),
            selectinload(Resignation.clearance_requests)
            .selectinload(ClearanceRequest.items),
            selectinload(Resignation.clearance_requests)
            .selectinload(ClearanceRequest.assigned_to),
        )
        .where(Resignation.id == resignation_id)
    )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Resignation not found")
    return r


async def _notify(db, user_id: int, title: str, message: str,
                   resource_type: str = "resignation",
                   resource_id: str = ""):
    db.add(Notification(
        user_id=user_id, title=title, message=message,
        type="info", resource_type=resource_type,
        resource_id=str(resource_id),
    ))


async def _auto_advance_notice_period(db) -> None:
    """
    Lazy trigger: find any resignation in NOTICE_PERIOD whose last_working_day
    has passed (i.e. today > last_working_day) and auto-advance it to
    EXIT_INTERVIEW, notifying all HR users.

    Called at the top of every HR list/detail read so it fires on the next
    page load after the LWD passes — no background worker required.
    """
    today = date.today()

    result = await db.execute(
        select(Resignation)
        .options(
            selectinload(Resignation.employee).selectinload(Employee.user),
        )
        .where(
            Resignation.status == ResignationStatus.NOTICE_PERIOD,
            Resignation.last_working_day < today,
        )
    )
    overdue = result.scalars().all()
    if not overdue:
        return

    for resignation in overdue:
        resignation.status = ResignationStatus.EXIT_INTERVIEW
        emp_name = (
            resignation.employee.user.full_name
            if resignation.employee and resignation.employee.user
            else "Employee"
        )
        lwd = resignation.last_working_day.strftime("%d %b %Y")

        # Notify the employee
        await _notify(
            db,
            resignation.employee.user_id,
            "Notice Period Complete",
            f"Your notice period ended on {lwd}. Please complete your exit interview form.",
            resource_id=str(resignation.id),
        )

        # Notify HR users (those with hr employee write permission via role check
        # is complex here — notify all active users who have manager_id=None as a
        # proxy, or simply notify the accepted_by user if available)
        notify_user_ids: set[int] = set()
        if resignation.accepted_by_id:
            notify_user_ids.add(resignation.accepted_by_id)
        # Also notify the employee's manager
        if resignation.employee and resignation.employee.user and resignation.employee.user.manager_id:
            notify_user_ids.add(resignation.employee.user.manager_id)

        for uid in notify_user_ids:
            await _notify(
                db,
                uid,
                "Notice Period Complete — Action Required",
                f"{emp_name}'s notice period ended on {lwd}. Please initiate exit interview and clearance.",
                resource_id=str(resignation.id),
            )

    await db.commit()


# ─── Employee: Submit Resignation ─────────────────────────────

@router.post("/resign", response_model=ResignationRead)
async def submit_resignation(
    *,
    db: deps.DBDep,
    body: ResignationSubmit,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Employee submits their resignation."""
    emp = await _get_employee_for_user(db, current_user.id)

    # Check no active resignation
    existing = await db.execute(
        select(Resignation).where(
            Resignation.employee_id == emp.id,
            Resignation.status.notin_([
                ResignationStatus.WITHDRAWN,
                ResignationStatus.REJECTED,
                ResignationStatus.RELEASED,
            ])
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="You already have an active resignation"
        )

    today = date.today()
    notice_days = emp.notice_period_days if emp.notice_period_days is not None else 30
    last_working_day = today + timedelta(days=notice_days)

    resignation = Resignation(
        employee_id=emp.id,
        reason=body.reason,
        reason_details=body.reason_details,
        status=ResignationStatus.SUBMITTED,
        resignation_date=today,
        last_working_day=last_working_day,
        notice_period_days=notice_days,
    )
    db.add(resignation)

    # Notify manager
    if current_user.manager_id:
        await _notify(
            db, current_user.manager_id,
            "Resignation Submitted",
            f"{current_user.full_name} has submitted their resignation.",
        )

    await db.commit()
    await db.refresh(resignation)

    # Re-fetch with relationships
    resignation = await _get_resignation(db, resignation.id)
    return _resignation_to_read(resignation)


# ─── Employee: Withdraw Resignation ──────────────────────────

@router.post("/resign/withdraw", response_model=ResignationRead)
async def withdraw_resignation(
    *,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Employee withdraws their resignation (only before accepted)."""
    emp = await _get_employee_for_user(db, current_user.id)

    result = await db.execute(
        select(Resignation)
        .options(
            selectinload(Resignation.employee).selectinload(Employee.user),
            selectinload(Resignation.accepted_by),
            selectinload(Resignation.released_by),
        )
        .where(
            Resignation.employee_id == emp.id,
            Resignation.status.in_([
                ResignationStatus.SUBMITTED,
                ResignationStatus.ACCEPTED,
            ])
        )
    )
    resignation = result.scalar_one_or_none()
    if not resignation:
        raise HTTPException(
            status_code=404,
            detail="No active resignation to withdraw"
        )

    resignation.status = ResignationStatus.WITHDRAWN
    resignation.withdrawn_at = datetime.now(timezone.utc)

    # Notify manager
    if current_user.manager_id:
        await _notify(
            db, current_user.manager_id,
            "Resignation Withdrawn",
            f"{current_user.full_name} has withdrawn their resignation.",
        )

    await db.commit()
    await db.refresh(resignation)
    return _resignation_to_read(resignation)


# ─── Employee: Get My Resignation ─────────────────────────────

@router.get("/resign/my", response_model=Optional[ExitDetailsRead])
async def get_my_resignation(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Get the current employee's active resignation details."""
    emp = await _get_employee_for_user(db, current_user.id)

    result = await db.execute(
        select(Resignation)
        .options(
            selectinload(Resignation.employee).selectinload(Employee.user),
            selectinload(Resignation.accepted_by),
            selectinload(Resignation.released_by),
            selectinload(Resignation.exit_interview),
            selectinload(Resignation.clearance_requests)
            .selectinload(ClearanceRequest.items),
            selectinload(Resignation.clearance_requests)
            .selectinload(ClearanceRequest.assigned_to),
        )
        .where(
            Resignation.employee_id == emp.id,
            Resignation.status.notin_([
                ResignationStatus.WITHDRAWN,
                ResignationStatus.REJECTED,
            ])
        )
        .order_by(Resignation.id.desc())
    )
    resignation = result.scalar_one_or_none()
    if not resignation:
        return None

    days_remaining = (resignation.last_working_day - date.today()).days
    all_cleared = all(
        c.status == ClearanceStatus.CLEARED
        for c in resignation.clearance_requests
    ) if resignation.clearance_requests else False

    return ExitDetailsRead(
        resignation=_resignation_to_read(resignation),
        exit_interview=ExitInterviewRead.model_validate(
            resignation.exit_interview, from_attributes=True
        ) if resignation.exit_interview else None,
        clearance_requests=[
            _clearance_to_read(c) for c in resignation.clearance_requests
        ],
        days_remaining=max(0, days_remaining),
        all_cleared=all_cleared,
    )


# ─── Employee: Submit Exit Interview ──────────────────────────

@router.post("/resign/exit-interview", response_model=ExitInterviewRead)
async def submit_exit_interview(
    *,
    db: deps.DBDep,
    body: ExitInterviewSubmit,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Employee fills out exit interview form."""
    emp = await _get_employee_for_user(db, current_user.id)

    result = await db.execute(
        select(Resignation).where(
            Resignation.employee_id == emp.id,
            Resignation.status.in_([
                ResignationStatus.ACCEPTED,
                ResignationStatus.NOTICE_PERIOD,
                ResignationStatus.EXIT_INTERVIEW,
                ResignationStatus.CLEARANCE,
            ])
        )
    )
    resignation = result.scalar_one_or_none()
    if not resignation:
        raise HTTPException(
            status_code=400,
            detail="No active resignation found or not yet accepted"
        )

    # Check if already submitted
    existing = await db.execute(
        select(ExitInterview).where(
            ExitInterview.resignation_id == resignation.id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Exit interview already submitted"
        )

    interview = ExitInterview(
        resignation_id=resignation.id,
        employee_id=emp.id,
        submitted_at=datetime.now(timezone.utc),
        **body.model_dump(),
    )
    db.add(interview)

    # Advance status if currently in exit_interview phase
    if resignation.status == ResignationStatus.EXIT_INTERVIEW:
        resignation.status = ResignationStatus.CLEARANCE

    await db.commit()
    await db.refresh(interview)
    return ExitInterviewRead.model_validate(interview, from_attributes=True)


# ─── HR: List All Resignations ────────────────────────────────

@router.get("/resignations", response_model=List[ResignationRead])
async def list_resignations(
    db: deps.DBDep,
    status: Optional[str] = Query(None),
    current_user: User = Depends(deps.check_permissions([HR_READ])),
) -> Any:
    """HR views all resignations, optionally filtered by status."""
    await _auto_advance_notice_period(db)
    q = (
        select(Resignation)
        .options(
            selectinload(Resignation.employee).selectinload(Employee.user),
            selectinload(Resignation.accepted_by),
            selectinload(Resignation.released_by),
        )
        .order_by(Resignation.created_at.desc())
    )
    if status:
        q = q.where(Resignation.status == status)

    result = await db.execute(q)
    return [_resignation_to_read(r) for r in result.scalars().all()]


# ─── HR: Get Full Exit Details ────────────────────────────────

@router.get(
    "/resignations/{resignation_id}",
    response_model=ExitDetailsRead,
)
async def get_exit_details(
    resignation_id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([HR_READ])),
) -> Any:
    """HR gets full exit details for a resignation."""
    await _auto_advance_notice_period(db)
    resignation = await _get_resignation(db, resignation_id)

    days_remaining = (resignation.last_working_day - date.today()).days
    all_cleared = all(
        c.status == ClearanceStatus.CLEARED
        for c in resignation.clearance_requests
    ) if resignation.clearance_requests else False

    return ExitDetailsRead(
        resignation=_resignation_to_read(resignation),
        exit_interview=ExitInterviewRead.model_validate(
            resignation.exit_interview, from_attributes=True
        ) if resignation.exit_interview else None,
        clearance_requests=[
            _clearance_to_read(c) for c in resignation.clearance_requests
        ],
        days_remaining=max(0, days_remaining),
        all_cleared=all_cleared,
    )


# ─── HR: Accept Resignation ──────────────────────────────────

@router.post(
    "/resignations/{resignation_id}/accept",
    response_model=ResignationRead,
)
async def accept_resignation(
    *,
    db: deps.DBDep,
    resignation_id: int,
    body: ResignationAccept,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """HR accepts a resignation, optionally adjusting last working day."""
    resignation = await _get_resignation(db, resignation_id)

    if resignation.status != ResignationStatus.SUBMITTED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot accept resignation in '{resignation.status}' status"
        )

    resignation.status = ResignationStatus.NOTICE_PERIOD
    resignation.accepted_by_id = current_user.id
    resignation.accepted_at = datetime.now(timezone.utc)

    if body.last_working_day:
        resignation.last_working_day = body.last_working_day

    # Update employee status
    emp = resignation.employee
    emp.status = "notice_period"

    # Notify employee
    await _notify(
        db, emp.user_id,
        "Resignation Accepted",
        f"Your resignation has been accepted. Last working day: {resignation.last_working_day}",
        resource_id=str(resignation.id),
    )

    await db.commit()
    await db.refresh(resignation)
    return _resignation_to_read(resignation)


# ─── HR: Reject Resignation ──────────────────────────────────

@router.post(
    "/resignations/{resignation_id}/reject",
    response_model=ResignationRead,
)
async def reject_resignation(
    *,
    db: deps.DBDep,
    resignation_id: int,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """HR rejects a resignation."""
    resignation = await _get_resignation(db, resignation_id)

    if resignation.status != ResignationStatus.SUBMITTED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject resignation in '{resignation.status}' status"
        )

    resignation.status = ResignationStatus.REJECTED

    # Notify employee
    await _notify(
        db, resignation.employee.user_id,
        "Resignation Rejected",
        "Your resignation request has been rejected. Please contact HR for details.",
        resource_id=str(resignation.id),
    )

    await db.commit()
    await db.refresh(resignation)
    return _resignation_to_read(resignation)


# ─── HR: Cancel / Expedite ───────────────────────────────────


class CancelResignationBody(BaseModel):
    note: str


class ExpediteResignationBody(BaseModel):
    note: str
    last_working_day: date


def _audit(db, request: Optional[Request], current_user: User, action: str,
           resource_id: int, details: dict) -> None:
    """Inline audit-log entry — exit_management doesn't have a shared helper."""
    db.add(AuditLog(
        user_id=current_user.id,
        action=action,
        resource_type="resignation",
        resource_id=str(resource_id),
        details=details,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    ))


CANCELLABLE_STATES = (
    ResignationStatus.SUBMITTED,
    ResignationStatus.ACCEPTED,
    ResignationStatus.NOTICE_PERIOD,
    ResignationStatus.EXIT_INTERVIEW,
    ResignationStatus.CLEARANCE,
)

EXPEDITABLE_STATES = (
    ResignationStatus.ACCEPTED,
    ResignationStatus.NOTICE_PERIOD,
    ResignationStatus.EXIT_INTERVIEW,
)


@router.post(
    "/resignations/{resignation_id}/cancel",
    response_model=ResignationRead,
)
async def cancel_resignation(
    *,
    db: deps.DBDep,
    request: Request,
    resignation_id: int,
    body: CancelResignationBody,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """HR cancels a resignation that's already in motion.

    Differs from the employee-initiated `withdraw` endpoint: HR can cancel
    at any pre-release stage (including notice period and clearance), and
    must record a note explaining why. The employee's status reverts to
    'active' if it was 'notice_period'.
    """
    note = (body.note or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="Note is required")

    resignation = await _get_resignation(db, resignation_id)
    if resignation.status not in CANCELLABLE_STATES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel resignation in '{resignation.status}' status",
        )

    previous_status = resignation.status
    resignation.status = ResignationStatus.WITHDRAWN
    resignation.withdrawn_at = datetime.now(timezone.utc)
    resignation.hr_note = note

    emp = resignation.employee
    if emp and emp.status == "notice_period":
        emp.status = "active"

    if emp and emp.user_id:
        await _notify(
            db, emp.user_id,
            "Resignation Cancelled by HR",
            f"HR cancelled your resignation. Note: {note}",
            resource_id=str(resignation.id),
        )
    if emp and emp.user and emp.user.manager_id:
        await _notify(
            db, emp.user.manager_id,
            "Resignation Cancelled",
            f"HR cancelled the resignation for {emp.user.full_name}.",
            resource_id=str(resignation.id),
        )

    _audit(
        db, request, current_user, "CANCEL_RESIGNATION", resignation.id,
        {
            "employee_id": resignation.employee_id,
            "employee_name": emp.user.full_name if emp and emp.user else None,
            "previous_status": previous_status,
            "note": note,
        },
    )

    await db.commit()
    await db.refresh(resignation)
    return _resignation_to_read(resignation)


@router.post(
    "/resignations/{resignation_id}/expedite",
    response_model=ResignationRead,
)
async def expedite_resignation(
    *,
    db: deps.DBDep,
    request: Request,
    resignation_id: int,
    body: ExpediteResignationBody,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """Pull the last-working-day forward to shorten the notice period.

    Allowed once the resignation has been accepted. The new date must be
    today or later, and earlier than the current LWD. Notice-period days
    are recomputed from the resignation_date so downstream calculations
    stay consistent. The auto-advancer at the top of HR list/detail reads
    will then push the resignation into EXIT_INTERVIEW once the new LWD
    passes — no extra plumbing needed.
    """
    note = (body.note or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="Note is required")

    resignation = await _get_resignation(db, resignation_id)
    if resignation.status not in EXPEDITABLE_STATES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot expedite resignation in '{resignation.status}' status",
        )

    today = date.today()
    new_lwd = body.last_working_day
    if new_lwd < today:
        raise HTTPException(
            status_code=400,
            detail="New last working day cannot be in the past",
        )
    if new_lwd >= resignation.last_working_day:
        raise HTTPException(
            status_code=400,
            detail="New last working day must be earlier than the current one",
        )

    old_lwd = resignation.last_working_day
    old_notice = resignation.notice_period_days

    resignation.last_working_day = new_lwd
    resignation.notice_period_days = max(0, (new_lwd - resignation.resignation_date).days)
    resignation.hr_note = note

    emp = resignation.employee
    if emp and emp.user_id:
        await _notify(
            db, emp.user_id,
            "Resignation Expedited",
            (
                f"HR has moved your last working day forward to "
                f"{new_lwd.strftime('%d %b %Y')}. Note: {note}"
            ),
            resource_id=str(resignation.id),
        )
    if emp and emp.user and emp.user.manager_id:
        await _notify(
            db, emp.user.manager_id,
            "Resignation Expedited",
            (
                f"{emp.user.full_name}'s last working day moved to "
                f"{new_lwd.strftime('%d %b %Y')}."
            ),
            resource_id=str(resignation.id),
        )

    _audit(
        db, request, current_user, "EXPEDITE_RESIGNATION", resignation.id,
        {
            "employee_id": resignation.employee_id,
            "employee_name": emp.user.full_name if emp and emp.user else None,
            "old_last_working_day": old_lwd.isoformat(),
            "new_last_working_day": new_lwd.isoformat(),
            "old_notice_period_days": old_notice,
            "new_notice_period_days": resignation.notice_period_days,
            "note": note,
        },
    )

    await db.commit()
    await db.refresh(resignation)
    return _resignation_to_read(resignation)


# ─── HR: Advance to Exit Interview Phase ─────────────────────

@router.post(
    "/resignations/{resignation_id}/request-exit-interview",
    response_model=ResignationRead,
)
async def request_exit_interview(
    *,
    db: deps.DBDep,
    resignation_id: int,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """HR asks employee to fill exit interview."""
    resignation = await _get_resignation(db, resignation_id)

    if resignation.status not in (
        ResignationStatus.ACCEPTED,
        ResignationStatus.NOTICE_PERIOD,
    ):
        raise HTTPException(
            status_code=400,
            detail="Resignation must be accepted/in notice period first"
        )

    resignation.status = ResignationStatus.EXIT_INTERVIEW

    await _notify(
        db, resignation.employee.user_id,
        "Exit Interview Required",
        "Please complete your exit interview form before your last working day.",
        resource_id=str(resignation.id),
    )

    await db.commit()
    await db.refresh(resignation)
    return _resignation_to_read(resignation)


# ─── HR: Add HR Remarks to Exit Interview ────────────────────

@router.post(
    "/resignations/{resignation_id}/exit-interview/remarks",
    response_model=ExitInterviewRead,
)
async def add_exit_interview_remarks(
    *,
    db: deps.DBDep,
    resignation_id: int,
    body: ExitInterviewHRRemarks,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """HR adds remarks to exit interview."""
    result = await db.execute(
        select(ExitInterview).where(
            ExitInterview.resignation_id == resignation_id
        )
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(
            status_code=404,
            detail="Exit interview not found"
        )

    interview.hr_remarks = body.hr_remarks
    interview.hr_reviewed_by_id = current_user.id
    await db.commit()
    await db.refresh(interview)
    return ExitInterviewRead.model_validate(interview, from_attributes=True)


# ─── HR: Initiate Clearance ──────────────────────────────────

@router.post(
    "/resignations/{resignation_id}/clearance",
    response_model=List[ClearanceRequestRead],
)
async def initiate_clearance(
    *,
    db: deps.DBDep,
    resignation_id: int,
    body: InitiateClearance,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """HR initiates clearance by tagging departments/users."""
    resignation = await _get_resignation(db, resignation_id)

    if resignation.status not in (
        ResignationStatus.NOTICE_PERIOD,
        ResignationStatus.EXIT_INTERVIEW,
        ResignationStatus.CLEARANCE,
        ResignationStatus.ACCEPTED,
    ):
        raise HTTPException(
            status_code=400,
            detail="Cannot initiate clearance at this stage"
        )

    resignation.status = ResignationStatus.CLEARANCE

    created = []
    for c in body.clearances:
        cr = ClearanceRequest(
            resignation_id=resignation.id,
            department=c.department,
            assigned_to_id=c.assigned_to_id,
            status=ClearanceStatus.PENDING,
        )
        db.add(cr)
        await db.flush()

        for item in c.items:
            db.add(ClearanceItem(
                clearance_request_id=cr.id,
                item_name=item.item_name,
            ))

        # Notify assigned user
        emp_name = resignation.employee.user.full_name if resignation.employee.user else "Employee"
        await _notify(
            db, c.assigned_to_id,
            "Clearance Required",
            f"Please complete clearance for {emp_name} ({c.department}).",
            resource_type="clearance",
            resource_id=str(cr.id),
        )
        created.append(cr)

    await db.commit()

    # Re-fetch with items
    result = await db.execute(
        select(ClearanceRequest)
        .options(
            selectinload(ClearanceRequest.items),
            selectinload(ClearanceRequest.assigned_to),
        )
        .where(ClearanceRequest.resignation_id == resignation_id)
    )
    return [_clearance_to_read(c) for c in result.scalars().all()]


# ─── Department Head: Action Clearance ────────────────────────

@router.post(
    "/clearance/{clearance_id}/action",
    response_model=ClearanceRequestRead,
)
async def action_clearance(
    *,
    db: deps.DBDep,
    clearance_id: int,
    body: ClearanceAction,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Department head clears or flags a clearance request."""
    result = await db.execute(
        select(ClearanceRequest)
        .options(
            selectinload(ClearanceRequest.items),
            selectinload(ClearanceRequest.assigned_to),
            selectinload(ClearanceRequest.resignation)
            .selectinload(Resignation.employee)
            .selectinload(Employee.user),
        )
        .where(ClearanceRequest.id == clearance_id)
    )
    cr = result.scalar_one_or_none()
    if not cr:
        raise HTTPException(status_code=404, detail="Clearance request not found")

    # Must be assigned user or HR
    is_hr = any(
        p.name == HR_WRITE
        for r in current_user.roles
        for p in r.permissions
    )
    if cr.assigned_to_id != current_user.id and not is_hr:
        raise HTTPException(status_code=403, detail="Not authorized")

    if body.status not in (ClearanceStatus.CLEARED, ClearanceStatus.FLAGGED):
        raise HTTPException(
            status_code=400,
            detail="Status must be 'cleared' or 'flagged'"
        )

    cr.status = body.status
    cr.remarks = body.remarks
    if body.status == ClearanceStatus.CLEARED:
        cr.cleared_at = datetime.now(timezone.utc)

    # Update individual items if provided
    if body.items and cr.items:
        for idx, item_update in enumerate(body.items):
            if idx < len(cr.items):
                cr.items[idx].is_cleared = item_update.is_cleared
                cr.items[idx].remarks = item_update.remarks

    await db.commit()
    await db.refresh(cr)
    return _clearance_to_read(cr)


# ─── User: My Clearance Tasks ────────────────────────────────

@router.get("/clearance/my", response_model=List[ClearanceRequestRead])
async def my_clearance_tasks(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Get clearance tasks assigned to the current user."""
    result = await db.execute(
        select(ClearanceRequest)
        .options(
            selectinload(ClearanceRequest.items),
            selectinload(ClearanceRequest.assigned_to),
            selectinload(ClearanceRequest.resignation)
            .selectinload(Resignation.employee)
            .selectinload(Employee.user),
        )
        .where(ClearanceRequest.assigned_to_id == current_user.id)
        .order_by(ClearanceRequest.created_at.desc())
    )
    return [_clearance_to_read(c) for c in result.scalars().all()]


# ─── HR: Final Release ───────────────────────────────────────

@router.post(
    "/resignations/{resignation_id}/release",
    response_model=ResignationRead,
)
async def final_release(
    *,
    db: deps.DBDep,
    resignation_id: int,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """HR final release — deactivates user account."""
    resignation = await _get_resignation(db, resignation_id)

    if resignation.status not in (
        ResignationStatus.CLEARANCE,
        ResignationStatus.EXIT_INTERVIEW,
        ResignationStatus.NOTICE_PERIOD,
    ):
        raise HTTPException(
            status_code=400,
            detail="Cannot release at this stage"
        )

    # Check all clearances are done
    pending = [
        c for c in resignation.clearance_requests
        if c.status != ClearanceStatus.CLEARED
    ]
    if pending:
        depts = ", ".join(c.department for c in pending)
        raise HTTPException(
            status_code=400,
            detail=f"Pending clearances from: {depts}"
        )

    resignation.status = ResignationStatus.RELEASED
    resignation.released_by_id = current_user.id
    resignation.released_at = datetime.now(timezone.utc)

    # Deactivate employee and user
    emp = resignation.employee
    emp.status = "inactive"
    emp.user.is_active = False

    # Notify employee
    await _notify(
        db, emp.user_id,
        "Employment Released",
        "Your employment has been formally released. Thank you for your service.",
        resource_id=str(resignation.id),
    )

    await db.commit()
    await db.refresh(resignation)
    return _resignation_to_read(resignation)
