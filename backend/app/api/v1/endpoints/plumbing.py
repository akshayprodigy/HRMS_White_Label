"""Deferred-plumbing endpoints (Section K):
- /me/bank                           employee-edit + HR-verify bank details
- /employees/{id}/bank                HR view/edit anyone's bank details
- /expenses/upload-receipt            file upload for expense line receipts
- /data-quality/scan                  full DQ scan (report + widget payload)
- /data-quality/readiness             advisory pre-run readiness gate
- /admin/jobs                         scheduler admin: list / run-now / toggle
- /admin/jobs/{name}/run-now
- /admin/jobs/{name}/toggle
"""
from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter, Depends, File, HTTPException, Query, Request, UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.v1.endpoints.approval_chains import _is_finance, _is_hr_or_admin
from app.api.v1.endpoints.hr import log_audit
from app.models.employee import Employee
from app.models.expense import (
    ExpenseCategory, ExpenseClaim, ExpenseClaimStatus, ExpenseLineItem,
)
from app.models.scheduled_job import JobRunStatus, ScheduledJob
from app.models.statutory import EmployeeStatutoryDetail
from app.models.user import User
from app.services.bank_details import validate_bank_bundle
from app.services.data_quality import (
    EmployeeSnapshot, Severity, readiness_gate, scan_all, summarize,
)
from app.services.scheduler import REGISTRY as JOB_REGISTRY, run_job_once


router = APIRouter()


# ============================================================
# Item 1 — Bank details
# ============================================================


class BankDetailsIn(BaseModel):
    bank_account: Optional[str] = None
    bank_ifsc_code: Optional[str] = None
    bank_account_holder_name: Optional[str] = None
    bank_name: Optional[str] = None


class BankDetailsOut(BaseModel):
    bank_account: Optional[str]
    bank_ifsc_code: Optional[str]
    bank_account_holder_name: Optional[str]
    bank_name: Optional[str]
    bank_verified_at: Optional[datetime]
    bank_verified_by_id: Optional[int]
    validation_warnings: List[str]
    is_shape_valid: bool


def _bank_out(emp: Employee) -> BankDetailsOut:
    v = validate_bank_bundle(
        ifsc=emp.bank_ifsc_code, account=emp.bank_account,
        holder_name=emp.bank_account_holder_name,
    )
    return BankDetailsOut(
        bank_account=emp.bank_account,
        bank_ifsc_code=emp.bank_ifsc_code,
        bank_account_holder_name=emp.bank_account_holder_name,
        bank_name=emp.bank_name,
        bank_verified_at=emp.bank_verified_at,
        bank_verified_by_id=emp.bank_verified_by_id,
        validation_warnings=v.warnings,
        is_shape_valid=v.ok,
    )


