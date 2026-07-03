import io
import json
import pandas as pd
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional, Dict, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, or_, case
from sqlalchemy.orm import selectinload

from pathlib import Path
from uuid import uuid4

from fastapi.responses import FileResponse

from app.api import deps
from app.core.config import settings
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_asset import EmployeeAsset
from app.models.employee_document import EmployeeDocument
from app.models.required_document_type import RequiredDocumentType
from app.models.user import User, Role
from app.models.audit import AuditLog
from app.models.hr import (
    HolidayCalendar, PolicyDocument, PolicyAcknowledgement,
    EmployeeLetter, LetterType
)
from app.models.recruitment import ManpowerRequisition, RequisitionStatus, ApplicantStatus, Applicant
from app.models.attendance import (
    AttendanceCorrectionRequest, Attendance, CorrectionStatus
)
from app.models.leave import LeaveRequest, LeaveStatus
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.models.bd import Lead, LeadStage
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeProfileUpdate,
    EmployeeRead,
    EmployeeHRRead,
    EmployeeList
)
from app.schemas.hr import (
    HolidayCalendarCreate, HolidayCalendarRead,
    PolicyDocumentCreate, PolicyDocumentRead,
    PolicyAcknowledgementCreate, PolicyAcknowledgementRead,
    HRDashboardStats, ActivityItem,
    LetterGenerateRequest, EmployeeLetterRead
)
from app.services.letter_pdf import generate_letter, LETTER_GENERATORS
from app.services.salary_calculator import calculate_salary
from app.schemas.attendance import (
    AttendanceCorrectionCreate, AttendanceCorrectionRead,
    AttendanceCorrectionUpdate, AttendanceRead,
    AttendanceTimesEdit, AttendanceManualCreate,
    TimeRulesRead, TimeRulesUpdate,
)
from app.schemas.employee import EmployeeCreateWithUser
from app.schemas.user import UserLinkRead
from app.schemas.user import RoleSchema, UserRolesUpdate
from app.core.security import get_password_hash

router = APIRouter()

EMP_NOT_FOUND = "Employee not found"
HR_WRITE = "hr employee write"
HR_READ = "hr employee read"
HR_ROLE_ASSIGN = "hr role assign"
PAYROLL_VIEW = "hr payroll view"
PAYROLL_WRITE = "hr payroll write"


def api_error(
    code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }


@router.get("/users", response_model=List[UserLinkRead])
async def list_users_for_employee_onboarding(
    *,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([HR_READ])),
) -> Any:
    """List active users for HR to link when onboarding employees."""
    result = await db.execute(
        select(User).where(User.is_active.is_(True)).order_by(User.full_name)
    )
    return [UserLinkRead.model_validate(u) for u in result.scalars().all()]


@router.get("/roles", response_model=List[RoleSchema])
async def list_roles_for_hr(
    *,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([HR_READ])),
) -> Any:
    """List roles that HR can assign to employees."""
    result = await db.execute(select(Role).order_by(Role.name))
    roles = list(result.scalars().all())
    # Do not expose Super Admin assignment in HR UI.
    roles = [r for r in roles if r.name != "Super Admin"]
    return [RoleSchema.model_validate(r) for r in roles]


@router.patch("/employees/{emp_id}/roles", response_model=EmployeeHRRead)
async def update_employee_roles(
    *,
    db: deps.DBDep,
    request: Request,
    emp_id: int,
    obj_in: UserRolesUpdate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Update the linked login user's roles for a given employee."""
    # Check permissions manually to allow both HR_ROLE_ASSIGN and ADMIN_ACCESS/Superuser
    user_permissions = {p.name for r in current_user.roles for p in r.permissions}
    is_admin = current_user.is_superuser or "admin access" in user_permissions
    is_hr_role_assign = "hr role assign" in user_permissions

    if not is_admin and not is_hr_role_assign:
        raise HTTPException(
            status_code=403,
            detail=api_error("FORBIDDEN", "Not enough permissions to assign roles")
        )

    if emp_id <= 0:
        raise HTTPException(
            status_code=400,
            detail=api_error("INVALID_EMPLOYEE_ID", "Invalid employee id"),
        )

    query = (
        select(Employee)
        .where(Employee.id == emp_id)
        .options(
            selectinload(Employee.user)
            .selectinload(User.roles)
            .selectinload(Role.permissions)
        )
    )
    emp = (await db.execute(query)).scalar_one_or_none()
    if not emp or not emp.user:
        raise HTTPException(
            status_code=404,
            detail=api_error("EMPLOYEE_NOT_FOUND", EMP_NOT_FOUND),
        )

    # Avoid self-lockout.
    if emp.user.id == current_user.id:
        raise HTTPException(
            status_code=403,
            detail=api_error(
                "CANNOT_EDIT_SELF_ROLES",
                "You cannot change your own roles.",
            ),
        )

    before_role_names = [r.name for r in (emp.user.roles or [])]

    requested_ids = list(dict.fromkeys(obj_in.role_ids or []))
    if not requested_ids:
        raise HTTPException(
            status_code=400,
            detail=api_error(
                "ROLE_IDS_REQUIRED",
                "At least one role must be selected.",
            ),
        )

    result = await db.execute(select(Role).where(Role.id.in_(requested_ids)))
    roles = list(result.scalars().all())
    found_ids = {r.id for r in roles}
    missing = [rid for rid in requested_ids if rid not in found_ids]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=api_error(
                "ROLE_NOT_FOUND",
                "One or more roles were not found.",
                {"missing_role_ids": missing},
            ),
        )

    # Block any attempt to grant Super Admin, and block edits of existing
    # Super Admin users.
    if "Super Admin" in before_role_names:
        raise HTTPException(
            status_code=403,
            detail=api_error(
                "ROLE_EDIT_FORBIDDEN",
                "Cannot modify roles for Super Admin accounts.",
            ),
        )
    if any(r.name == "Super Admin" for r in roles):
        raise HTTPException(
            status_code=403,
            detail=api_error(
                "ROLE_ASSIGN_FORBIDDEN",
                "HR cannot assign the Super Admin role.",
            ),
        )

    employee_role = (
        await db.execute(select(Role).where(Role.name == "Employee").limit(1))
    ).scalars().first()
    if employee_role and employee_role.id not in found_ids:
        roles.append(employee_role)

    emp.user.roles = roles
    db.add(emp.user)
    await db.commit()
    await db.refresh(emp)

    after_role_names = [r.name for r in (emp.user.roles or [])]
    await log_audit(
        db,
        current_user.id,
        "UPDATE_ROLES",
        "user",
        str(emp.user.id),
        {
            "employee_id": emp.employee_id,
            "target_user_id": emp.user.id,
            "before_roles": before_role_names,
            "after_roles": after_role_names,
            "requested_role_ids": requested_ids,
        },
        request,
    )

    refreshed_res = await db.execute(
        select(Employee)
        .where(Employee.id == emp_id)
        .options(
            selectinload(Employee.user)
            .selectinload(User.roles)
            .selectinload(Role.permissions)
        ).limit(1)
    )
    refreshed = refreshed_res.scalars().first()
    return refreshed

# Bulk upload column names
COL_FULL_NAME = "Full Name"
COL_EMAIL = "Email"
COL_PASSWORD = "Password"
COL_ROLE = "Role"
COL_EMP_ID = "Employee ID"
COL_DEPT = "Department"
COL_DESIG = "Designation"
COL_JOIN_DATE = "Joining Date (YYYY-MM-DD)"
COL_SALARY = "Salary (Basic)"
COL_CA = "Conveyance Allowance"
COL_HRA = "HRA"
COL_OA = "Other Allowance"
COL_ESIC = "ESIC Applicable (Y/N)"
COL_BANK = "Bank Account"
COL_PF = "PF Number"
COL_PAN = "PAN Number"
COL_MANAGER_EMAIL = "Manager Email"
COL_NOTICE_PERIOD = "Notice Period (Days)"
COL_EMP_TYPE = "Employment Type (permanent/contractual)"


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


async def log_audit(
    db: deps.DBDep,
    user_id: int,
    action: str,
    resource_type: str,
    resource_id: str,
    details: Any,
    request: Request
) -> None:
    # Handle Pydantic models by converting to JSON-compatible dict
    if hasattr(details, "model_dump"):
        data = details.model_dump(mode="json")
    else:
        # For plain dicts, use the custom serializer to handle dates
        data = json.loads(json.dumps(details, default=json_serial))
    
    audit = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=data,
        ip_address=request.client.host if request.client else None
    )
    db.add(audit)
    await db.commit()


def check_payroll_permission(user: User, action: str = "view") -> bool:
    if user.is_superuser:
        return True
    perm_to_check = PAYROLL_VIEW if action == "view" else PAYROLL_WRITE
    for role in user.roles:
        for perm in role.permissions:
            if perm.name == perm_to_check:
                return True
    return False


async def _department_exists(db, name: str) -> bool:
    result = await db.execute(
        select(Department.id).where(Department.name == name).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _require_known_department(db, name: Optional[str]) -> None:
    """Raise 400 if `name` is not a department registered in the admin table."""
    if name is None:
        return
    if not await _department_exists(db, name):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Department '{name}' is not configured. "
                "Ask an admin to add it in System Administration first."
            ),
        )


def _serialize_employee_with_manager(emp: Employee) -> Dict[str, Any]:
    """Serialize an Employee for any user-facing employee response.

    Adds a flat `manager` block under `user` so the HR dashboard and the
    user-profile screen can both show the reporting line without an
    additional round-trip. Caller MUST eager-load `Employee.user.manager`.
    """
    data = EmployeeHRRead.model_validate(emp).model_dump(mode="json")
    mgr = emp.user.manager if emp.user else None
    data.setdefault("user", {})["manager"] = (
        {"id": mgr.id, "full_name": mgr.full_name, "email": mgr.email}
        if mgr else None
    )
    return data


@router.get("/employees/template")
async def get_employee_template(
    current_user: User = Depends(deps.check_permissions([HR_READ]))
) -> Any:
    """Download a sample Excel template for bulk employee upload."""
    columns = [
        COL_FULL_NAME, COL_EMAIL, COL_PASSWORD, COL_ROLE, COL_EMP_ID,
        COL_DEPT, COL_DESIG, COL_JOIN_DATE, COL_SALARY,
        COL_CA, COL_HRA, COL_OA, COL_ESIC,
        COL_BANK, COL_PF, COL_PAN, COL_MANAGER_EMAIL,
        COL_NOTICE_PERIOD, COL_EMP_TYPE
    ]
    df = pd.DataFrame(columns=columns)

    # Example rows: IMPORTANT — managers/seniors must appear BEFORE their
    # reportees so the system can auto-map the reporting relationship.
    # Row 1-3: Managers / HODs (no Manager Email needed)
    # Row 4-5: Employees reporting to the managers above
    examples = [
        # ── Managers first (no Manager Email) ──────────────────────
        ["Suresh Reddy", "suresh@company.com", "test@12345", "CEO", "EMP100",
         "Management", "Chief Executive Officer", "2026-01-01", "150000",
         "45000", "75000", "30000", "N",
         "1234567894", "PF-100", "EFGHI5678J", "", "90", "permanent"],
        ["Priya Sharma", "priya@company.com", "test@12345", "PM", "EMP101",
         "Engineering", "Project Manager", "2026-01-10", "60000",
         "18000", "30000", "12000", "N",
         "1234567891", "PF-101", "BCDEF2345G", "suresh@company.com", "60", "permanent"],
        ["Anita Verma", "anita@company.com", "test@12345", "HR", "EMP102",
         "Human Resources", "HR Manager", "2026-02-01", "45000",
         "13500", "22500", "9000", "Y",
         "1234567892", "PF-102", "CDEFG3456H", "suresh@company.com", "30", "permanent"],
        # ── Employees (with Manager Email pointing to rows above) ──
        ["Rahul Kumar", "rahul@company.com", "test@12345", "employee", "EMP103",
         "Engineering", "Software Engineer", "2026-01-15", "30000",
         "9000", "15000", "6000", "Y",
         "1234567890", "PF-103", "ABCDE1234F", "priya@company.com", "30", "permanent"],
        ["Vikram Singh", "vikram@company.com", "test@12345", "Business Developer", "EMP104",
         "Sales", "Business Developer", "2026-02-15", "40000",
         "12000", "20000", "8000", "Y",
         "1234567893", "PF-104", "DEFGH4567I", "priya@company.com", "30", "contractual"],
    ]
    for i, row in enumerate(examples):
        df.loc[i] = row

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Employees")

        # Add instructions sheet
        instructions = pd.DataFrame({
            "Instructions": [
                "1. Fill managers/HODs FIRST (rows at the top), then employees below them.",
                "2. In the 'Manager Email' column, enter the email of the reporting manager.",
                "3. The manager must already exist in the system OR appear in a row ABOVE the employee.",
                "4. Leave 'Manager Email' blank for top-level roles (CEO, Director, etc.).",
                "5. Required fields: Full Name, Email, Employee ID, Department, Designation.",
                "6. Password defaults to 'test@12345' if left blank.",
                "7. Role must match an existing role in the system (e.g., employee, PM, HR, CEO, etc.).",
                "8. Date format: YYYY-MM-DD (e.g., 2026-01-15).",
                "9. ESIC Applicable: Y or N.",
                "10. Employment Type: 'permanent' (default) or 'contractual'. Contractual employees have only 10% TDS deducted — no PF/ESI/Prof Tax.",
            ]
        })
        instructions.to_excel(writer, index=False, sheet_name="Instructions")

    output.seek(0)
    headers = {
        'Content-Disposition': 'attachment; filename="employee_template.xlsx"'
    }
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # noqa: E501
        headers=headers
    )


