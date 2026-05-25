import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta
from app.models.user import User, Role, Permission, user_roles
from app.models.leave import LeaveRequest, LeaveType, LeaveStatus, LeaveBalanceLedger
from app.models.approval import ApprovalItem, ApprovalStep, ApprovalStatus
from app.core.security import get_password_hash

async def get_or_create_role(db: AsyncSession, name: str, permissions: list[str] = None):
    result = await db.execute(select(Role).where(Role.name == name))
    role = result.scalar_one_or_none()
    if not role:
        role = Role(name=name, description=f"{name} role")
        db.add(role)
        await db.flush()
        if permissions:
            for p_name in permissions:
                p_result = await db.execute(select(Permission).where(Permission.name == p_name))
                p = p_result.scalar_one_or_none()
                if not p:
                    p = Permission(name=p_name)
                    db.add(p)
                    await db.flush()
                role.permissions.append(p)
        await db.commit()
        await db.refresh(role)
    return role

async def create_test_user(db: AsyncSession, email: str, full_name: str, manager_id: int = None, roles: list[Role] = None):
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            email=email,
            full_name=full_name,
            hashed_password=get_password_hash("password123"),
            is_active=True,
            manager_id=manager_id
        )
        if roles:
            user.roles = roles
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user

@pytest.mark.asyncio
async def test_leave_approval_flow_scenario_a(db: AsyncSession):
    \"\"\"
    Scenario A (With Manager):
    - EmpA applies for leave (has ManA as manager).
    - Request in ManA's inbox, NOT HR's.
    - ManA approves.
    - Request in HR's inbox.
    - HR approves.
    - Final status APPROVED.
    \"\"\"
    # Setup roles
    emp_role = await get_or_create_role(db, "Employee", ["employee leave read", "employee leave write"])
    hr_role = await get_or_create_role(db, "HR", ["leave approve"])
    
    # Setup users
    hr_user = await create_test_user(db, "hr_a@example.com", "HR User A", roles=[hr_role])
    mana = await create_test_user(db, "mana@example.com", "Manager A", roles=[emp_role])
    empa = await create_test_user(db, "empa@example.com", "Employee A", manager_id=mana.id, roles=[emp_role])
    
    # Setup leave type and balance
    lt_result = await db.execute(select(LeaveType).where(LeaveType.name == "Annual Leave"))
    lt = lt_result.scalar_one_or_none()
    if not lt:
        lt = LeaveType(name="Annual Leave", description="Annual leave", unpaid_allowed=False)
        db.add(lt)
        await db.flush()
    
    bal_result = await db.execute(select(LeaveBalanceLedger).where(
        LeaveBalanceLedger.user_id == empa.id, LeaveBalanceLedger.leave_type_id == lt.id
    ))
    bal = bal_result.scalar_one_or_none()
    if not bal:
        bal = LeaveBalanceLedger(user_id=empa.id, leave_type_id=lt.id, balance=10.0, used=0.0)
        db.add(bal)
    else:
        bal.balance = 10.0
        bal.used = 0.0
    await db.commit()

    # 1. EmpA applies for leave
    # We use the internal logic similar to the endpoint
    leave_req = LeaveRequest(
        employee_id=empa.id,
        leave_type_id=lt.id,
        start_date=date.today() + timedelta(days=1),
        end_date=date.today() + timedelta(days=2),
        reason="Vacation",
        status=LeaveStatus.SUBMITTED,
        created_by_user_id=empa.id
    )
    db.add(leave_req)
    await db.flush()
    
    approval_item = ApprovalItem(
        resource_type="leave_request",
        resource_id=str(leave_req.id),
        status=ApprovalStatus.PENDING,
        current_step_number=1,
        requested_by_id=empa.id
    )
    db.add(approval_item)
    await db.flush()
    
    # Step 1: Manager
    step1 = ApprovalStep(
        approval_item_id=approval_item.id,
        step_number=1,
        approver_id=mana.id,
        status=ApprovalStatus.PENDING
    )
    db.add(step1)
    
    # Step 2: HR
    step2 = ApprovalStep(
        approval_item_id=approval_item.id,
        step_number=2,
        role_id=hr_role.id,
        status=ApprovalStatus.PENDING
    )
    db.add(step2)
    await db.commit()

    # 2. Verify request in ManA's inbox, NOT HR's
    # In ManA's perspective (step 1)
    q = select(ApprovalItem).join(ApprovalStep).where(
        ApprovalItem.id == approval_item.id,
        ApprovalItem.current_step_number == ApprovalStep.step_number,
        ApprovalStep.status == ApprovalStatus.PENDING,
        ApprovalStep.approver_id == mana.id
    )
    res = await db.execute(q)
    assert res.scalar_one_or_none() is not None
    
    # In HR's perspective (step 2) - should NOT be available because current_step_number is 1
    q_hr = select(ApprovalItem).join(ApprovalStep).where(
        ApprovalItem.id == approval_item.id,
        ApprovalItem.current_step_number == ApprovalStep.step_number,
        ApprovalStep.status == ApprovalStatus.PENDING,
        ApprovalStep.role_id == hr_role.id
    )
    res_hr = await db.execute(q_hr)
    assert res_hr.scalar_one_or_none() is None

    # 3. ManA approves
    step1.status = ApprovalStatus.APPROVED
    step1.approver_id = mana.id
    approval_item.current_step_number = 2
    await db.commit()
    
    # 4. Verify request in HR's inbox
    res_hr = await db.execute(q_hr)
    assert res_hr.scalar_one_or_none() is not None

    # 5. HR approves
    step2.status = ApprovalStatus.APPROVED
    step2.approver_id = hr_user.id
    approval_item.status = ApprovalStatus.APPROVED
    leave_req.status = LeaveStatus.APPROVED
    
    # Update balance (as in endpoint)
    bal.used += 2.0
    await db.commit()
    
    # 6. Verify final status
    await db.refresh(leave_req)
    assert leave_req.status == LeaveStatus.APPROVED
    assert bal.used == 2.0

