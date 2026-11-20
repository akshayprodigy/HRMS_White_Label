"""Phase 6A models: optional holiday picks + work-location requests."""
import uuid
from datetime import date

from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.hr import HolidayCalendar
from app.models.optional_holiday import OptionalHolidayPick, PickStatus
from app.models.user import User
from app.models.work_location import (
    DayPortion, WorkLocationKind, WorkLocationRequest, WorkLocationStatus,
)


def _user(sfx):
    return User(email=f"p6am_{sfx}@test.com", hashed_password="x",
                full_name="P6A Model", is_active=True)


async def _cleanup(sfx):
    async with SessionLocal() as db:
        uids = list((await db.execute(select(User.id).where(
            User.email.like(f"p6am\\_%{sfx}@test.com")))).scalars().all())
        if uids:
            await db.execute(delete(OptionalHolidayPick).where(
                OptionalHolidayPick.user_id.in_(uids)))
            await db.execute(delete(WorkLocationRequest).where(
                WorkLocationRequest.user_id.in_(uids)))
            await db.execute(delete(User).where(User.id.in_(uids)))
        await db.execute(delete(HolidayCalendar).where(
            HolidayCalendar.name == f"P6A {sfx}"))
        await db.commit()


async def test_insert_and_read_back():
    sfx = uuid.uuid4().hex[:8]
    try:
        async with SessionLocal() as db:
            u = _user(sfx)
            h = HolidayCalendar(name=f"P6A {sfx}", date=date(2031, 3, 1),
                                location="All", is_optional=True)
            db.add_all([u, h])
            await db.flush()
            db.add(OptionalHolidayPick(holiday_id=h.id, user_id=u.id,
                                       year=2031, reason="family"))
            db.add(WorkLocationRequest(
                user_id=u.id, kind=WorkLocationKind.CLIENT_VISIT,
                start_date=date(2031, 3, 2), end_date=date(2031, 3, 3),
                place="Acme", purpose="demo"))
            await db.commit()
            uid = u.id
        async with SessionLocal() as db:
            p = (await db.execute(select(OptionalHolidayPick).where(
                OptionalHolidayPick.user_id == uid))).scalar_one()
            assert p.status == PickStatus.PENDING and p.year == 2031
            assert p.created_at is not None and p.decided_by_id is None
            w = (await db.execute(select(WorkLocationRequest).where(
                WorkLocationRequest.user_id == uid))).scalar_one()
            assert w.status == WorkLocationStatus.PENDING
            assert w.day_portion == DayPortion.FULL
            assert w.place == "Acme" and w.end_date == date(2031, 3, 3)
    finally:
        await _cleanup(sfx)


async def test_user_delete_cascades():
    sfx = uuid.uuid4().hex[:8]
    try:
        async with SessionLocal() as db:
            u = _user(sfx)
            h = HolidayCalendar(name=f"P6A {sfx}", date=date(2031, 3, 1),
                                location="All", is_optional=True)
            db.add_all([u, h])
            await db.flush()
            db.add(OptionalHolidayPick(holiday_id=h.id, user_id=u.id,
                                       year=2031))
            db.add(WorkLocationRequest(
                user_id=u.id, kind=WorkLocationKind.WFH,
                start_date=date(2031, 3, 2), end_date=date(2031, 3, 2),
                purpose="focus"))
            await db.commit()
            uid = u.id
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()
        async with SessionLocal() as db:
            assert (await db.execute(select(OptionalHolidayPick).where(
                OptionalHolidayPick.user_id == uid))).first() is None
            assert (await db.execute(select(WorkLocationRequest).where(
                WorkLocationRequest.user_id == uid))).first() is None
    finally:
        await _cleanup(sfx)


async def test_holiday_delete_cascades_picks():
    sfx = uuid.uuid4().hex[:8]
    try:
        async with SessionLocal() as db:
            u = _user(sfx)
            h = HolidayCalendar(name=f"P6A {sfx}", date=date(2031, 3, 1),
                                location="All", is_optional=True)
            db.add_all([u, h])
            await db.flush()
            db.add(OptionalHolidayPick(holiday_id=h.id, user_id=u.id,
                                       year=2031))
            await db.commit()
            hid, uid = h.id, u.id
        async with SessionLocal() as db:
            await db.execute(delete(HolidayCalendar).where(
                HolidayCalendar.id == hid))
            await db.commit()
        async with SessionLocal() as db:
            assert (await db.execute(select(OptionalHolidayPick).where(
                OptionalHolidayPick.user_id == uid))).first() is None
    finally:
        await _cleanup(sfx)