@router.get("/dashboard/stats", response_model=HRDashboardStats)
async def get_hr_dashboard_stats(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([HR_READ]))
) -> Any:
    """Get aggregated stats for HR Dashboard."""
    # 1. Total Employees
    total_emp_query = select(func.count(Employee.id))
    total_emp = (await db.execute(total_emp_query)).scalar() or 0

    # 2. Active Requisitions (Pending or Approved)
    active_req_query = select(func.count(ManpowerRequisition.id)).where(
        ManpowerRequisition.status.in_([RequisitionStatus.PENDING, RequisitionStatus.APPROVED])
    )
    active_req = (await db.execute(active_req_query)).scalar() or 0

    # 3. Pending HR Actions (Attendance Corrections)
    pending_actions_query = select(func.count(AttendanceCorrectionRequest.id)).where(
        AttendanceCorrectionRequest.status == CorrectionStatus.PENDING
    )
    pending_actions = (await db.execute(pending_actions_query)).scalar() or 0

    # 4. Onboarding Count (Applicants in HIRED status but not yet employees? Or maybe just 'OFFERED')
    # For now let's say OFFERED status means they are in onboarding pipeline
    onboarding_query = select(func.count(Applicant.id)).where(
        Applicant.status == ApplicantStatus.OFFERED
    )
    onboarding_count = (await db.execute(onboarding_query)).scalar() or 0

    # Attendance trends: last 5 business days, split by on-time vs late.
    # NOTE: captured_at is stored as timezone-aware datetime (UTC). We currently
    # classify on-time vs late using the stored timestamp's clock time.
    on_time_cutoff = "10:00:00"  # HH:MM:SS
    today = datetime.now(timezone.utc).date()
    business_days: List[date] = []
    cursor = today
    while len(business_days) < 5:
        if cursor.weekday() < 5:
            business_days.append(cursor)
        cursor = cursor - timedelta(days=1)
    business_days_sorted = sorted(business_days)

    attendance_agg_query = (
        select(
            func.date(Attendance.captured_at).label("d"),
            func.sum(
                case(
                    (func.time(Attendance.captured_at) <= on_time_cutoff, 1),
                    else_=0,
                )
            ).label("on_time"),
            func.sum(
                case(
                    (func.time(Attendance.captured_at) > on_time_cutoff, 1),
                    else_=0,
                )
            ).label("late"),
            func.count(Attendance.id).label("total"),
        )
        .where(func.date(Attendance.captured_at).in_(business_days_sorted))
        .group_by(func.date(Attendance.captured_at))
    )

    attendance_rows = (await db.execute(attendance_agg_query)).all()
    attendance_by_day: Dict[date, Dict[str, int]] = {
        row.d: {
            "on_time": int(row.on_time or 0),
            "late": int(row.late or 0),
            "total": int(row.total or 0),
        }
        for row in attendance_rows
    }

    attendance_trends: List[Dict[str, Any]] = []
    for d in business_days_sorted:
        agg = attendance_by_day.get(d, {"on_time": 0, "late": 0, "total": 0})
        total = agg["total"]
        on_time_pct = round((agg["on_time"] / total) * 100) if total else 0
        late_pct = round((agg["late"] / total) * 100) if total else 0
        attendance_trends.append(
            {
                "day": d.strftime("%a"),
                "onTime": on_time_pct,
                "late": late_pct,
            }
        )

    # Leave requisition trends: last 6 months count (excluding drafts/cancelled).
    now = datetime.now(timezone.utc)
    current_month_index = now.year * 12 + (now.month - 1)
    start_month_index = current_month_index - 5
    end_month_index = current_month_index + 1

    start_month = datetime(
        start_month_index // 12,
        (start_month_index % 12) + 1,
        1,
        tzinfo=timezone.utc,
    )
    end_month = datetime(
        end_month_index // 12,
        (end_month_index % 12) + 1,
        1,
        tzinfo=timezone.utc,
    )

    leave_agg_query = (
        select(
            func.year(LeaveRequest.created_at).label("y"),
            func.month(LeaveRequest.created_at).label("m"),
            func.count(LeaveRequest.id).label("c"),
        )
        .where(
            LeaveRequest.created_at >= start_month,
            LeaveRequest.created_at < end_month,
            ~LeaveRequest.status.in_([LeaveStatus.DRAFT, LeaveStatus.CANCELLED]),
        )
        .group_by(func.year(LeaveRequest.created_at), func.month(LeaveRequest.created_at))
    )

    leave_rows = (await db.execute(leave_agg_query)).all()
    leave_by_month: Dict[tuple[int, int], int] = {
        (int(row.y), int(row.m)): int(row.c or 0) for row in leave_rows
    }

    # Build last 6 months in chronological order.
    leave_trends: List[Dict[str, Any]] = []
    for idx in range(start_month_index, current_month_index + 1):
        y = idx // 12
        m = (idx % 12) + 1
        label = datetime(y, m, 1).strftime("%b")
        leave_trends.append({"month": label, "count": leave_by_month.get((y, m), 0)})

    # ----- real operational metrics (no fabricated numbers) -----
    from app.models.shift import ShiftChangeRequest, ShiftChangeStatus

    def _ago(ts) -> str:
        if ts is None:
            return ""
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        secs = max(0, (now - ts).total_seconds())
        if secs < 3600:
            return f"{int(secs // 60)}m ago"
        if secs < 86400:
            return f"{int(secs // 3600)}h ago"
        return f"{int(secs // 86400)}d ago"

    # Avg worked span over the last 7 days of closed punches.
    span_rows = (await db.execute(
        select(Attendance.captured_at, Attendance.punch_out_time).where(
            Attendance.punch_out_time.isnot(None),
            Attendance.work_date >= today - timedelta(days=7),
        )
    )).all()
    if span_rows:
        total_secs = sum(
            (o - i).total_seconds() for i, o in span_rows if o and o > i
        )
        avg_secs = total_secs / len(span_rows)
        avg_working_hours = f"{int(avg_secs // 3600):02d}h {int((avg_secs % 3600) // 60):02d}m"
    else:
        avg_working_hours = "—"

    # Attendance rate: mean daily presence over the last 5 business days.
    active_emp = (await db.execute(
        select(func.count(Employee.id)).where(Employee.status == "active")
    )).scalar() or 0
    # Join to Employee so punches from non-employee accounts (e.g. a
    # CEO login without an employee record) can't push the rate >100%.
    presence_rows = (await db.execute(
        select(
            Attendance.work_date,
            func.count(func.distinct(Attendance.user_id)),
        )
        .join(Employee, Employee.user_id == Attendance.user_id)
        .where(
            Attendance.work_date.in_(business_days_sorted),
            Employee.status == "active",
        )
        .group_by(Attendance.work_date)
    )).all()
    if active_emp and presence_rows:
        attendance_rate = round(
            sum(c for _, c in presence_rows)
            / (len(business_days_sorted) * active_emp) * 100, 1,
        )
    else:
        attendance_rate = 0.0

    # Requisitions raised in the last 7 days.
    req_week = (await db.execute(
        select(func.count(ManpowerRequisition.id)).where(
            ManpowerRequisition.created_at >= now - timedelta(days=7)
        )
    )).scalar() or 0

    joined_this_month = (await db.execute(
        select(func.count(Employee.id)).where(
            Employee.date_of_joining >= today.replace(day=1)
        )
    )).scalar() or 0

    today_present = (await db.execute(
        select(func.count(func.distinct(Attendance.user_id))).where(
            Attendance.work_date == today
        )
    )).scalar() or 0
    today_on_leave = (await db.execute(
        select(func.count(LeaveRequest.id)).where(
            LeaveRequest.status == LeaveStatus.APPROVED,
            LeaveRequest.start_date <= today,
            LeaveRequest.end_date >= today,
        )
    )).scalar() or 0

    # Live activity feed: real pending items across modules, newest first.
    activities: List[ActivityItem] = []
    corr_rows = (await db.execute(
        select(AttendanceCorrectionRequest, User)
        .join(User, AttendanceCorrectionRequest.user_id == User.id)
        .where(AttendanceCorrectionRequest.status == CorrectionStatus.PENDING)
        .order_by(AttendanceCorrectionRequest.id.desc()).limit(3)
    )).all()
    for c, u in corr_rows:
        activities.append(ActivityItem(
            name=u.full_name, identifier=f"COR-{c.id}",
            action=f"Attendance correction · {c.date.isoformat()}",
            type="Attendance", time=_ago(getattr(c, "created_at", None)),
        ))
    leave_rows_p = (await db.execute(
        select(LeaveRequest, User)
        .join(User, LeaveRequest.employee_id == User.id)
        .where(LeaveRequest.status == LeaveStatus.SUBMITTED)
        .order_by(LeaveRequest.created_at.desc()).limit(3)
    )).all()
    for lv, u in leave_rows_p:
        activities.append(ActivityItem(
            name=u.full_name, identifier=f"LV-{lv.id}",
            action=f"Leave approval · {lv.start_date.isoformat()}",
            type="Leave", time=_ago(lv.created_at),
        ))
    shift_rows = (await db.execute(
        select(ShiftChangeRequest, User)
        .join(User, ShiftChangeRequest.user_id == User.id)
        .where(ShiftChangeRequest.status == ShiftChangeStatus.PENDING)
        .order_by(ShiftChangeRequest.created_at.desc()).limit(3)
    )).all()
    for sc, u in shift_rows:
        activities.append(ActivityItem(
            name=u.full_name, identifier=f"SC-{sc.id}",
            action=f"Shift change · from {sc.effective_from.isoformat()}",
            type="Shifts", time=_ago(sc.created_at),
        ))
    activities = activities[:5]

    return HRDashboardStats(
        total_employees=total_emp,
        active_requisitions=active_req,
        pending_actions=pending_actions,
        avg_working_hours=avg_working_hours,
        attendance_rate=attendance_rate,
        requisition_trend=f"+{req_week} this week",
        onboarding_count=onboarding_count,
        attendance_trends=attendance_trends,
        leave_trends=leave_trends,
        activities=activities,
        joined_this_month=joined_this_month,
        today_present=today_present,
        today_on_leave=today_on_leave,
        active_employees=active_emp,
    )


DEFAULT_PASSWORD = "test@12345"