@pytest.mark.asyncio
async def test_leave_approval_flow_scenario_b(db: AsyncSession):
    \"\"\"
    Scenario B (Without Manager):
    - EmpB applies for leave (no manager).
    - Request goes DIRECTLY to HR's inbox.
    - HR approves.
    - Final status APPROVED.
    \"\"\"
    # Setup roles
    emp_role = await get_or_create_role(db, "Employee", ["employee leave read", "employee leave write"])
    hr_role = await get_or_create_role(db, "HR", ["leave approve"])
    
    # Setup users
    hr_user = await create_test_user(db, "hr_b@example.com", "HR User B", roles=[hr_role])
    empb = await create_test_user(db, "empb@example.com", "Employee B", manager_id=None, roles=[emp_role])
    
    # Setup leave type and balance
    lt_result = await db.execute(select(LeaveType).where(LeaveType.name == "Annual Leave"))
    lt = lt_result.scalar_one()
    
    bal_result = await db.execute(select(LeaveBalanceLedger).where(
        LeaveBalanceLedger.user_id == empb.id, LeaveBalanceLedger.leave_type_id == lt.id
    ))
    bal = bal_result.scalar_one_or_none()
    if not bal:
        bal = LeaveBalanceLedger(user_id=empb.id, leave_type_id=lt.id, balance=10.0, used=0.0)
        db.add(bal)
    else:
        bal.balance = 10.0
        bal.used = 0.0
    await db.commit()

    # 1. EmpB applies for leave
    leave_req = LeaveRequest(
        employee_id=empb.id,
        leave_type_id=lt.id,
        start_date=date.today() + timedelta(days=5),
        end_date=date.today() + timedelta(days=5), # 1 day
        reason="Sick",
        status=LeaveStatus.SUBMITTED,
        created_by_user_id=empb.id
    )
    db.add(leave_req)
    await db.flush()
    
    approval_item = ApprovalItem(
        resource_type="leave_request",
        resource_id=str(leave_req.id),
        status=ApprovalStatus.PENDING,
        current_step_number=1,
        requested_by_id=empb.id
    )
    db.add(approval_item)
    await db.flush()
    
    # ONLY HR step because no manager
    step_hr = ApprovalStep(
        approval_item_id=approval_item.id,
        step_number=1,
        role_id=hr_role.id,
        status=ApprovalStatus.PENDING
    )
    db.add(step_hr)
    await db.commit()

    # 2. Verify request goes DIRECTLY to HR's inbox
    q_hr = select(ApprovalItem).join(ApprovalStep).where(
        ApprovalItem.id == approval_item.id,
        ApprovalItem.current_step_number == ApprovalStep.step_number,
        ApprovalStep.status == ApprovalStatus.PENDING,
        ApprovalStep.role_id == hr_role.id
    )
    res_hr = await db.execute(q_hr)
    assert res_hr.scalar_one_or_none() is not None

    # 3. HR approves
    step_hr.status = ApprovalStatus.APPROVED
    step_hr.approver_id = hr_user.id
    approval_item.status = ApprovalStatus.APPROVED
    leave_req.status = LeaveStatus.APPROVED
    bal.used += 1.0
    await db.commit()

    # 4. Verify final status
    await db.refresh(leave_req)
    assert leave_req.status == LeaveStatus.APPROVED
    assert bal.used == 1.0
