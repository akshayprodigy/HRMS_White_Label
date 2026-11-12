"""assert_attendance_editable: only MONTHLY runs past DRAFT lock a month."""
import pytest
from fastapi import HTTPException
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.models.payroll import PayrollRun, PayrollRunStatus
from app.services.attendance_lock import assert_attendance_editable
from datetime import date

YEAR, MONTH = 2016, 5  # nobody uses this month


async def _make(run_type, status):
    async with SessionLocal() as db:
        r = PayrollRun(month=MONTH, year=YEAR, status=status, run_type=run_type)
        db.add(r)
        await db.commit()
        return r.id


async def _cleanup(ids):
    async with SessionLocal() as db:
        if ids:
            await db.execute(delete(PayrollRun).where(PayrollRun.id.in_(ids)))
        await db.commit()


async def test_off_cycle_past_draft_does_not_block():
    ids = []
    try:
        ids.append(await _make("off_cycle", PayrollRunStatus.PUBLISHED))
        async with SessionLocal() as db:
            await assert_attendance_editable(db, date(YEAR, MONTH, 10))
    finally:
        await _cleanup(ids)


async def test_monthly_past_draft_blocks():
    ids = []
    try:
        ids.append(await _make("monthly", PayrollRunStatus.ATTENDANCE_LOCKED))
        async with SessionLocal() as db:
            with pytest.raises(HTTPException) as ei:
                await assert_attendance_editable(db, date(YEAR, MONTH, 10))
        assert ei.value.status_code == 409
    finally:
        await _cleanup(ids)


async def test_monthly_draft_does_not_block():
    ids = []
    try:
        ids.append(await _make("monthly", PayrollRunStatus.DRAFT))
        async with SessionLocal() as db:
            await assert_attendance_editable(db, date(YEAR, MONTH, 10))
    finally:
        await _cleanup(ids)