async def process_employee_row(
    db: deps.DBDep,
    index: int,
    row: pd.Series,
    current_user_id: int,
    request: Request,
    role_map: dict
) -> Optional[str]:
    """Process a single row: create user (if needed) + employee record."""
    row_num = index + 2  # Excel row (1-indexed header + 1-indexed data)

    # Helper to read a column safely (supports fallback column names)
    def col_val(name: str, *fallbacks: str):
        for n in (name, *fallbacks):
            if n in row.index and pd.notnull(row[n]):
                return row[n]
        return None

    full_name = str(row[COL_FULL_NAME]).strip() if pd.notnull(row.get(COL_FULL_NAME)) else ""
    email = str(row[COL_EMAIL]).strip() if pd.notnull(row.get(COL_EMAIL)) else ""
    emp_id = str(row[COL_EMP_ID]).strip() if pd.notnull(row.get(COL_EMP_ID)) else ""
    dept = str(row[COL_DEPT]).strip() if pd.notnull(row.get(COL_DEPT)) else ""
    desig = str(row[COL_DESIG]).strip() if pd.notnull(row.get(COL_DESIG)) else ""

    # Validate required fields with clear messages
    if not full_name or full_name == "nan":
        return f"Row {row_num} ({email or 'no email'}): Full Name is required"
    if not email or email == "nan":
        return f"Row {row_num} ({full_name}): Email is required"
    if not emp_id or emp_id == "nan":
        return f"Row {row_num} ({full_name}): Employee ID is required"
    if not dept or dept == "nan":
        return f"Row {row_num} ({full_name}): Department is required"
    if not desig or desig == "nan":
        return f"Row {row_num} ({full_name}): Designation is required"

    if not await _department_exists(db, dept):
        return (
            f"Row {row_num} ({full_name}): Department '{dept}' is not configured. "
            "Add it in System Administration first."
        )

    # Check if employee ID already taken
    id_exists = (await db.execute(
        select(Employee).where(Employee.employee_id == emp_id).limit(1)
    )).scalar_one_or_none()
    if id_exists:
        return f"Row {row_num} ({full_name}): Employee ID '{emp_id}' is already assigned to another employee"

    # Resolve role
    role_name = str(col_val(COL_ROLE) or "employee").strip()
    role_name_lower = role_name.lower()
    matched_role = role_map.get(role_name_lower)
    if not matched_role:
        available = ", ".join(sorted(role_map.keys()))
        return f"Row {row_num} ({full_name}): Role '{role_name}' not found. Available roles: {available}"

    # Find or create user
    user = (await db.execute(
        select(User).where(User.email == email).limit(1)
    )).scalar_one_or_none()

    if user:
        # Check if employee already exists for this user
        existing = (await db.execute(
            select(Employee).where(Employee.user_id == user.id).limit(1)
        )).scalar_one_or_none()
        if existing:
            return f"Row {row_num} ({full_name}): An employee record already exists for email {email}"
    else:
        # Create new user
        password = str(col_val(COL_PASSWORD) or DEFAULT_PASSWORD)
        if len(password) < 6:
            return f"Row {row_num} ({full_name}): Password must be at least 6 characters"

        # Resolve manager
        manager_id = None
        manager_email = col_val(COL_MANAGER_EMAIL)
        if manager_email:
            mgr_email_str = str(manager_email).strip()
            manager = (await db.execute(
                select(User).where(User.email == mgr_email_str).limit(1)
            )).scalar_one_or_none()
            if not manager:
                return f"Row {row_num} ({full_name}): Manager email '{mgr_email_str}' not found in system"
            manager_id = manager.id

        user = User(
            email=email,
            hashed_password=get_password_hash(password),
            full_name=full_name,
            is_active=True,
            manager_id=manager_id
        )
        user.roles = [matched_role]
        db.add(user)
        await db.flush()

    # Parse ESIC applicable flag
    esic_raw = col_val(COL_ESIC)
    esic_applicable = str(esic_raw).strip().upper() in ("Y", "YES", "TRUE", "1") if esic_raw else False

    # Parse employment type (defaults to permanent)
    emp_type_raw = col_val(COL_EMP_TYPE)
    employment_type = str(emp_type_raw).strip().lower() if emp_type_raw else "permanent"
    if employment_type not in ("permanent", "contractual", "advisor"):
        employment_type = "permanent"

    # Support old "Salary" column name as fallback
    salary_val = col_val(COL_SALARY, "Salary")

    # Parse joining date
    join_date_val = col_val(COL_JOIN_DATE)
    join_date = str(join_date_val) if join_date_val else str(date.today())

    # Create employee
    try:
        employee = Employee(
            user_id=user.id,
            employee_id=emp_id,
            department=dept,
            designation=desig,
            date_of_joining=join_date,
            salary=float(salary_val) if salary_val is not None else None,
            conveyance_allowance=float(col_val(COL_CA)) if col_val(COL_CA) is not None else None,  # noqa: E501
            hra=float(col_val(COL_HRA)) if col_val(COL_HRA) is not None else None,
            other_allowance=float(col_val(COL_OA)) if col_val(COL_OA) is not None else None,  # noqa: E501
            esic_applicable=esic_applicable,
            employment_type=employment_type,
            bank_account=str(col_val(COL_BANK)) if col_val(COL_BANK) is not None else None,  # noqa: E501
            pf_number=str(col_val(COL_PF)) if col_val(COL_PF) is not None else None,
            pan_number=str(col_val(COL_PAN)) if col_val(COL_PAN) is not None else None,  # noqa: E501
            notice_period_days=int(col_val(COL_NOTICE_PERIOD)) if col_val(COL_NOTICE_PERIOD) is not None else 30,  # noqa: E501
            status=EmployeeStatus.ACTIVE
        )
    except (ValueError, TypeError) as e:
        return f"Row {row_num} ({full_name}): Invalid data — {str(e)}"

    db.add(employee)
    await db.flush()

    await log_audit(
        db, current_user_id, "CREATE_BULK", "employee", str(employee.id),
        {"email": email, "employee_id": emp_id, "full_name": full_name,
         "role": role_name}, request
    )
    return None


@router.post("/employees/bulk-upload")
async def bulk_upload_employees(
    *,
    db: deps.DBDep,
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    """Upload multiple employees via Excel file."""
    if not file.filename or not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file format. Please upload an Excel file."
        )

    try:
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to read Excel file: {str(e)}"
        )

    # Support old column name "User Email" as alias for "Email"
    if "User Email" in df.columns and COL_EMAIL not in df.columns:
        df.rename(columns={"User Email": COL_EMAIL}, inplace=True)

    required_cols = [COL_FULL_NAME, COL_EMAIL, COL_EMP_ID, COL_DEPT, COL_DESIG]
    for col in required_cols:
        if col not in df.columns:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required column: {col}"
            )

    # Build role lookup map (lowercase name -> Role object)
    all_roles = (await db.execute(select(Role))).scalars().all()
    role_map = {r.name.lower(): r for r in all_roles}
    if "employee" not in role_map:
        raise HTTPException(status_code=500, detail="Employee role not configured in system")

    results = {"success": 0, "failed": 0, "errors": []}

    for index, row in df.iterrows():
        try:
            error = await process_employee_row(
                db, index, row, current_user.id, request, role_map
            )
            if error:
                results["failed"] += 1
                results["errors"].append(error)
            else:
                results["success"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"Row {index+2}: {str(e)}")

    await db.commit()
    return results


@router.get("/departments")
async def list_departments_for_hr(
    *,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([HR_READ])),
) -> Any:
    """Read-only department list for HR pickers and filters.

    The admin variant at `/admin/departments` is gated by ADMIN_ACCESS,
    which HR users don't have — so the Employee Management filter would
    silently come back empty for them. This alias reuses the same table
    behind the HR_READ permission. Writes still go through admin.
    """
    rows = (await db.execute(
        select(Department).order_by(Department.name)
    )).scalars().all()
    return [
        {"id": d.id, "name": d.name, "description": d.description}
        for d in rows
    ]


@router.get("/employees")
async def get_employees(
    *,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([HR_READ])),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=500),
    department: Optional[str] = None,
    role: Optional[str] = None,
    employee_status: Optional[str] = Query(None, alias="status"),
    employment_type: Optional[str] = None,
    search: Optional[str] = None
) -> Any:
    """List employees with pagination and filters.

    Returns each row through `_serialize_employee_with_manager` so the HR
    table can show the reporting line. The pydantic `EmployeeList` model
    strips the injected `manager` block, so we hand back dicts directly.
    """
    query = select(Employee).options(
        selectinload(Employee.user).selectinload(User.roles)
        .selectinload(Role.permissions),
        selectinload(Employee.user).selectinload(User.manager),
    )

    if department:
        query = query.where(Employee.department == department)
    if employee_status:
        query = query.where(Employee.status == employee_status)
    if employment_type:
        query = query.where(Employee.employment_type == employment_type)
    if role:
        query = query.join(Employee.user).join(User.roles).where(
            Role.name == role
        )
    if search:
        query = query.join(Employee.user).where(
            or_(
                User.full_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
                Employee.employee_id.ilike(f"%{search}%")
            )
        )

    total = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total_count = total.scalar() or 0

    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    employees = result.scalars().all()

    has_payroll = check_payroll_permission(current_user)
    items: list[Dict[str, Any]] = []
    for emp in employees:
        if has_payroll:
            items.append(_serialize_employee_with_manager(emp))
        else:
            # Strip payroll-only fields to keep parity with EmployeeRead.
            base = EmployeeRead.model_validate(emp).model_dump(mode="json")
            mgr = emp.user.manager if emp.user else None
            base.setdefault("user", {})["manager"] = (
                {"id": mgr.id, "full_name": mgr.full_name, "email": mgr.email}
                if mgr else None
            )
            items.append(base)

    return {"items": items, "total": total_count}


@router.post("/employees", response_model=EmployeeHRRead)
async def create_employee(
    *,
    db: deps.DBDep,
    request: Request,
    obj_in: EmployeeCreate,
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    """Create new employee record."""
    user = (await db.execute(
        select(User).where(User.id == obj_in.user_id).limit(1)
    )).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    emp_exists = (await db.execute(
        select(Employee).where(Employee.user_id == obj_in.user_id).limit(1)
    )).scalars().first()
    if emp_exists:
        raise HTTPException(
            status_code=400,
            detail="Employee record already exists for this user"
        )
    
    id_exists = (await db.execute(
        select(Employee).where(Employee.employee_id == obj_in.employee_id).limit(1)
    )).scalars().first()
    if id_exists:
        raise HTTPException(
            status_code=400, detail="Employee ID already taken"
        )

    await _require_known_department(db, obj_in.department)

    data = obj_in.model_dump(exclude={"manager_id"})
    db_obj = Employee(**data)

    if obj_in.manager_id is not None:
        user.manager_id = obj_in.manager_id
        db.add(user)

    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    
    await log_audit(
        db, current_user.id, "CREATE", "employee", str(db_obj.id),
        obj_in.model_dump(mode="json"), request
    )
    
    result = await db.execute(
        select(Employee).where(Employee.id == db_obj.id).options(
            selectinload(Employee.user)
            .selectinload(User.roles)
            .selectinload(Role.permissions)
        ).limit(1)
    )
    return result.scalars().first()


@router.post("/employees/with-user", response_model=EmployeeHRRead)
async def create_employee_with_user(
    *,
    db: deps.DBDep,
    request: Request,
    obj_in: EmployeeCreateWithUser,
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    """Create a new login user (Employee role) and the linked employee record."""

    # Ensure email is unique.
    existing = (await db.execute(select(User).where(User.email == obj_in.user.email).limit(1))).scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    # Ensure employee_id is unique.
    id_exists = (await db.execute(select(Employee).where(Employee.employee_id == obj_in.employee_id).limit(1))).scalar_one_or_none()
    if id_exists:
        raise HTTPException(status_code=400, detail="Employee ID already taken")

    await _require_known_department(db, obj_in.department)

    employee_role_res = await db.execute(select(Role).where(Role.name == "Employee").limit(1))
    employee_role = employee_role_res.scalar_one_or_none()
    if not employee_role:
        raise HTTPException(status_code=500, detail="Employee role not configured")

    new_user = User(
        email=obj_in.user.email,
        hashed_password=get_password_hash(obj_in.user.password),
        full_name=obj_in.user.full_name,
        is_active=True,
        manager_id=obj_in.user.manager_id
    )
    new_user.roles = [employee_role]
    db.add(new_user)
    await db.flush()

    emp_payload = obj_in.model_dump(mode="json", exclude={"user"})
    db_obj = Employee(**emp_payload, user_id=new_user.id)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)

    await log_audit(
        db,
        current_user.id,
        "CREATE",
        "employee",
        str(db_obj.id),
        {
            **emp_payload,
            "user": {
                "email": obj_in.user.email,
                "full_name": obj_in.user.full_name,
            },
        },
        request,
    )

    result = await db.execute(
        select(Employee).where(Employee.id == db_obj.id).options(
            selectinload(Employee.user)
            .selectinload(User.roles)
            .selectinload(Role.permissions)
        ).limit(1)
    )
    return result.scalars().first()


@router.get("/employees/me")
async def get_my_employee_profile(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
) -> Any:
    """Get the current user's employee profile."""
    query = select(Employee).where(Employee.user_id == current_user.id).options(
        selectinload(Employee.user).selectinload(User.roles)
        .selectinload(Role.permissions),
        selectinload(Employee.user).selectinload(User.manager),
    ).limit(1)
    emp = (await db.execute(query)).scalars().first()
    if emp:
        return _serialize_employee_with_manager(emp)
    return {
        "id": None, "user_id": current_user.id,
        "employee_id": "", "department": "", "designation": "",
        "date_of_joining": None, "status": "active",
        "kra": current_user.kra, "phone": current_user.phone,
        "location": current_user.location, "notice_period_days": 0,
        "user": {"id": current_user.id, "email": current_user.email,
                 "full_name": current_user.full_name, "is_active": current_user.is_active,
                 "phone": current_user.phone, "location": current_user.location,
                 "roles": []},
    }


@router.patch("/employees/me/profile")
async def update_my_profile(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    body: EmployeeProfileUpdate,
) -> Any:
    """Update the current user's profile (name, phone, location).

    Single source of truth: phone/location live on Employee when an employee
    record exists; otherwise they fall back to User (admin-only case). The
    full_name always lives on User since it's the auth identity.
    """
    # full_name is always on the User row.
    if body.full_name is not None:
        current_user.full_name = body.full_name
        db.add(current_user)

    emp_query = select(Employee).where(Employee.user_id == current_user.id).limit(1)
    emp = (await db.execute(emp_query)).scalars().first()
    if emp:
        # Canonical: phone/location live on the Employee row.
        if body.phone is not None:
            emp.phone = body.phone
        if body.location is not None:
            emp.location = body.location
        db.add(emp)
    else:
        # Fallback for users without an employee record (admins).
        if body.phone is not None:
            current_user.phone = body.phone
        if body.location is not None:
            current_user.location = body.location
        db.add(current_user)

    await db.commit()

    return {
        "status": "success",
        "user_id": current_user.id,
        "full_name": current_user.full_name,
        "phone": (emp.phone if emp else current_user.phone),
        "location": (emp.location if emp else current_user.location),
    }


class KRAUpdateBody(BaseModel):
    kra: str = ""

@router.patch("/employees/me/kra")
async def update_my_kra(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    body: KRAUpdateBody,
) -> Any:
    """Update the current user's KRA (Key Result Areas).

    Single source of truth: KRA lives on Employee when an employee record
    exists; otherwise it falls back to User (admin-only case).
    """
    kra_text = body.kra

    query = select(Employee).where(Employee.user_id == current_user.id).options(
        selectinload(Employee.user).selectinload(User.roles)
        .selectinload(Role.permissions),
        selectinload(Employee.user).selectinload(User.manager),
    ).limit(1)
    emp = (await db.execute(query)).scalars().first()
    if emp:
        emp.kra = kra_text
        db.add(emp)
    else:
        current_user.kra = kra_text
        db.add(current_user)

    await db.commit()

    if emp:
        await db.refresh(emp)
        return _serialize_employee_with_manager(emp)

    await db.refresh(current_user)
    return {
        "id": None, "user_id": current_user.id,
        "employee_id": "", "department": "", "designation": "",
        "date_of_joining": None, "status": "active",
        "kra": current_user.kra, "phone": current_user.phone,
        "location": current_user.location, "notice_period_days": 0,
        "user": {"id": current_user.id, "email": current_user.email,
                 "full_name": current_user.full_name, "is_active": current_user.is_active,
                 "phone": current_user.phone, "location": current_user.location,
                 "roles": []},
    }


def _avatar_dir() -> Path:
    return Path(settings.AVATAR_DIR)


@router.post("/employees/me/avatar")
async def upload_my_avatar(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    file: UploadFile = File(...),
) -> Any:
    """Upload/replace the current user's profile photo."""
    allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    content_type = file.content_type or ""
    if content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, WebP or GIF images are allowed")

    avatar_dir = _avatar_dir()
    avatar_dir.mkdir(parents=True, exist_ok=True)

    # Remove old avatar if it exists
    if current_user.avatar_url:
        old_file = avatar_dir / current_user.avatar_url
        old_file.unlink(missing_ok=True)

    ext = content_type.split("/")[-1]
    stored_name = f"{uuid4().hex}.{ext}"
    dest = avatar_dir / stored_name

    max_bytes = int(settings.AVATAR_MAX_BYTES)
    total = 0
    with dest.open("wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Image exceeds maximum size (5MB)")
            f.write(chunk)

    current_user.avatar_url = stored_name
    db.add(current_user)
    await db.commit()
    return {"avatar_url": stored_name}


@router.get("/employees/me/avatar")
async def get_my_avatar(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
) -> Any:
    """Serve the current user's profile photo."""
    if not current_user.avatar_url:
        raise HTTPException(status_code=404, detail="No avatar uploaded")
    file_path = _avatar_dir() / current_user.avatar_url
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Avatar file not found")
    ext = file_path.suffix.lstrip(".")
    media_type = f"image/{ext}" if ext else "application/octet-stream"
    return FileResponse(path=str(file_path), media_type=media_type)


@router.get("/employees/{emp_id}")
async def get_employee(
    *,
    db: deps.DBDep,
    emp_id: int,
    current_user: User = Depends(deps.check_permissions([HR_READ]))
) -> Any:
    """Get employee details. Returns the manager block under `user`."""
    query = select(Employee).where(Employee.id == emp_id).options(
        selectinload(Employee.user).selectinload(User.roles)
        .selectinload(Role.permissions),
        selectinload(Employee.user).selectinload(User.manager),
    )
    emp = (await db.execute(query)).scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail=EMP_NOT_FOUND)

    if check_payroll_permission(current_user):
        return _serialize_employee_with_manager(emp)
    base = EmployeeRead.model_validate(emp).model_dump(mode="json")
    mgr = emp.user.manager if emp.user else None
    base.setdefault("user", {})["manager"] = (
        {"id": mgr.id, "full_name": mgr.full_name, "email": mgr.email}
        if mgr else None
    )
    return base


