"""Statutory filing endpoints.

Generators READ finalized payroll only. They never recompute salary,
never modify Employee, never touch salary_calculator or revision tables.
"""
import io
from datetime import date, datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.v1.endpoints.hr import log_audit
from app.models.employee import Employee
from app.models.payroll import (
    PayrollLine, PayrollRun, PayrollRunStatus,
)
from app.models.statutory import (
    EmployeeStatutoryDetail, EmployerIdentifier, FilingStatus,
    PTStateSlab, StatutoryConfig, StatutoryFiling, StatutoryStream,
)
from app.models.user import User
from app.schemas.statutory import (
    ComplianceCard, ComplianceDashboard,
    DriftFindingRead, EmployeeStatutoryDetailRead, EmployeeStatutoryDetailUpsert,
    EmployerIdentifierCreate, EmployerIdentifierRead, EmployerIdentifierUpdate,
    FilingStatusUpdate, GenerateRequest, GenerateResult,
    PTSlabCreate, PTSlabRead, PTSlabUpdate,
    ReconciliationReport, StatutoryConfigCreate, StatutoryConfigRead,
    StatutoryConfigUpdate, StatutoryFilingRead,
)
from app.services.statutory import (
    compute_ecr_row, compute_esic_row, current_period_window,
    esic_due_date, is_under_esic, pf_due_date, pick_config_for_month,
    pick_pt_slab, pt_due_date, reconcile_esic, reconcile_pf, reconcile_pt,
    render_ecr_text, render_esic_csv, render_pt_csv,
    summarize_ecr, summarize_esic,
)


router = APIRouter()

PERM_CONFIG_WRITE = "statutory config write"
PERM_GENERATE = "statutory generate"
PERM_VIEW = "statutory view"


# =====================================================================
# helpers
# =====================================================================


async def _active_employer(db) -> Optional[EmployerIdentifier]:
    return (await db.execute(
        select(EmployerIdentifier).where(EmployerIdentifier.is_active.is_(True))
        .order_by(EmployerIdentifier.id).limit(1)
    )).scalar_one_or_none()


async def _resolve_config(
    db, year: int, month: int, override_id: Optional[int],
) -> Optional[StatutoryConfig]:
    if override_id is not None:
        return await db.get(StatutoryConfig, override_id)
    rows = (await db.execute(
        select(StatutoryConfig).where(StatutoryConfig.is_active.is_(True))
    )).scalars().all()
    return pick_config_for_month(rows, year, month)


async def _payroll_lines_for_run(
    db, run_id: int,
) -> List[tuple[PayrollLine, Employee, User, Optional[EmployeeStatutoryDetail]]]:
    """Pull (line, employee, user, stat_detail) for every line in the run."""
    line_rows = (await db.execute(
        select(PayrollLine).where(PayrollLine.payroll_run_id == run_id)
    )).scalars().all()
    if not line_rows:
        return []

    user_ids = {ln.user_id for ln in line_rows}
    user_map = {
        u.id: u for u in (await db.execute(
            select(User).where(User.id.in_(user_ids))
        )).scalars().all()
    }
    emp_rows = (await db.execute(
        select(Employee).where(Employee.user_id.in_(user_ids))
    )).scalars().all()
    emp_by_user = {e.user_id: e for e in emp_rows}
    detail_rows = (await db.execute(
        select(EmployeeStatutoryDetail).where(
            EmployeeStatutoryDetail.employee_id.in_(
                {e.id for e in emp_rows}
            )
        )
    )).scalars().all()
    detail_by_emp = {d.employee_id: d for d in detail_rows}

    out = []
    for ln in line_rows:
        emp = emp_by_user.get(ln.user_id)
        if emp is None:
            continue   # detached payroll line — skip silently
        out.append((
            ln, emp, user_map.get(ln.user_id),
            detail_by_emp.get(emp.id),
        ))
    return out


def _gross_for_line(ln: PayrollLine) -> float:
    """The gross-wages number used by every filing.

    We use the line's stored gross_pay so OT, night-allowance, arrears
    and incentives are all included — same number the employee sees on
    their payslip. PF wages are independently capped to basic.
    """
    return float(ln.gross_pay or 0.0)


