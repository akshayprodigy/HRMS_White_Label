"""Payroll attendance lock check shared by HR edits and regularization."""
from datetime import date

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import OperationalError


async def assert_attendance_editable(
    db, work_date: date, fresh: bool = False) -> None:
    """Refuse edits once a payroll run has locked attendance for that
    month (user rule: 'edit should be before payroll is clicked')."""
    from app.models.payroll import PayrollRun, PayrollRunStatus

    stmt = (
        select(PayrollRun).where(
            PayrollRun.month == work_date.month,
            PayrollRun.year == work_date.year,
            PayrollRun.status != PayrollRunStatus.DRAFT,
            # Off-cycle (bonus/settlement) runs don't use attendance, so
            # they must not lock it; NULL/legacy run_type counts as monthly.
            or_(PayrollRun.run_type.is_(None),
                PayrollRun.run_type != "off_cycle"),
        )
    )
    if fresh:
        # Shared-lock read sees rows committed after our snapshot.
        stmt = stmt.with_for_update(read=True).execution_options(
            populate_existing=True)
    try:
        run = (await db.execute(stmt)).scalars().first()
    except OperationalError as exc:
        if not fresh or getattr(exc.orig, "args", (None,))[0] != 1020:
            raise
        # MariaDB 1020: payroll state changed after our snapshot.
        raise HTTPException(
            status_code=409,
            detail=f"Attendance for {work_date.isoformat()} is locked by a "
                   "payroll run that just changed; retry.") from exc
    if run:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Attendance for {work_date.isoformat()} is locked by the "
                f"{run.month:02d}/{run.year} payroll run "
                f"(status: {run.status.value}). Punch edits must happen "
                "before payroll locks attendance."
            ),
        )