@router.patch("/employees/{emp_id}", response_model=EmployeeHRRead)
async def update_employee(
    *,
    db: deps.DBDep,
    request: Request,
    emp_id: int,
    obj_in: EmployeeUpdate,
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    """Update employee record."""
    query = select(Employee).where(Employee.id == emp_id).options(
        selectinload(Employee.user)
        .selectinload(User.roles)
        .selectinload(Role.permissions)
    ).limit(1)
    db_obj = (await db.execute(query)).scalars().first()
    if not db_obj:
        raise HTTPException(status_code=404, detail=EMP_NOT_FOUND)
    
    update_data = obj_in.model_dump(exclude_unset=True)
    payroll_fields = {"salary", "bank_account", "pf_number", "pan_number"}

    if any(field in update_data for field in payroll_fields):
        if not check_payroll_permission(current_user, "write"):
            raise HTTPException(
                status_code=403,
                detail="Not enough permissions to update payroll fields"
            )

    if "department" in update_data:
        await _require_known_department(db, update_data["department"])

    for field, value in update_data.items():
        if field == "manager_id" and db_obj.user:
            db_obj.user.manager_id = value
            db.add(db_obj.user)
        else:
            setattr(db_obj, field, value)
    
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    
    await log_audit(
        db,
        current_user.id,
        "UPDATE",
        "employee",
        str(emp_id),
        obj_in.model_dump(mode="json", exclude_unset=True),
        request,
    )
    result = await db.execute(
        select(Employee).where(Employee.id == emp_id).options(
            selectinload(Employee.user)
            .selectinload(User.roles)
            .selectinload(Role.permissions)
        ).limit(1)
    )
    return result.scalars().first()


@router.post("/employees/{emp_id}/salary-calculate")
async def calculate_employee_salary(
    *,
    db: deps.DBDep,
    emp_id: int,
    paid_days: int = Query(..., ge=0, le=31),
    days_in_month: int = Query(31, ge=28, le=31),
    guest_house: float = Query(0, ge=0),
    tds: float = Query(0, ge=0),
    current_user: User = Depends(deps.check_permissions([HR_READ])),
) -> Any:
    """Calculate salary breakdown for an employee given paid_days."""
    query = select(Employee).where(Employee.id == emp_id).limit(1)
    emp = (await db.execute(query)).scalars().first()
    if not emp:
        raise HTTPException(status_code=404, detail=EMP_NOT_FOUND)

    basic = emp.salary or 0.0
    ca = emp.conveyance_allowance if emp.conveyance_allowance is not None else round(basic * 0.30)
    hra = emp.hra if emp.hra is not None else round(basic * 0.50)
    other = emp.other_allowance if emp.other_allowance is not None else round(basic * 0.20)
    esic = emp.esic_applicable or False

    result = calculate_salary(
        basic_salary=basic,
        conveyance_allowance=ca,
        hra=hra,
        other_allowance=other,
        esic_applicable=esic,
        paid_days=paid_days,
        days_in_month=days_in_month,
        guest_house=guest_house,
        tds=tds,
    )
    return result


@router.post("/salary/preview")
async def preview_salary_calculation(
    *,
    basic_salary: float = Query(..., ge=0),
    conveyance_allowance: float = Query(0, ge=0),
    hra: float = Query(0, ge=0),
    other_allowance: float = Query(0, ge=0),
    esic_applicable: bool = Query(False),
    paid_days: int = Query(31, ge=0, le=31),
    days_in_month: int = Query(31, ge=28, le=31),
    guest_house: float = Query(0, ge=0),
    tds: float = Query(0, ge=0),
    current_user: User = Depends(deps.check_permissions([HR_READ])),
) -> Any:
    """Preview salary calculation without saving. Accepts salary components in the body."""
    result = calculate_salary(
        basic_salary=basic_salary,
        conveyance_allowance=conveyance_allowance,
        hra=hra,
        other_allowance=other_allowance,
        esic_applicable=esic_applicable,
        paid_days=paid_days,
        days_in_month=days_in_month,
        guest_house=guest_house,
        tds=tds,
    )
    return result


@router.post("/employees/{emp_id}/deactivate", response_model=EmployeeRead)
async def deactivate_employee(
    *,
    db: deps.DBDep,
    request: Request,
    emp_id: int,
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    """Deactivate employee record."""
    query = select(Employee).where(Employee.id == emp_id).options(
        selectinload(Employee.user)
        .selectinload(User.roles)
        .selectinload(Role.permissions)
    ).limit(1)
    db_obj = (await db.execute(query)).scalars().first()
    if not db_obj:
        raise HTTPException(status_code=404, detail=EMP_NOT_FOUND)
    
    db_obj.status = EmployeeStatus.INACTIVE
    # Also disable user login
    db_obj.user.is_active = False
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)

    await log_audit(
        db, current_user.id, "DEACTIVATE", "employee", str(emp_id),
        {"status": EmployeeStatus.INACTIVE}, request
    )
    result = await db.execute(
        select(Employee).where(Employee.id == emp_id).options(
            selectinload(Employee.user)
            .selectinload(User.roles)
            .selectinload(Role.permissions)
        ).limit(1)
    )
    return result.scalars().first()


@router.post(
    "/employees/{emp_id}/reactivate",
    response_model=EmployeeRead
)
async def reactivate_employee(
    *,
    db: deps.DBDep,
    request: Request,
    emp_id: int,
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    """Reactivate a deactivated employee."""
    query = select(Employee).where(Employee.id == emp_id).options(
        selectinload(Employee.user)
        .selectinload(User.roles)
        .selectinload(Role.permissions)
    ).limit(1)
    db_obj = (await db.execute(query)).scalars().first()
    if not db_obj:
        raise HTTPException(status_code=404, detail=EMP_NOT_FOUND)

    db_obj.status = EmployeeStatus.ACTIVE
    db_obj.user.is_active = True
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)

    await log_audit(
        db, current_user.id, "REACTIVATE", "employee",
        str(emp_id), {"status": EmployeeStatus.ACTIVE}, request
    )
    result = await db.execute(
        select(Employee).where(Employee.id == emp_id).options(
            selectinload(Employee.user)
            .selectinload(User.roles)
            .selectinload(Role.permissions)
        ).limit(1)
    )
    return result.scalars().first()


async def _gather_employee_delete_blockers(db, user_id: int) -> list[dict]:
    """Return work-state reasons that prevent deleting this employee.

    A blocker is anything that would silently lose project, sales, or
    delivery context if we removed the user — active project memberships
    (PM/employee), open BD leads they own, or open task assignments on
    active projects.
    """
    blockers: list[dict] = []

    pm_rows = (await db.execute(
        select(ProjectMember).join(Project, ProjectMember.project_id == Project.id)
        .options(selectinload(ProjectMember.project))
        .where(ProjectMember.user_id == user_id, Project.status == "active")
    )).scalars().all()
    for pm in pm_rows:
        blockers.append({
            "type": "project_member",
            "role": pm.role,
            "project_id": pm.project_id,
            "project_name": pm.project.name if pm.project else f"Project {pm.project_id}",
            "project_code": pm.project.code if pm.project else None,
        })

    open_lead_stages = [s for s in LeadStage if s not in (LeadStage.WON, LeadStage.LOST)]
    open_leads = (await db.execute(
        select(Lead).where(
            Lead.owner_user_id == user_id,
            Lead.stage.in_(open_lead_stages),
        )
    )).scalars().all()
    for ld in open_leads:
        stage_val = ld.stage.value if hasattr(ld.stage, "value") else str(ld.stage)
        blockers.append({
            "type": "lead_owner",
            "lead_id": ld.lead_id,
            "title": ld.title,
            "stage": stage_val,
        })

    closed_task_states = ["done", "closed", "cancelled", "completed"]
    open_tasks = (await db.execute(
        select(Task).join(Project, Task.project_id == Project.id)
        .options(selectinload(Task.project))
        .where(
            Task.assignee_id == user_id,
            Project.status == "active",
            Task.status.notin_(closed_task_states),
        )
    )).scalars().all()
    for tk in open_tasks:
        blockers.append({
            "type": "task_assignee",
            "task_id": tk.id,
            "title": tk.title,
            "project_name": tk.project.name if tk.project else None,
            "status": tk.status,
        })

    return blockers


@router.get("/employees/{emp_id}/delete-blockers")
async def get_employee_delete_blockers(
    *,
    db: deps.DBDep,
    emp_id: int,
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    """Preview what currently prevents this employee from being deleted.

    Used by the HR confirm dialog so the user can see — before clicking
    Delete — that the person is on N active projects or owns M open leads.
    """
    emp = (await db.execute(
        select(Employee).where(Employee.id == emp_id).options(selectinload(Employee.user))
    )).scalars().first()
    if not emp:
        raise HTTPException(status_code=404, detail=EMP_NOT_FOUND)
    if not emp.user_id:
        return {"blockers": [], "deletable": True}

    blockers = await _gather_employee_delete_blockers(db, emp.user_id)
    return {"blockers": blockers, "deletable": len(blockers) == 0}


@router.delete("/employees/{emp_id}")
async def delete_employee(
    *,
    db: deps.DBDep,
    request: Request,
    emp_id: int,
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    """Permanently delete an employee and their user account.

    Refuses to delete employees that still own work — open leads, active
    project memberships, or assigned tasks on active projects. HR must
    reassign or close those first to avoid silent data loss.
    """
    query = select(Employee).where(
        Employee.id == emp_id
    ).options(selectinload(Employee.user)).limit(1)
    db_obj = (await db.execute(query)).scalars().first()
    if not db_obj:
        raise HTTPException(status_code=404, detail=EMP_NOT_FOUND)

    user = db_obj.user
    emp_id_str = db_obj.employee_id
    email = user.email

    blockers = await _gather_employee_delete_blockers(db, user.id)
    if blockers:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"Cannot delete {user.full_name}: still tied to active work. "
                    "Reassign or close the items below, then try again. "
                    "You can also deactivate instead — that disables login but "
                    "preserves project history."
                ),
                "blockers": blockers,
            },
        )

    await log_audit(
        db, current_user.id, "DELETE", "employee",
        str(emp_id),
        {"employee_id": emp_id_str, "email": email},
        request
    )

    await db.delete(db_obj)
    await db.delete(user)
    await db.commit()

    # DB rows are gone via cascade; clean up the on-disk document folder so
    # we don't leave orphan files. Best-effort — if it fails we still return
    # success because the canonical state (the DB) is correct.
    docs_dir = _emp_docs_dir() / str(emp_id)
    if docs_dir.exists():
        import shutil
        try:
            shutil.rmtree(docs_dir)
        except OSError:
            pass

    return {"detail": "Employee and user deleted successfully"}