def _basic_for_pf(ln: PayrollLine) -> float:
    """Basic salary actually paid this month (after LOP proration)."""
    al = ln.allowances or {}
    return float(al.get("basic_salary_actual", ln.base_salary or 0.0))


def _ensure_run_finalized_or_published(run: PayrollRun) -> None:
    if run.status not in (
        PayrollRunStatus.FINALIZED, PayrollRunStatus.PUBLISHED,
    ):
        raise HTTPException(
            400,
            "Statutory files can only be generated from FINALIZED or "
            "PUBLISHED payroll runs.",
        )


def _build_filing_read(
    f: StatutoryFiling, *, run: Optional[PayrollRun] = None,
) -> StatutoryFilingRead:
    data = {c.name: getattr(f, c.name) for c in f.__table__.columns}
    if run is not None:
        data["payroll_period"] = f"{run.month:02d}/{run.year}"
        due = (
            pt_due_date(run.year, run.month, f.state or "")
            if f.stream == StatutoryStream.PT
            else pf_due_date(run.year, run.month)
        )
        data["due_date"] = due
        data["days_to_due"] = (due - date.today()).days
    return StatutoryFilingRead.model_validate(data)


# =====================================================================
# EmployerIdentifier CRUD
# =====================================================================


@router.get("/employers", response_model=List[EmployerIdentifierRead])
async def list_employers(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([PERM_VIEW])),
) -> Any:
    rows = (await db.execute(
        select(EmployerIdentifier).order_by(EmployerIdentifier.name)
    )).scalars().all()
    return rows


@router.post("/employers", response_model=EmployerIdentifierRead)
async def create_employer(
    payload: EmployerIdentifierCreate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CONFIG_WRITE])),
) -> Any:
    obj = EmployerIdentifier(**payload.model_dump())
    db.add(obj)
    await db.flush()
    await log_audit(
        db, current_user.id, "EMPLOYER_CREATE", "employer_identifier",
        str(obj.id), payload.model_dump(), request,
    )
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/employers/{eid}", response_model=EmployerIdentifierRead)
async def update_employer(
    eid: int,
    payload: EmployerIdentifierUpdate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CONFIG_WRITE])),
) -> Any:
    obj = await db.get(EmployerIdentifier, eid)
    if obj is None:
        raise HTTPException(404, "Employer not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)
    await log_audit(
        db, current_user.id, "EMPLOYER_UPDATE", "employer_identifier",
        str(eid), data, request,
    )
    await db.commit()
    await db.refresh(obj)
    return obj


# =====================================================================
# StatutoryConfig CRUD
# =====================================================================


@router.get("/configs", response_model=List[StatutoryConfigRead])
async def list_configs(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([PERM_VIEW])),
) -> Any:
    rows = (await db.execute(
        select(StatutoryConfig).order_by(StatutoryConfig.effective_from.desc())
    )).scalars().all()
    return rows


