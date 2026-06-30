"""Designation/Grade master + SalaryRevision + RevisionCycle endpoints.

Promotion gating: PROMOTION revisions require `revision approve hr` (HR
or CEO). All other revision types (INCREMENT/CORRECTION/DEMOTION) accept
the broader `revision approve` permission (manager / dept head / HR).
"""
import io
import json
from datetime import date, datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.v1.endpoints.hr import log_audit
from app.models.approval import ApprovalItem, ApprovalStatus, ApprovalStep
from app.models.designation import Designation, Grade
from app.models.employee import Employee
from app.models.hr import EmployeeLetter, LetterType
from app.models.notification import Notification
from app.models.revision import (
    CycleStatus, RevisionCycle, RevisionStatus, RevisionType,
    SalaryRevision,
)
from app.models.user import User
from app.schemas.revision import (
    ActionRequest,
    ApplyDueResult,
    BulkActionResult,
    CompensationHistoryEntry,
    CycleBulkDraftRequest,
    CycleBulkSubmitRequest,
    CycleCreate, CycleRead, CycleUpdate,
    DesignationCreate, DesignationRead, DesignationUpdate,
    GradeCreate, GradeRead, GradeUpdate,
    SalaryRevisionCreate, SalaryRevisionRead, SalaryRevisionUpdate,
)
from app.services.letter_pdf import generate_letter
from app.services.revisions import (
    band_warning_for, derive_hike,
)

router = APIRouter()


PERM_MASTER_WRITE = "designation master write"
PERM_REV_WRITE = "revision write"
PERM_REV_APPROVE = "revision approve"          # mgr / dept head / HR
PERM_REV_APPROVE_HR = "revision approve hr"    # HR / CEO — required for PROMOTION
PERM_REV_APPLY = "revision apply"              # HR manual apply-now
PERM_REV_VIEW_ALL = "revision view all"


# =====================================================================
# helpers
# =====================================================================


def _user_can_view_all(user: User) -> bool:
    if user.is_superuser:
        return True
    role_names = [(r.name or "").lower() for r in user.roles or []]
    if any(n in role_names for n in ("hr", "super admin", "admin", "ceo")):
        return True
    for role in user.roles or []:
        for perm in role.permissions or []:
            if (perm.name or "") in (
                PERM_REV_VIEW_ALL, PERM_REV_APPROVE, PERM_REV_APPROVE_HR,
                PERM_REV_WRITE,
            ):
                return True
    return False


def _user_has_perm(user: User, name: str) -> bool:
    if user.is_superuser:
        return True
    for role in user.roles or []:
        for perm in role.permissions or []:
            if (perm.name or "") == name:
                return True
    return False


def _ensure_can_approve(user: User, rev: SalaryRevision) -> None:
    if rev.revision_type == RevisionType.PROMOTION:
        if not _user_has_perm(user, PERM_REV_APPROVE_HR):
            raise HTTPException(
                403,
                "Promotion approval requires HR / CEO authority.",
            )
        return
    if not (
        _user_has_perm(user, PERM_REV_APPROVE)
        or _user_has_perm(user, PERM_REV_APPROVE_HR)
    ):
        raise HTTPException(403, "Not authorized to approve revisions")


async def _enrich_revision(
    db, rev: SalaryRevision
) -> SalaryRevisionRead:
    emp = await db.get(Employee, rev.employee_id, options=[
        selectinload(Employee.user),
    ])
    full_name = code = dept = None
    if emp:
        code = emp.employee_id
        dept = emp.department
        if emp.user:
            full_name = emp.user.full_name

    def _title(_id: Optional[int]) -> Optional[str]:
        return None if _id is None else None  # placeholder; resolved below
    od = await db.get(Designation, rev.old_designation_id) if rev.old_designation_id else None
    nd = await db.get(Designation, rev.new_designation_id) if rev.new_designation_id else None
    og = await db.get(Grade, rev.old_grade_id) if rev.old_grade_id else None
    ng = await db.get(Grade, rev.new_grade_id) if rev.new_grade_id else None

    data = {c.name: getattr(rev, c.name) for c in rev.__table__.columns}
    data["employee_full_name"] = full_name
    data["employee_code"] = code
    data["department"] = dept
    data["old_designation_title"] = od.title if od else None
    data["new_designation_title"] = nd.title if nd else None
    data["old_grade_name"] = og.name if og else None
    data["new_grade_name"] = ng.name if ng else None
    return SalaryRevisionRead.model_validate(data)