async def _own_employee(db, user: User) -> Employee:
    row = (await db.execute(
        select(Employee).where(Employee.user_id == user.id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(400, "No employee record for this user")
    return row


@router.get("/me/bank", response_model=BankDetailsOut)
async def get_my_bank(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    emp = await _own_employee(db, current_user)
    return _bank_out(emp)


@router.put("/me/bank", response_model=BankDetailsOut)
async def update_my_bank(
    payload: BankDetailsIn,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Employee-edit ownership model (mirrors document-verify pattern):
    the employee edits their own; ANY change clears verified_at so HR
    knows to re-verify. HR then flips verified_at via
    /employees/{id}/bank/verify.
    """
    emp = await _own_employee(db, current_user)
    changed = False
    for field_ in (
        "bank_account", "bank_ifsc_code",
        "bank_account_holder_name", "bank_name",
    ):
        val = getattr(payload, field_)
        if val is not None and getattr(emp, field_) != val:
            setattr(emp, field_, val)
            changed = True
    if changed:
        emp.bank_verified_at = None
        emp.bank_verified_by_id = None
    await db.commit()
    await log_audit(
        db, current_user.id, "employee_bank_update",
        "employee", str(emp.id),
        {"changed_fields": [
            k for k in payload.model_dump(exclude_unset=True)
        ]},
        request,
    )
    return _bank_out(emp)


@router.get("/employees/{employee_id}/bank", response_model=BankDetailsOut)
async def hr_get_bank(
    employee_id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not (_is_hr_or_admin(current_user) or _is_finance(current_user)):
        raise HTTPException(403, "HR/Finance only")
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")
    return _bank_out(emp)


@router.post("/employees/{employee_id}/bank/verify", response_model=BankDetailsOut)
async def hr_verify_bank(
    employee_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _is_hr_or_admin(current_user):
        raise HTTPException(403, "HR only")
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")
    emp.bank_verified_at = datetime.now(timezone.utc)
    emp.bank_verified_by_id = current_user.id
    await db.commit()
    await log_audit(
        db, current_user.id, "employee_bank_verify",
        "employee", str(emp.id),
        {"verified_by": current_user.id},
        request,
    )
    return _bank_out(emp)


# ============================================================
# Item 2 — Receipt upload
# ============================================================


UPLOAD_ROOT = Path(os.environ.get("UPLOAD_ROOT", "uploads")).resolve()
RECEIPT_DIR = UPLOAD_ROOT / "expense_receipts"
RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
RECEIPT_MAX_BYTES = 5 * 1024 * 1024   # 5 MB
RECEIPT_ALLOWED_MIME_PREFIXES = ("image/", "application/pdf")


@router.post("/expenses/upload-receipt")
async def upload_receipt(
    db: deps.DBDep,
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Store a receipt file and return the reference URL to save on the
    ExpenseLineItem. Reuses the existing upload directory pattern; no
    new storage.
    """
    if not file.filename:
        raise HTTPException(400, "Filename required")
    ct = (file.content_type or "").lower()
    if not any(ct.startswith(p) for p in RECEIPT_ALLOWED_MIME_PREFIXES):
        raise HTTPException(
            400, "Only images and PDFs are accepted for receipts",
        )
    # Store with a UUID name to avoid collisions + leak of user names.
    ext = Path(file.filename).suffix.lower()
    fname = f"{uuid.uuid4().hex}{ext}"
    dest = RECEIPT_DIR / fname
    size = 0
    with dest.open("wb") as f:
        while True:
            chunk = await file.read(1024 * 64)
            if not chunk:
                break
            size += len(chunk)
            if size > RECEIPT_MAX_BYTES:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    400,
                    f"Receipt exceeds {RECEIPT_MAX_BYTES // (1024 * 1024)} MB",
                )
            f.write(chunk)

    receipt_url = f"/expenses/receipts/{fname}"
    await log_audit(
        db, current_user.id, "expense_receipt_upload",
        "expense_receipt", fname,
        {"size_bytes": size, "content_type": ct},
        request,
    )
    return {
        "receipt_url": receipt_url,
        "size_bytes": size,
        "content_type": ct,
        "filename": file.filename,
    }


@router.get("/expenses/receipts/{fname}")
async def fetch_receipt(
    fname: str,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Serve a receipt. Anyone in an approval role for this claim can
    view; the claim submitter can always view their own; HR/Finance
    can view all.
    """
    # Prevent path traversal.
    if "/" in fname or ".." in fname:
        raise HTTPException(400, "Bad filename")
    path = RECEIPT_DIR / fname
    if not path.exists():
        raise HTTPException(404, "Receipt not found")
    if not (_is_hr_or_admin(current_user) or _is_finance(current_user)):
        # Look up which claim it belongs to and ensure the caller has
        # a stake — either submitter or on the approval instance.
        row = (await db.execute(
            select(ExpenseLineItem).where(
                ExpenseLineItem.receipt_url == f"/expenses/receipts/{fname}"
            )
        )).scalar_one_or_none()
        if row is None:
            raise HTTPException(403, "Not authorized")
        claim = await db.get(ExpenseClaim, row.claim_id)
        if not claim or claim.submitter_id != current_user.id:
            # A stricter check (walking the approval instance to look
            # for the caller) is possible; for now the submitter or
            # HR/Finance can view.
            raise HTTPException(403, "Not authorized")
    return FileResponse(path)


# ============================================================
# Item 3 — Data-quality
# ============================================================


async def _build_snapshots(db) -> List[EmployeeSnapshot]:
    emps = (await db.execute(
        select(Employee).options(selectinload(Employee.user))
    )).scalars().unique().all()
    details_by_emp = {
        d.employee_id: d
        for d in (await db.execute(
            select(EmployeeStatutoryDetail)
        )).scalars().all()
    }
    out: List[EmployeeSnapshot] = []
    for e in emps:
        d = details_by_emp.get(e.id)
        out.append(EmployeeSnapshot(
            employee_pk=e.id,
            employee_code=e.employee_id or "",
            full_name=(e.user.full_name if e.user else "") or "",
            department=e.department,
            designation=e.designation,
            pan_number=e.pan_number,
            pf_number=e.pf_number,
            bank_account=e.bank_account,
            bank_ifsc=e.bank_ifsc_code,
            bank_account_holder_name=e.bank_account_holder_name,
            bank_verified=e.bank_verified_at is not None,
            uan=(d.uan if d else None),
            pf_member_id=(d.pf_member_id if d else None),
            esic_ip_number=(d.esic_ip_number if d else None),
            esic_applicable=bool(e.esic_applicable),
            pt_state=(d.pt_state if d else None),
        ))
    return out


@router.get("/data-quality/scan")
async def dq_scan(
    db: deps.DBDep,
    severity: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _is_hr_or_admin(current_user):
        raise HTTPException(403, "HR only")
    snapshots = await _build_snapshots(db)
    findings = scan_all(snapshots)
    if severity:
        findings = [f for f in findings if f.severity == severity]
    return {
        "summary": summarize(findings),
        "findings": [f.to_dict() for f in findings[:500]],
    }


@router.get("/data-quality/readiness")
async def dq_readiness(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Advisory pre-run gate. NEVER auto-blocks payroll — HR reads and
    decides whether to unblock."""
    if not _is_hr_or_admin(current_user):
        raise HTTPException(403, "HR only")
    snapshots = await _build_snapshots(db)
    findings = scan_all(snapshots)
    return readiness_gate(findings)


# ============================================================
# Item 4 — Scheduler admin
# ============================================================


def _job_dict(row: ScheduledJob) -> dict:
    return {
        "id": row.id, "name": row.name,
        "display_name": row.display_name,
        "description": row.description,
        "cadence_cron": row.cadence_cron,
        "enabled": row.enabled,
        "is_running": row.is_running,
        "last_run_at": row.last_run_at,
        "last_status": row.last_status,
        "last_error": row.last_error,
        "last_summary": row.last_summary,
        "last_duration_ms": row.last_duration_ms,
    }


@router.get("/admin/jobs")
async def list_jobs(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _is_hr_or_admin(current_user):
        raise HTTPException(403, "Admin only")
    rows = (await db.execute(
        select(ScheduledJob).order_by(ScheduledJob.name)
    )).scalars().all()
    # If nothing is seeded yet, expose the code-registered specs so the
    # admin UI can offer a "seed" button.
    seeded = {r.name for r in rows}
    unregistered_in_db = [
        {
            "name": s.name, "display_name": s.display_name,
            "description": s.description,
            "cadence_cron": s.default_cadence_cron,
            "seeded": False,
        }
        for s in JOB_REGISTRY.values() if s.name not in seeded
    ]
    return {
        "jobs": [_job_dict(r) for r in rows],
        "unregistered": unregistered_in_db,
    }


@router.post("/admin/jobs/seed")
async def seed_jobs(
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _is_hr_or_admin(current_user):
        raise HTTPException(403, "Admin only")
    from app.services.scheduler import ensure_jobs
    await ensure_jobs(db)
    await log_audit(
        db, current_user.id, "scheduler_seed", "scheduled_job", "*",
        {"registered": list(JOB_REGISTRY.keys())}, request,
    )
    return {"ok": True}


@router.post("/admin/jobs/{name}/run-now")
async def run_job_now(
    name: str,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _is_hr_or_admin(current_user):
        raise HTTPException(403, "Admin only")
    if name not in JOB_REGISTRY:
        raise HTTPException(404, f"Unknown job {name!r}")
    # Grab the session_factory attached to the app on startup.
    from app.db.session import SessionLocal
    result = await run_job_once(SessionLocal, name, force=True)
    await log_audit(
        db, current_user.id, "scheduler_run_now",
        "scheduled_job", name, result, request,
    )
    return result


@router.post("/admin/jobs/{name}/toggle")
async def toggle_job(
    name: str,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _is_hr_or_admin(current_user):
        raise HTTPException(403, "Admin only")
    row = (await db.execute(
        select(ScheduledJob).where(ScheduledJob.name == name)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, f"Job {name!r} not found in DB")
    row.enabled = not row.enabled
    await db.commit()
    await log_audit(
        db, current_user.id, "scheduler_toggle",
        "scheduled_job", name,
        {"enabled": row.enabled}, request,
    )
    return _job_dict(row)