@router.post("/configs", response_model=StatutoryConfigRead)
async def create_config(
    payload: StatutoryConfigCreate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CONFIG_WRITE])),
) -> Any:
    obj = StatutoryConfig(**payload.model_dump())
    db.add(obj)
    await db.flush()
    await log_audit(
        db, current_user.id, "STATUTORY_CONFIG_CREATE", "statutory_config",
        str(obj.id), payload.model_dump(mode="json"), request,
    )
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/configs/{cid}", response_model=StatutoryConfigRead)
async def update_config(
    cid: int,
    payload: StatutoryConfigUpdate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CONFIG_WRITE])),
) -> Any:
    obj = await db.get(StatutoryConfig, cid)
    if obj is None:
        raise HTTPException(404, "Config not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)
    await log_audit(
        db, current_user.id, "STATUTORY_CONFIG_UPDATE", "statutory_config",
        str(cid), {k: (v.isoformat() if hasattr(v, "isoformat") else v)
                   for k, v in data.items()},
        request,
    )
    await db.commit()
    await db.refresh(obj)
    return obj


# =====================================================================
# PT slab CRUD
# =====================================================================


@router.get("/pt-slabs", response_model=List[PTSlabRead])
async def list_pt_slabs(
    db: deps.DBDep,
    state: Optional[str] = Query(None),
    current_user: User = Depends(deps.check_permissions([PERM_VIEW])),
) -> Any:
    stmt = select(PTStateSlab)
    if state:
        stmt = stmt.where(func.upper(PTStateSlab.state) == state.upper())
    stmt = stmt.order_by(
        PTStateSlab.state, PTStateSlab.effective_from.desc(),
        PTStateSlab.slab_min,
    )
    return list((await db.execute(stmt)).scalars().all())


@router.post("/pt-slabs", response_model=PTSlabRead)
async def create_pt_slab(
    payload: PTSlabCreate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CONFIG_WRITE])),
) -> Any:
    obj = PTStateSlab(**payload.model_dump())
    db.add(obj)
    await db.flush()
    await log_audit(
        db, current_user.id, "PT_SLAB_CREATE", "pt_state_slab",
        str(obj.id), payload.model_dump(mode="json"), request,
    )
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/pt-slabs/{sid}", response_model=PTSlabRead)
async def update_pt_slab(
    sid: int,
    payload: PTSlabUpdate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CONFIG_WRITE])),
) -> Any:
    obj = await db.get(PTStateSlab, sid)
    if obj is None:
        raise HTTPException(404, "Slab not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)
    await log_audit(
        db, current_user.id, "PT_SLAB_UPDATE", "pt_state_slab",
        str(sid), data, request,
    )
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/pt-slabs/{sid}")
async def delete_pt_slab(
    sid: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CONFIG_WRITE])),
) -> Any:
    obj = await db.get(PTStateSlab, sid)
    if obj is None:
        raise HTTPException(404, "Slab not found")
    obj.is_active = False
    await log_audit(
        db, current_user.id, "PT_SLAB_DEACTIVATE", "pt_state_slab",
        str(sid), {}, request,
    )
    await db.commit()
    return {"message": "Slab deactivated"}


# =====================================================================
# employee statutory detail (UAN / IP number etc.)
# =====================================================================


@router.get("/employee-details", response_model=List[EmployeeStatutoryDetailRead])
async def list_employee_details(
    db: deps.DBDep,
    employee_id: Optional[int] = Query(None),
    current_user: User = Depends(deps.check_permissions([PERM_VIEW])),
) -> Any:
    stmt = select(EmployeeStatutoryDetail)
    if employee_id:
        stmt = stmt.where(EmployeeStatutoryDetail.employee_id == employee_id)
    return list((await db.execute(stmt)).scalars().all())


@router.put("/employee-details", response_model=EmployeeStatutoryDetailRead)
async def upsert_employee_detail(
    payload: EmployeeStatutoryDetailUpsert,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CONFIG_WRITE])),
) -> Any:
    existing = (await db.execute(
        select(EmployeeStatutoryDetail).where(
            EmployeeStatutoryDetail.employee_id == payload.employee_id
        )
    )).scalar_one_or_none()
    data = payload.model_dump()
    if existing is None:
        existing = EmployeeStatutoryDetail(**data)
        db.add(existing)
    else:
        for k, v in data.items():
            setattr(existing, k, v)
    await db.flush()
    await log_audit(
        db, current_user.id, "EMP_STATUTORY_UPSERT",
        "employee_statutory_detail",
        str(existing.id), data, request,
    )
    await db.commit()
    await db.refresh(existing)
    return existing


# =====================================================================
# GENERATE — PF / ESIC / PT
# =====================================================================