# ─── Reassignment: change PM, task assignee, lead owner ──────


class ReassignBody(BaseModel):
    new_user_id: int


async def _resolve_user_or_404(db, user_id: int) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user


def _user_label(u: Optional[User]) -> Optional[str]:
    return u.full_name if u else None


@router.patch("/projects/{project_id}/manager")
async def reassign_project_manager(
    *,
    db: deps.DBDep,
    request: Request,
    project_id: int,
    body: ReassignBody,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """Reassign a project's PM (the ProjectMember with role='manager').

    If the project has no manager yet, this just adds one. If the new user
    is already a member of the project, their existing row is promoted to
    manager and the previous manager's row is demoted to 'member' so the
    history of involvement isn't lost.
    """
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    new_user = await _resolve_user_or_404(db, body.new_user_id)

    existing_manager = (await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.role == "manager",
        ).limit(1)
    )).scalars().first()

    new_user_membership = (await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == new_user.id,
        ).limit(1)
    )).scalars().first()

    old_user_id = existing_manager.user_id if existing_manager else None
    old_user = await db.get(User, old_user_id) if old_user_id else None

    if existing_manager and existing_manager.user_id == new_user.id:
        return {"detail": "Already the manager", "project_id": project_id}

    if existing_manager:
        # Demote the previous PM to 'member' so we preserve the involvement
        # record. The full transition is captured in the audit log too.
        existing_manager.role = "member"
        db.add(existing_manager)

    if new_user_membership:
        new_user_membership.role = "manager"
        db.add(new_user_membership)
    else:
        db.add(ProjectMember(
            project_id=project_id,
            user_id=new_user.id,
            role="manager",
        ))

    await log_audit(
        db, current_user.id, "REASSIGN_PM", "project",
        str(project_id),
        {
            "project_name": project.name,
            "project_code": project.code,
            "from_user_id": old_user_id,
            "from_user_name": _user_label(old_user),
            "to_user_id": new_user.id,
            "to_user_name": new_user.full_name,
        },
        request,
    )
    await db.commit()
    return {
        "detail": "Project manager reassigned",
        "project_id": project_id,
        "from_user_id": old_user_id,
        "to_user_id": new_user.id,
    }


