"""CSV / Excel punch import (Roadmap v2 Phase 4, Task 6).

Pure parsing tests plus DB-backed endpoint tests on the real dev DB with full
teardown. Dates are in the current month (the import rejects future / >400d)."""
import io
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook
from sqlalchemy import delete, insert, select, update

from app.api import deps
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.attendance import Attendance
from app.models.audit import AuditLog
from app.models.biometric import (
    BiometricDevice, BiometricDeviceStatus as DS, BiometricPunch,
    BiometricPunchState as S, BiometricUserMap,
)
from app.models.employee import Employee, EmployeeStatus
from app.models.notification import Notification
from app.models.user import Role, User, user_roles
from app.services import biometric as bio
from app.services import biometric_import as imp

P = "/api/v1/biometric"
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
D = "2026-11-03"


def utc(h, m=0, s=0, day=3):
    return datetime(2026, 11, day, h, m, s, tzinfo=timezone.utc)


def ist(h, m=0, s=0, day=3):
    return utc(h, m, s, day) - timedelta(minutes=330)


# ---------------- pure parsing / validation ----------------

def test_csv_leading_zero_bom_headers_and_blank_rows():
    data = ("﻿Employee Code, Time-Stamp ,x\n00123,2026-11-03 09:00,1\n"
            ",,\n  007 ,2026-11-03 10:00:05,2\n").encode("utf-8")
    raw = imp.read_rows("a.CSV", data)
    assert [n for n, _ in raw] == [2, 4]
    p = imp.validate_rows(raw, "employee_code", 330, NOW)
    assert [r.ident for r in p.rows] == ["00123", "007"]
    assert p.rows[0].when == utc(3, 30)  # 09:00 IST
    assert p.invalid == 0


def test_timestamp_formats_and_offset_rules():
    mk = lambda ts, **k: imp.parse_timestamp({"timestamp": ts, **k}, 330)
    assert mk("2026-11-03 09:00") == utc(3, 30)
    assert mk("03-11-2026 09:00:15") == utc(3, 30, 15)
    assert mk("03/11/2026 09:00") == utc(3, 30)
    assert mk("2026-11-03T09:00:00") == utc(3, 30)
    assert mk("2026-11-03T09:00:00Z") == utc(9)        # explicit offset wins
    assert mk("2026-11-03T09:00:00+01:00") == utc(8)
    assert imp.parse_timestamp({"timestamp": "2026-11-03 09:00"}, 0) == utc(9)
    assert imp.parse_timestamp(
        {"date": "03/11/2026", "time": "09:00"}, 330) == utc(3, 30)
    assert imp.parse_timestamp(
        {"date": date(2026, 11, 3), "time": datetime(2026, 11, 3, 9, 0).time()},
        330) == utc(3, 30)
    assert imp.parse_timestamp({"timestamp": datetime(2026, 11, 3, 9, 0)},
                               330) == utc(3, 30)
    with pytest.raises(ValueError):
        mk("yesterday")
    with pytest.raises(ValueError):
        imp.parse_timestamp({"date": "2026-11-03"}, 330)


def test_future_old_and_row_numbers():
    raw = [(2, {"employee_code": "a", "timestamp": "2026-11-14 12:00"}),
           (3, {"employee_code": "a", "timestamp": "2026-11-20 09:00"}),
           (4, {"employee_code": "a", "timestamp": "2024-01-01 09:00"}),
           (5, {"employee_code": "", "timestamp": "2026-11-03 09:00"}),
           (6, {"employee_code": "a", "timestamp": "zzz"})]
    p = imp.validate_rows(raw, "employee_code", 330, NOW)
    assert len(p.rows) == 1 and p.invalid == 4
    assert [e["row"] for e in p.errors] == [3, 4, 5, 6]
    assert "future" in p.errors[0]["message"]
    assert "400 days" in p.errors[1]["message"]


