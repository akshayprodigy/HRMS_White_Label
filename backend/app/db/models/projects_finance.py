from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import AuditMixin

_FK_PROJECTS_ID = "projects.id"


class ProjectDirectExpense(AuditMixin, Base):
    __tablename__ = "project_direct_expenses"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    project_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_PROJECTS_ID),
        nullable=False,
    )

    expense_date: Mapped[dt.date] = mapped_column(sa.Date(), nullable=False)
    category: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
    )
    amount: Mapped[float] = mapped_column(sa.Numeric(14, 2), nullable=False)

    vendor: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    reference_no: Mapped[str | None] = mapped_column(
        sa.String(80),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)

    __table_args__ = (
        sa.Index("ix_project_direct_expenses_project_id", "project_id"),
        sa.Index("ix_project_direct_expenses_expense_date", "expense_date"),
        sa.Index(
            "ix_project_direct_expenses_project_id_expense_date",
            "project_id",
            "expense_date",
        ),
    )


class ProjectRevenue(AuditMixin, Base):
    __tablename__ = "project_revenues"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    project_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_PROJECTS_ID),
        nullable=False,
    )

    revenue_date: Mapped[dt.date] = mapped_column(sa.Date(), nullable=False)
    category: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
    )
    amount: Mapped[float] = mapped_column(sa.Numeric(14, 2), nullable=False)

    client: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    reference_no: Mapped[str | None] = mapped_column(
        sa.String(80),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)

    __table_args__ = (
        sa.Index("ix_project_revenues_project_id", "project_id"),
        sa.Index("ix_project_revenues_revenue_date", "revenue_date"),
        sa.Index(
            "ix_project_revenues_project_id_revenue_date",
            "project_id",
            "revenue_date",
        ),
    )