@router.patch("/tasks/{task_id}/assignee")
async def reassign_task_assignee(
    *,
    db: deps.DBDep,
    request: Request,
    task_id: int,
    body: ReassignBody,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """Reassign a task to a different employee. Audit-logged."""
    task = (await db.execute(
        select(Task).where(Task.id == task_id).options(selectinload(Task.project))
    )).scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    new_user = await _resolve_user_or_404(db, body.new_user_id)
    old_user_id = task.assignee_id
    old_user = await db.get(User, old_user_id) if old_user_id else None

    if old_user_id == new_user.id:
        return {"detail": "Already assigned to this user", "task_id": task_id}

    task.assignee_id = new_user.id
    db.add(task)

    await log_audit(
        db, current_user.id, "REASSIGN_TASK", "task",
        str(task_id),
        {
            "task_title": task.title,
            "project_id": task.project_id,
            "project_name": task.project.name if task.project else None,
            "from_user_id": old_user_id,
            "from_user_name": _user_label(old_user),
            "to_user_id": new_user.id,
            "to_user_name": new_user.full_name,
        },
        request,
    )
    await db.commit()
    return {
        "detail": "Task reassigned",
        "task_id": task_id,
        "from_user_id": old_user_id,
        "to_user_id": new_user.id,
    }


@router.patch("/leads/{lead_id}/owner")
async def reassign_lead_owner(
    *,
    db: deps.DBDep,
    request: Request,
    lead_id: int,
    body: ReassignBody,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """Reassign a BD lead to a different owner. Audit-logged."""
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    new_user = await _resolve_user_or_404(db, body.new_user_id)
    old_user_id = lead.owner_user_id
    old_user = await db.get(User, old_user_id) if old_user_id else None

    if old_user_id == new_user.id:
        return {"detail": "Already owned by this user", "lead_id": lead_id}

    lead.owner_user_id = new_user.id
    db.add(lead)

    await log_audit(
        db, current_user.id, "REASSIGN_LEAD", "lead",
        str(lead_id),
        {
            "lead_id": lead.lead_id,
            "title": lead.title,
            "from_user_id": old_user_id,
            "from_user_name": _user_label(old_user),
            "to_user_id": new_user.id,
            "to_user_name": new_user.full_name,
        },
        request,
    )
    await db.commit()
    return {
        "detail": "Lead owner reassigned",
        "lead_id": lead_id,
        "from_user_id": old_user_id,
        "to_user_id": new_user.id,
    }


class TransferWorkBody(BaseModel):
    to_user_id: int


@router.post("/employees/{emp_id}/transfer-work")
async def transfer_employee_work(
    *,
    db: deps.DBDep,
    request: Request,
    emp_id: int,
    body: TransferWorkBody,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """Bulk-reassign all of this employee's open work to another user.

    Used as the cleanup step before deleting an employee — covers active
    project memberships (PM and otherwise), open BD leads they own, and
    open task assignments on active projects. Each row produces its own
    audit log entry so the previous owner is preserved.
    """
    emp = (await db.execute(
        select(Employee).where(Employee.id == emp_id).options(selectinload(Employee.user))
    )).scalars().first()
    if not emp or not emp.user_id:
        raise HTTPException(status_code=404, detail=EMP_NOT_FOUND)

    if emp.user_id == body.to_user_id:
        raise HTTPException(status_code=400, detail="Cannot transfer to the same user")

    new_user = await _resolve_user_or_404(db, body.to_user_id)
    old_user = emp.user

    summary = {"projects": 0, "leads": 0, "tasks": 0}

    pm_rows = (await db.execute(
        select(ProjectMember).join(Project, ProjectMember.project_id == Project.id)
        .options(selectinload(ProjectMember.project))
        .where(ProjectMember.user_id == emp.user_id, Project.status == "active")
    )).scalars().all()
    for pm in pm_rows:
        # If the new user is already a member of this project, just remove
        # the old row to avoid a duplicate; if the old row was manager,
        # promote the new user's row to manager so the project keeps its PM.
        existing_new = (await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == pm.project_id,
                ProjectMember.user_id == new_user.id,
            ).limit(1)
        )).scalars().first()
        old_role = pm.role
        if existing_new:
            if old_role == "manager" and existing_new.role != "manager":
                existing_new.role = "manager"
                db.add(existing_new)
            await db.delete(pm)
        else:
            pm.user_id = new_user.id
            db.add(pm)
        summary["projects"] += 1
        await log_audit(
            db, current_user.id,
            "REASSIGN_PM" if old_role == "manager" else "REASSIGN_PROJECT_MEMBER",
            "project",
            str(pm.project_id),
            {
                "project_name": pm.project.name if pm.project else None,
                "role": old_role,
                "from_user_id": emp.user_id,
                "from_user_name": old_user.full_name if old_user else None,
                "to_user_id": new_user.id,
                "to_user_name": new_user.full_name,
                "context": "transfer_work",
            },
            request,
        )

    open_lead_stages = [s for s in LeadStage if s not in (LeadStage.WON, LeadStage.LOST)]
    open_leads = (await db.execute(
        select(Lead).where(
            Lead.owner_user_id == emp.user_id,
            Lead.stage.in_(open_lead_stages),
        )
    )).scalars().all()
    for ld in open_leads:
        ld.owner_user_id = new_user.id
        db.add(ld)
        summary["leads"] += 1
        await log_audit(
            db, current_user.id, "REASSIGN_LEAD", "lead",
            str(ld.id),
            {
                "lead_id": ld.lead_id,
                "title": ld.title,
                "from_user_id": emp.user_id,
                "from_user_name": old_user.full_name if old_user else None,
                "to_user_id": new_user.id,
                "to_user_name": new_user.full_name,
                "context": "transfer_work",
            },
            request,
        )

    closed_task_states = ["done", "closed", "cancelled", "completed"]
    open_tasks = (await db.execute(
        select(Task).join(Project, Task.project_id == Project.id)
        .options(selectinload(Task.project))
        .where(
            Task.assignee_id == emp.user_id,
            Project.status == "active",
            Task.status.notin_(closed_task_states),
        )
    )).scalars().all()
    for tk in open_tasks:
        tk.assignee_id = new_user.id
        db.add(tk)
        summary["tasks"] += 1
        await log_audit(
            db, current_user.id, "REASSIGN_TASK", "task",
            str(tk.id),
            {
                "task_title": tk.title,
                "project_id": tk.project_id,
                "project_name": tk.project.name if tk.project else None,
                "from_user_id": emp.user_id,
                "from_user_name": old_user.full_name if old_user else None,
                "to_user_id": new_user.id,
                "to_user_name": new_user.full_name,
                "context": "transfer_work",
            },
            request,
        )

    await db.commit()
    return {
        "detail": "Work transferred",
        "from_user_id": emp.user_id,
        "to_user_id": new_user.id,
        "summary": summary,
    }


ATTENDANCE_CORR_APPROVE = "attendance correction approve"


@router.post(
    "/attendance-corrections", response_model=AttendanceCorrectionRead
)
async def create_attendance_correction(
    *,
    db: deps.DBDep,
    request: Request,
    obj_in: AttendanceCorrectionCreate,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    """Submit a request for attendance correction."""
    db_obj = AttendanceCorrectionRequest(
        **obj_in.model_dump(),
        user_id=current_user.id,
        created_by_id=current_user.id
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.get(
    "/attendance-corrections",
    response_model=List[AttendanceCorrectionRead]
)
async def list_attendance_corrections(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([HR_READ]))
) -> Any:
    """List all attendance correction requests for HR review."""
    result = await db.execute(select(AttendanceCorrectionRequest))
    return result.scalars().all()


@router.post(
    "/attendance-corrections/{corr_id}/action",
    response_model=AttendanceCorrectionRead
)
async def attendance_correction_action(
    *,
    db: deps.DBDep,
    request: Request,
    corr_id: int,
    obj_in: AttendanceCorrectionUpdate,
    current_user: User = Depends(
        deps.check_permissions([ATTENDANCE_CORR_APPROVE])
    )
) -> Any:
    """Approve or reject an attendance correction request."""
    corr = await db.get(AttendanceCorrectionRequest, corr_id)
    if not corr:
        raise HTTPException(
            status_code=404, detail="Correction request not found"
        )
    
    if corr.status != CorrectionStatus.SUBMITTED:
        raise HTTPException(
            status_code=400, detail="Request already processed"
        )
    
    corr.status = obj_in.status
    
    if obj_in.status == CorrectionStatus.APPROVED:
        # Update or create attendance record
        work_date_change = None
        if corr.attendance_id:
            attendance = await db.get(Attendance, corr.attendance_id)
            if attendance:
                attendance.mode = corr.requested_mode
                attendance.remarks = corr.requested_remarks
                # Apply optional work_date retag: this is the shift-aware
                # correction path. Old work_date is captured in the audit
                # log so HR can undo if needed.
                if corr.requested_work_date is not None and (
                    attendance.work_date != corr.requested_work_date
                ):
                    work_date_change = {
                        "from": attendance.work_date.isoformat()
                        if attendance.work_date else None,
                        "to": corr.requested_work_date.isoformat(),
                    }
                    attendance.work_date = corr.requested_work_date
                    # Clear the flag — HR has explicitly retagged this row.
                    attendance.attribution_flag = None
                db.add(attendance)
        else:
            # Create new attendance record
            from datetime import time, datetime, timezone
            captured_at = datetime.combine(
                corr.date, time(9, 0), tzinfo=timezone.utc
            )
            # New record: trust the work_date from the correction request if
            # provided; otherwise fall back to the calendar date in `date`.
            new_work_date = corr.requested_work_date or corr.date
            attendance = Attendance(
                user_id=corr.user_id,
                mode=corr.requested_mode,
                remarks=corr.requested_remarks,
                captured_at=captured_at,
                work_date=new_work_date,
            )
            db.add(attendance)
            await db.flush()
            corr.attendance_id = attendance.id

        audit_details = {"status": obj_in.status, "user_id": corr.user_id}
        if work_date_change is not None:
            audit_details["work_date_change"] = work_date_change
        await log_audit(
            db, current_user.id, "APPROVE_ATTENDANCE_CORRECTION",
            "attendance_correction", str(corr_id),
            audit_details,
            request
        )
    else:
        await log_audit(
            db, current_user.id, "REJECT_ATTENDANCE_CORRECTION",
            "attendance_correction", str(corr_id),
            {"status": obj_in.status, "user_id": corr.user_id},
            request
        )

    db.add(corr)
    await db.commit()
    await db.refresh(corr)
    return corr


# ---------------------------------------------------------------------------
# Section Q: HR/admin direct attendance edit + org time rules
# ---------------------------------------------------------------------------

ATTENDANCE_EDIT = "attendance edit"


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """MariaDB round-trips DATETIME columns as naive; treat them as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def _assert_attendance_editable(db, work_date: date) -> None:
    """Refuse edits once a payroll run has locked attendance for that
    month (user rule: 'edit should be before payroll is clicked')."""
    from app.models.payroll import PayrollRun, PayrollRunStatus

    run = (await db.execute(
        select(PayrollRun).where(
            PayrollRun.month == work_date.month,
            PayrollRun.year == work_date.year,
            PayrollRun.status != PayrollRunStatus.DRAFT,
        )
    )).scalars().first()
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


def _require_reason(reason: str) -> str:
    cleaned = (reason or "").strip()
    if len(cleaned) < 5:
        raise HTTPException(
            status_code=422,
            detail="A reason of at least 5 characters is required.",
        )
    return cleaned


@router.patch("/attendance/{attendance_id}", response_model=AttendanceRead)
async def edit_attendance_times(
    *,
    db: deps.DBDep,
    attendance_id: int,
    obj_in: AttendanceTimesEdit,
    request: Request,
    current_user: User = Depends(deps.check_permissions([ATTENDANCE_EDIT])),
) -> Any:
    """Directly edit punch-in / punch-out times (HR/admin).

    Employees forget to punch; HR fixes it here with a mandatory reason.
    Old and new values land in the audit log; the row is permanently
    badged via edited_by/edited_at.
    """
    reason = _require_reason(obj_in.reason)
    if obj_in.punch_in_time is None and obj_in.punch_out_time is None:
        raise HTTPException(
            status_code=422,
            detail="Provide punch_in_time and/or punch_out_time.",
        )

    att = await db.get(Attendance, attendance_id)
    if not att:
        raise HTTPException(status_code=404, detail="Attendance not found")

    await _assert_attendance_editable(db, att.work_date)

    new_in = _as_utc(obj_in.punch_in_time) or _as_utc(att.captured_at)
    new_out = (
        _as_utc(obj_in.punch_out_time)
        if obj_in.punch_out_time is not None
        else _as_utc(att.punch_out_time)
    )
    if new_out is not None and new_out <= new_in:
        raise HTTPException(
            status_code=422,
            detail="Punch-out must be after punch-in.",
        )

    old = {
        "punch_in_time": _as_utc(att.captured_at).isoformat(),
        "punch_out_time": (
            _as_utc(att.punch_out_time).isoformat()
            if att.punch_out_time else None
        ),
    }

    att.captured_at = new_in
    att.punch_out_time = new_out
    att.edited_by_id = current_user.id
    att.edited_at = datetime.now(timezone.utc)
    db.add(att)

    await log_audit(
        db, current_user.id, "EDIT_ATTENDANCE",
        "attendance", str(att.id),
        {
            "user_id": att.user_id,
            "work_date": att.work_date.isoformat(),
            "old": old,
            "new": {
                "punch_in_time": new_in.isoformat(),
                "punch_out_time": new_out.isoformat() if new_out else None,
            },
            "reason": reason,
        },
        request,
    )
    await db.commit()
    await db.refresh(att)
    return att


@router.post("/attendance/manual", response_model=AttendanceRead)
async def create_manual_attendance(
    *,
    db: deps.DBDep,
    obj_in: AttendanceManualCreate,
    request: Request,
    current_user: User = Depends(deps.check_permissions([ATTENDANCE_EDIT])),
) -> Any:
    """Create an attendance record for a day the employee never punched.

    Mode is 'manual'; geofence checks don't apply — HR is asserting the
    times. Refuses when a record already exists (edit that instead) or
    when payroll has locked the month.
    """
    reason = _require_reason(obj_in.reason)

    target = await db.get(User, obj_in.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    await _assert_attendance_editable(db, obj_in.work_date)

    punch_in = _as_utc(obj_in.punch_in_time)
    punch_out = _as_utc(obj_in.punch_out_time)
    if punch_out is not None and punch_out <= punch_in:
        raise HTTPException(
            status_code=422,
            detail="Punch-out must be after punch-in.",
        )

    existing = (await db.execute(
        select(Attendance).where(
            Attendance.user_id == obj_in.user_id,
            Attendance.work_date == obj_in.work_date,
        )
    )).scalars().first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=(
                "An attendance record already exists for "
                f"{obj_in.work_date.isoformat()} — edit it instead."
            ),
        )

    # Snapshot the employee's shift for correct late/early evaluation.
    from app.api.v1.endpoints.attendance import _effective_shift_on
    shift = await _effective_shift_on(db, obj_in.user_id, obj_in.work_date)

    att = Attendance(
        user_id=obj_in.user_id,
        mode="manual",
        captured_at=punch_in,
        punch_out_time=punch_out,
        work_date=obj_in.work_date,
        shift_template_id=shift.id if shift else None,
        attribution_flag=None if shift else "no_shift",
        edited_by_id=current_user.id,
        edited_at=datetime.now(timezone.utc),
    )
    db.add(att)
    await db.flush()

    await log_audit(
        db, current_user.id, "CREATE_MANUAL_ATTENDANCE",
        "attendance", str(att.id),
        {
            "user_id": obj_in.user_id,
            "work_date": obj_in.work_date.isoformat(),
            "punch_in_time": punch_in.isoformat(),
            "punch_out_time": punch_out.isoformat() if punch_out else None,
            "reason": reason,
        },
        request,
    )
    await db.commit()
    await db.refresh(att)
    return att


@router.get("/time-rules", response_model=TimeRulesRead)
async def get_time_rules_endpoint(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([ATTENDANCE_EDIT])),
) -> Any:
    from app.services.time_rules import get_time_rules
    return TimeRulesRead(rules=await get_time_rules(db))


@router.put("/time-rules", response_model=TimeRulesRead)
async def update_time_rules_endpoint(
    *,
    db: deps.DBDep,
    obj_in: TimeRulesUpdate,
    request: Request,
    current_user: User = Depends(deps.check_permissions([ATTENDANCE_EDIT])),
) -> Any:
    from app.services.time_rules import get_time_rules, set_time_rules

    before = await get_time_rules(db)
    after = await set_time_rules(db, obj_in.rules)
    changed = {
        k: {"from": before[k], "to": after[k]}
        for k in after if before.get(k) != after[k]
    }
    if changed:
        await log_audit(
            db, current_user.id, "UPDATE_TIME_RULES",
            "system_setting", "time-rules", {"changed": changed}, request,
        )
        await db.commit()
    return TimeRulesRead(rules=after)


# Holiday Calendar
@router.post("/holidays", response_model=HolidayCalendarRead)
async def create_holiday(
    *,
    db: deps.DBDep,
    obj_in: HolidayCalendarCreate,
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    db_obj = HolidayCalendar(**obj_in.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.get("/holidays", response_model=List[HolidayCalendarRead])
async def list_holidays(
    db: deps.DBDep,
    location: Optional[str] = None,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    query = select(HolidayCalendar)
    if location:
        query = query.where(
            or_(
                HolidayCalendar.location == location,
                HolidayCalendar.location == "All"
            )
        )
    result = await db.execute(query)
    return result.scalars().all()


@router.delete("/holidays/{holiday_id}")
async def delete_holiday(
    *,
    db: deps.DBDep,
    holiday_id: int,
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    obj = await db.get(HolidayCalendar, holiday_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Holiday not found")
    await db.delete(obj)
    await db.commit()
    return {"status": "success"}


@router.put("/holidays/{holiday_id}", response_model=HolidayCalendarRead)
async def update_holiday(
    *,
    db: deps.DBDep,
    holiday_id: int,
    obj_in: HolidayCalendarCreate,
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    obj = await db.get(HolidayCalendar, holiday_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Holiday not found")
    for field, value in obj_in.model_dump().items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


# Policy Documents
@router.post("/policies", response_model=PolicyDocumentRead)
async def create_policy(
    *,
    db: deps.DBDep,
    obj_in: PolicyDocumentCreate,
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    db_obj = PolicyDocument(**obj_in.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.get("/policies", response_model=List[PolicyDocumentRead])
async def list_policies(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    result = await db.execute(
        select(PolicyDocument).where(PolicyDocument.is_active)
    )
    return result.scalars().all()


@router.post(
    "/policies/{policy_id}/acknowledge",
    response_model=PolicyAcknowledgementRead
)
async def acknowledge_policy(
    *,
    db: deps.DBDep,
    policy_id: int,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    # Check if already acknowledged
    existing = await db.execute(
        select(PolicyAcknowledgement).where(
            PolicyAcknowledgement.policy_id == policy_id,
            PolicyAcknowledgement.user_id == current_user.id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already acknowledged")
    
    db_obj = PolicyAcknowledgement(
        policy_id=policy_id, user_id=current_user.id
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.get(
    "/policies/{policy_id}/acknowledgements",
    response_model=List[PolicyAcknowledgementRead]
)
async def list_policy_acknowledgements(
    db: deps.DBDep,
    policy_id: int,
    current_user: User = Depends(deps.check_permissions([HR_READ]))
) -> Any:
    result = await db.execute(
        select(PolicyAcknowledgement).where(
            PolicyAcknowledgement.policy_id == policy_id
        )
    )
    return result.scalars().all()


# ─── Policy Upload / Delete / Download ───────────────────────

def _policy_base_dir() -> Path:
    return Path(settings.POLICY_DOCUMENTS_DIR)


def _safe_policy_filename(name: str) -> str:
    name = (name or "").strip().replace("\x00", "")
    name = name.replace("/", "_").replace("\\", "_")
    if not name:
        return "policy.pdf"
    return name[:200]


@router.post("/policies/upload", response_model=PolicyDocumentRead)
async def upload_policy(
    *,
    db: deps.DBDep,
    file: UploadFile = File(...),
    title: str = Query(..., min_length=1),
    description: Optional[str] = Query(None),
    version: str = Query("1.0"),
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    """Upload a policy PDF document."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    base = _policy_base_dir()
    base.mkdir(parents=True, exist_ok=True)

    filename = _safe_policy_filename(file.filename)
    stored_name = f"{uuid4().hex}_{filename}"
    dest = base / stored_name

    max_bytes = int(settings.POLICY_DOCUMENT_MAX_BYTES)
    total = 0

    with dest.open("wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File exceeds maximum size (25MB)")
            f.write(chunk)

    db_obj = PolicyDocument(
        title=title,
        description=description or "",
        file_url=stored_name,
        version=version,
        is_active=True,
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.delete("/policies/{policy_id}")
async def delete_policy(
    *,
    db: deps.DBDep,
    policy_id: int,
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    """Delete a policy and its file."""
    policy = await db.get(PolicyDocument, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    # Delete file from disk
    file_path = _policy_base_dir() / policy.file_url
    if file_path.exists():
        file_path.unlink()

    await db.delete(policy)
    await db.commit()
    return {"status": "success"}


@router.get("/policies/{policy_id}/download")
async def download_policy(
    *,
    db: deps.DBDep,
    policy_id: int,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    """Download a policy PDF file."""
    policy = await db.get(PolicyDocument, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    file_path = _policy_base_dir() / policy.file_url
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Policy file not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=f"{policy.title}.pdf",
    )


# ─── Employee Letters ─────────────────────────────────────────

@router.get("/letters/types")
async def get_letter_types(
    current_user: User = Depends(deps.check_permissions([HR_READ]))
) -> Any:
    """Get available letter types."""
    return [
        {"key": k, "label": k.replace("_", " ").title()}
        for k in LETTER_GENERATORS.keys()
    ]


@router.get(
    "/letters",
    response_model=List[EmployeeLetterRead]
)
async def list_letters(
    db: deps.DBDep,
    employee_id: Optional[int] = None,
    current_user: User = Depends(deps.check_permissions([HR_READ]))
) -> Any:
    """List generated letters, optionally filtered by employee."""
    query = select(EmployeeLetter).order_by(
        EmployeeLetter.generated_at.desc()
    )
    if employee_id:
        query = query.where(
            EmployeeLetter.employee_id == employee_id
        )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/letters/generate")
async def generate_employee_letter(
    *,
    db: deps.DBDep,
    request: Request,
    body: LetterGenerateRequest,
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    """Generate a letter PDF for an employee."""
    if body.letter_type not in LETTER_GENERATORS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid letter type. Valid types: "
                   f"{', '.join(LETTER_GENERATORS.keys())}"
        )

    # Fetch employee with user info
    emp_query = select(Employee).where(
        Employee.id == body.employee_id
    ).options(selectinload(Employee.user))
    emp = (await db.execute(emp_query)).scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail=EMP_NOT_FOUND)

    # Generate reference number
    from datetime import datetime as dt_cls
    now = dt_cls.now(timezone.utc)
    year_str = now.strftime("%Y")
    count_q = select(func.count(EmployeeLetter.id)).where(
        EmployeeLetter.letter_type == body.letter_type
    )
    count = (await db.execute(count_q)).scalar() or 0
    ref_prefix = body.letter_type.upper().replace("_", "-")
    ref_number = f"UEIPL/{ref_prefix}/{year_str}/{count + 1:04d}"

    # Build template data from employee + overrides
    template_data = {
        "reference_number": ref_number,
        "date": (body.date or now.date()).isoformat(),
        "employee_name": emp.user.full_name if emp.user else "",
        "employee_code": emp.employee_id,
        "designation": body.designation or emp.designation,
        "department": body.department or emp.department,
        "joining_date": (
            body.joining_date or emp.date_of_joining
        ).isoformat() if (
            body.joining_date or emp.date_of_joining
        ) else "",
        "email": body.email or (
            emp.user.email if emp.user else ""
        ),
        "phone": body.phone or "",
        "ctc": body.ctc or "",
        "posting_location": body.posting_location or "Kolkata",
        "confirmation_date": (
            body.confirmation_date.isoformat()
            if body.confirmation_date else ""
        ),
        "last_working_date": (
            body.last_working_date.isoformat()
            if body.last_working_date else ""
        ),
        "resignation_date": (
            body.resignation_date.isoformat()
            if body.resignation_date else ""
        ),
        "relieving_date": (
            body.relieving_date.isoformat()
            if body.relieving_date else ""
        ),
        "cessation_cause": body.cessation_cause or "Resignation",
        "performance_rating": (
            body.performance_rating or "Satisfactory"
        ),
    }

    # Generate PDF
    pdf_bytes = generate_letter(body.letter_type, template_data)

    # Save record
    letter_record = EmployeeLetter(
        employee_id=body.employee_id,
        letter_type=body.letter_type,
        reference_number=ref_number,
        generated_by_id=current_user.id,
        template_data=json.dumps(template_data),
        status="generated",
    )
    db.add(letter_record)
    await db.commit()
    await db.refresh(letter_record)

    await log_audit(
        db, current_user.id, "GENERATE_LETTER",
        "employee_letter", str(letter_record.id),
        {
            "letter_type": body.letter_type,
            "employee_id": body.employee_id,
            "ref": ref_number,
        },
        request,
    )

    # Return PDF as streaming response
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ref_number.replace("/", "_")}.pdf"'
            )
        },
    )


@router.get("/letters/{letter_id}/download")
async def download_letter(
    *,
    db: deps.DBDep,
    letter_id: int,
    current_user: User = Depends(deps.check_permissions([HR_READ]))
) -> Any:
    """Re-generate and download a previously generated letter."""
    letter = await db.get(EmployeeLetter, letter_id)
    if not letter:
        raise HTTPException(
            status_code=404, detail="Letter not found"
        )

    template_data = json.loads(letter.template_data or "{}")
    pdf_bytes = generate_letter(letter.letter_type, template_data)

    ref = letter.reference_number or f"letter_{letter_id}"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ref.replace("/", "_")}.pdf"'
            )
        },
    )