async def _generate_pf(
    db, *, run: PayrollRun, employer: Optional[EmployerIdentifier],
    config: StatutoryConfig, actor_id: int,
) -> StatutoryFiling:
    line_rows = await _payroll_lines_for_run(db, run.id)
    ecr_rows = []
    notes: list[str] = []
    for ln, emp, user, detail in line_rows:
        uan = (detail.uan if detail else None) or ""
        if not uan:
            notes.append(
                f"missing UAN for employee {emp.employee_id} ({user.full_name if user else ''})"
            )
        ecr_rows.append(compute_ecr_row(
            uan=uan,
            member_name=user.full_name if user else "",
            gross_wages=_gross_for_line(ln),
            basic_for_pf=_basic_for_pf(ln),
            config=config,
            ncp_days=int(ln.lop_days or 0),
        ))
    text = render_ecr_text(ecr_rows)
    summary = summarize_ecr(ecr_rows)
    fname = f"ECR_{run.year}{run.month:02d}.txt"

    return await _persist_filing(
        db, run=run, stream=StatutoryStream.EPF, state=None,
        employer=employer, config=config, actor_id=actor_id,
        file_bytes=text.encode("utf-8"),
        file_name=fname, summary={**summary, "notes": notes},
    )


async def _generate_esic(
    db, *, run: PayrollRun, employer: Optional[EmployerIdentifier],
    config: StatutoryConfig, actor_id: int,
) -> StatutoryFiling:
    line_rows = await _payroll_lines_for_run(db, run.id)
    esic_rows = []
    notes: list[str] = []
    payroll_month = date(run.year, run.month, 1)
    for ln, emp, user, detail in line_rows:
        gross = _gross_for_line(ln)
        cont = detail.esic_continuation_until if detail else None
        if not is_under_esic(
            gross_wages_this_month=gross, config=config,
            payroll_month=payroll_month, continuation_until=cont,
        ):
            continue
        ip_number = (detail.esic_ip_number if detail else None) or ""
        if not ip_number:
            notes.append(
                f"missing ESIC IP number for {emp.employee_id} "
                f"({user.full_name if user else ''})"
            )
        esic_rows.append(compute_esic_row(
            ip_number=ip_number,
            name=user.full_name if user else "",
            days_worked=int(round(ln.payable_days or 0)),
            gross_wages=gross,
            config=config,
        ))
    csv_text = render_esic_csv(esic_rows)
    summary = summarize_esic(esic_rows)
    fname = f"ESIC_{run.year}{run.month:02d}.csv"
    return await _persist_filing(
        db, run=run, stream=StatutoryStream.ESIC, state=None,
        employer=employer, config=config, actor_id=actor_id,
        file_bytes=csv_text.encode("utf-8"),
        file_name=fname, summary={**summary, "notes": notes},
    )


async def _generate_pt_for_state(
    db, *, run: PayrollRun, employer: Optional[EmployerIdentifier],
    config: StatutoryConfig, state: str, actor_id: int,
) -> Optional[StatutoryFiling]:
    line_rows = await _payroll_lines_for_run(db, run.id)
    # Filter to employees in this state.
    in_state = []
    for ln, emp, user, detail in line_rows:
        emp_state = (detail.pt_state if detail else None) or (
            employer.default_pt_state if employer else None
        )
        if (emp_state or "").upper() == (state or "").upper():
            in_state.append((ln, emp, user, detail))

    if not in_state:
        return None

    # Pull slabs once for this state.
    slabs = list((await db.execute(
        select(PTStateSlab).where(
            and_(
                PTStateSlab.is_active.is_(True),
                func.upper(PTStateSlab.state) == state.upper(),
            )
        )
    )).scalars().all())

    rows: list[dict] = []
    total_pt = 0.0
    for ln, emp, user, detail in in_state:
        gross = _gross_for_line(ln)
        chosen = pick_pt_slab(
            slabs, state=state, year=run.year, month=run.month,
            gross_for_pt=gross,
            gender=(detail.gender if detail else "ALL") or "ALL",
        )
        amount = float(chosen.monthly_amount) if chosen else 0.0
        total_pt += amount
        rows.append({
            "employee_id": emp.employee_id,
            "name": user.full_name if user else "",
            "gender": (detail.gender if detail else "ALL") or "ALL",
            "gross_wages": gross, "pt_amount": amount,
        })

    csv_text = render_pt_csv(rows)
    summary = {
        "employee_count": len(rows), "total_pt_amount": round(total_pt, 2),
        "total_gross_wages": round(sum(r["gross_wages"] for r in rows), 2),
    }
    fname = f"PT_{state.upper()}_{run.year}{run.month:02d}.csv"
    return await _persist_filing(
        db, run=run, stream=StatutoryStream.PT, state=state.upper(),
        employer=employer, config=config, actor_id=actor_id,
        file_bytes=csv_text.encode("utf-8"),
        file_name=fname, summary=summary,
    )


