import pytest
from datetime import date

from app.models.user import User
from app.models.department import Department
from app.models.employee import Employee
from app.services import functional_head as fh


async def _mk_user(db, email, name):
    u = User(email=email, full_name=name, hashed_password="x", is_active=True)
    db.add(u)
    await db.flush()
    return u


async def _mk_employee(db, user, dept, status="active"):
    e = Employee(
        employee_id=f"E{user.id}",
        user_id=user.id,
        department=dept,
        designation="Engineer",
        status=status,
        date_of_joining=date(2024, 1, 1),
        salary=0.0,
        employment_type="permanent",
    )
    db.add(e)
    await db.flush()
    return e


@pytest.mark.asyncio
async def test_resolve_head_returns_head_then_deputy(db):
    head = await _mk_user(db, "fh_head@pytest.local", "Head One")
    deputy = await _mk_user(db, "fh_dep@pytest.local", "Deputy One")
    emp_user = await _mk_user(db, "fh_emp@pytest.local", "Emp One")
    dept = Department(name="FH_ENG", is_active=True, head_user_id=head.id, deputy_head_user_id=deputy.id)
    db.add(dept)
    await db.flush()
    emp = await _mk_employee(db, emp_user, "FH_ENG")

    resolved = await fh.resolve_head(db, emp)
    assert resolved is not None and resolved.id == head.id

    # With no primary head, falls back to deputy
    dept.head_user_id = None
    await db.flush()
    resolved2 = await fh.resolve_head(db, emp)
    assert resolved2 is not None and resolved2.id == deputy.id


@pytest.mark.asyncio
async def test_resolve_head_none_when_unassigned_or_no_dept(db):
    emp_user = await _mk_user(db, "fh_emp2@pytest.local", "Emp Two")
    dept = Department(name="FH_OPS", is_active=True)
    db.add(dept)
    await db.flush()
    emp = await _mk_employee(db, emp_user, "FH_OPS")
    assert await fh.resolve_head(db, emp) is None


@pytest.mark.asyncio
async def test_resolve_team_returns_active_members_of_headed_depts(db):
    head = await _mk_user(db, "fh_head3@pytest.local", "Head Three")
    dept = Department(name="FH_QA", is_active=True, head_user_id=head.id)
    db.add(dept)
    await db.flush()
    u1 = await _mk_user(db, "fh_m1@pytest.local", "M1")
    u2 = await _mk_user(db, "fh_m2@pytest.local", "M2")
    u3 = await _mk_user(db, "fh_m3@pytest.local", "M3")
    await _mk_employee(db, u1, "FH_QA")
    await _mk_employee(db, u2, "FH_QA")
    await _mk_employee(db, u3, "FH_QA", status="inactive")  # excluded

    team = await fh.resolve_team(db, head)
    emails = {m.user.full_name for m in team}
    assert emails == {"M1", "M2"}


@pytest.mark.asyncio
async def test_resolve_team_empty_when_heads_nothing(db):
    nobody = await _mk_user(db, "fh_nobody@pytest.local", "Nobody")
    assert await fh.resolve_team(db, nobody) == []


@pytest.mark.asyncio
async def test_is_head_of_true_for_head_and_deputy(db):
    head = await _mk_user(db, "fh_h4@pytest.local", "H4")
    deputy = await _mk_user(db, "fh_d4@pytest.local", "D4")
    other = await _mk_user(db, "fh_o4@pytest.local", "O4")
    dept = Department(name="FH_DES", is_active=True, head_user_id=head.id, deputy_head_user_id=deputy.id)
    db.add(dept)
    await db.flush()
    emp_user = await _mk_user(db, "fh_e4@pytest.local", "E4")
    emp = await _mk_employee(db, emp_user, "FH_DES")

    assert await fh.is_head_of(db, head, emp) is True
    assert await fh.is_head_of(db, deputy, emp) is True
    assert await fh.is_head_of(db, other, emp) is False


@pytest.mark.asyncio
async def test_resolve_head_skips_inactive_head_falls_to_deputy(db):
    head = await _mk_user(db, "fh_inh@pytest.local", "Inactive Head")
    head.is_active = False
    deputy = await _mk_user(db, "fh_actd@pytest.local", "Active Deputy")
    await db.flush()
    dept = Department(name="FH_SUP", is_active=True, head_user_id=head.id, deputy_head_user_id=deputy.id)
    db.add(dept)
    await db.flush()
    emp_user = await _mk_user(db, "fh_supemp@pytest.local", "Sup Emp")
    emp = await _mk_employee(db, emp_user, "FH_SUP")

    resolved = await fh.resolve_head(db, emp)
    assert resolved is not None and resolved.id == deputy.id

    # both inactive -> None
    deputy.is_active = False
    await db.flush()
    assert await fh.resolve_head(db, emp) is None