async def _snapshot_current_employee(
    db, emp: Employee,
) -> dict:
    """Capture the current Employee state to seed the OLD side of a
    revision. Pulls existing designation / grade FKs when set, falls
    back to the legacy strings via a best-effort lookup."""
    old_designation_id = emp.designation_id
    if old_designation_id is None and emp.designation:
        d = (await db.execute(
            select(Designation).where(
                func.lower(Designation.title) == func.lower(emp.designation)
            ).limit(1)
        )).scalar_one_or_none()
        old_designation_id = d.id if d else None
    old_grade_id = emp.grade_id

    basic = float(emp.salary or 0.0)
    ca = float(
        emp.conveyance_allowance if emp.conveyance_allowance is not None
        else round(basic * 0.30)
    )
    hra = float(
        emp.hra if emp.hra is not None else round(basic * 0.50)
    )
    other = float(
        emp.other_allowance if emp.other_allowance is not None
        else round(basic * 0.20)
    )
    ctc = basic + ca + hra + other
    return {
        "old_designation_id": old_designation_id,
        "old_grade_id": old_grade_id,
        "old_basic": basic,
        "old_conveyance": ca,
        "old_hra": hra,
        "old_other_allowance": other,
        "old_ctc": ctc,
    }


async def _band_warning(
    db, *, new_grade_id: Optional[int], new_ctc: float
) -> Optional[str]:
    if new_grade_id is None:
        return None
    g = await db.get(Grade, new_grade_id)
    if g is None:
        return None
    return band_warning_for(new_ctc, g.min_salary, g.max_salary)


# =====================================================================
# Grade CRUD
# =====================================================================


@router.get("/grades", response_model=List[GradeRead])
async def list_grades(
    db: deps.DBDep,
    include_inactive: bool = Query(False),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(Grade)
    if not include_inactive:
        stmt = stmt.where(Grade.is_active.is_(True))
    stmt = stmt.order_by(Grade.rank, Grade.name)
    return list((await db.execute(stmt)).scalars().all())


@router.post("/grades", response_model=GradeRead)
async def create_grade(
    payload: GradeCreate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_MASTER_WRITE])),
) -> Any:
    obj = Grade(**payload.model_dump())
    db.add(obj)
    await db.flush()
    await log_audit(db, current_user.id, "GRADE_CREATE", "grade",
                    str(obj.id), payload.model_dump(), request)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/grades/{grade_id}", response_model=GradeRead)
async def update_grade(
    grade_id: int,
    payload: GradeUpdate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_MASTER_WRITE])),
) -> Any:
    g = await db.get(Grade, grade_id)
    if g is None:
        raise HTTPException(404, "Grade not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(g, k, v)
    await log_audit(db, current_user.id, "GRADE_UPDATE", "grade",
                    str(grade_id), data, request)
    await db.commit()
    await db.refresh(g)
    return g


@router.delete("/grades/{grade_id}")
async def delete_grade(
    grade_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_MASTER_WRITE])),
) -> Any:
    g = await db.get(Grade, grade_id)
    if g is None:
        raise HTTPException(404, "Grade not found")
    g.is_active = False
    await log_audit(db, current_user.id, "GRADE_DEACTIVATE", "grade",
                    str(grade_id), {}, request)
    await db.commit()
    return {"message": "Grade deactivated"}


# =====================================================================
# Designation CRUD
# =====================================================================


@router.get("/designations", response_model=List[DesignationRead])
async def list_designations(
    db: deps.DBDep,
    include_inactive: bool = Query(False),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(Designation).options(selectinload(Designation.grade))
    if not include_inactive:
        stmt = stmt.where(Designation.is_active.is_(True))
    rows = (await db.execute(stmt.order_by(Designation.title))).scalars().all()
    out: List[DesignationRead] = []
    for d in rows:
        out.append(DesignationRead.model_validate({
            **{c.name: getattr(d, c.name) for c in d.__table__.columns},
            "grade_name": d.grade.name if d.grade else None,
        }))
    return out


@router.post("/designations", response_model=DesignationRead)
async def create_designation(
    payload: DesignationCreate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_MASTER_WRITE])),
) -> Any:
    obj = Designation(**payload.model_dump())
    db.add(obj)
    await db.flush()
    await log_audit(db, current_user.id, "DESIGNATION_CREATE", "designation",
                    str(obj.id), payload.model_dump(), request)
    await db.commit()
    await db.refresh(obj, ["grade"])
    return DesignationRead.model_validate({
        **{c.name: getattr(obj, c.name) for c in obj.__table__.columns},
        "grade_name": obj.grade.name if obj.grade else None,
    })


