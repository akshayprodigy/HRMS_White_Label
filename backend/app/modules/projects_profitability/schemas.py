from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class ProfitabilityQuery(BaseModel):
    date_from: dt.date | None = None
    date_to: dt.date | None = None


class MoneyByCategory(BaseModel):
    category: str
    amount: float


class LaborByEmployee(BaseModel):
    employee_id: int
    hours: float
    cost: float
    avg_rate: float


class MaterialByItem(BaseModel):
    item_id: int
    qty_issued: float
    cost: float
    avg_unit_cost: float


class ProjectProfitabilityPublic(BaseModel):
    project_id: int
    date_from: dt.date
    date_to: dt.date

    revenue_total: float
    revenue_by_category: list[MoneyByCategory] = []

    labor_hours_total: float
    labor_cost_total: float
    labor_avg_rate: float
    labor_by_employee: list[LaborByEmployee] = []

    materials_qty_total: float
    materials_cost_total: float
    materials_avg_unit_cost: float
    materials_by_item: list[MaterialByItem] = []

    direct_expenses_total: float
    direct_expenses_by_category: list[MoneyByCategory] = []

    total_cost: float
    gross_profit: float
    gross_margin_percent: float = Field(
        description=(
            "gross_profit / revenue_total * 100, 0 when revenue_total=0"
        )
    )
