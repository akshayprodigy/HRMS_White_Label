from __future__ import annotations

import datetime as dt

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.core import Project
from app.db.models.hr_attendance import AttendanceEntry
from app.db.models.inventory import StockLedger
from app.db.models.projects_finance import ProjectDirectExpense, ProjectRevenue
from app.modules.projects_profitability.schemas import (
    LaborByEmployee,
    MaterialByItem,
    MoneyByCategory,
    ProjectProfitabilityPublic,
)

_ERR_DATE_RANGE = "date_from must be <= date_to"
_ERR_PROJECT_NOT_FOUND = "Project not found"


def _normalize_date_range(
    *,
    date_from: dt.date | None,
    date_to: dt.date | None,
    default_days: int = 30,
) -> tuple[dt.date, dt.date]:
    today = dt.date.today()

    out_to = date_to or today
    out_from = date_from or (out_to - dt.timedelta(days=default_days))

    if out_from > out_to:
        raise HTTPException(status_code=400, detail=_ERR_DATE_RANGE)

    return out_from, out_to


def _get_revenue(
    db: Session,
    *,
    project_id: int,
    date_from: dt.date,
    date_to: dt.date,
) -> tuple[float, list[MoneyByCategory]]:
    rows = list(
        db.execute(
            select(
                ProjectRevenue.category,
                func.coalesce(func.sum(ProjectRevenue.amount), 0),
            )
            .where(
                ProjectRevenue.project_id == project_id,
                ProjectRevenue.revenue_date >= date_from,
                ProjectRevenue.revenue_date <= date_to,
            )
            .group_by(ProjectRevenue.category)
            .order_by(ProjectRevenue.category.asc())
        ).all()
    )

    by_category = [
        MoneyByCategory(category=str(cat), amount=float(amt or 0))
        for cat, amt in rows
        if cat is not None
    ]
    total = float(sum(r.amount for r in by_category))
    return total, by_category


def _get_labor(
    db: Session,
    *,
    project_id: int,
    date_from: dt.date,
    date_to: dt.date,
) -> tuple[float, float, float, list[LaborByEmployee]]:
    tot_hours, tot_cost = db.execute(
        select(
            func.coalesce(func.sum(AttendanceEntry.hours), 0),
            func.coalesce(
                func.sum(AttendanceEntry.hours * AttendanceEntry.hourly_rate),
                0,
            ),
        ).where(
            AttendanceEntry.project_id == project_id,
            AttendanceEntry.work_date >= date_from,
            AttendanceEntry.work_date <= date_to,
        )
    ).one()

    hours_total = float(tot_hours or 0)
    cost_total = float(tot_cost or 0)
    avg_rate = 0.0 if hours_total <= 0 else cost_total / hours_total

    rows = list(
        db.execute(
            select(
                AttendanceEntry.employee_id,
                func.coalesce(func.sum(AttendanceEntry.hours), 0),
                func.coalesce(
                    func.sum(
                        AttendanceEntry.hours * AttendanceEntry.hourly_rate
                    ),
                    0,
                ),
            )
            .where(
                AttendanceEntry.project_id == project_id,
                AttendanceEntry.work_date >= date_from,
                AttendanceEntry.work_date <= date_to,
            )
            .group_by(AttendanceEntry.employee_id)
            .order_by(AttendanceEntry.employee_id.asc())
        ).all()
    )

    by_employee: list[LaborByEmployee] = []
    for employee_id, hours, cost in rows:
        h = float(hours or 0)
        c = float(cost or 0)
        by_employee.append(
            LaborByEmployee(
                employee_id=int(employee_id),
                hours=h,
                cost=c,
                avg_rate=(0.0 if h <= 0 else c / h),
            )
        )

    return hours_total, cost_total, float(avg_rate), by_employee