async def _persist_filing(
    db, *, run: PayrollRun, stream: str, state: Optional[str],
    employer: Optional[EmployerIdentifier],
    config: Optional[StatutoryConfig],
    actor_id: int, file_bytes: bytes, file_name: str, summary: dict,
) -> StatutoryFiling:
    """Upsert one filing record. Re-generating an existing
    (run, stream, state) updates the file blob + summary so HR can
    iterate without DB cleanup. Status moves back to GENERATED unless
    already paid/submitted, in which case we keep the audit metadata
    and refuse to overwrite — protects against accidental re-issue
    after submission.
    """
    existing = (await db.execute(
        select(StatutoryFiling).where(and_(
            StatutoryFiling.payroll_run_id == run.id,
            StatutoryFiling.stream == stream,
            StatutoryFiling.state.is_(state) if state is None
            else StatutoryFiling.state == state,
        ))
    )).scalar_one_or_none()

    if existing is not None and existing.status in (
        FilingStatus.SUBMITTED, FilingStatus.PAID, FilingStatus.ACKNOWLEDGED,
    ):
        raise HTTPException(
            400,
            f"{stream.upper()} filing for run {run.id}"
            + (f"/{state}" if state else "")
            + f" is already {existing.status}. "
            "Mark it REJECTED first if you really need to re-issue.",
        )

    file_url = f"/statutory/{file_name}"
    if existing is None:
        obj = StatutoryFiling(
            payroll_run_id=run.id, stream=stream, state=state,
            status=FilingStatus.GENERATED,
            file_url=file_url, file_name=file_name,
            employer_identifier_id=employer.id if employer else None,
            config_id=config.id if config else None,
            summary=summary, generated_by_id=actor_id,
        )
        db.add(obj)
        await db.flush()
    else:
        obj = existing
        obj.file_url = file_url
        obj.file_name = file_name
        obj.summary = summary
        obj.status = FilingStatus.GENERATED
        obj.generated_at = datetime.now(timezone.utc)
        obj.generated_by_id = actor_id
        obj.config_id = config.id if config else None
        obj.employer_identifier_id = employer.id if employer else None

    # Stash bytes for the synchronous download endpoint — keep in the
    # summary JSON to avoid a new column. file_url is the canonical
    # download path; the byte cache lets /download/{id} return the
    # exact bytes that were generated.
    obj.summary = {**(obj.summary or {}), "_bytes_hex": file_bytes.hex()}
    return obj


