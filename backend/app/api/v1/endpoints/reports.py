from typing import Any
from datetime import datetime, timedelta, timezone
import random
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func

from app.api import deps
from app.models.user import User
from app.models.attendance import Attendance
from app.models.timesheet import TimeEntry
from app.models.project import Project, CostBaseline
from app.models.leave import LeaveBalanceLedger, LeaveType
from app.schemas.report import (
    ReportsSummary, AttendanceCompliance, ProjectUtilization,
    LeaveBalanceSummary, CostVariance
)

router = APIRouter()


@router.get("/summary", response_model=ReportsSummary)
async def get_reports_summary(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    """
    Get summary of all reports for dashboard.
    Authorized for Admin, CEO, and HR roles.
    """
    # Authorization logic
    allowed_roles = {"admin", "ceo", "hr"}
    user_roles = {role.name.lower() for role in current_user.roles}
    
    if not current_user.is_superuser and not (user_roles & allowed_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions to view operational reports"
        )

    # 1. Attendance Compliance (Last 7 days)
    seven_days_ago = datetime.now(timezone.utc).date() - timedelta(days=7)

    total_active_users_result = await db.execute(
        select(func.count(User.id)).where(User.is_active.is_(True))
    )
    # Avoid div by zero
    total_active_users = total_active_users_result.scalar() or 1

    attendance_query = select(
        func.date(Attendance.captured_at).label("date"),
        func.count(func.distinct(Attendance.user_id)).label("present_count")
    ).where(
        func.date(Attendance.captured_at) >= seven_days_ago
    ).group_by(
        func.date(Attendance.captured_at)
    ).order_by(
        func.date(Attendance.captured_at).desc()
    )

    attendance_results = await db.execute(attendance_query)
    attendance_compliance = []
    for res in attendance_results:
        percentage = round((res.present_count / total_active_users) * 100, 2)
        attendance_compliance.append(AttendanceCompliance(
            date=res.date,
            total_employees=total_active_users,
            present_count=res.present_count,
            compliance_percentage=percentage
        ))

    # 2. Project Utilization
    util_query = select(
        Project.id,
        Project.name,
        func.sum(TimeEntry.duration_seconds).label("total_seconds")
    ).join(
        TimeEntry, Project.id == TimeEntry.project_id
    ).group_by(
        Project.id, Project.name
    )

    util_results = await db.execute(util_query)
    project_utilization = []
    for res in util_results:
        hours = res.total_seconds / 3600
        project_utilization.append(ProjectUtilization(
            project_id=res.id,
            project_name=res.name,
            total_hours=round(hours, 2),
            # Assuming all hours are billable for now
            billable_hours=round(hours, 2),
            utilization_percentage=100.0  # Placeholder
        ))

    # 3. Leave Balances Summary
    leave_query = select(
        User.id,
        User.full_name,
        LeaveType.name.label("leave_type"),
        LeaveBalanceLedger.balance,
        LeaveBalanceLedger.used
    ).join(
        LeaveBalanceLedger, User.id == LeaveBalanceLedger.user_id
    ).join(
        LeaveType, LeaveBalanceLedger.leave_type_id == LeaveType.id
    )

    leave_results = await db.execute(leave_query)
    leave_balances = []
    for res in leave_results:
        leave_balances.append(LeaveBalanceSummary(
            employee_id=res.id,
            employee_name=res.full_name,
            leave_type=res.leave_type,
            total_allotted=res.balance + res.used,
            taken=res.used,
            remaining=res.balance
        ))

    # 4. Cost Variance Summary
    cost_baseline_query = select(
        Project.name,
        CostBaseline.amount.label("budget")
    ).join(
        CostBaseline, Project.id == CostBaseline.project_id
    ).where(
        CostBaseline.is_active.is_(True)
    )

    cost_results = await db.execute(cost_baseline_query)
    cost_variance = []
    for res in cost_results:
        # Mock actual cost as 85-115% of budget for demo
        actual = res.budget * random.uniform(0.85, 1.15)
        variance = res.budget - actual
        cost_variance.append(CostVariance(
            category=res.name,
            budgeted_cost=res.budget,
            actual_cost=round(actual, 2),
            variance=round(variance, 2),
            variance_percentage=round((variance / res.budget) * 100, 2)
        ))

    return ReportsSummary(
        attendance_compliance=attendance_compliance,
        project_utilization=project_utilization,
        leave_balances=leave_balances,
        cost_variance=cost_variance
    )