@router.patch("/designations/{designation_id}", response_model=DesignationRead)
async def update_designation(
    designation_id: int,
    payload: DesignationUpdate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_MASTER_WRITE])),
) -> Any:
    d = await db.get(Designation, designation_id)
    if d is None:
        raise HTTPException(404, "Designation not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(d, k, v)
    await log_audit(db, current_user.id, "DESIGNATION_UPDATE", "designation",
                    str(designation_id), data, request)
    await db.commit()
    await db.refresh(d, ["grade"])
    return DesignationRead.model_validate({
        **{c.name: getattr(d, c.name) for c in d.__table__.columns},
        "grade_name": d.grade.name if d.grade else None,
    })


@router.delete("/designations/{designation_id}")
async def delete_designation(
    designation_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_MASTER_WRITE])),
) -> Any:
    d = await db.get(Designation, designation_id)
    if d is None:
        raise HTTPException(404, "Designation not found")
    d.is_active = False
    await log_audit(db, current_user.id, "DESIGNATION_DEACTIVATE",
                    "designation", str(designation_id), {}, request)
    await db.commit()
    return {"message": "Designation deactivated"}


@router.get("/designations/unmatched-employees")
async def list_unmatched_employees(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([PERM_MASTER_WRITE])),
) -> Any:
    """Employees whose legacy designation string has no FK match — the
    migration cleanup queue."""
    rows = (await db.execute(
        select(Employee).where(
            and_(
                Employee.designation_id.is_(None),
                Employee.designation.isnot(None),
            )
        ).options(selectinload(Employee.user))
    )).scalars().all()
    return [
        {
            "employee_id": e.employee_id, "user_id": e.user_id,
            "name": e.user.full_name if e.user else None,
            "department": e.department,
            "designation_text": e.designation,
        }
        for e in rows
    ]


# =====================================================================
# SalaryRevision — create / edit / submit / approve / reject / apply
# =====================================================================


async def _save_with_derivation(
    db, rev: SalaryRevision,
) -> None:
    rev.hike_amount, rev.hike_percent = derive_hike(rev.old_ctc, rev.new_ctc)
    rev.band_warning = await _band_warning(
        db, new_grade_id=rev.new_grade_id, new_ctc=rev.new_ctc,
    )


@router.post("/revisions", response_model=SalaryRevisionRead)
async def create_revision(
    payload: SalaryRevisionCreate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_REV_WRITE])),
) -> Any:
    emp = await db.get(Employee, payload.employee_id)
    if emp is None:
        raise HTTPException(404, "Employee not found")
    snap = await _snapshot_current_employee(db, emp)
    rev = SalaryRevision(
        employee_id=payload.employee_id,
        cycle_id=payload.cycle_id,
        revision_type=payload.revision_type,
        effective_from=payload.effective_from,
        reason=payload.reason,
        new_designation_id=payload.new_designation_id,
        new_grade_id=payload.new_grade_id,
        new_basic=payload.new_basic,
        new_conveyance=payload.new_conveyance,
        new_hra=payload.new_hra,
        new_other_allowance=payload.new_other_allowance,
        new_ctc=payload.new_ctc,
        status=RevisionStatus.DRAFT,
        created_by_id=current_user.id,
        **snap,
    )
    await _save_with_derivation(db, rev)
    db.add(rev)
    await db.flush()
    await log_audit(
        db, current_user.id, "REVISION_CREATE", "salary_revision",
        str(rev.id),
        {"employee_id": rev.employee_id, "type": rev.revision_type},
        request,
    )
    await db.commit()
    await db.refresh(rev)
    return await _enrich_revision(db, rev)


@router.patch("/revisions/{rev_id}", response_model=SalaryRevisionRead)
async def update_revision(
    rev_id: int,
    payload: SalaryRevisionUpdate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_REV_WRITE])),
) -> Any:
    rev = await db.get(SalaryRevision, rev_id)
    if rev is None:
        raise HTTPException(404, "Revision not found")
    if rev.status not in (RevisionStatus.DRAFT, RevisionStatus.PENDING):
        raise HTTPException(
            400, f"Cannot edit a revision in status {rev.status}"
        )
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(rev, k, v)
    await _save_with_derivation(db, rev)
    await log_audit(db, current_user.id, "REVISION_UPDATE",
                    "salary_revision", str(rev_id), data, request)
    await db.commit()
    await db.refresh(rev)
    return await _enrich_revision(db, rev)