@router.post("/generate", response_model=GenerateResult)
async def generate(
    payload: GenerateRequest,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_GENERATE])),
) -> Any:
    run = await db.get(PayrollRun, payload.payroll_run_id)
    if run is None:
        raise HTTPException(404, "Payroll run not found")
    _ensure_run_finalized_or_published(run)

    config = await _resolve_config(db, run.year, run.month, payload.config_id)
    if config is None:
        raise HTTPException(
            400,
            "No active StatutoryConfig found for this payroll month. "
            "Create one (or activate an existing one) before generating.",
        )
    employer = (
        await db.get(EmployerIdentifier, payload.employer_identifier_id)
        if payload.employer_identifier_id is not None
        else await _active_employer(db)
    )

    filings: List[StatutoryFiling] = []
    skipped_states: List[str] = []
    notes: List[str] = []

    pf = await _generate_pf(
        db, run=run, employer=employer, config=config, actor_id=current_user.id,
    )
    filings.append(pf)
    esic = await _generate_esic(
        db, run=run, employer=employer, config=config, actor_id=current_user.id,
    )
    filings.append(esic)

    # PT: if state was supplied, only that state. Else one filing per
    # distinct employee PT state.
    line_rows = await _payroll_lines_for_run(db, run.id)
    if payload.state:
        states = [payload.state.upper()]
    else:
        states = sorted({
            ((detail.pt_state if detail else None)
             or (employer.default_pt_state if employer else None) or "").upper()
            for _, _, _, detail in line_rows
        } - {""})

    for s in states:
        f = await _generate_pt_for_state(
            db, run=run, employer=employer, config=config, state=s,
            actor_id=current_user.id,
        )
        if f is None:
            skipped_states.append(s)
            notes.append(f"PT: no employees in state {s}")
        else:
            filings.append(f)

    await log_audit(
        db, current_user.id, "STATUTORY_GENERATE", "statutory_filing",
        f"run:{run.id}", {
            "stream_count": len(filings),
            "states_generated": [f.state for f in filings if f.state],
            "config_id": config.id,
        },
        request,
    )
    await db.commit()
    for f in filings:
        await db.refresh(f)

    return GenerateResult(
        filings=[_build_filing_read(f, run=run) for f in filings],
        skipped_states=skipped_states, notes=notes,
    )


@router.get("/filings", response_model=List[StatutoryFilingRead])
async def list_filings(
    db: deps.DBDep,
    payroll_run_id: Optional[int] = Query(None),
    stream: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: User = Depends(deps.check_permissions([PERM_VIEW])),
) -> Any:
    stmt = select(StatutoryFiling)
    if payroll_run_id:
        stmt = stmt.where(StatutoryFiling.payroll_run_id == payroll_run_id)
    if stream:
        stmt = stmt.where(StatutoryFiling.stream == stream)
    if status:
        stmt = stmt.where(StatutoryFiling.status == status)
    stmt = stmt.order_by(StatutoryFiling.generated_at.desc())
    rows = (await db.execute(stmt)).scalars().all()

    # Enrich with run.year/month for due_date.
    run_ids = {r.payroll_run_id for r in rows}
    runs = {
        r.id: r for r in (await db.execute(
            select(PayrollRun).where(PayrollRun.id.in_(run_ids))
        )).scalars().all()
    }
    return [_build_filing_read(r, run=runs.get(r.payroll_run_id)) for r in rows]


@router.get("/filings/{fid}/download")
async def download_filing(
    fid: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([PERM_VIEW])),
) -> Any:
    f = await db.get(StatutoryFiling, fid)
    if f is None:
        raise HTTPException(404, "Filing not found")
    summary = f.summary or {}
    hex_blob = summary.get("_bytes_hex")
    if not hex_blob:
        raise HTTPException(410, "File bytes no longer available — regenerate")
    media = "text/plain" if f.stream == StatutoryStream.EPF else "text/csv"
    fname = f.file_name or f"statutory_{fid}"
    return StreamingResponse(
        io.BytesIO(bytes.fromhex(hex_blob)), media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.patch("/filings/{fid}/status", response_model=StatutoryFilingRead)
async def update_filing_status(
    fid: int,
    payload: FilingStatusUpdate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_GENERATE])),
) -> Any:
    f = await db.get(StatutoryFiling, fid)
    if f is None:
        raise HTTPException(404, "Filing not found")
    f.status = payload.status
    if payload.challan_number is not None:
        f.challan_number = payload.challan_number
    if payload.paid_amount is not None:
        f.paid_amount = payload.paid_amount
    now = datetime.now(timezone.utc)
    if payload.status == FilingStatus.SUBMITTED and f.submitted_at is None:
        f.submitted_at = now
    if payload.status == FilingStatus.PAID and f.paid_at is None:
        f.paid_at = now
    await log_audit(
        db, current_user.id, "STATUTORY_STATUS_UPDATE", "statutory_filing",
        str(fid), payload.model_dump(), request,
    )
    await db.commit()
    await db.refresh(f)
    run = await db.get(PayrollRun, f.payroll_run_id)
    return _build_filing_read(f, run=run)


