from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import AuditMixin

_CASCADE_ALL_DELETE_ORPHAN = "all, delete-orphan"
_FK_EMPLOYEES_ID = "employees.id"
_FK_LEAVE_TYPES_ID = "leave_types.id"
_FK_USERS_ID = "users.id"


class Employee(AuditMixin, Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    employee_code: Mapped[str | None] = mapped_column(
        sa.String(50),
        nullable=True,
    )

    first_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    last_name: Mapped[str | None] = mapped_column(
        sa.String(100),
        nullable=True,
    )

    email: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(sa.String(30), nullable=True)

    date_of_birth: Mapped[dt.date | None] = mapped_column(
        sa.Date(),
        nullable=True,
    )
    gender: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)

    address_line1: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
    )
    address_line2: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
    )
    city: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(
        sa.String(20),
        nullable=True,
    )
    country: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)

    bank_name: Mapped[str | None] = mapped_column(
        sa.String(150),
        nullable=True,
    )
    bank_account_number: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
    )
    bank_ifsc: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    bank_branch: Mapped[str | None] = mapped_column(
        sa.String(150),
        nullable=True,
    )

    emergency_contact_name: Mapped[str | None] = mapped_column(
        sa.String(150),
        nullable=True,
    )
    emergency_contact_relation: Mapped[str | None] = mapped_column(
        sa.String(80), nullable=True
    )
    emergency_contact_phone: Mapped[str | None] = mapped_column(
        sa.String(30),
        nullable=True,
    )

    employment_type: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    employment_status: Mapped[str] = mapped_column(
        sa.String(30),
        nullable=False,
    )

    joining_date: Mapped[dt.date] = mapped_column(sa.Date(), nullable=False)
    exit_date: Mapped[dt.date | None] = mapped_column(sa.Date(), nullable=True)

    documents: Mapped[list[EmployeeDocument]] = relationship(
        back_populates="employee",
        cascade=_CASCADE_ALL_DELETE_ORPHAN,
    )
    assets: Mapped[list[EmployeeAsset]] = relationship(
        back_populates="employee",
        cascade=_CASCADE_ALL_DELETE_ORPHAN,
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "employee_code",
            name="uq_employees_employee_code",
        ),
        sa.Index("ix_employees_email", "email"),
        sa.Index("ix_employees_phone", "phone"),
        sa.Index("ix_employees_employment_status", "employment_status"),
    )


class EmployeeDocument(AuditMixin, Base):
    __tablename__ = "employee_documents"

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

    document_type: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    title: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    file_ref: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(
        sa.String(100),
        nullable=True,
    )
    issued_on: Mapped[dt.date | None] = mapped_column(sa.Date(), nullable=True)
    expires_on: Mapped[dt.date | None] = mapped_column(
        sa.Date(),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)

    employee: Mapped[Employee] = relationship(back_populates="documents")

    __table_args__ = (
        sa.Index("ix_employee_documents_employee_id", "employee_id"),
        sa.Index("ix_employee_documents_document_type", "document_type"),
    )


class EmployeeAsset(AuditMixin, Base):
    __tablename__ = "employee_assets"

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

    asset_category: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    asset_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    asset_tag: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)

    issued_on: Mapped[dt.date] = mapped_column(sa.Date(), nullable=False)
    returned_on: Mapped[dt.date | None] = mapped_column(
        sa.Date(),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)

    employee: Mapped[Employee] = relationship(back_populates="assets")

    __table_args__ = (
        sa.Index("ix_employee_assets_employee_id", "employee_id"),
        sa.Index("ix_employee_assets_asset_category", "asset_category"),
    )


class LeaveType(AuditMixin, Base):
    __tablename__ = "leave_types"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    code: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("1"),
    )

    policies: Mapped[list[LeavePolicy]] = relationship(
        back_populates="leave_type",
        cascade=_CASCADE_ALL_DELETE_ORPHAN,
    )

    __table_args__ = (
        sa.UniqueConstraint("code", name="uq_leave_types_code"),
        sa.Index("ix_leave_types_is_active", "is_active"),
    )


class LeavePolicy(AuditMixin, Base):
    __tablename__ = "leave_policies"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    leave_type_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_LEAVE_TYPES_ID),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(sa.String(150), nullable=False)
    monthly_credit_days: Mapped[float] = mapped_column(
        sa.Numeric(10, 2),
        nullable=False,
        server_default=sa.text("0"),
    )
    max_balance_days: Mapped[float | None] = mapped_column(
        sa.Numeric(10, 2),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("1"),
    )
    notes: Mapped[str | None] = mapped_column(
        sa.String(500),
        nullable=True,
    )

    leave_type: Mapped[LeaveType] = relationship(back_populates="policies")

    __table_args__ = (
        sa.Index("ix_leave_policies_leave_type_id", "leave_type_id"),
        sa.Index("ix_leave_policies_is_active", "is_active"),
    )


class LeaveBalance(AuditMixin, Base):
    __tablename__ = "leave_balances"

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
    leave_type_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_LEAVE_TYPES_ID),
        nullable=False,
    )

    balance_days: Mapped[float] = mapped_column(
        sa.Numeric(10, 2),
        nullable=False,
        server_default=sa.text("0"),
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "employee_id",
            "leave_type_id",
            name="uq_leave_balances_employee_leave_type",
        ),
        sa.Index("ix_leave_balances_employee_id", "employee_id"),
        sa.Index("ix_leave_balances_leave_type_id", "leave_type_id"),
    )


class LeaveRequest(AuditMixin, Base):
    __tablename__ = "leave_requests"

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
    leave_type_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_LEAVE_TYPES_ID),
        nullable=False,
    )

    date_from: Mapped[dt.date] = mapped_column(sa.Date(), nullable=False)
    date_to: Mapped[dt.date] = mapped_column(sa.Date(), nullable=False)
    days: Mapped[float] = mapped_column(sa.Numeric(10, 2), nullable=False)

    reason: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False)

    applied_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    decided_at: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(),
        nullable=True,
    )
    decided_by_user_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_USERS_ID),
        nullable=True,
    )
    decision_comment: Mapped[str | None] = mapped_column(
        sa.String(500),
        nullable=True,
    )

    __table_args__ = (
        sa.Index("ix_leave_requests_employee_id", "employee_id"),
        sa.Index("ix_leave_requests_leave_type_id", "leave_type_id"),
        sa.Index("ix_leave_requests_status", "status"),
        sa.Index("ix_leave_requests_date_from", "date_from"),
        sa.Index("ix_leave_requests_date_to", "date_to"),
    )


class HolidayCalendar(AuditMixin, Base):
    __tablename__ = "holiday_calendars"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    holiday_date: Mapped[dt.date] = mapped_column(sa.Date(), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(150), nullable=False)
    is_optional: Mapped[bool] = mapped_column(
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("0"),
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "holiday_date",
            name="uq_holiday_calendars_holiday_date",
        ),
        sa.Index("ix_holiday_calendars_holiday_date", "holiday_date"),
    )
