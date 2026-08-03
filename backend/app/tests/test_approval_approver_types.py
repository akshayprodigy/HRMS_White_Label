import pytest
from types import SimpleNamespace

from sqlalchemy import select

from app.models.user import User, Role
from app.models.department import Department
from app.models.approval_chain import ApproverType
from app.api.v1.endpoints.approval_chains import _resolve_approvers
from app.services.approval_engine import build_plan, ChainSpec, StepSpec, RequestContext


async def _user(db, email, name):
    u = User(email=email, full_name=name, hashed_password="x", is_active=True)
    db.add(u)
    await db.flush()
    return u


async def _user_with_role(db, email, role_name):
    role = (await db.execute(select(Role).where(Role.name == role_name))).scalars().first()
    if role is None:
        role = Role(name=role_name, description=role_name)
        db.add(role)
        await db.flush()
    u = User(email=email, full_name=email, hashed_password="x", is_active=True, roles=[role])
    db.add(u)
    await db.flush()
    return u


def _step(approver_type, approver_ref=None):
    return SimpleNamespace(approver_type=approver_type, approver_ref=approver_ref)


@pytest.mark.asyncio
async def test_functional_head_resolves_department_head(db):
    head = await _user(db, "at_fh_head@pytest.local", "Head")
    dept = Department(name="AT_ENG", is_active=True, head_user_id=head.id)
    db.add(dept)
    await db.flush()
    submitter = await _user(db, "at_sub@pytest.local", "Sub")

    ids = await _resolve_approvers(db, _step(ApproverType.FUNCTIONAL_HEAD), submitter.id, department="AT_ENG")
    assert ids == [head.id]

    # no department context -> no approver
    ids_none = await _resolve_approvers(db, _step(ApproverType.FUNCTIONAL_HEAD), submitter.id, department=None)
    assert ids_none == []


@pytest.mark.asyncio
async def test_ceo_and_md_resolve_by_role(db):
    ceo = await _user_with_role(db, "at_ceo@pytest.local", "CEO")
    md = await _user_with_role(db, "at_md@pytest.local", "MD")
    submitter = await _user(db, "at_sub2@pytest.local", "Sub2")

    ceo_ids = await _resolve_approvers(db, _step(ApproverType.CEO), submitter.id)
    md_ids = await _resolve_approvers(db, _step(ApproverType.MD), submitter.id)
    assert ceo.id in ceo_ids
    assert md.id in md_ids


@pytest.mark.asyncio
async def test_dept_head_resolver_uses_correct_case(db):
    dh = await _user_with_role(db, "at_dh@pytest.local", "DEPT_HEAD")
    submitter = await _user(db, "at_sub3@pytest.local", "Sub3")
    ids = await _resolve_approvers(db, _step(ApproverType.DEPT_HEAD), submitter.id)
    assert dh.id in ids  # would have been empty before the case fix


def test_sod_drops_submitter_when_resolver_returns_self():
    # build_plan applies skip_if_same_person; a functional_head who is also
    # the submitter must be removed, leaving the step with no approver.
    step = StepSpec(step_order=1, approver_type=ApproverType.FUNCTIONAL_HEAD,
                    min_amount_paise=None, max_amount_paise=None)
    chain = ChainSpec(id=1, name="c", entity_type="revision", steps=(step,),
                      auto_approve_below_paise=None, skip_if_same_person=True, department=None)
    ctx = RequestContext(submitter_id=7, amount_paise=100_000)
    plan = build_plan(chain, ctx, lambda s, c: [7])  # resolver returns the submitter
    assert plan[0].approver_user_ids == []
    assert plan[0].skip_reason == "no_eligible_approver"
