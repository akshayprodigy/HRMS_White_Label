from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.modules.projects_finance.schemas import (
    ProjectDirectExpenseCreate,
    ProjectDirectExpensePublic,
    ProjectFinanceListQuery,
    ProjectRevenueCreate,
    ProjectRevenuePublic,
)
from app.modules.projects_finance.service import (
    create_project_direct_expense,
    create_project_revenue,
    list_project_direct_expenses,
    list_project_revenues,
)

router = APIRouter(tags=["Projects • Finance"])


@router.post(
    "/{project_id}/direct-expenses",
    response_model=ProjectDirectExpensePublic,
    dependencies=[Depends(require_permissions({"projects.finance.write"}))],
)
def projects_create_direct_expense(
    project_id: int,
    payload: ProjectDirectExpenseCreate,
    db: Session = Depends(get_db),
) -> ProjectDirectExpensePublic:
    row = create_project_direct_expense(
        db,
        project_id=project_id,
        expense_date=payload.expense_date,
        category=payload.category,
        description=payload.description,
        amount=payload.amount,
        vendor=payload.vendor,
        reference_no=payload.reference_no,
        notes=payload.notes,
    )
    return ProjectDirectExpensePublic.model_validate(row)


@router.get(
    "/{project_id}/direct-expenses",
    response_model=list[ProjectDirectExpensePublic],
    dependencies=[Depends(require_permissions({"projects.finance.read"}))],
)
def projects_list_direct_expenses(
    project_id: int,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[ProjectDirectExpensePublic]:
    q = ProjectFinanceListQuery(
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    rows = list_project_direct_expenses(
        db,
        project_id=project_id,
        date_from=q.date_from,
        date_to=q.date_to,
        limit=q.limit,
        offset=q.offset,
    )
    return [ProjectDirectExpensePublic.model_validate(r) for r in rows]


@router.post(
    "/{project_id}/revenues",
    response_model=ProjectRevenuePublic,
    dependencies=[Depends(require_permissions({"projects.finance.write"}))],
)
def projects_create_revenue(
    project_id: int,
    payload: ProjectRevenueCreate,
    db: Session = Depends(get_db),
) -> ProjectRevenuePublic:
    row = create_project_revenue(
        db,
        project_id=project_id,
        revenue_date=payload.revenue_date,
        category=payload.category,
        description=payload.description,
        amount=payload.amount,
        client=payload.client,
        reference_no=payload.reference_no,
        notes=payload.notes,
    )
    return ProjectRevenuePublic.model_validate(row)


@router.get(
    "/{project_id}/revenues",
    response_model=list[ProjectRevenuePublic],
    dependencies=[Depends(require_permissions({"projects.finance.read"}))],
)
def projects_list_revenues(
    project_id: int,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[ProjectRevenuePublic]:
    q = ProjectFinanceListQuery(
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    rows = list_project_revenues(
        db,
        project_id=project_id,
        date_from=q.date_from,
        date_to=q.date_to,
        limit=q.limit,
        offset=q.offset,
    )
    return [ProjectRevenuePublic.model_validate(r) for r in rows]
