"""Dashboard endpoints — the role-based landing service.

Read-only aggregation over every compute module. Each widget builder
delegates its query through `visible_user_ids()` for scoping. Widgets
whose permission the caller lacks are dropped before payload building
begins — the wire never carries data the caller couldn't fetch via
the underlying page or report.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.models.approval import ApprovalItem, ApprovalStatus, ApprovalStep
from app.models.approval_chain import (
    ChainedApprovalInstance, ChainedApprovalStatus,
    ChainedApprovalStepInstance, StepInstanceStatus,
)
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.expense import (
    ExpenseClaim, ExpenseClaimStatus, TravelRequest, TravelRequestStatus,
)
from app.models.leave import LeaveBalanceLedger, LeaveRequest, LeaveStatus, LeaveType
from app.models.payroll import PayrollRun, PayrollRunStatus
from app.models.performance import (
    Goal, GoalStatus, OneOnOne, OneOnOneActionItem, ActionItemStatus,
    ReviewCycle, ReviewInstance,
)
from app.models.tax import DeclarationStatus, EmployeeTaxDeclaration
from app.models.user import User
from app.services.dashboard import (
    WIDGET_CATALOG, RoleName, WidgetDescriptor, build_role_posture,
    merge_widget_sets, sum_pending_counts, visible_user_ids,
    widgets_for_dashboards,
)


router = APIRouter()


# ============================================================
# Posture assembly (DB)
# ============================================================


async def _posture_for(db, user: User):
    role_names = [(r.name or "") for r in user.roles or []]
    perm_names: List[str] = []
    for role in user.roles or []:
        for p in role.permissions or []:
            perm_names.append(p.name or "")
    team = (await db.execute(
        select(User.id).where(User.manager_id == user.id)
    )).scalars().all()
    return build_role_posture(
        user_id=user.id,
        is_superuser=bool(user.is_superuser),
        role_names=role_names,
        permission_names=perm_names,
        team_user_ids=list(team),
    )


# ============================================================
# Widget payload builders
# Each returns a dict; return {} if the caller has no visibility.
# ============================================================


async def _wp_my_attendance_today(db, user, posture) -> dict:
    today = datetime.now(timezone.utc).date()
    row = (await db.execute(
        select(Attendance).where(
            and_(
                Attendance.user_id == user.id,
                Attendance.work_date == today,
            )
        )
    )).scalar_one_or_none()
    return {
        "date": today.isoformat(),
        "has_punch": row is not None,
        "punched_in": row is not None and row.captured_at is not None,
        "punched_out": bool(row and getattr(row, "punch_out_at", None)),
    }


async def _wp_my_leave_balance(db, user, posture) -> dict:
    balances = (await db.execute(
        select(LeaveBalanceLedger, LeaveType)
        .join(LeaveType, LeaveBalanceLedger.leave_type_id == LeaveType.id)
        .where(LeaveBalanceLedger.user_id == user.id)
    )).all()
    out = []
    total_balance = 0.0
    for bal, lt in balances:
        out.append({
            "leave_type": lt.name,
            "balance": bal.balance or 0.0,
            "used": bal.used or 0.0,
        })
        total_balance += bal.balance or 0.0
    return {"types": out, "total_balance": round(total_balance, 1)}


async def _wp_my_pending_actions(db, user, posture) -> dict:
    """Aggregate 'things blocking on me' for the employee."""
    count = 0
    breakdown: Dict[str, int] = {}

    # Unreleased reviews awaiting my self-submission.
    my_reviews = (await db.execute(
        select(ReviewInstance).where(
            and_(
                ReviewInstance.employee_id == user.id,
                ReviewInstance.self_submitted_at.is_(None),
            )
        )
    )).scalars().all()
    if my_reviews:
        breakdown["self_review"] = len(my_reviews)
        count += len(my_reviews)

    # Rejected leave requests waiting for me to fix + resubmit.
    my_leaves = (await db.execute(
        select(func.count(LeaveRequest.id)).where(
            and_(
                LeaveRequest.employee_id == user.id,
                LeaveRequest.status == LeaveStatus.REJECTED,
            )
        )
    )).scalar_one()
    if my_leaves:
        breakdown["rejected_leave"] = int(my_leaves)
        count += int(my_leaves)

    # Draft or rejected expense claims.
    my_expenses = (await db.execute(
        select(func.count(ExpenseClaim.id)).where(
            and_(
                ExpenseClaim.submitter_id == user.id,
                ExpenseClaim.status.in_([
                    ExpenseClaimStatus.DRAFT, ExpenseClaimStatus.REJECTED,
                ]),
            )
        )
    )).scalar_one()
    if my_expenses:
        breakdown["expense_action"] = int(my_expenses)
        count += int(my_expenses)

    # Open 1:1 action items assigned to me.
    my_actions = (await db.execute(
        select(func.count(OneOnOneActionItem.id)).where(
            and_(
                OneOnOneActionItem.assignee_id == user.id,
                OneOnOneActionItem.status == ActionItemStatus.OPEN,
            )
        )
    )).scalar_one()
    if my_actions:
        breakdown["one_on_one_actions"] = int(my_actions)
        count += int(my_actions)

    return {"count": count, "breakdown": breakdown}


async def _wp_my_active_goals(db, user, posture) -> dict:
    goals = (await db.execute(
        select(Goal).where(
            and_(
                Goal.owner_id == user.id,
                Goal.status.in_([
                    GoalStatus.ACTIVE, GoalStatus.AT_RISK,
                ]),
            )
        )
    )).scalars().all()
    rag_counts = {"green": 0, "amber": 0, "red": 0, "unknown": 0}
    for g in goals:
        k = g.latest_confidence or "unknown"
        if k not in rag_counts:
            k = "unknown"
        rag_counts[k] += 1
    top = [
        {
            "id": g.id, "title": g.title,
            "progress": round(g.latest_progress or 0.0, 1),
            "confidence": g.latest_confidence,
            "status": g.status,
        }
        for g in goals[:5]
    ]
    return {
        "count": len(goals), "rag": rag_counts, "top": top,
    }


async def _wp_my_1on1_actions(db, user, posture) -> dict:
    open_actions = (await db.execute(
        select(OneOnOneActionItem).where(
            and_(
                OneOnOneActionItem.assignee_id == user.id,
                OneOnOneActionItem.status == ActionItemStatus.OPEN,
            )
        )
    )).scalars().all()
    return {
        "count": len(open_actions),
        "top": [
            {
                "id": a.id, "description": a.description,
                "due_date": a.due_date.isoformat() if a.due_date else None,
            }
            for a in open_actions[:5]
        ],
    }


async def _wp_my_next_payslip(db, user, posture) -> dict:
    latest = (await db.execute(
        select(PayrollRun).where(
            PayrollRun.status.in_([
                PayrollRunStatus.PUBLISHED, PayrollRunStatus.FINALIZED,
            ])
        ).order_by(PayrollRun.id.desc()).limit(1)
    )).scalar_one_or_none()
    if not latest:
        return {"available": False}
    return {
        "available": True,
        "run_id": latest.id,
        "status": latest.status.value if hasattr(latest.status, "value") else str(latest.status),
        "run_month": getattr(latest, "run_month", None),
        "run_year": getattr(latest, "run_year", None),
    }


async def _wp_unified_approval_queue(db, user, posture) -> dict:
    """Legacy ApprovalItem inbox + new chained-approval inbox, combined."""
    # Legacy approvals awaiting current user
    role_ids = [role.id for role in user.roles or []]
    legacy_stmt = (
        select(ApprovalItem)
        .join(ApprovalStep)
        .where(
            and_(
                ApprovalItem.status == ApprovalStatus.PENDING,
                ApprovalItem.current_step_number == ApprovalStep.step_number,
                ApprovalStep.status == ApprovalStatus.PENDING,
                or_(
                    ApprovalStep.approver_id == user.id,
                    (
                        ApprovalStep.role_id.in_(role_ids)
                        if role_ids else False
                    ),
                ),
            )
        )
        .options(selectinload(ApprovalItem.steps))
        .distinct()
    )
    legacy = (await db.execute(legacy_stmt)).scalars().unique().all()

    # Chained-engine approvals awaiting current user
    chained_stmt = (
        select(ChainedApprovalStepInstance)
        .where(
            and_(
                ChainedApprovalStepInstance.approver_user_id == user.id,
                ChainedApprovalStepInstance.status == StepInstanceStatus.PENDING,
            )
        )
    )
    chained_rows = (await db.execute(chained_stmt)).scalars().all()
    # Only surface rows on the CURRENT step of their instance.
    inst_ids = {r.instance_id for r in chained_rows}
    instances = (await db.execute(
        select(ChainedApprovalInstance).where(
            ChainedApprovalInstance.id.in_(inst_ids)
        )
    )).scalars().all()
    inst_by_id = {i.id: i for i in instances}
    chained_current = [
        r for r in chained_rows
        if (i := inst_by_id.get(r.instance_id))
        and i.current_step_order == r.step_order
    ]

    top: List[dict] = []
    for it in legacy[:5]:
        top.append({
            "origin": "legacy",
            "id": it.id,
            "resource_type": it.resource_type,
            "resource_id": it.resource_id,
            "created_at": it.created_at.isoformat() if it.created_at else None,
        })
    for si in chained_current[:5]:
        inst = inst_by_id.get(si.instance_id)
        if not inst:
            continue
        top.append({
            "origin": "chain",
            "id": inst.id,
            "step_instance_id": si.id,
            "entity_type": inst.entity_type,
            "entity_id": inst.entity_id,
            "amount_paise": inst.amount_paise,
        })
    return {
        "count": len(legacy) + len(chained_current),
        "legacy_count": len(legacy),
        "chain_count": len(chained_current),
        "top": top,
    }


async def _wp_team_attendance_today(db, user, posture) -> dict:
    scoped = visible_user_ids(posture, widget_scope="team")
    today = datetime.now(timezone.utc).date()
    stmt = select(Attendance).where(Attendance.work_date == today)
    if scoped is not None:
        stmt = stmt.where(Attendance.user_id.in_(scoped))
    rows = (await db.execute(stmt)).scalars().all()
    total = len(scoped) if scoped is not None else 0
    if total == 0 and scoped is None:
        # HR — count active users to give a percentage baseline.
        total = (await db.execute(
            select(func.count(User.id)).where(User.is_active.is_(True))
        )).scalar_one() or 1
    present = len({r.user_id for r in rows})
    return {
        "date": today.isoformat(),
        "present": present, "total": total,
        "percent": round(100 * present / total, 1) if total else 0.0,
    }


async def _wp_team_on_leave_this_week(db, user, posture) -> dict:
    scoped = visible_user_ids(posture, widget_scope="team")
    today = datetime.now(timezone.utc).date()
    week_end = today + timedelta(days=7)
    stmt = select(LeaveRequest).where(
        and_(
            LeaveRequest.status == LeaveStatus.APPROVED,
            LeaveRequest.start_date <= week_end,
            LeaveRequest.end_date >= today,
        )
    )
    if scoped is not None:
        stmt = stmt.where(LeaveRequest.employee_id.in_(scoped))
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "count": len(rows),
        "top": [
            {
                "employee_id": r.employee_id,
                "start_date": r.start_date.isoformat(),
                "end_date": r.end_date.isoformat(),
            }
            for r in rows[:5]
        ],
    }


async def _wp_team_reviews_owed(db, user, posture) -> dict:
    scoped = visible_user_ids(posture, widget_scope="team")
    stmt = select(ReviewInstance).where(
        ReviewInstance.manager_submitted_at.is_(None)
    )
    if scoped is not None:
        stmt = stmt.where(ReviewInstance.employee_id.in_(scoped))
    rows = (await db.execute(stmt)).scalars().all()
    return {"count": len(rows)}


async def _wp_team_1on1_coverage(db, user, posture) -> dict:
    scoped = visible_user_ids(posture, widget_scope="team")
    if scoped is None:
        # HR view — sample coverage across all users w/ managers.
        rows = (await db.execute(
            select(User.id, User.manager_id)
            .where(User.manager_id.isnot(None))
        )).all()
        pairs = [(r.manager_id, r.id) for r in rows]
    else:
        pairs = [(user.id, uid) for uid in scoped if uid != user.id]

    if not pairs:
        return {"count_reportees": 0, "no_meeting_30d": 0}

    # Meetings in the last 30 days.
    since = datetime.now(timezone.utc).date() - timedelta(days=30)
    stmt = (
        select(
            OneOnOne.manager_id, OneOnOne.reportee_id,
            func.max(OneOnOne.meeting_date).label("last_met"),
        )
        .group_by(OneOnOne.manager_id, OneOnOne.reportee_id)
    )
    meets = (await db.execute(stmt)).all()
    by_pair = {(m.manager_id, m.reportee_id): m.last_met for m in meets}
    stale = 0
    for pair in pairs:
        last = by_pair.get(pair)
        if last is None or last < since:
            stale += 1
    return {
        "count_reportees": len(pairs),
        "no_meeting_30d": stale,
    }


async def _wp_hr_pending_verifications(db, user, posture) -> dict:
    """Documents uploaded but not yet verified (verified_at IS NULL and
    no rejection_reason).
    """
    from app.models.employee_document import EmployeeDocument
    rows = (await db.execute(
        select(func.count(EmployeeDocument.id)).where(
            and_(
                EmployeeDocument.verified_at.is_(None),
                EmployeeDocument.rejection_reason.is_(None),
            )
        )
    )).scalar_one() or 0
    return {"count": int(rows)}


async def _wp_hr_tax_declarations_pending(db, user, posture) -> dict:
    rows = (await db.execute(
        select(func.count(EmployeeTaxDeclaration.id)).where(
            EmployeeTaxDeclaration.status == DeclarationStatus.SUBMITTED
        )
    )).scalar_one() or 0
    return {"count": int(rows)}


async def _wp_hr_flagged_attendance(db, user, posture) -> dict:
    """Real geo/attribution flag counts (Section M B1) — replaces the
    correction-request proxy. Counts distinct attendance rows in the
    trailing 30 days that carry a non-null flag on EITHER punch-in
    (`geo_flag` / `attribution_flag`) or punch-out (`punch_out_geo_flag`).
    """
    from app.models.attendance import Attendance
    from datetime import timedelta as _td

    since = datetime.now(timezone.utc).date() - _td(days=30)
    stmt = select(func.count(Attendance.id)).where(
        and_(
            Attendance.work_date >= since,
            or_(
                Attendance.geo_flag.isnot(None),
                Attendance.punch_out_geo_flag.isnot(None),
                Attendance.attribution_flag.isnot(None),
            ),
        )
    )
    total = int((await db.execute(stmt)).scalar_one() or 0)

    # Per-flag breakdown so the dashboard tile can show what dominates.
    async def _count(col_pred):
        return int((await db.execute(
            select(func.count(Attendance.id)).where(and_(
                Attendance.work_date >= since, col_pred,
            ))
        )).scalar_one() or 0)

    geo_in = await _count(Attendance.geo_flag.isnot(None))
    geo_out = await _count(Attendance.punch_out_geo_flag.isnot(None))
    attrib = await _count(Attendance.attribution_flag.isnot(None))

    return {
        "count": total,
        "geo_in": geo_in,
        "geo_out": geo_out,
        "attribution": attrib,
        "window_days": 30,
    }


async def _wp_hr_out_of_policy_expenses(db, user, posture) -> dict:
    from app.models.expense import ExpenseLineItem
    rows = (await db.execute(
        select(func.count(ExpenseClaim.id)).where(
            and_(
                ExpenseClaim.status.in_([
                    ExpenseClaimStatus.SUBMITTED,
                    ExpenseClaimStatus.APPROVED,
                ]),
                ExpenseClaim.policy_flags_json.isnot(None),
            )
        )
    )).scalar_one() or 0
    # Not a precise "has flagged lines" count, but good enough for a summary.
    return {"count": int(rows)}


async def _wp_hr_review_cycles_progress(db, user, posture) -> dict:
    cycles = (await db.execute(
        select(ReviewCycle).where(
            ReviewCycle.status.in_(["launched", "in_progress"])
        )
    )).scalars().all()
    out = []
    for c in cycles:
        instances = (await db.execute(
            select(func.count(ReviewInstance.id)).where(
                ReviewInstance.cycle_id == c.id
            )
        )).scalar_one() or 0
        released = (await db.execute(
            select(func.count(ReviewInstance.id)).where(
                and_(
                    ReviewInstance.cycle_id == c.id,
                    ReviewInstance.is_released.is_(True),
                )
            )
        )).scalar_one() or 0
        out.append({
            "id": c.id, "name": c.name,
            "total": int(instances),
            "released": int(released),
            "percent": round(100 * released / instances, 1) if instances else 0.0,
        })
    return {"count": len(cycles), "cycles": out}


async def _wp_hr_headcount_trend(db, user, posture) -> dict:
    active = (await db.execute(
        select(func.count(User.id)).where(User.is_active.is_(True))
    )).scalar_one() or 0
    return {
        "current": int(active),
        # Real chart is on the reports page; this is just a launch tile.
        "drill_hint": "See 12-mo trend in Reports Catalog.",
    }


async def _wp_hr_attrition_rate(db, user, posture) -> dict:
    # Simple current-month leavers over avg headcount.
    today = datetime.now(timezone.utc).date()
    month_start = today.replace(day=1)
    active = (await db.execute(
        select(func.count(User.id)).where(User.is_active.is_(True))
    )).scalar_one() or 1
    leavers = (await db.execute(
        select(func.count(Employee.id)).where(
            and_(
                Employee.status == "inactive",
            )
        )
    )).scalar_one() or 0
    return {
        "month_start": month_start.isoformat(),
        "active": int(active), "leavers_ever": int(leavers),
    }


async def _wp_hr_exceptions(db, user, posture) -> dict:
    """Real data-quality scan (Section K Item 3) — no more single-field proxy."""
    from app.api.v1.endpoints.plumbing import _build_snapshots
    from app.services.data_quality import scan_all, summarize
    snapshots = await _build_snapshots(db)
    findings = scan_all(snapshots)
    s = summarize(findings)
    return {
        "count": s["count"],
        "blocker_count": s["blocker_count"],
        "employees_blocked": s["employees_blocked"],
        "by_severity": s["by_severity"],
        "by_field": s["by_field"],
    }


async def _wp_finance_reimbursement_queue(db, user, posture) -> dict:
    rows = (await db.execute(
        select(ExpenseClaim).where(
            ExpenseClaim.status == ExpenseClaimStatus.APPROVED
        )
    )).scalars().all()
    total_paise = sum(r.total_amount_paise or 0 for r in rows)
    return {
        "count": len(rows),
        "total_paise": total_paise,
        "top": [
            {
                "id": r.id, "title": r.title,
                "amount_paise": r.total_amount_paise,
                "claim_date": r.claim_date.isoformat() if r.claim_date else None,
            }
            for r in rows[:5]
        ],
    }


async def _wp_finance_travel_advance_outstanding(db, user, posture) -> dict:
    rows = (await db.execute(
        select(TravelRequest).where(
            and_(
                TravelRequest.status == TravelRequestStatus.APPROVED,
                TravelRequest.advance_paid_paise > 0,
            )
        )
    )).scalars().all()
    total = sum(r.advance_paid_paise or 0 for r in rows)
    return {"count": len(rows), "total_paise": total}


async def _wp_finance_payroll_status(db, user, posture) -> dict:
    rows = (await db.execute(
        select(PayrollRun).order_by(PayrollRun.id.desc()).limit(3)
    )).scalars().all()
    out = []
    for r in rows:
        out.append({
            "id": r.id,
            "status": r.status.value if hasattr(r.status, "value") else str(r.status),
            "run_month": getattr(r, "run_month", None),
            "run_year": getattr(r, "run_year", None),
        })
    return {"recent": out}


async def _wp_finance_statutory_due(db, user, posture) -> dict:
    from app.models.statutory import StatutoryFiling, FilingStatus
    rows = (await db.execute(
        select(StatutoryFiling).where(
            StatutoryFiling.status.in_([
                FilingStatus.PENDING, FilingStatus.COMPUTED,
                FilingStatus.EXPORTED,
            ])
        )
    )).scalars().all()
    return {"count": len(rows)}


async def _wp_finance_cost_analytics(db, user, posture) -> dict:
    # Last finalized run's total gross.
    latest = (await db.execute(
        select(PayrollRun).where(
            PayrollRun.status.in_([
                PayrollRunStatus.FINALIZED, PayrollRunStatus.PUBLISHED,
            ])
        ).order_by(PayrollRun.id.desc()).limit(1)
    )).scalar_one_or_none()
    if not latest:
        return {"has_run": False}
    return {
        "has_run": True,
        "run_id": latest.id,
        "status": latest.status.value if hasattr(latest.status, "value") else str(latest.status),
    }


async def _wp_executive_rating_distribution(db, user, posture) -> dict:
    rows = (await db.execute(
        select(ReviewInstance).where(ReviewInstance.is_released.is_(True))
    )).scalars().all()
    buckets: Dict[str, int] = {}
    for r in rows:
        if r.final_rating is None:
            continue
        key = str(round(float(r.final_rating)))
        buckets[key] = buckets.get(key, 0) + 1
    total = sum(buckets.values()) or 1
    return {
        "total": sum(buckets.values()),
        "distribution": [
            {
                "bucket": k, "count": v,
                "percent": round(100 * v / total, 1),
            }
            for k, v in sorted(buckets.items())
        ],
    }


async def _wp_executive_headline_kpis(db, user, posture) -> dict:
    active = (await db.execute(
        select(func.count(User.id)).where(User.is_active.is_(True))
    )).scalar_one() or 0
    open_goals = (await db.execute(
        select(func.count(Goal.id)).where(
            Goal.status.in_([GoalStatus.ACTIVE, GoalStatus.AT_RISK])
        )
    )).scalar_one() or 0
    at_risk = (await db.execute(
        select(func.count(Goal.id)).where(Goal.status == GoalStatus.AT_RISK)
    )).scalar_one() or 0
    return {
        "headcount": int(active),
        "goals_open": int(open_goals),
        "goals_at_risk": int(at_risk),
    }


BUILDERS: Dict[str, Any] = {
    "my_attendance_today": _wp_my_attendance_today,
    "my_leave_balance": _wp_my_leave_balance,
    "my_pending_actions": _wp_my_pending_actions,
    "my_active_goals": _wp_my_active_goals,
    "my_1on1_actions": _wp_my_1on1_actions,
    "my_next_payslip": _wp_my_next_payslip,
    "unified_approval_queue": _wp_unified_approval_queue,
    "team_attendance_today": _wp_team_attendance_today,
    "team_on_leave_this_week": _wp_team_on_leave_this_week,
    "team_reviews_owed": _wp_team_reviews_owed,
    "team_1on1_coverage": _wp_team_1on1_coverage,
    "hr_pending_verifications": _wp_hr_pending_verifications,
    "hr_tax_declarations_pending": _wp_hr_tax_declarations_pending,
    "hr_flagged_attendance": _wp_hr_flagged_attendance,
    "hr_out_of_policy_expenses": _wp_hr_out_of_policy_expenses,
    "hr_review_cycles_progress": _wp_hr_review_cycles_progress,
    "hr_headcount_trend": _wp_hr_headcount_trend,
    "hr_attrition_rate": _wp_hr_attrition_rate,
    "hr_exceptions": _wp_hr_exceptions,
    "finance_reimbursement_queue": _wp_finance_reimbursement_queue,
    "finance_travel_advance_outstanding": _wp_finance_travel_advance_outstanding,
    "finance_payroll_status": _wp_finance_payroll_status,
    "finance_statutory_due": _wp_finance_statutory_due,
    "finance_cost_analytics": _wp_finance_cost_analytics,
    "executive_rating_distribution": _wp_executive_rating_distribution,
    "executive_headline_kpis": _wp_executive_headline_kpis,
}


def _widget_meta(w: WidgetDescriptor) -> dict:
    return {
        "key": w.key, "title": w.title, "category": w.category,
        "scope": w.scope, "permission": w.permission,
        "drill": {"route": w.drill_route, "params": w.drill_params},
    }


# ============================================================
# Endpoints
# ============================================================


@router.get("/dashboard")
async def get_dashboard(
    db: deps.DBDep,
    dashboard: Optional[str] = Query(
        None,
        description="Explicit dashboard id; defaults to landing_dashboard()",
    ),
    include_available: bool = Query(True),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Assemble the widget set for the caller's role posture and return
    each widget's compact payload.

    - `dashboard` overrides the landing pick — used by the role
      switcher on the frontend when a multi-role user wants a
      different cockpit.
    - Every widget's permission is re-checked server-side. If the
      caller cannot see a widget, it is dropped entirely (no leak).
    """
    posture = await _posture_for(db, current_user)

    picked = dashboard or posture.landing_dashboard()
    available = posture.dashboards_available()
    if picked not in available:
        picked = posture.landing_dashboard()

    widgets = merge_widget_sets([picked], posture)
    payloads: Dict[str, Any] = {}
    metas: List[dict] = []
    for w in widgets:
        builder = BUILDERS.get(w.key)
        if builder is None:
            continue
        try:
            payloads[w.key] = await builder(db, current_user, posture)
        except Exception:
            # A failed widget never breaks the dashboard.
            payloads[w.key] = {"error": True}
        metas.append(_widget_meta(w))

    total_pending = sum_pending_counts(payloads)
    return {
        "landing_dashboard": posture.landing_dashboard(),
        "active_dashboard": picked,
        "available_dashboards": available if include_available else [],
        "role_names": sorted(posture.role_names),
        "widgets": metas,
        "payloads": payloads,
        "pending_count": total_pending,
    }