# =====================================================================
# RECONCILIATION
# =====================================================================


@router.get(
    "/runs/{run_id}/reconciliation",
    response_model=ReconciliationReport,
)
async def reconcile_run(
    run_id: int,
    db: deps.DBDep,
    config_id: Optional[int] = Query(None),
    current_user: User = Depends(deps.check_permissions([PERM_VIEW])),
) -> Any:
    """Drift report: for every employee in this run, compare what
    payroll DEDUCTED vs. what the active StatutoryConfig SAYS it should
    have been. Pure read — never edits payroll.
    """
    run = await db.get(PayrollRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")

    config = await _resolve_config(db, run.year, run.month, config_id)
    if config is None:
        raise HTTPException(
            400, "No StatutoryConfig in scope for this payroll month.",
        )

    line_rows = await _payroll_lines_for_run(db, run.id)

    # Pre-load PT slabs (once per state seen).
    pt_states_seen = sorted({
        ((detail.pt_state if detail else None) or "").upper()
        for _, _, _, detail in line_rows
    } - {""})
    pt_slabs_by_state: dict[str, list] = {}
    for state in pt_states_seen:
        pt_slabs_by_state[state] = list((await db.execute(
            select(PTStateSlab).where(and_(
                PTStateSlab.is_active.is_(True),
                func.upper(PTStateSlab.state) == state,
            ))
        )).scalars().all())

    payroll_month = date(run.year, run.month, 1)
    findings: list[DriftFindingRead] = []
    employees_checked = 0

    for ln, emp, user, detail in line_rows:
        employees_checked += 1
        ded = ln.deductions or {}
        actual_emp_pf = float(ded.get("employee_pf", 0.0))
        actual_employer_pf = float(ded.get("employer_pf", 0.0))
        actual_emp_esi = float(ded.get("employee_esi", 0.0))
        actual_employer_esi = float(ded.get("employer_esic", 0.0))
        actual_pt = float(ded.get("professional_tax", 0.0))

        for f in reconcile_pf(
            actual_employee_pf=actual_emp_pf,
            actual_employer_pf=actual_employer_pf,
            basic_for_pf=_basic_for_pf(ln), config=config,
            user_id=ln.user_id, employee_code=emp.employee_id,
            name=user.full_name if user else None,
        ):
            findings.append(DriftFindingRead.model_validate(f.__dict__))

        gross = _gross_for_line(ln)
        is_covered = is_under_esic(
            gross_wages_this_month=gross, config=config,
            payroll_month=payroll_month,
            continuation_until=detail.esic_continuation_until if detail else None,
        )
        for f in reconcile_esic(
            actual_employee_esi=actual_emp_esi,
            actual_employer_esi=actual_employer_esi,
            gross_wages=gross, config=config, is_covered=is_covered,
            user_id=ln.user_id, employee_code=emp.employee_id,
            name=user.full_name if user else None,
        ):
            findings.append(DriftFindingRead.model_validate(f.__dict__))

        state = ((detail.pt_state if detail else None) or "").upper()
        if state and pt_slabs_by_state.get(state):
            slab = pick_pt_slab(
                pt_slabs_by_state[state],
                state=state, year=run.year, month=run.month,
                gross_for_pt=gross,
                gender=(detail.gender if detail else "ALL") or "ALL",
            )
            expected_pt = float(slab.monthly_amount) if slab else 0.0
            for f in reconcile_pt(
                actual_pt=actual_pt, expected_pt=expected_pt,
                user_id=ln.user_id, employee_code=emp.employee_id,
                name=user.full_name if user else None,
            ):
                findings.append(DriftFindingRead.model_validate(f.__dict__))

    return ReconciliationReport(
        payroll_run_id=run.id, config_id=config.id,
        config_effective_from=config.effective_from,
        employees_checked=employees_checked,
        drift_count=len(findings), findings=findings,
    )


# =====================================================================
# COMPLIANCE DASHBOARD
# =====================================================================


@router.get("/compliance/dashboard", response_model=ComplianceDashboard)
async def compliance_dashboard(
    db: deps.DBDep,
    months_back: int = Query(6, ge=1, le=24),
    current_user: User = Depends(deps.check_permissions([PERM_VIEW])),
) -> Any:
    """One card per (payroll_run, stream[, state]) for the last N months.

    Streams that ought to exist (PF, ESIC, and one PT per state with
    employees) but for which no filing has been generated yet are
    listed with status=draft so HR can see the gap.
    """
    today = date.today()
    # Last N finalized/published runs
    cutoff_year = today.year - (months_back // 12 + 1)
    runs = list((await db.execute(
        select(PayrollRun).where(and_(
            PayrollRun.status.in_([
                PayrollRunStatus.FINALIZED, PayrollRunStatus.PUBLISHED,
            ]),
            PayrollRun.year >= cutoff_year,
        )).order_by(PayrollRun.year.desc(), PayrollRun.month.desc())
        .limit(months_back * 2)
    )).scalars().all())

    cards: List[ComplianceCard] = []
    overdue = 0
    due_within_7_days = 0

    # Existing filings keyed by (run_id, stream, state-or-empty)
    existing_rows = (await db.execute(
        select(StatutoryFiling).where(
            StatutoryFiling.payroll_run_id.in_({r.id for r in runs})
        )
    )).scalars().all() if runs else []
    by_key: dict[tuple, StatutoryFiling] = {}
    for f in existing_rows:
        by_key[(f.payroll_run_id, f.stream, f.state or "")] = f

    for run in runs:
        # PF + ESIC: always one card each.
        for stream in (StatutoryStream.EPF, StatutoryStream.ESIC):
            due = pf_due_date(run.year, run.month)
            f = by_key.get((run.id, stream, ""))
            card = ComplianceCard(
                stream=stream, state=None,
                payroll_run_id=run.id,
                payroll_period=f"{run.month:02d}/{run.year}",
                due_date=due,
                days_to_due=(due - today).days,
                status=f.status if f else FilingStatus.DRAFT,
                filing_id=f.id if f else None,
                total_amount=(
                    (f.summary or {}).get("total_employee_epf", 0.0)
                    + (f.summary or {}).get("total_employer_epf", 0.0)
                    + (f.summary or {}).get("total_employer_eps", 0.0)
                    if (f and stream == StatutoryStream.EPF) else
                    (f.summary or {}).get("total_employee_contribution", 0.0)
                    + (f.summary or {}).get("total_employer_contribution", 0.0)
                    if f else None
                ),
                employee_count=(f.summary or {}).get("employee_count") if f else None,
            )
            cards.append(card)
            if card.days_to_due < 0 and card.status not in (
                FilingStatus.PAID, FilingStatus.ACKNOWLEDGED,
            ):
                overdue += 1
            elif 0 <= card.days_to_due <= 7:
                due_within_7_days += 1

        # PT: one per state that has a filing OR that the run could need.
        pt_filings = [
            f for f in existing_rows
            if f.payroll_run_id == run.id and f.stream == StatutoryStream.PT
        ]
        for f in pt_filings:
            due = pt_due_date(run.year, run.month, f.state or "")
            card = ComplianceCard(
                stream=StatutoryStream.PT, state=f.state,
                payroll_run_id=run.id,
                payroll_period=f"{run.month:02d}/{run.year}",
                due_date=due,
                days_to_due=(due - today).days,
                status=f.status, filing_id=f.id,
                total_amount=(f.summary or {}).get("total_pt_amount"),
                employee_count=(f.summary or {}).get("employee_count"),
            )
            cards.append(card)
            if card.days_to_due < 0 and card.status not in (
                FilingStatus.PAID, FilingStatus.ACKNOWLEDGED,
            ):
                overdue += 1
            elif 0 <= card.days_to_due <= 7:
                due_within_7_days += 1

    cards.sort(key=lambda c: (c.due_date, c.stream, c.state or ""))
    return ComplianceDashboard(
        as_of=today, cards=cards,
        overdue=overdue, due_within_7_days=due_within_7_days,
    )