def _get_materials(
    db: Session,
    *,
    project_id: int,
    date_from: dt.date,
    date_to: dt.date,
) -> tuple[float, float, float, list[MaterialByItem]]:
    unit_cost0 = func.coalesce(StockLedger.unit_cost, 0)
    tot_qty, tot_cost = db.execute(
        select(
            func.coalesce(func.sum(StockLedger.qty_out), 0),
            func.coalesce(func.sum(StockLedger.qty_out * unit_cost0), 0),
        ).where(
            StockLedger.source_type == "issue",
            StockLedger.project_id == project_id,
            StockLedger.txn_date >= date_from,
            StockLedger.txn_date <= date_to,
        )
    ).one()

    qty_total = float(tot_qty or 0)
    cost_total = float(tot_cost or 0)
    avg_unit_cost = 0.0 if qty_total <= 0 else cost_total / qty_total

    rows = list(
        db.execute(
            select(
                StockLedger.item_id,
                func.coalesce(func.sum(StockLedger.qty_out), 0),
                func.coalesce(func.sum(StockLedger.qty_out * unit_cost0), 0),
            )
            .where(
                StockLedger.source_type == "issue",
                StockLedger.project_id == project_id,
                StockLedger.txn_date >= date_from,
                StockLedger.txn_date <= date_to,
            )
            .group_by(StockLedger.item_id)
            .order_by(StockLedger.item_id.asc())
        ).all()
    )

    by_item: list[MaterialByItem] = []
    for item_id, qty, cost in rows:
        if item_id is None:
            continue
        q = float(qty or 0)
        c = float(cost or 0)
        by_item.append(
            MaterialByItem(
                item_id=int(item_id),
                qty_issued=q,
                cost=c,
                avg_unit_cost=(0.0 if q <= 0 else c / q),
            )
        )

    return qty_total, cost_total, float(avg_unit_cost), by_item


def _get_direct_expenses(
    db: Session,
    *,
    project_id: int,
    date_from: dt.date,
    date_to: dt.date,
) -> tuple[float, list[MoneyByCategory]]:
    rows = list(
        db.execute(
            select(
                ProjectDirectExpense.category,
                func.coalesce(func.sum(ProjectDirectExpense.amount), 0),
            )
            .where(
                ProjectDirectExpense.project_id == project_id,
                ProjectDirectExpense.expense_date >= date_from,
                ProjectDirectExpense.expense_date <= date_to,
            )
            .group_by(ProjectDirectExpense.category)
            .order_by(ProjectDirectExpense.category.asc())
        ).all()
    )
    by_category = [
        MoneyByCategory(category=str(cat), amount=float(amt or 0))
        for cat, amt in rows
        if cat is not None
    ]
    total = float(sum(r.amount for r in by_category))
    return total, by_category


def get_project_profitability(
    db: Session,
    *,
    project_id: int,
    date_from: dt.date | None,
    date_to: dt.date | None,
) -> ProjectProfitabilityPublic:
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail=_ERR_PROJECT_NOT_FOUND)

    d_from, d_to = _normalize_date_range(date_from=date_from, date_to=date_to)

    revenue_total, revenue_by_category = _get_revenue(
        db,
        project_id=project_id,
        date_from=d_from,
        date_to=d_to,
    )
    (
        labor_hours_total,
        labor_cost_total,
        labor_avg_rate,
        labor_by_employee,
    ) = _get_labor(
        db,
        project_id=project_id,
        date_from=d_from,
        date_to=d_to,
    )
    (
        materials_qty_total,
        materials_cost_total,
        materials_avg_unit_cost,
        materials_by_item,
    ) = _get_materials(
        db,
        project_id=project_id,
        date_from=d_from,
        date_to=d_to,
    )
    direct_expenses_total, direct_expenses_by_category = _get_direct_expenses(
        db,
        project_id=project_id,
        date_from=d_from,
        date_to=d_to,
    )

    total_cost = float(
        labor_cost_total + materials_cost_total + direct_expenses_total
    )
    gross_profit = float(revenue_total - total_cost)
    gross_margin_percent = (
        0.0 if revenue_total <= 0 else (gross_profit / revenue_total) * 100.0
    )

    return ProjectProfitabilityPublic(
        project_id=project_id,
        date_from=d_from,
        date_to=d_to,
        revenue_total=revenue_total,
        revenue_by_category=revenue_by_category,
        labor_hours_total=labor_hours_total,
        labor_cost_total=labor_cost_total,
        labor_avg_rate=float(labor_avg_rate),
        labor_by_employee=labor_by_employee,
        materials_qty_total=materials_qty_total,
        materials_cost_total=materials_cost_total,
        materials_avg_unit_cost=float(materials_avg_unit_cost),
        materials_by_item=materials_by_item,
        direct_expenses_total=direct_expenses_total,
        direct_expenses_by_category=direct_expenses_by_category,
        total_cost=total_cost,
        gross_profit=gross_profit,
        gross_margin_percent=float(gross_margin_percent),
    )