# ─── Employee Documents ───────────────────────────────────────

# Allowlisted MIME types for employee document uploads. Anything outside this
# list is rejected; we don't want users uploading executables or HTML that
# could be served back by a careless download flow.
_EMPLOYEE_DOC_ALLOWED_MIME = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/gif",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
}

_DOC_TYPES_ALLOWED = {"Legal", "KYC", "Education", "Experience", "Finance", "Other"}


def _emp_docs_dir() -> Path:
    return Path(settings.EMPLOYEE_DOCUMENTS_DIR)


def _validate_doc_upload(file: UploadFile, doc_type: str) -> None:
    """Reject uploads that don't meet our allowlist or naming rules."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    content_type = (file.content_type or "").lower()
    if content_type and content_type not in _EMPLOYEE_DOC_ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. Allowed: PDF, JPG, PNG, WebP, HEIC, "
                "GIF, Word, Excel, or plain text."
            ),
        )
    if doc_type not in _DOC_TYPES_ALLOWED:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown document type '{doc_type}'",
        )


def _safe_stored_name(original: str) -> tuple[str, str]:
    """Return (sanitized_original, uuid_prefixed_stored_name)."""
    safe = original.replace("/", "_").replace("\\", "_").lstrip(".")[:200]
    if not safe:
        safe = "document"
    return safe, f"{uuid4().hex}_{safe}"


def _serialize_doc(doc: EmployeeDocument, *, current_user_id: int) -> Dict[str, Any]:
    """Wire format for an EmployeeDocument row.

    Includes verification metadata so the UI can render badges:
    - `verification_status` is `verified` / `rejected` / `pending`.
    - `is_self_uploaded` lets the caller decide whether the current user
      can delete it (employees can only delete docs they uploaded).
    """
    if doc.rejection_reason:
        verification_status = "rejected"
    elif doc.verified_at is not None:
        verification_status = "verified"
    else:
        verification_status = "pending"

    return {
        "id": doc.id,
        "doc_type": doc.doc_type,
        "original_filename": doc.original_filename,
        "remark": doc.remark,
        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        "uploaded_by_id": doc.uploaded_by_id,
        "uploaded_by_name": doc.uploaded_by.full_name if doc.uploaded_by else None,
        "is_self_uploaded": doc.uploaded_by_id == current_user_id,
        "verified_at": doc.verified_at.isoformat() if doc.verified_at else None,
        "verified_by_id": doc.verified_by_id,
        "verified_by_name": doc.verified_by.full_name if doc.verified_by else None,
        "rejection_reason": doc.rejection_reason,
        "verification_status": verification_status,
        "download_url": (
            f"/api/v1/hr/employees/{doc.employee_id}/documents/{doc.id}/download"
        ),
    }


async def _get_my_employee_or_404(db, current_user: User) -> Employee:
    """Resolve the Employee row for the current user — required by /me/* endpoints."""
    emp = (await db.execute(
        select(Employee).where(Employee.user_id == current_user.id).limit(1)
    )).scalar_one_or_none()
    if not emp:
        raise HTTPException(
            status_code=404,
            detail="No employee profile linked to this account",
        )
    return emp


# ── Self-service document endpoints (employee uploading their own files) ──

@router.get("/employees/me/documents")
async def list_my_documents(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
) -> Any:
    """List documents attached to the current user's employee record.

    Includes both employee-uploaded and HR-uploaded documents — the
    `is_self_uploaded` flag lets the UI gate the delete button.
    """
    emp = await _get_my_employee_or_404(db, current_user)
    result = await db.execute(
        select(EmployeeDocument)
        .where(EmployeeDocument.employee_id == emp.id)
        .options(
            selectinload(EmployeeDocument.uploaded_by),
            selectinload(EmployeeDocument.verified_by),
        )
        .order_by(EmployeeDocument.uploaded_at.desc())
    )
    return [
        _serialize_doc(d, current_user_id=current_user.id)
        for d in result.scalars().all()
    ]


@router.post("/employees/me/documents/upload")
async def upload_my_document(
    *,
    db: deps.DBDep,
    request: Request,
    current_user: deps.CurrentUser,
    file: UploadFile = File(...),
    doc_type: str = Query("Other"),
    remark: Optional[str] = Query(None),
) -> Any:
    """Employee uploads a document to their own profile.

    Files land in the same on-disk folder and DB table that HR uses, so HR
    sees them immediately in the employee's Documents tab.
    """
    emp = await _get_my_employee_or_404(db, current_user)
    _validate_doc_upload(file, doc_type)

    max_bytes = int(settings.EMPLOYEE_DOCUMENT_MAX_BYTES)
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {max_bytes // (1024 * 1024)} MB",
        )

    docs_dir = _emp_docs_dir() / str(emp.id)
    docs_dir.mkdir(parents=True, exist_ok=True)
    safe_name, stored_name = _safe_stored_name(file.filename or "document")
    (docs_dir / stored_name).write_bytes(content)

    doc = EmployeeDocument(
        employee_id=emp.id,
        doc_type=doc_type,
        original_filename=safe_name,
        stored_filename=stored_name,
        remark=remark,
        uploaded_by_id=current_user.id,
    )
    db.add(doc)
    await db.flush()
    await log_audit(
        db, current_user.id, "UPLOAD", "employee_document",
        str(doc.id),
        {"employee_id": emp.id, "doc_type": doc_type, "filename": safe_name},
        request,
    )
    await db.commit()
    await db.refresh(doc, attribute_names=["uploaded_by"])
    return _serialize_doc(doc, current_user_id=current_user.id)


@router.get("/employees/me/documents/{doc_id}/download")
async def download_my_document(
    *,
    db: deps.DBDep,
    doc_id: int,
    current_user: deps.CurrentUser,
) -> Any:
    """Download one of the current user's own documents."""
    emp = await _get_my_employee_or_404(db, current_user)
    doc = (await db.execute(
        select(EmployeeDocument).where(
            EmployeeDocument.id == doc_id,
            EmployeeDocument.employee_id == emp.id,
        ).limit(1)
    )).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    file_path = _emp_docs_dir() / str(emp.id) / doc.stored_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(path=str(file_path), filename=doc.original_filename)


@router.delete("/employees/me/documents/{doc_id}")
async def delete_my_document(
    *,
    db: deps.DBDep,
    request: Request,
    doc_id: int,
    current_user: deps.CurrentUser,
) -> Any:
    """Delete a document the current user uploaded themselves.

    Documents uploaded by HR cannot be deleted by the employee; HR has to
    do that from the admin endpoint.
    """
    emp = await _get_my_employee_or_404(db, current_user)
    doc = (await db.execute(
        select(EmployeeDocument).where(
            EmployeeDocument.id == doc_id,
            EmployeeDocument.employee_id == emp.id,
        ).limit(1)
    )).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.uploaded_by_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only delete documents you uploaded yourself. "
                   "Ask HR to remove documents they uploaded for you.",
        )

    file_path = _emp_docs_dir() / str(emp.id) / doc.stored_filename
    file_path.unlink(missing_ok=True)
    await db.delete(doc)
    await log_audit(
        db, current_user.id, "DELETE", "employee_document",
        str(doc_id),
        {"employee_id": emp.id, "filename": doc.original_filename},
        request,
    )
    await db.commit()
    return {"status": "deleted"}


# ── Required-document compliance status ──

async def _build_required_status(db, employee_id: int) -> Dict[str, Any]:
    """Compute uploaded/verified counts for each active required doc type.

    `is_complete` is true when every required type has at least one *verified*
    document. The looser `is_uploaded_complete` is for the user-facing banner
    so employees know they've at least submitted everything.
    """
    required = (await db.execute(
        select(RequiredDocumentType).where(RequiredDocumentType.is_active == True)  # noqa: E712
        .order_by(RequiredDocumentType.doc_type)
    )).scalars().all()
    docs = (await db.execute(
        select(EmployeeDocument).where(EmployeeDocument.employee_id == employee_id)
    )).scalars().all()

    by_type: Dict[str, list[EmployeeDocument]] = {}
    for d in docs:
        by_type.setdefault(d.doc_type, []).append(d)

    out_types = []
    satisfied = 0
    verified_satisfied = 0
    for r in required:
        bucket = by_type.get(r.doc_type, [])
        uploaded_count = len(bucket)
        verified_count = sum(
            1 for d in bucket
            if d.verified_at is not None and not d.rejection_reason
        )
        is_uploaded = uploaded_count > 0
        is_verified = verified_count > 0
        if is_uploaded:
            satisfied += 1
        if is_verified:
            verified_satisfied += 1
        out_types.append({
            "doc_type": r.doc_type,
            "description": r.description,
            "uploaded_count": uploaded_count,
            "verified_count": verified_count,
            "is_uploaded": is_uploaded,
            "is_verified": is_verified,
        })

    total = len(required)
    return {
        "required_types": out_types,
        "total_required": total,
        "satisfied": satisfied,
        "verified_satisfied": verified_satisfied,
        "is_uploaded_complete": total > 0 and satisfied == total,
        "is_verified_complete": total > 0 and verified_satisfied == total,
    }


@router.get("/employees/me/documents/required-status")
async def my_required_doc_status(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
) -> Any:
    """Compliance summary for the current user — used to drive the
    "X of Y required documents uploaded" banner on the profile."""
    emp = await _get_my_employee_or_404(db, current_user)
    return await _build_required_status(db, emp.id)


@router.get("/employees/{employee_id}/documents/required-status")
async def employee_required_doc_status(
    *,
    db: deps.DBDep,
    employee_id: int,
    current_user: User = Depends(deps.check_permissions([HR_READ])),
) -> Any:
    """Compliance summary HR sees on the employee detail page."""
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail=EMP_NOT_FOUND)
    return await _build_required_status(db, employee_id)


# ── HR document verification ──

class VerifyDocumentBody(BaseModel):
    pass  # Empty body — verify is a simple action


class RejectDocumentBody(BaseModel):
    reason: str


@router.post("/employees/{employee_id}/documents/{doc_id}/verify")
async def verify_employee_document(
    *,
    db: deps.DBDep,
    request: Request,
    employee_id: int,
    doc_id: int,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """HR marks a document as verified. Clears any previous rejection."""
    doc = (await db.execute(
        select(EmployeeDocument).where(
            EmployeeDocument.id == doc_id,
            EmployeeDocument.employee_id == employee_id,
        ).options(
            selectinload(EmployeeDocument.uploaded_by),
            selectinload(EmployeeDocument.verified_by),
        ).limit(1)
    )).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.verified_at = datetime.now(timezone.utc)
    doc.verified_by_id = current_user.id
    doc.rejection_reason = None
    await db.flush()
    await log_audit(
        db, current_user.id, "VERIFY", "employee_document",
        str(doc_id),
        {"employee_id": employee_id},
        request,
    )
    await db.commit()
    await db.refresh(doc, attribute_names=["verified_by"])
    return _serialize_doc(doc, current_user_id=current_user.id)


@router.post("/employees/{employee_id}/documents/{doc_id}/reject")
async def reject_employee_document(
    *,
    db: deps.DBDep,
    request: Request,
    employee_id: int,
    doc_id: int,
    body: RejectDocumentBody,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """HR rejects a document with a reason. The employee sees the reason and
    can re-upload."""
    reason = (body.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Rejection reason is required")

    doc = (await db.execute(
        select(EmployeeDocument).where(
            EmployeeDocument.id == doc_id,
            EmployeeDocument.employee_id == employee_id,
        ).options(
            selectinload(EmployeeDocument.uploaded_by),
            selectinload(EmployeeDocument.verified_by),
        ).limit(1)
    )).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.verified_at = None
    doc.verified_by_id = current_user.id
    doc.rejection_reason = reason
    await db.flush()
    await log_audit(
        db, current_user.id, "REJECT", "employee_document",
        str(doc_id),
        {"employee_id": employee_id, "reason": reason[:200]},
        request,
    )
    await db.commit()
    await db.refresh(doc, attribute_names=["verified_by"])
    return _serialize_doc(doc, current_user_id=current_user.id)


@router.get("/employees/{employee_id}/documents")
async def list_employee_documents(
    *,
    db: deps.DBDep,
    employee_id: int,
    current_user: User = Depends(deps.check_permissions([HR_READ]))
) -> Any:
    """List all uploaded documents for an employee."""
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail=EMP_NOT_FOUND)

    result = await db.execute(
        select(EmployeeDocument)
        .where(EmployeeDocument.employee_id == employee_id)
        .options(
            selectinload(EmployeeDocument.uploaded_by),
            selectinload(EmployeeDocument.verified_by),
        )
        .order_by(EmployeeDocument.uploaded_at.desc())
    )
    return [
        _serialize_doc(d, current_user_id=current_user.id)
        for d in result.scalars().all()
    ]


@router.post("/employees/{employee_id}/documents/upload")
async def upload_employee_document(
    *,
    db: deps.DBDep,
    request: Request,
    employee_id: int,
    file: UploadFile = File(...),
    doc_type: str = Query("Other"),
    remark: Optional[str] = Query(None),
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    """HR uploads a document on behalf of an employee."""
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail=EMP_NOT_FOUND)

    _validate_doc_upload(file, doc_type)

    max_bytes = int(settings.EMPLOYEE_DOCUMENT_MAX_BYTES)
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {max_bytes // (1024*1024)} MB"
        )

    docs_dir = _emp_docs_dir() / str(employee_id)
    docs_dir.mkdir(parents=True, exist_ok=True)
    safe_name, stored_name = _safe_stored_name(file.filename or "document")
    (docs_dir / stored_name).write_bytes(content)

    doc = EmployeeDocument(
        employee_id=employee_id,
        doc_type=doc_type,
        original_filename=safe_name,
        stored_filename=stored_name,
        remark=remark,
        uploaded_by_id=current_user.id,
    )
    db.add(doc)
    await db.flush()
    await log_audit(
        db, current_user.id, "UPLOAD", "employee_document",
        str(doc.id),
        {"employee_id": employee_id, "doc_type": doc_type, "filename": safe_name},
        request,
    )
    await db.commit()
    await db.refresh(doc, attribute_names=["uploaded_by"])
    return _serialize_doc(doc, current_user_id=current_user.id)


@router.get("/employees/{employee_id}/documents/{doc_id}/download")
async def download_employee_document(
    *,
    db: deps.DBDep,
    employee_id: int,
    doc_id: int,
    current_user: User = Depends(deps.check_permissions([HR_READ]))
) -> Any:
    """Download a specific employee document."""
    result = await db.execute(
        select(EmployeeDocument).where(
            EmployeeDocument.id == doc_id,
            EmployeeDocument.employee_id == employee_id
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = _emp_docs_dir() / str(employee_id) / doc.stored_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=str(file_path),
        filename=doc.original_filename,
    )


@router.delete("/employees/{employee_id}/documents/{doc_id}")
async def delete_employee_document(
    *,
    db: deps.DBDep,
    request: Request,
    employee_id: int,
    doc_id: int,
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    """Delete an employee document."""
    result = await db.execute(
        select(EmployeeDocument).where(
            EmployeeDocument.id == doc_id,
            EmployeeDocument.employee_id == employee_id
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = _emp_docs_dir() / str(employee_id) / doc.stored_filename
    file_path.unlink(missing_ok=True)
    original = doc.original_filename
    await db.delete(doc)
    await log_audit(
        db, current_user.id, "DELETE", "employee_document",
        str(doc_id),
        {"employee_id": employee_id, "filename": original},
        request,
    )
    await db.commit()
    return {"status": "deleted"}


# ─── Org Chart ────────────────────────────────────────────────

@router.get("/org-chart")
async def get_org_chart(
    *,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([HR_READ])),
) -> Any:
    """Return the reporting hierarchy as a tree.

    Roots are employees whose manager is unset or whose manager is not an
    employee themselves. Each node carries enough info for the UI to render
    cards without follow-up requests.
    """
    rows = (await db.execute(
        select(Employee).options(
            selectinload(Employee.user)
        )
    )).scalars().all()

    by_user_id: Dict[int, Dict[str, Any]] = {}
    for emp in rows:
        if not emp.user:
            continue
        by_user_id[emp.user.id] = {
            "user_id": emp.user.id,
            "employee_id": emp.employee_id,
            "full_name": emp.user.full_name,
            "designation": emp.designation,
            "department": emp.department,
            "email": emp.user.email,
            "manager_id": emp.user.manager_id,
            "subordinates": [],
        }

    roots: list[Dict[str, Any]] = []
    for node in by_user_id.values():
        parent = (
            by_user_id.get(node["manager_id"])
            if node["manager_id"] is not None else None
        )
        if parent is None:
            roots.append(node)
        else:
            parent["subordinates"].append(node)

    # Sort siblings alphabetically for stable rendering.
    def sort_subordinates(node):
        node["subordinates"].sort(key=lambda n: (n.get("full_name") or "").lower())
        for child in node["subordinates"]:
            sort_subordinates(child)

    roots.sort(key=lambda n: (n.get("full_name") or "").lower())
    for r in roots:
        sort_subordinates(r)

    return {"roots": roots, "total": len(by_user_id)}


# ─── Celebrations: birthdays & work anniversaries ─────────────

@router.get("/celebrations/upcoming")
async def upcoming_celebrations(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    days: int = Query(30, ge=1, le=90),
) -> Any:
    """Birthdays and work anniversaries falling in the next `days` window.

    Year-agnostic comparison — we only care about month-day match. This
    avoids wrap-around bugs at year-end without database date_part calls
    that would be MariaDB-specific.
    """
    today = date.today()
    end = today + timedelta(days=days)

    employees = (await db.execute(
        select(Employee).options(selectinload(Employee.user))
        .where(Employee.status == "active")
    )).scalars().all()

    def in_window(d: date) -> Optional[date]:
        # Project the recurring event into this year (or next, if it's
        # already past) and return the upcoming occurrence date.
        try:
            this_year = d.replace(year=today.year)
        except ValueError:
            # Feb 29 fallback
            this_year = d.replace(year=today.year, day=28)
        if this_year < today:
            try:
                this_year = d.replace(year=today.year + 1)
            except ValueError:
                this_year = d.replace(year=today.year + 1, day=28)
        return this_year if today <= this_year <= end else None

    birthdays = []
    anniversaries = []
    for emp in employees:
        if not emp.user:
            continue
        if emp.user.date_of_birth:
            occ = in_window(emp.user.date_of_birth)
            if occ:
                birthdays.append({
                    "user_id": emp.user.id,
                    "employee_id": emp.employee_id,
                    "full_name": emp.user.full_name,
                    "designation": emp.designation,
                    "date": occ.isoformat(),
                    "days_away": (occ - today).days,
                })
        if emp.date_of_joining:
            occ = in_window(emp.date_of_joining)
            if occ and occ != emp.date_of_joining:
                # Skip the original joining date itself; only show recurrences.
                years = today.year - emp.date_of_joining.year
                if occ.year > today.year:
                    years += 1
                anniversaries.append({
                    "user_id": emp.user.id,
                    "employee_id": emp.employee_id,
                    "full_name": emp.user.full_name,
                    "designation": emp.designation,
                    "date": occ.isoformat(),
                    "days_away": (occ - today).days,
                    "years": years,
                })

    birthdays.sort(key=lambda x: x["days_away"])
    anniversaries.sort(key=lambda x: x["days_away"])
    return {"birthdays": birthdays, "anniversaries": anniversaries}


# ─── Employee Assets ──────────────────────────────────────────

class AssetCreate(BaseModel):
    asset_type: str
    model: str
    identifier: Optional[str] = None
    serial_no: Optional[str] = None
    issued_date: Optional[date] = None
    condition: Optional[str] = None
    remarks: Optional[str] = None


class AssetUpdate(BaseModel):
    status: Optional[str] = None
    returned_date: Optional[date] = None
    condition: Optional[str] = None
    remarks: Optional[str] = None


def _serialize_asset(a: EmployeeAsset) -> Dict[str, Any]:
    return {
        "id": a.id,
        "employee_id": a.employee_id,
        "asset_type": a.asset_type,
        "model": a.model,
        "identifier": a.identifier,
        "serial_no": a.serial_no,
        "issued_date": a.issued_date.isoformat() if a.issued_date else None,
        "returned_date": a.returned_date.isoformat() if a.returned_date else None,
        "status": a.status,
        "condition": a.condition,
        "remarks": a.remarks,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("/employees/me/assets")
async def list_my_assets(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
) -> Any:
    """Read-only view of assets currently or previously assigned to the user."""
    emp = await _get_my_employee_or_404(db, current_user)
    rows = (await db.execute(
        select(EmployeeAsset).where(EmployeeAsset.employee_id == emp.id)
        .order_by(EmployeeAsset.created_at.desc())
    )).scalars().all()
    return [_serialize_asset(a) for a in rows]


@router.get("/employees/{employee_id}/assets")
async def list_employee_assets(
    *,
    db: deps.DBDep,
    employee_id: int,
    current_user: User = Depends(deps.check_permissions([HR_READ])),
) -> Any:
    rows = (await db.execute(
        select(EmployeeAsset).where(EmployeeAsset.employee_id == employee_id)
        .order_by(EmployeeAsset.created_at.desc())
    )).scalars().all()
    return [_serialize_asset(a) for a in rows]


@router.post("/employees/{employee_id}/assets")
async def allocate_employee_asset(
    *,
    db: deps.DBDep,
    request: Request,
    employee_id: int,
    body: AssetCreate,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail=EMP_NOT_FOUND)

    asset = EmployeeAsset(
        employee_id=employee_id,
        asset_type=body.asset_type.strip()[:50] or "Other",
        model=body.model.strip()[:150] or "Unknown",
        identifier=(body.identifier or None),
        serial_no=(body.serial_no or None),
        issued_date=body.issued_date or date.today(),
        condition=(body.condition or None),
        remarks=(body.remarks or None),
        status="allocated",
        created_by_id=current_user.id,
    )
    db.add(asset)
    await db.flush()
    await log_audit(
        db, current_user.id, "ALLOCATE", "employee_asset",
        str(asset.id),
        {"employee_id": employee_id, "model": asset.model, "type": asset.asset_type},
        request,
    )
    await db.commit()
    await db.refresh(asset)
    return _serialize_asset(asset)


@router.patch("/assets/{asset_id}")
async def update_asset(
    *,
    db: deps.DBDep,
    request: Request,
    asset_id: int,
    body: AssetUpdate,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    asset = await db.get(EmployeeAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    update_data = body.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"] not in (
        "allocated", "returned", "lost"
    ):
        raise HTTPException(
            status_code=400,
            detail="status must be one of: allocated, returned, lost",
        )
    # If marking returned without a date, default to today.
    if update_data.get("status") == "returned" and not update_data.get("returned_date") and not asset.returned_date:
        update_data["returned_date"] = date.today()

    for field, value in update_data.items():
        setattr(asset, field, value)
    db.add(asset)
    await db.flush()
    await log_audit(
        db, current_user.id, "UPDATE", "employee_asset",
        str(asset_id),
        update_data,
        request,
    )
    await db.commit()
    await db.refresh(asset)
    return _serialize_asset(asset)


@router.delete("/assets/{asset_id}")
async def delete_asset(
    *,
    db: deps.DBDep,
    request: Request,
    asset_id: int,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    asset = await db.get(EmployeeAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    emp_id = asset.employee_id
    await db.delete(asset)
    await log_audit(
        db, current_user.id, "DELETE", "employee_asset",
        str(asset_id),
        {"employee_id": emp_id},
        request,
    )
    await db.commit()
    return {"status": "deleted"}


# ─── Employee Confirmation ────────────────────────────────────

class ConfirmEmployeeBody(BaseModel):
    confirmation_date: Optional[date] = None
    probation_end_date: Optional[date] = None


@router.post("/employees/{employee_id}/confirm")
async def confirm_employee(
    *,
    db: deps.DBDep,
    employee_id: int,
    body: ConfirmEmployeeBody,
    request: Request,
    current_user: User = Depends(deps.check_permissions([HR_WRITE]))
) -> Any:
    """Confirm an employee (mark end of probation period)."""
    result = await db.execute(
        select(Employee).where(Employee.id == employee_id).options(selectinload(Employee.user))
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail=EMP_NOT_FOUND)

    now = datetime.now(timezone.utc)
    emp.confirmation_date = body.confirmation_date or now.date()
    if body.probation_end_date:
        emp.probation_end_date = body.probation_end_date

    await log_audit(
        db, current_user.id, "CONFIRM_EMPLOYEE",
        "employee", str(emp.id),
        {
            "confirmation_date": emp.confirmation_date.isoformat(),
            "employee_name": emp.user.full_name if emp.user else "",
        },
        request,
    )
    await db.commit()

    return {
        "status": "confirmed",
        "confirmation_date": emp.confirmation_date.isoformat(),
        "probation_end_date": emp.probation_end_date.isoformat() if emp.probation_end_date else None,
    }