@router.post("/revisions/{rev_id}/submit", response_model=SalaryRevisionRead)
async def submit_revision(
    rev_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_REV_WRITE])),
) -> Any:
    rev = await db.get(SalaryRevision, rev_id)
    if rev is None:
        raise HTTPException(404, "Revision not found")
    if rev.status != RevisionStatus.DRAFT:
        raise HTTPException(400, f"Can only submit DRAFT (was {rev.status})")
    # Create approval-engine row.
    emp = await db.get(Employee, rev.employee_id, options=[
        selectinload(Employee.user)
    ])
    requester_id = emp.user.id if emp and emp.user else current_user.id

    item = ApprovalItem(
        resource_type="salary_revision",
        resource_id=str(rev.id),
        status=ApprovalStatus.PENDING,
        current_step_number=1,
        requested_by_id=requester_id,
    )
    db.add(item)
    await db.flush()

    # Step 1: manager (if exists) else HR-fallback (skipped to step 2).
    manager_id = getattr(emp.user, "manager_id", None) if emp and emp.user else None
    db.add(ApprovalStep(
        approval_item_id=item.id, step_number=1,
        approver_id=manager_id, status=ApprovalStatus.PENDING,
    ))
    rev.approval_item_id = item.id
    rev.status = RevisionStatus.PENDING

    if manager_id:
        db.add(Notification(
            user_id=manager_id,
            title="Salary revision awaiting approval",
            message=(
                f"Revision for {emp.user.full_name if emp and emp.user else 'employee'} "
                f"(₹{rev.new_ctc:,.0f}, effective {rev.effective_from}) needs your approval."
            ),
            type="info",
            resource_type="salary_revision",
            resource_id=str(rev.id),
        ))

    await log_audit(db, current_user.id, "REVISION_SUBMIT", "salary_revision",
                    str(rev.id), {"effective_from": rev.effective_from.isoformat()},
                    request)
    await db.commit()
    await db.refresh(rev)
    return await _enrich_revision(db, rev)


