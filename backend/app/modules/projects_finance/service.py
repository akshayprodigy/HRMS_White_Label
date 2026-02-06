from __future__ import annotations

import datetime as dt

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import log_audit, model_to_dict
from app.db.models.core import Project
from app.db.models.projects_finance import ProjectDirectExpense, ProjectRevenue

_ERR_PROJECT_NOT_FOUND = "Project not found"


def create_project_direct_expense(
    db: Session,
    *,
    project_id: int,
    expense_date: dt.date,
    category: str,
    description: str | None,
    amount: float,
    vendor: str | None,
    reference_no: str | None,
    notes: str | None,
) -> ProjectDirectExpense:
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail=_ERR_PROJECT_NOT_FOUND)

    row = ProjectDirectExpense(
        project_id=project_id,
        expense_date=expense_date,
        category=category,
        description=description,
        amount=amount,
        vendor=vendor,
        reference_no=reference_no,
        notes=notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    log_audit(
        db,
        entity_type="project_direct_expenses",
        entity_id=str(row.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(row),
    )

    return row


def list_project_direct_expenses(
    db: Session,
    *,
    project_id: int,
    date_from: dt.date | None,
    date_to: dt.date | None,
    limit: int,
    offset: int,
) -> list[ProjectDirectExpense]:
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail=_ERR_PROJECT_NOT_FOUND)

    stmt = select(ProjectDirectExpense).where(
        ProjectDirectExpense.project_id == project_id
    )
    if date_from is not None:
        stmt = stmt.where(ProjectDirectExpense.expense_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(ProjectDirectExpense.expense_date <= date_to)

    stmt = stmt.order_by(
        ProjectDirectExpense.expense_date.desc(),
        ProjectDirectExpense.id.desc(),
    )
    stmt = stmt.limit(limit).offset(offset)

    return list(db.execute(stmt).scalars().all())


def create_project_revenue(
    db: Session,
    *,
    project_id: int,
    revenue_date: dt.date,
    category: str,
    description: str | None,
    amount: float,
    client: str | None,
    reference_no: str | None,
    notes: str | None,
) -> ProjectRevenue:
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail=_ERR_PROJECT_NOT_FOUND)

    row = ProjectRevenue(
        project_id=project_id,
        revenue_date=revenue_date,
        category=category,
        description=description,
        amount=amount,
        client=client,
        reference_no=reference_no,
        notes=notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    log_audit(
        db,
        entity_type="project_revenues",
        entity_id=str(row.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(row),
    )

    return row


def list_project_revenues(
    db: Session,
    *,
    project_id: int,
    date_from: dt.date | None,
    date_to: dt.date | None,
    limit: int,
    offset: int,
) -> list[ProjectRevenue]:
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail=_ERR_PROJECT_NOT_FOUND)

    stmt = select(ProjectRevenue).where(
        ProjectRevenue.project_id == project_id
    )
    if date_from is not None:
        stmt = stmt.where(ProjectRevenue.revenue_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(ProjectRevenue.revenue_date <= date_to)

    stmt = stmt.order_by(
        ProjectRevenue.revenue_date.desc(),
        ProjectRevenue.id.desc(),
    )
    stmt = stmt.limit(limit).offset(offset)

    return list(db.execute(stmt).scalars().all())
