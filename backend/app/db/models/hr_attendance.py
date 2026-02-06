from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import AuditMixin

_FK_EMPLOYEES_ID = "employees.id"
_FK_PROJECTS_ID = "projects.id"


class AttendanceEntry(AuditMixin, Base):
    __tablename__ = "attendance_entries"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    employee_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_EMPLOYEES_ID),
        nullable=False,
    )
    project_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_PROJECTS_ID),
        nullable=False,
    )

    work_date: Mapped[dt.date] = mapped_column(sa.Date(), nullable=False)

    hours: Mapped[float] = mapped_column(sa.Numeric(8, 2), nullable=False)
    hourly_rate: Mapped[float] = mapped_column(
        sa.Numeric(14, 2),
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)

    __table_args__ = (
        sa.Index(
            "ix_attendance_entries_project_id_work_date",
            "project_id",
            "work_date",
        ),
        sa.Index(
            "ix_attendance_entries_employee_id_work_date",
            "employee_id",
            "work_date",
        ),
    )