@router.post("/revisions/{rev_id}/action", response_model=SalaryRevisionRead)
async def action_revision(
    rev_id: int,
    payload: ActionRequest,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    rev = await db.get(SalaryRevision, rev_id)
    if rev is None:
        raise HTTPException(404, "Revision not found")
    if payload.action == "cancel":
        if rev.status not in (RevisionStatus.DRAFT, RevisionStatus.PENDING):
            raise HTTPException(400, f"Cannot cancel in status {rev.status}")
        if not _user_has_perm(current_user, PERM_REV_WRITE):
            raise HTTPException(403, "Not authorized")
        rev.status = RevisionStatus.CANCELLED
        await log_audit(db, current_user.id, "REVISION_CANCEL",
                        "salary_revision", str(rev.id),
                        {"comment": payload.comment}, request)
        await db.commit()
        await db.refresh(rev)
        return await _enrich_revision(db, rev)

    if rev.status != RevisionStatus.PENDING:
        raise HTTPException(400, f"Not actionable in status {rev.status}")

    _ensure_can_approve(current_user, rev)

    now = datetime.now(timezone.utc)
    if payload.action == "approve":
        rev.status = RevisionStatus.APPROVED
    else:
        rev.status = RevisionStatus.REJECTED
        rev.rejected_reason = payload.comment or None

    # Mirror onto the approval item.
    if rev.approval_item_id:
        ai = await db.execute(
            select(ApprovalItem).where(
                ApprovalItem.id == rev.approval_item_id
            ).options(selectinload(ApprovalItem.steps))
        )
        ai = ai.scalar_one_or_none()
        if ai:
            for step in ai.steps:
                if step.status == ApprovalStatus.PENDING:
                    step.status = (
                        ApprovalStatus.APPROVED if payload.action == "approve"
                        else ApprovalStatus.REJECTED
                    )
                    step.approver_id = current_user.id
                    step.actioned_at = now
                    step.comment = payload.comment or step.comment
            ai.status = (
                ApprovalStatus.APPROVED if payload.action == "approve"
                else ApprovalStatus.REJECTED
            )

    # Notify employee.
    emp = await db.get(Employee, rev.employee_id, options=[
        selectinload(Employee.user)
    ])
    if emp and emp.user:
        if payload.action == "approve":
            title = "Salary revision approved"
            msg = (
                f"Your revision is approved and will take effect on "
                f"{rev.effective_from}."
            )
            ntype = "success"
        else:
            title = "Salary revision rejected"
            msg = f"Your revision was rejected: {payload.comment or 'No reason'}"
            ntype = "warning"
        db.add(Notification(
            user_id=emp.user.id, title=title, message=msg, type=ntype,
            resource_type="salary_revision", resource_id=str(rev.id),
        ))

    await log_audit(
        db, current_user.id,
        "REVISION_APPROVE" if payload.action == "approve" else "REVISION_REJECT",
        "salary_revision", str(rev.id),
        {"comment": payload.comment}, request,
    )
    await db.commit()
    await db.refresh(rev)
    return await _enrich_revision(db, rev)


# ----- apply (manual + due-job) --------------------------------------


async def _apply_one(
    db, rev: SalaryRevision, *, actor_id: int,
) -> tuple[bool, Optional[str]]:
    """Apply the revision to the employee master and generate the letter.

    Returns (success, error_message_if_skipped).
    """
    if rev.status != RevisionStatus.APPROVED:
        return False, f"Revision {rev.id} not APPROVED"
    emp = await db.get(Employee, rev.employee_id, options=[
        selectinload(Employee.user)
    ])
    if emp is None:
        return False, f"Employee {rev.employee_id} missing"

    # Mutate the employee master.
    emp.salary = rev.new_basic
    emp.conveyance_allowance = rev.new_conveyance
    emp.hra = rev.new_hra
    emp.other_allowance = rev.new_other_allowance
    if rev.new_designation_id:
        emp.designation_id = rev.new_designation_id
        # Mirror onto the legacy free-text column for downstream readers
        # that haven't migrated yet (letters, payslip PDFs).
        d = await db.get(Designation, rev.new_designation_id)
        if d:
            emp.designation = d.title
    if rev.new_grade_id:
        emp.grade_id = rev.new_grade_id
        g = await db.get(Grade, rev.new_grade_id)
        if g:
            emp.grade = g.name

    rev.status = RevisionStatus.APPLIED
    rev.applied_at = datetime.now(timezone.utc)
    rev.applied_by_id = actor_id

    # Generate letter (Promotion or Salary Revision).
    letter_type = (
        LetterType.PROMOTION if rev.revision_type == RevisionType.PROMOTION
        else LetterType.SALARY_REVISION
    )
    count_q = select(func.count(EmployeeLetter.id)).where(
        EmployeeLetter.letter_type == letter_type
    )
    n = (await db.execute(count_q)).scalar() or 0
    ref_prefix = letter_type.upper().replace("_", "-")
    year_str = datetime.now(timezone.utc).strftime("%Y")
    ref_number = f"UEIPL/{ref_prefix}/{year_str}/{n + 1:04d}"

    old_d = await db.get(Designation, rev.old_designation_id) if rev.old_designation_id else None
    new_d = await db.get(Designation, rev.new_designation_id) if rev.new_designation_id else None
    old_g = await db.get(Grade, rev.old_grade_id) if rev.old_grade_id else None
    new_g = await db.get(Grade, rev.new_grade_id) if rev.new_grade_id else None

    template_data = {
        "reference_number": ref_number,
        "date": rev.applied_at.date().isoformat(),
        "employee_name": emp.user.full_name if emp.user else "",
        "employee_code": emp.employee_id,
        "department": emp.department,
        "designation": (new_d.title if new_d else emp.designation),
        "old_designation": old_d.title if old_d else emp.designation,
        "new_designation": new_d.title if new_d else emp.designation,
        "old_grade": old_g.name if old_g else "",
        "new_grade": new_g.name if new_g else "",
        "old_ctc": rev.old_ctc, "new_ctc": rev.new_ctc,
        "hike_amount": rev.hike_amount,
        "hike_percent": rev.hike_percent,
        "effective_date": rev.effective_from.isoformat(),
        "revision_type": rev.revision_type,
        "new_basic": rev.new_basic, "new_hra": rev.new_hra,
        "new_conveyance": rev.new_conveyance,
        "new_other_allowance": rev.new_other_allowance,
    }
    pdf_bytes = generate_letter(letter_type, template_data)
    file_url = f"/letters/{ref_number.replace('/', '_')}.pdf"

    letter = EmployeeLetter(
        employee_id=emp.id, letter_type=letter_type,
        reference_number=ref_number, generated_by_id=actor_id,
        template_data=json.dumps(template_data),
        status="generated", file_url=file_url,
    )
    db.add(letter)
    await db.flush()
    rev.letter_id = letter.id
    # Persist PDF bytes onto template_data so the download endpoint
    # below can regenerate identically (matches existing letter flow
    # that stores template_data + regenerates).
    return True, None


@router.post("/revisions/{rev_id}/apply", response_model=SalaryRevisionRead)
async def apply_now(
    rev_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_REV_APPLY])),
) -> Any:
    rev = await db.get(SalaryRevision, rev_id)
    if rev is None:
        raise HTTPException(404, "Revision not found")
    ok, err = await _apply_one(db, rev, actor_id=current_user.id)
    if not ok:
        raise HTTPException(400, err or "Cannot apply")
    await log_audit(db, current_user.id, "REVISION_APPLY",
                    "salary_revision", str(rev.id),
                    {"effective_from": rev.effective_from.isoformat(),
                     "letter_id": rev.letter_id}, request)
    await db.commit()
    await db.refresh(rev)
    return await _enrich_revision(db, rev)