def test_missing_columns_and_file_errors():
    raw = [(2, {"foo": "1", "timestamp": "2026-11-03 09:00"})]
    with pytest.raises(imp.ImportFileError):
        imp.validate_rows(raw, "employee_code", 330, NOW)
    with pytest.raises(imp.ImportFileError):
        imp.validate_rows([(2, {"pin": "1"})], "pin", 330, NOW)
    with pytest.raises(imp.ImportFileError) as e:
        imp.read_rows("a.txt", b"x")
    assert e.value.status == 400
    with pytest.raises(imp.ImportFileError):
        imp.read_rows("a.csv", b"\xff\xfe\x00bad\x80")
    with pytest.raises(imp.ImportFileError):
        imp.read_rows("a.xlsx", b"not a zip at all")
    with pytest.raises(imp.ImportFileError) as e:
        imp.read_rows("a.csv", b"x" * (imp.MAX_BYTES + 1))
    assert e.value.status == 413


def test_xlsx_cells_numeric_code_and_datetime():
    wb = Workbook()
    ws = wb.active
    ws.append(["Employee Code", "Timestamp"])
    ws.append([123.0, datetime(2026, 11, 3, 9, 0)])
    ws.append(["00123", datetime(2026, 11, 3, 9, 5)])
    ws.append([456, "2026-11-03 09:10"])
    buf = io.BytesIO()
    wb.save(buf)
    raw = imp.read_rows("x.xlsx", buf.getvalue())
    p = imp.validate_rows(raw, "employee_code", 330, NOW)
    assert [r.ident for r in p.rows] == ["123", "00123", "456"]
    assert p.rows[0].when == utc(3, 30)


# ---------------- DB-backed ----------------

