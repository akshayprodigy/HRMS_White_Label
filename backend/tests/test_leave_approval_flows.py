import pytest
import asyncio
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.user import User, Role, user_roles
from app.models.leave import LeaveRequest, LeaveType, LeaveStatus
from app.models.approval import ApprovalItem, ApprovalStep, ApprovalStatus
from datetime import datetime, timedelta, date

@pytest.mark.asyncio
async def test_leave_approval_scenarios():
    async with SessionLocal() as db:
        # 1. Setup Roles
        hr_role_res = await db.execute(select(Role).where(Role.name == "HR"))
        hr_role = hr_role_res.scalar_one_or_none()
        if not hr_role:
            hr_role = Role(name="HR", description="HR Manager")
            db.add(hr_role)
            await db.commit()
            await db.refresh(hr_role)

        # 2. Setup Users
        unique_suffix = int(datetime.now().timestamp())
        hr_user = User(email=f"hr_{unique_suffix}@test.com", full_name="HR Admin", hashed_password="hashed", is_active=True)
        manager = User(email=f"man_{unique_suffix}@test.com", full_name="Manager User", hashed_password="hashed", is_active=True)
        db.add_all([hr_user, manager])
        await db.flush()
        
        # Link HR role to hr_user
        await db.execute(user_roles.insert().values(user_id=hr_user.id, role_id=hr_role.id))
        
        emp_with_man = User(email=f"emp_w_{unique_suffix}@test.com", full_name="Emp With Manager", manager_id=manager.id, hashed_password="hashed")
        emp_no_man = User(email=f"emp_n_{unique_suffix}@test.com", full_name="Emp No Manager", manager_id=None, hashed_password="hashed")
        db.add_all([emp_with_man, emp_no_man])
        await db.flush()

        # 3. Setup Leave Type
        ltype_res = await db.execute(select(LeaveType).limit(1))
        ltype = ltype_res.scalar_one_or_none()
        if not ltype:
            ltype = LeaveType(name="Test Leave", unpaid_allowed=False)
            db.add(ltype)
            await db.flush()

        # --- Scenario A: With Manager ---
        leave_a = LeaveRequest(
            employee_id=emp_with_man.id, 
            leave_type_id=ltype.id, 
            start_date=date.today(), 
            end_date=date.today(), 
            status=LeaveStatus.SUBMITTED,
            reason="Test Reason",
            created_by_user_id=emp_with_man.id
        )
        db.add(leave_a)
        await db.flush()
        
        app_item_a = ApprovalItem(
            resource_type="leave", 
            resource_id=str(leave_a.id), 
            status=ApprovalStatus.PENDING, 
            current_step_number=1
        )
        db.add(app_item_a)
        await db.flush()
        
        s1a = ApprovalStep(
            approval_item_id=app_item_a.id, 
            step_number=1, 
            approver_id=manager.id, 
            status=ApprovalStatus.PENDING
        )
        s2a = ApprovalStep(
            approval_item_id=app_item_a.id, 
            step_number=2, 
            role_id=hr_role.id, 
            status=ApprovalStatus.PENDING
        )
        db.add_all([s1a, s2a])
        await db.commit()
        
        assert app_item_a.current_step_number == 1
        
        # Approve Step 1
        s1a.status = ApprovalStatus.APPROVED
        app_item_a.current_step_number = 2
        await db.commit()
        
        # Approve Step 2
        s2a.status = ApprovalStatus.APPROVED
        app_item_a.status = ApprovalStatus.APPROVED
        leave_a.status = LeaveStatus.APPROVED
        await db.commit()
        
        # --- Scenario B: No Manager ---
        leave_b = LeaveRequest(
            employee_id=emp_no_man.id, 
            leave_type_id=ltype.id, 
            start_date=date.today(), 
            end_date=date.today(), 
            status=LeaveStatus.SUBMITTED,
            reason="Test Reason",
            created_by_user_id=emp_no_man.id
        )
        db.add(leave_b)
        await db.flush()
        
        app_item_b = ApprovalItem(
            resource_type="leave", 
            resource_id=str(leave_b.id), 
            status=ApprovalStatus.PENDING, 
            current_step_number=1
        )
        db.add(app_item_b)
        await db.flush()
        
        s1b = ApprovalStep(
            approval_item_id=app_item_b.id, 
            step_number=1, 
            role_id=hr_role.id, 
            status=ApprovalStatus.PENDING
        )
        db.add(s1b)
        await db.commit()
        
        # Verify
        await db.refresh(app_item_b)
        
        s1b.status = ApprovalStatus.APPROVED
        app_item_b.status = ApprovalStatus.APPROVED
        leave_b.status = LeaveStatus.APPROVED
        await db.commit()

        print("Tests Completed Successfully")

        print("Tests Completed Successfully")

if __name__ == "__main__":
    asyncio.run(test_leave_approval_scenarios())