@router.post("/revisions/apply-due", response_model=ApplyDueResult)
async def apply_due(
    db: deps.DBDep,
    request: Request,
    as_of: Optional[date] = Query(None),
    current_user: User = Depends(deps.check_permissions([PERM_REV_APPLY])),
) -> Any:
    """Apply every APPROVED revision whose effective_from <= as_of (today)."""
    cutoff = as_of or date.today()
    rows = (await db.execute(
        select(SalaryRevision).where(and_(
            SalaryRevision.status == RevisionStatus.APPROVED,
            SalaryRevision.effective_from <= cutoff,
        ))
    )).scalars().all()
    applied = skipped = 0
    errors: List[str] = []
    for r in rows:
        ok, err = await _apply_one(db, r, actor_id=current_user.id)
        if ok:
            applied += 1
        else:
            skipped += 1
            if err:
                errors.append(f"#{r.id}: {err}")
    await log_audit(
        db, current_user.id, "REVISION_APPLY_DUE", "salary_revision", "*",
        {"as_of": cutoff.isoformat(), "applied": applied, "skipped": skipped},
        request,
    )
    await db.commit()
    return ApplyDueResult(
        as_of=cutoff, applied=applied, skipped=skipped, errors=errors,
    )


@router.get("/revisions", response_model=List[SalaryRevisionRead])
async def list_revisions(
    db: deps.DBDep,
    status: Optional[str] = Query(None),
    employee_id: Optional[int] = Query(None),
    cycle_id: Optional[int] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(SalaryRevision)
    if status:
        stmt = stmt.where(SalaryRevision.status == status)
    if cycle_id is not None:
        stmt = stmt.where(SalaryRevision.cycle_id == cycle_id)
    view_all = _user_can_view_all(current_user)
    if not view_all:
        # Limit to own
        emp = (await db.execute(
            select(Employee).where(Employee.user_id == current_user.id)
        )).scalar_one_or_none()
        if emp is None:
            return []
        stmt = stmt.where(SalaryRevision.employee_id == emp.id)
    elif employee_id is not None:
        stmt = stmt.where(SalaryRevision.employee_id == employee_id)
    stmt = stmt.order_by(SalaryRevision.effective_from.desc(),
                         SalaryRevision.id.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [await _enrich_revision(db, r) for r in rows]


@router.get(
    "/revisions/my",
    response_model=List[SalaryRevisionRead],
)
async def my_revisions(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    emp = (await db.execute(
        select(Employee).where(Employee.user_id == current_user.id)
    )).scalar_one_or_none()
    if emp is None:
        return []
    rows = (await db.execute(
        select(SalaryRevision).where(
            SalaryRevision.employee_id == emp.id,
        ).order_by(SalaryRevision.effective_from.desc())
    )).scalars().all()
    return [await _enrich_revision(db, r) for r in rows]


@router.get(
    "/revisions/history/{employee_id}",
    response_model=List[CompensationHistoryEntry],
)
async def compensation_history(
    employee_id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    # Self or anyone with view-all may see.
    emp = await db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(404, "Employee not found")
    if emp.user_id != current_user.id and not _user_can_view_all(current_user):
        raise HTTPException(403, "Not authorized")
    rows = (await db.execute(
        select(SalaryRevision).where(
            SalaryRevision.employee_id == employee_id,
        ).order_by(SalaryRevision.effective_from)
    )).scalars().all()
    out: List[CompensationHistoryEntry] = []
    for r in rows:
        od = await db.get(Designation, r.old_designation_id) if r.old_designation_id else None
        nd = await db.get(Designation, r.new_designation_id) if r.new_designation_id else None
        out.append(CompensationHistoryEntry(
            revision_id=r.id, effective_from=r.effective_from,
            revision_type=r.revision_type, status=r.status,
            old_designation_title=od.title if od else None,
            new_designation_title=nd.title if nd else None,
            old_ctc=r.old_ctc, new_ctc=r.new_ctc,
            hike_amount=r.hike_amount, hike_percent=r.hike_percent,
            applied_at=r.applied_at, letter_id=r.letter_id,
        ))
    return out


# =====================================================================
# letter download (shared with existing /hr/letters/{id}/download)
# =====================================================================


@router.get("/revisions/{rev_id}/letter")
async def download_revision_letter(
    rev_id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    rev = await db.get(SalaryRevision, rev_id)
    if rev is None:
        raise HTTPException(404, "Revision not found")
    if rev.letter_id is None:
        raise HTTPException(404, "No letter generated yet")
    emp = await db.get(Employee, rev.employee_id)
    if emp is None:
        raise HTTPException(404, "Employee missing")
    if (
        emp.user_id != current_user.id
        and not _user_can_view_all(current_user)
    ):
        raise HTTPException(403, "Not authorized")
    letter = await db.get(EmployeeLetter, rev.letter_id)
    if letter is None or letter.template_data is None:
        raise HTTPException(404, "Letter record missing")
    template_data = json.loads(letter.template_data)
    pdf_bytes = generate_letter(letter.letter_type, template_data)
    fname = (letter.reference_number or f"revision_{rev_id}").replace("/", "_")
    return StreamingResponse(
        io.BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'},
    )


# =====================================================================
# RevisionCycle
# =====================================================================


async def _cycle_summary(db, cycle: RevisionCycle) -> dict:
    rows = (await db.execute(
        select(SalaryRevision).where(SalaryRevision.cycle_id == cycle.id)
    )).scalars().all()
    by_status: dict = {}
    total_hike = 0.0
    pct_sum = 0.0
    pct_count = 0
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        total_hike += r.hike_amount
        if r.hike_percent:
            pct_sum += r.hike_percent
            pct_count += 1
    return {
        "total_revisions": len(rows),
        "total_hike_amount": round(total_hike, 2),
        "avg_hike_percent": round(pct_sum / pct_count, 2) if pct_count else 0.0,
        "by_status": by_status,
    }


@router.get("/cycles", response_model=List[CycleRead])
async def list_cycles(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    rows = (await db.execute(
        select(RevisionCycle).order_by(RevisionCycle.effective_from.desc())
    )).scalars().all()
    out = []
    for c in rows:
        s = await _cycle_summary(db, c)
        out.append(CycleRead.model_validate({
            **{col.name: getattr(c, col.name) for col in c.__table__.columns},
            **s,
        }))
    return out


@router.post("/cycles", response_model=CycleRead)
async def create_cycle(
    payload: CycleCreate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_REV_WRITE])),
) -> Any:
    c = RevisionCycle(**payload.model_dump(), created_by_id=current_user.id)
    db.add(c)
    await db.flush()
    await log_audit(db, current_user.id, "CYCLE_CREATE", "revision_cycle",
                    str(c.id), payload.model_dump(mode="json"), request)
    await db.commit()
    await db.refresh(c)
    s = await _cycle_summary(db, c)
    return CycleRead.model_validate({
        **{col.name: getattr(c, col.name) for col in c.__table__.columns},
        **s,
    })


@router.patch("/cycles/{cycle_id}", response_model=CycleRead)
async def update_cycle(
    cycle_id: int,
    payload: CycleUpdate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_REV_WRITE])),
) -> Any:
    c = await db.get(RevisionCycle, cycle_id)
    if c is None:
        raise HTTPException(404, "Cycle not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(c, k, v)
    await log_audit(db, current_user.id, "CYCLE_UPDATE", "revision_cycle",
                    str(cycle_id),
                    {k: (v.isoformat() if hasattr(v, "isoformat") else v)
                     for k, v in data.items()},
                    request)
    await db.commit()
    await db.refresh(c)
    s = await _cycle_summary(db, c)
    return CycleRead.model_validate({
        **{col.name: getattr(c, col.name) for col in c.__table__.columns},
        **s,
    })


@router.post("/cycles/{cycle_id}/bulk-draft", response_model=BulkActionResult)
async def cycle_bulk_draft(
    cycle_id: int,
    payload: CycleBulkDraftRequest,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_REV_WRITE])),
) -> Any:
    cycle = await db.get(RevisionCycle, cycle_id)
    if cycle is None:
        raise HTTPException(404, "Cycle not found")
    if cycle.status not in (CycleStatus.DRAFT, CycleStatus.PENDING):
        raise HTTPException(400, f"Cycle locked (status={cycle.status})")

    # Resolve target employees.
    if payload.employee_ids:
        emp_q = select(Employee).where(
            Employee.id.in_(payload.employee_ids),
            Employee.status == "active",
        )
    else:
        emp_q = select(Employee).where(
            Employee.department == payload.department,
            Employee.status == "active",
        )
    emps = (await db.execute(emp_q.options(selectinload(Employee.user)))).scalars().all()

    affected = skipped = 0
    errors: List[str] = []
    for emp in emps:
        # Skip if an open revision already exists in this cycle.
        existing = (await db.execute(
            select(SalaryRevision).where(and_(
                SalaryRevision.cycle_id == cycle_id,
                SalaryRevision.employee_id == emp.id,
                SalaryRevision.status.in_([
                    RevisionStatus.DRAFT, RevisionStatus.PENDING,
                    RevisionStatus.APPROVED,
                ]),
            )).limit(1)
        )).scalar_one_or_none()
        if existing is not None:
            skipped += 1
            continue

        snap = await _snapshot_current_employee(db, emp)
        old_ctc = snap["old_ctc"]
        # Compute new CTC from blanket hike.
        if payload.blanket_hike_amount is not None:
            new_ctc = round(old_ctc + payload.blanket_hike_amount, 2)
        elif payload.blanket_hike_percent is not None:
            new_ctc = round(old_ctc * (1 + payload.blanket_hike_percent / 100), 2)
        else:
            new_ctc = old_ctc  # no auto-hike; HR will edit per row
        # Distribute pro-rata using existing component ratios.
        if old_ctc > 0 and new_ctc != old_ctc:
            ratio = new_ctc / old_ctc
            new_basic = round(snap["old_basic"] * ratio, 2)
            new_conv = round(snap["old_conveyance"] * ratio, 2)
            new_hra = round(snap["old_hra"] * ratio, 2)
            new_other = round(snap["old_other_allowance"] * ratio, 2)
        else:
            new_basic = snap["old_basic"]
            new_conv = snap["old_conveyance"]
            new_hra = snap["old_hra"]
            new_other = snap["old_other_allowance"]
            new_ctc = old_ctc

        rev = SalaryRevision(
            employee_id=emp.id, cycle_id=cycle_id,
            revision_type=payload.revision_type,
            effective_from=cycle.effective_from,
            reason=payload.reason,
            new_designation_id=snap["old_designation_id"],
            new_grade_id=snap["old_grade_id"],
            new_basic=new_basic, new_conveyance=new_conv,
            new_hra=new_hra, new_other_allowance=new_other,
            new_ctc=new_ctc,
            status=RevisionStatus.DRAFT,
            created_by_id=current_user.id,
            **snap,
        )
        await _save_with_derivation(db, rev)
        db.add(rev)
        affected += 1

    await log_audit(db, current_user.id, "CYCLE_BULK_DRAFT", "revision_cycle",
                    str(cycle_id),
                    {"affected": affected, "skipped": skipped,
                     "scope_dept": payload.department,
                     "scope_ids": payload.employee_ids},
                    request)
    await db.commit()
    return BulkActionResult(affected=affected, skipped=skipped, errors=errors)