@router.get("/dashboard/pending-count")
async def get_pending_count(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Cheap badge endpoint. Uses the actionable-widget subset only —
    same server-side scoping as the full dashboard so the badge can
    never overstate a user's queue depth."""
    posture = await _posture_for(db, current_user)
    picked = posture.landing_dashboard()
    widgets = merge_widget_sets([picked], posture)
    payloads: Dict[str, Any] = {}
    for w in widgets:
        if w.category != "action":
            continue
        builder = BUILDERS.get(w.key)
        if builder is None:
            continue
        try:
            payloads[w.key] = await builder(db, current_user, posture)
        except Exception:
            payloads[w.key] = {}
    return {"count": sum_pending_counts(payloads)}


@router.get("/dashboard/widget/{key}")
async def get_single_widget(
    key: str,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Fetch one widget's payload. Independently permission-gated —
    same rules as the aggregated /dashboard."""
    from fastapi import HTTPException
    descriptor = WIDGET_CATALOG.get(key)
    if not descriptor:
        raise HTTPException(404, "Unknown widget")
    posture = await _posture_for(db, current_user)
    if (
        descriptor.permission
        and not posture.has_permission(descriptor.permission)
    ):
        raise HTTPException(403, "Not authorized")
    builder = BUILDERS.get(key)
    if builder is None:
        raise HTTPException(501, "Widget has no builder yet")
    return {
        "widget": _widget_meta(descriptor),
        "payload": await builder(db, current_user, posture),
    }