@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    ids: dict = {"sfx": sfx}
    try:
        async with SessionLocal() as db:
            us = {}
            for n in ("hr", "a", "b", "c", "inact"):
                us[n] = User(email=f"bimp_{n}_{sfx}@t.com",
                             full_name=f"Bimp {n} {sfx}",
                             hashed_password=get_password_hash("x"),
                             is_active=(n != "inact"))
            db.add_all(us.values())
            await db.commit()
            role = (await db.execute(
                select(Role).where(Role.name == "HR"))).scalars().first()
            await db.execute(insert(user_roles).values(
                user_id=us["hr"].id, role_id=role.id))
            for n in ("a", "b", "c", "inact"):
                db.add(Employee(
                    user_id=us[n].id, employee_id=f"BI{sfx}{n}",
                    department="T", designation="T",
                    date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            dev = BiometricDevice(serial=f"BIMP{sfx}", utc_offset_minutes=330,
                                  status=DS.ACTIVE)
            db.add(dev)
            await db.commit()
            ids.update({n: u.id for n, u in us.items()})
            ids["dev"] = dev.id
        yield ids
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"bimp\\_%\\_{sfx}@t.com")))).scalars().all())
            await db.execute(delete(BiometricPunch).where(
                BiometricPunch.pin.like(f"%{sfx}%")))
            await db.execute(delete(BiometricUserMap).where(
                BiometricUserMap.pin.like(f"%{sfx}%")))
            await db.execute(delete(Attendance).where(
                Attendance.user_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(AuditLog).where(
                AuditLog.user_id.in_(uids)))
            await db.execute(delete(BiometricDevice).where(
                BiometricDevice.serial.like(f"BIMP{sfx}%")))
            await db.execute(delete(Employee).where(
                Employee.user_id.in_(uids)))
            await db.execute(delete(user_roles).where(
                user_roles.c.user_id.in_(uids)))
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def _login(c, email):
    r = await c.post("/api/v1/auth/login",
                     data={"username": email, "password": "x"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def api(world):
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        c.hr = await _login(c, f"bimp_hr_{world['sfx']}@t.com")
        c.emp = await _login(c, f"bimp_a_{world['sfx']}@t.com")
        yield c


def _csv(text):
    return ("t.csv", text.encode(), "text/csv")


async def _post(api, kind, file, headers=None, **form):
    return await api.post(f"{P}/import/{kind}", headers=headers or api.hr,
                          files={"file": file}, data=form)


async def _att(uid):
    async with SessionLocal() as db:
        return (await db.execute(select(Attendance).where(
            Attendance.user_id == uid))).scalars().all()


async def _batch_states(batch):
    async with SessionLocal() as db:
        return sorted((await db.execute(select(BiometricPunch.state).where(
            BiometricPunch.import_batch == batch))).scalars().all())


async def test_csv_by_code_preview_commit_first_in_last_out(api, world):
    s = world["sfx"]
    text = (
        "employee_code,timestamp\n"
        f"bi{s}a,{D} 09:00:00\n"                 # lower-case code, IST
        f"BI{s}A,03/11/2026 13:00\n"             # middle tap
        f"BI{s}a,03-11-2026 18:30:10\n"
        f"BI{s}b,{D}T09:00:00Z\n"                # explicit offset wins
        f"BI{s}b,{D}T09:00:00Z\n"                # in-file duplicate
    )
    r = await _post(api, "preview", _csv(text), utc_offset_minutes="330",
                    identify_by="employee_code")
    assert r.status_code == 200, r.text
    j = r.json()
    assert (j["rows"], j["valid"], j["invalid"]) == (5, 5, 0)
    assert j["duplicates_in_file"] == 1 and j["already_imported"] == 0
    assert j["unknown_people"] == 0 and j["errors"] == []
    assert j["date_range"]["from"].startswith("2026-11-03T03:30")
    assert len(j["sample"]) == 5
    async with SessionLocal() as db:  # preview wrote nothing
        assert (await db.execute(select(BiometricPunch.id).where(
            BiometricPunch.pin.like(f"%{s}%")))).first() is None

    r = await _post(api, "commit", _csv(text), utc_offset_minutes="330",
                    identify_by="employee_code")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["inserted"] == 4 and j["remaining"] == 0
    assert j["by_state"] == {"applied": 4}
    a = await _att(world["a"])
    assert len(a) == 1
    assert a[0].captured_at.replace(tzinfo=timezone.utc) == ist(9)
    assert a[0].punch_out_time.replace(tzinfo=timezone.utc) == ist(18, 30, 10)
    b = await _att(world["b"])
    assert len(b) == 1 and b[0].punch_out_time is None
    async with SessionLocal() as db:
        au = (await db.execute(select(AuditLog).where(
            AuditLog.user_id == world["hr"],
            AuditLog.action == "BIOMETRIC_IMPORT"))).scalars().all()
        assert len(au) == 1
        assert au[0].details["inserted"] == 4
        assert au[0].details["batch"] == j["import_batch"]
        assert au[0].details["filename"] == "t.csv"

    # re-import the same file: nothing new
    r = await _post(api, "preview", _csv(text), identify_by="employee_code",
                    utc_offset_minutes="330")
    assert r.json()["already_imported"] == 5
    r = await _post(api, "commit", _csv(text), identify_by="employee_code",
                    utc_offset_minutes="330")
    assert r.status_code == 200 and r.json()["inserted"] == 0


async def test_xlsx_with_datetime_cells(api, world):
    s = world["sfx"]
    wb = Workbook()
    ws = wb.active
    ws.append(["Employee Code", "Date", "Time"])
    ws.append([f"BI{s}c", datetime(2026, 11, 4), datetime(2026, 11, 4, 9, 0).time()])
    ws.append([f"BI{s}c", datetime(2026, 11, 4), datetime(2026, 11, 4, 17, 45).time()])
    buf = io.BytesIO()
    wb.save(buf)
    f = ("t.xlsx", buf.getvalue(), "application/octet-stream")
    r = await _post(api, "commit", f, utc_offset_minutes="330",
                    identify_by="employee_code")
    assert r.status_code == 200, r.text
    c = await _att(world["c"])
    assert len(c) == 1
    assert c[0].captured_at.replace(tzinfo=timezone.utc) == ist(9, day=4)
    assert c[0].punch_out_time.replace(tzinfo=timezone.utc) == ist(17, 45, day=4)


async def test_bad_rows_row_numbers_and_skip_invalid(api, world):
    s = world["sfx"]
    text = ("employee_code,timestamp,device_serial\n"
            f"BI{s}a,{D} 09:00,\n"
            f"BI{s}a,garbage,\n"
            f"BI{s}a,2030-01-01 09:00,\n"
            f"BI{s}a,2020-01-01 09:00,\n"
            f"BI{s}a,{D} 10:00,NOSUCHDEV\n"
            f",{D} 10:00,\n")
    r = await _post(api, "preview", _csv(text), identify_by="employee_code",
                    utc_offset_minutes="330")
    j = r.json()
    assert (j["rows"], j["valid"], j["invalid"]) == (6, 1, 5)
    assert sorted(e["row"] for e in j["errors"]) == [3, 4, 5, 6, 7]
    r = await _post(api, "commit", _csv(text), identify_by="employee_code",
                    utc_offset_minutes="330")
    assert r.status_code == 400
    assert r.json()["error"]["details"]["invalid"] == 5
    assert await _att(world["a"]) == []
    r = await _post(api, "commit", _csv(text), identify_by="employee_code",
                    utc_offset_minutes="330", skip_invalid="true")
    assert r.status_code == 200 and r.json()["inserted"] == 1
    assert r.json()["skipped_invalid"] == 5


async def test_known_device_serial_ok_and_inactive_user_unknown(api, world):
    s = world["sfx"]
    text = ("employee_code,timestamp,device_serial\n"
            f"BI{s}b,{D} 09:00,BIMP{s}\n"
            f"BI{s}inact,{D} 09:00,\n")
    j = (await _post(api, "preview", _csv(text), identify_by="employee_code",
                     utc_offset_minutes="330")).json()
    assert j["invalid"] == 0 and j["unknown_people"] == 1


async def test_pin_mode_with_global_and_device_map(api, world):
    s = world["sfx"]
    async with SessionLocal() as db:
        db.add_all([
            BiometricUserMap(device_id=None, pin=f"1{s}", user_id=world["a"]),
            BiometricUserMap(device_id=world["dev"], pin=f"2{s}",
                             user_id=world["b"]),
        ])
        await db.commit()
    text = ("pin,timestamp,device_serial\n"
            f"1{s},{D} 09:00,\n1{s},{D} 18:00,\n"
            f"2{s},{D} 09:30,BIMP{s}\n"
            f"2{s},{D} 09:40,\n")  # device-map pin without a device: unknown
    j = (await _post(api, "preview", _csv(text), identify_by="pin",
                     utc_offset_minutes="330")).json()
    assert j["valid"] == 4 and j["unknown_people"] == 1
    r = await _post(api, "commit", _csv(text), identify_by="pin",
                    utc_offset_minutes="330")
    assert r.status_code == 200, r.text
    a = await _att(world["a"])
    assert len(a) == 1 and a[0].punch_out_time is not None
    assert len(await _att(world["b"])) == 1
    assert r.json()["by_state"].get("unmapped") == 1


async def test_unknown_code_stored_unmapped_then_mapping_backfills(api, world):
    s = world["sfx"]
    code = f"GH{s}"
    text = f"employee_code,timestamp\n{code},{D} 09:00\n{code},{D} 18:00\n"
    j = (await _post(api, "preview", _csv(text), identify_by="employee_code",
                     utc_offset_minutes="330")).json()
    assert j["unknown_people"] == 1 and j["invalid"] == 0 and j["valid"] == 2
    r = await _post(api, "commit", _csv(text), identify_by="employee_code",
                    utc_offset_minutes="330")
    batch = r.json()["import_batch"]
    assert r.json()["by_state"] == {"unmapped": 2}
    assert await _batch_states(batch) == ["unmapped", "unmapped"]
    async with SessionLocal() as db:
        db.add(BiometricUserMap(device_id=None, pin=code, user_id=world["c"]))
        await db.commit()
    # continuation / reprocess scoped to the batch
    r = await api.post(f"{P}/punches/reprocess", headers=api.hr, json={
        "state": "unmapped", "import_batch": batch})
    assert r.status_code == 200, r.text
    assert r.json()["backfill"].get("applied") == 2
    assert await _batch_states(batch) == ["applied", "applied"]
    assert len(await _att(world["c"])) == 1
    # another batch is untouched by import_batch scoping
    r = await api.post(f"{P}/punches/reprocess", headers=api.hr, json={
        "state": "pending", "import_batch": str(uuid.uuid4())})
    assert r.json()["backfill"] == {} and r.json()["remaining"] == 0


async def test_backfill_keeps_code_identity_without_map(api, world):
    s = world["sfx"]
    text = f"employee_code,timestamp\nBI{s}a,{D} 09:00\n"
    r = await _post(api, "commit", _csv(text), identify_by="employee_code",
                    utc_offset_minutes="330")
    batch = r.json()["import_batch"]
    async with SessionLocal() as db:
        await db.execute(update(BiometricPunch).where(
            BiometricPunch.import_batch == batch).values(
            state="received", attendance_id=None))
        await db.execute(delete(Attendance).where(
            Attendance.user_id == world["a"]))
        await db.commit()
    res = await bio.apply_pending(SessionLocal, import_batch=batch,
                                  states={"received"})
    assert res["counts"] == {"applied": 1}
    async with SessionLocal() as db:
        bp = (await db.execute(select(BiometricPunch).where(
            BiometricPunch.import_batch == batch))).scalars().one()
        assert bp.user_id == world["a"]


async def test_limits_and_file_validation(api, world):
    s = world["sfx"]
    head = "employee_code,timestamp\n"
    row = f"X{s},{D} 09:00\n"
    big = _csv(head + row * 20001)
    r = await _post(api, "preview", big, identify_by="employee_code")
    assert r.status_code == 400 and "20000" in r.text
    ok = _csv(head + row * 20000)
    r = await _post(api, "preview", ok, identify_by="employee_code",
                    utc_offset_minutes="330")
    assert r.status_code == 200 and r.json()["rows"] == 20000
    assert r.json()["duplicates_in_file"] == 19999
    # size: by Content-Length, and by actual bytes just over the limit
    for n in (imp.MAX_BYTES + 100_000, imp.MAX_BYTES + 1):
        r = await _post(api, "preview",
                        ("t.csv", b"a" * n, "text/csv"),
                        identify_by="employee_code")
        assert r.status_code == 413, (n, r.status_code)
    r = await _post(api, "preview", ("t.pdf", b"%PDF", "application/pdf"),
                    identify_by="employee_code")
    assert r.status_code == 400
    r = await _post(api, "preview", ("t.xlsx", b"hello", "application/x"),
                    identify_by="employee_code")
    assert r.status_code == 400
    r = await _post(api, "preview", ("t.csv", b"\xff\xfe\x80\x81", "text/csv"),
                    identify_by="employee_code")
    assert r.status_code == 400 and "UTF-8" in r.text
    r = await _post(api, "preview", _csv("foo,bar\n1,2\n"),
                    identify_by="employee_code")
    assert r.status_code == 400
    r = await _post(api, "preview", _csv(head + row), identify_by="bogus")
    assert r.status_code == 400
    r = await _post(api, "preview", _csv(head + row), identify_by="pin")
    assert r.status_code == 400  # no pin column
    r = await api.post(f"{P}/import/preview", headers=api.hr)
    assert r.status_code == 400


async def test_iso_offset_overrides_form_offset(api, world):
    s = world["sfx"]
    text = ("employee_code,timestamp\n"
            f"BI{s}a,{D}T09:00:00+00:00\n"
            f"BI{s}a,{D} 18:00:00\n")
    r = await _post(api, "commit", _csv(text), identify_by="employee_code",
                    utc_offset_minutes="0")
    assert r.status_code == 200, r.text
    a = (await _att(world["a"]))[0]
    assert a.captured_at.replace(tzinfo=timezone.utc) == utc(9)
    assert a.punch_out_time.replace(tzinfo=timezone.utc) == utc(18)


async def test_default_offset_is_ist(api, world):
    s = world["sfx"]
    text = f"employee_code,timestamp\nBI{s}a,{D} 09:00\n"
    j = (await _post(api, "preview", _csv(text),
                     identify_by="employee_code")).json()
    assert j["date_range"]["from"].startswith("2026-11-03T03:30")


async def test_template_and_permission(api, world):
    r = await api.get(f"{P}/import/template", headers=api.hr)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.text.startswith("employee_code,")
    r = await api.get(f"{P}/import/template?identify_by=pin", headers=api.hr)
    assert r.text.startswith("pin,")
    s = world["sfx"]
    f = _csv(f"employee_code,timestamp\nBI{s}a,{D} 09:00\n")
    for kind in ("preview", "commit"):
        r = await _post(api, kind, f, headers=api.emp,
                        identify_by="employee_code")
        assert r.status_code == 403, (kind, r.status_code)
    assert (await api.get(f"{P}/import/template", headers=api.emp)
            ).status_code == 403
    assert await _att(world["a"]) == []