@router.post("/cycles/{cycle_id}/bulk-submit", response_model=BulkActionResult)
async def cycle_bulk_submit(
    cycle_id: int,
    payload: CycleBulkSubmitRequest,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_REV_WRITE])),
) -> Any:
    cycle = await db.get(RevisionCycle, cycle_id)
    if cycle is None:
        raise HTTPException(404, "Cycle not found")

    stmt = select(SalaryRevision).where(and_(
        SalaryRevision.cycle_id == cycle_id,
        SalaryRevision.status == RevisionStatus.DRAFT,
    ))
    if payload.only_revision_ids:
        stmt = stmt.where(SalaryRevision.id.in_(payload.only_revision_ids))
    rows = (await db.execute(stmt)).scalars().all()

    affected = 0
    errors: List[str] = []
    for r in rows:
        try:
            # Reuse the single-submit logic by inlining the minimum.
            emp = await db.get(Employee, r.employee_id, options=[
                selectinload(Employee.user)
            ])
            requester_id = emp.user.id if emp and emp.user else current_user.id
            item = ApprovalItem(
                resource_type="salary_revision",
                resource_id=str(r.id),
                status=ApprovalStatus.PENDING,
                current_step_number=1,
                requested_by_id=requester_id,
            )
            db.add(item)
            await db.flush()
            db.add(ApprovalStep(
                approval_item_id=item.id, step_number=1,
                approver_id=getattr(emp.user, "manager_id", None)
                if emp and emp.user else None,
                status=ApprovalStatus.PENDING,
            ))
            r.approval_item_id = item.id
            r.status = RevisionStatus.PENDING
            affected += 1
        except Exception as e:
            errors.append(f"#{r.id}: {e}")

    cycle.status = CycleStatus.PENDING
    await log_audit(db, current_user.id, "CYCLE_BULK_SUBMIT", "revision_cycle",
                    str(cycle_id), {"submitted": affected}, request)
    await db.commit()
    return BulkActionResult(affected=affected, skipped=0, errors=errors)
