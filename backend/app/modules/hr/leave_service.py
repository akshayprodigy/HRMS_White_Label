from __future__ import annotations

import datetime as dt

from fastapi import HTTPException
from sqlalchemy import Select, and_, select
from sqlalchemy.orm import Session

from app.core.audit import log_audit, model_to_dict
from app.db.models.hr import (
    Employee,
    HolidayCalendar,
    LeaveBalance,
    LeavePolicy,
    LeaveRequest,
    LeaveType,
)


def list_leave_types(db: Session) -> list[LeaveType]:
    stmt = select(LeaveType).order_by(LeaveType.id.desc())
    return list(db.execute(stmt).scalars().all())


def create_leave_type(
    db: Session,
    *,
    code: str,
    name: str,
    description: str | None,
    is_active: bool,
) -> LeaveType:
    existing = db.execute(
        select(LeaveType).where(LeaveType.code == code)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Leave type code exists")

    lt = LeaveType(
        code=code,
        name=name,
        description=description,
        is_active=is_active,
    )
    db.add(lt)
    db.commit()
    db.refresh(lt)

    log_audit(
        db,
        entity_type="leave_types",
        entity_id=str(lt.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(lt),
    )
    return lt


def update_leave_type(
    db: Session,
    *,
    leave_type: LeaveType,
    name: str | None,
    description: str | None,
    is_active: bool | None,
) -> LeaveType:
    before = model_to_dict(leave_type)

    if name is not None:
        leave_type.name = name
    if description is not None:
        leave_type.description = description
    if is_active is not None:
        leave_type.is_active = is_active

    db.add(leave_type)
    db.commit()
    db.refresh(leave_type)

    log_audit(
        db,
        entity_type="leave_types",
        entity_id=str(leave_type.id),
        action="update",
        before_json=before,
        after_json=model_to_dict(leave_type),
    )
    return leave_type


def delete_leave_type(db: Session, *, leave_type: LeaveType) -> None:
    before = model_to_dict(leave_type)
    db.delete(leave_type)
    db.commit()
    log_audit(
        db,
        entity_type="leave_types",
        entity_id=str(leave_type.id),
        action="delete",
        before_json=before,
        after_json=None,
    )


def list_leave_policies(db: Session) -> list[LeavePolicy]:
    stmt = select(LeavePolicy).order_by(LeavePolicy.id.desc())
    return list(db.execute(stmt).scalars().all())


def create_leave_policy(
    db: Session,
    *,
    leave_type_id: int,
    name: str,
    monthly_credit_days: float,
    max_balance_days: float | None,
    is_active: bool,
    notes: str | None,
) -> LeavePolicy:
    lt = db.get(LeaveType, leave_type_id)
    if not lt:
        raise HTTPException(status_code=404, detail="Leave type not found")

    policy = LeavePolicy(
        leave_type_id=leave_type_id,
        name=name,
        monthly_credit_days=monthly_credit_days,
        max_balance_days=max_balance_days,
        is_active=is_active,
        notes=notes,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)

    log_audit(
        db,
        entity_type="leave_policies",
        entity_id=str(policy.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(policy),
    )
    return policy


def update_leave_policy(
    db: Session,
    *,
    policy: LeavePolicy,
    name: str | None,
    monthly_credit_days: float | None,
    max_balance_days: float | None,
    is_active: bool | None,
    notes: str | None,
) -> LeavePolicy:
    before = model_to_dict(policy)

    if name is not None:
        policy.name = name
    if monthly_credit_days is not None:
        policy.monthly_credit_days = monthly_credit_days
    if max_balance_days is not None:
        policy.max_balance_days = max_balance_days
    if is_active is not None:
        policy.is_active = is_active
    if notes is not None:
        policy.notes = notes

    db.add(policy)
    db.commit()
    db.refresh(policy)

    log_audit(
        db,
        entity_type="leave_policies",
        entity_id=str(policy.id),
        action="update",
        before_json=before,
        after_json=model_to_dict(policy),
    )
    return policy


def delete_leave_policy(db: Session, *, policy: LeavePolicy) -> None:
    before = model_to_dict(policy)
    db.delete(policy)
    db.commit()
    log_audit(
        db,
        entity_type="leave_policies",
        entity_id=str(policy.id),
        action="delete",
        before_json=before,
        after_json=None,
    )


def list_holidays(
    db: Session,
    *,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
) -> list[HolidayCalendar]:
    stmt: Select[tuple[HolidayCalendar]] = select(HolidayCalendar)
    if date_from is not None:
        stmt = stmt.where(HolidayCalendar.holiday_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(HolidayCalendar.holiday_date <= date_to)
    stmt = stmt.order_by(HolidayCalendar.holiday_date.asc())
    return list(db.execute(stmt).scalars().all())


def create_holiday(
    db: Session,
    *,
    holiday_date: dt.date,
    name: str,
    is_optional: bool,
) -> HolidayCalendar:
    existing = db.execute(
        select(HolidayCalendar).where(
            HolidayCalendar.holiday_date == holiday_date
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Holiday already exists")

    row = HolidayCalendar(
        holiday_date=holiday_date,
        name=name,
        is_optional=is_optional,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    log_audit(
        db,
        entity_type="holiday_calendars",
        entity_id=str(row.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(row),
    )
    return row


def delete_holiday(db: Session, *, holiday: HolidayCalendar) -> None:
    before = model_to_dict(holiday)
    db.delete(holiday)
    db.commit()
    log_audit(
        db,
        entity_type="holiday_calendars",
        entity_id=str(holiday.id),
        action="delete",
        before_json=before,
        after_json=None,
    )


def _count_working_days(
    db: Session,
    *,
    date_from: dt.date,
    date_to: dt.date,
) -> float:
    if date_to < date_from:
        raise HTTPException(
            status_code=400,
            detail="date_to must be >= date_from",
        )

    holidays = {
        r[0]
        for r in db.execute(
            select(HolidayCalendar.holiday_date).where(
                and_(
                    HolidayCalendar.holiday_date >= date_from,
                    HolidayCalendar.holiday_date <= date_to,
                )
            )
        ).all()
    }

    cur = date_from
    days = 0
    while cur <= date_to:
        if cur.weekday() < 5 and cur not in holidays:
            days += 1
        cur += dt.timedelta(days=1)

    return float(days)


def _get_or_create_balance(
    db: Session,
    *,
    employee_id: int,
    leave_type_id: int,
) -> LeaveBalance:
    bal = db.execute(
        select(LeaveBalance).where(
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.leave_type_id == leave_type_id,
        )
    ).scalar_one_or_none()
    if bal is None:
        bal = LeaveBalance(
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            balance_days=0,
        )
        db.add(bal)
        db.flush()
    return bal


def list_leave_balances(
    db: Session,
    *,
    employee_id: int,
) -> list[LeaveBalance]:
    return list(
        db.execute(
            select(LeaveBalance)
            .where(LeaveBalance.employee_id == employee_id)
            .order_by(LeaveBalance.leave_type_id.asc())
        )
        .scalars()
        .all()
    )


def apply_leave_request(
    db: Session,
    *,
    employee_id: int,
    leave_type_id: int,
    date_from: dt.date,
    date_to: dt.date,
    reason: str | None,
) -> LeaveRequest:
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    lt = db.get(LeaveType, leave_type_id)
    if not lt or not lt.is_active:
        raise HTTPException(status_code=404, detail="Leave type not found")

    days = _count_working_days(db, date_from=date_from, date_to=date_to)
    if days <= 0:
        raise HTTPException(status_code=400, detail="No working days in range")

    bal = _get_or_create_balance(
        db,
        employee_id=employee_id,
        leave_type_id=leave_type_id,
    )

    if float(bal.balance_days) < float(days):
        raise HTTPException(
            status_code=400,
            detail="Insufficient leave balance",
        )

    before_bal = model_to_dict(bal)
    bal.balance_days = float(bal.balance_days) - float(days)

    req = LeaveRequest(
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        date_from=date_from,
        date_to=date_to,
        days=days,
        reason=reason,
        status="applied",
    )

    db.add(bal)
    db.add(req)
    db.commit()
    db.refresh(req)

    log_audit(
        db,
        entity_type="leave_requests",
        entity_id=str(req.id),
        action="apply",
        before_json=None,
        after_json=model_to_dict(req),
    )

    log_audit(
        db,
        entity_type="leave_balances",
        entity_id=str(bal.id),
        action="debit_on_apply",
        before_json=before_bal,
        after_json=model_to_dict(bal),
    )

    return req


def _ensure_status(req: LeaveRequest, allowed: set[str]) -> None:
    if req.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail="Invalid status transition",
        )


def approve_leave_request(
    db: Session,
    *,
    req: LeaveRequest,
    actor_user_id: int,
    comment: str | None,
) -> LeaveRequest:
    _ensure_status(req, {"applied"})

    before = model_to_dict(req)
    req.status = "approved"
    req.decided_at = dt.datetime.now(dt.UTC)
    req.decided_by_user_id = actor_user_id
    req.decision_comment = comment

    db.add(req)
    db.commit()
    db.refresh(req)

    log_audit(
        db,
        entity_type="leave_requests",
        entity_id=str(req.id),
        action="approve",
        before_json=before,
        after_json=model_to_dict(req),
    )
    return req


def reject_leave_request(
    db: Session,
    *,
    req: LeaveRequest,
    actor_user_id: int,
    comment: str | None,
) -> LeaveRequest:
    _ensure_status(req, {"applied"})

    bal = _get_or_create_balance(
        db,
        employee_id=req.employee_id,
        leave_type_id=req.leave_type_id,
    )
    before_bal = model_to_dict(bal)
    bal.balance_days = float(bal.balance_days) + float(req.days)

    before = model_to_dict(req)
    req.status = "rejected"
    req.decided_at = dt.datetime.now(dt.UTC)
    req.decided_by_user_id = actor_user_id
    req.decision_comment = comment

    db.add(bal)
    db.add(req)
    db.commit()
    db.refresh(req)

    log_audit(
        db,
        entity_type="leave_requests",
        entity_id=str(req.id),
        action="reject",
        before_json=before,
        after_json=model_to_dict(req),
    )
    log_audit(
        db,
        entity_type="leave_balances",
        entity_id=str(bal.id),
        action="refund_on_reject",
        before_json=before_bal,
        after_json=model_to_dict(bal),
    )
    return req


def cancel_leave_request(db: Session, *, req: LeaveRequest) -> LeaveRequest:
    _ensure_status(req, {"applied"})

    bal = _get_or_create_balance(
        db,
        employee_id=req.employee_id,
        leave_type_id=req.leave_type_id,
    )
    before_bal = model_to_dict(bal)
    bal.balance_days = float(bal.balance_days) + float(req.days)

    before = model_to_dict(req)
    req.status = "cancelled"
    req.decided_at = dt.datetime.now(dt.UTC)
    req.decision_comment = "Cancelled by applicant"

    db.add(bal)
    db.add(req)
    db.commit()
    db.refresh(req)

    log_audit(
        db,
        entity_type="leave_requests",
        entity_id=str(req.id),
        action="cancel",
        before_json=before,
        after_json=model_to_dict(req),
    )
    log_audit(
        db,
        entity_type="leave_balances",
        entity_id=str(bal.id),
        action="refund_on_cancel",
        before_json=before_bal,
        after_json=model_to_dict(bal),
    )
    return req


def list_leave_requests(
    db: Session,
    *,
    status: str | None = None,
    employee_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[LeaveRequest]:
    stmt: Select[tuple[LeaveRequest]] = select(LeaveRequest)
    if status is not None:
        stmt = stmt.where(LeaveRequest.status == status)
    if employee_id is not None:
        stmt = stmt.where(LeaveRequest.employee_id == employee_id)

    stmt = stmt.order_by(LeaveRequest.id.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def credit_monthly_leave_balances(
    db: Session,
    *,
    year: int,
    month: int,
    policy_id: int | None = None,
    leave_type_id: int | None = None,
) -> dict:
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Invalid month")

    policy_stmt = select(LeavePolicy).where(LeavePolicy.is_active.is_(True))
    if policy_id is not None:
        policy_stmt = policy_stmt.where(LeavePolicy.id == policy_id)
    if leave_type_id is not None:
        policy_stmt = policy_stmt.where(
            LeavePolicy.leave_type_id == leave_type_id
        )

    policies = list(db.execute(policy_stmt).scalars().all())
    if not policies:
        raise HTTPException(
            status_code=404,
            detail="No matching active leave policy",
        )

    employees = list(
        db.execute(
            select(Employee).where(Employee.employment_status == "active")
        ).scalars().all()
    )

    credited_rows = 0
    for pol in policies:
        credit = float(pol.monthly_credit_days)
        if credit <= 0:
            continue

        for emp in employees:
            bal = _get_or_create_balance(
                db,
                employee_id=emp.id,
                leave_type_id=pol.leave_type_id,
            )
            before = model_to_dict(bal)
            new_value = float(bal.balance_days) + credit
            if pol.max_balance_days is not None:
                new_value = min(new_value, float(pol.max_balance_days))
            bal.balance_days = new_value
            db.add(bal)
            credited_rows += 1

            log_audit(
                db,
                entity_type="leave_balances",
                entity_id=str(bal.id),
                action=f"credit_{year:04d}-{month:02d}",
                before_json=before,
                after_json=model_to_dict(bal),
            )

    db.commit()

    return {
        "status": "ok",
        "year": year,
        "month": month,
        "policies": len(policies),
        "employees": len(employees),
        "credits_applied": credited_rows,
    }
