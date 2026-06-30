from fastapi import APIRouter, Depends
from app.api import deps
from app.api.v1.endpoints import (
    auth, health, attendance, timesheets,
    tasks, admin, leave, hr, projects, payroll,
    approvals, notifications, reports, bd, recruitment,
    onboarding, clients, bd_bid_tasks, bd_lead_documents,
    admin_bid_line_items, bd_bid_line_items, exit_management,
    salary_advance, shifts,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(
    attendance.router, prefix="/attendance", tags=["attendance"]
)

# Gated routes - Attendance required
api_router.include_router(
    projects.router,
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(deps.verify_attendance)]
)
api_router.include_router(
    leave.router,
    prefix="/leave",
    tags=["leave"],
    dependencies=[Depends(deps.verify_attendance)]
)
api_router.include_router(
    hr.router,
    prefix="/hr",
    tags=["hr"],
    dependencies=[Depends(deps.verify_attendance)]
)
api_router.include_router(
    payroll.router,
    prefix="/hr/payroll",
    tags=["payroll"],
    dependencies=[Depends(deps.verify_attendance)]
)
api_router.include_router(
    onboarding.router,
    prefix="/hr/onboarding",
    tags=["onboarding"],
    dependencies=[Depends(deps.verify_attendance)]
)
api_router.include_router(
    approvals.router,
    prefix="/approvals",
    tags=["approvals"],
    dependencies=[Depends(deps.verify_attendance)]
)
api_router.include_router(
    notifications.router,
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(deps.verify_attendance)]
)
api_router.include_router(
    reports.router,
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(deps.verify_attendance)]
)
api_router.include_router(
    timesheets.router,
    prefix="/timesheets",
    tags=["timesheets"],
    dependencies=[Depends(deps.verify_attendance)]
)
api_router.include_router(
    tasks.router,
    prefix="/tasks",
    tags=["tasks"],
    dependencies=[Depends(deps.verify_attendance)]
)
api_router.include_router(
    admin.router,
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(deps.verify_attendance)]
)
api_router.include_router(
    admin_bid_line_items.router,
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(deps.verify_attendance)],
)
api_router.include_router(
    bd.router,
    prefix="/bd",
    tags=["bd"],
    dependencies=[Depends(deps.verify_attendance)]
)
api_router.include_router(
    bd_bid_tasks.router,
    prefix="/bd",
    tags=["bd"],
    dependencies=[Depends(deps.verify_attendance)],
)
api_router.include_router(
    bd_bid_line_items.router,
    prefix="/bd",
    tags=["bd"],
    dependencies=[Depends(deps.verify_attendance)],
)
api_router.include_router(
    bd_lead_documents.router,
    prefix="/bd",
    tags=["bd"],
    dependencies=[Depends(deps.verify_attendance)],
)
api_router.include_router(
    recruitment.router,
    prefix="/recruitment",
    tags=["recruitment"],
    dependencies=[Depends(deps.verify_attendance)]
)

api_router.include_router(
    clients.router,
    prefix="/clients",
    tags=["clients"],
    dependencies=[Depends(deps.verify_attendance)],
)
api_router.include_router(
    exit_management.router,
    prefix="/exit",
    tags=["exit-management"],
    dependencies=[Depends(deps.verify_attendance)],
)
api_router.include_router(
    salary_advance.router,
    prefix="/hr/salary",
    tags=["salary-advance"],
    dependencies=[Depends(deps.verify_attendance)],
)
api_router.include_router(
    shifts.router,
    prefix="/shifts",
    tags=["shifts"],
    dependencies=[Depends(deps.verify_attendance)],
)
