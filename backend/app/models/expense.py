"""Expense + Travel models — first consumer of the generic chain engine.

Money-typed columns store PAISE (int). Two-line rule: an ExpenseClaim is a
header; multi-line ExpenseLineItem rows carry the actual receipts. Status
mirrors the linked ChainedApprovalInstance so the frontend can render a
single value.
"""
from __future__ import annotations

from datetime import datetime, date as date_type, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User


SET_NULL = "SET NULL"
CASCADE = "CASCADE"


class ExpenseClaimStatus:
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    REIMBURSED = "reimbursed"
    PUSHED_TO_PAYROLL = "pushed_to_payroll"
    CANCELLED = "cancelled"


class TravelRequestStatus:
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReimbursementMode:
    DIRECT = "direct"        # Finance marks reimbursed with a reference.
    PAYROLL = "payroll"      # Injected as a non-taxable payroll line.


# ---------------------------------------------------------------------------
# Master data — HR-configurable
# ---------------------------------------------------------------------------


class ExpenseCategory(Base):
    __tablename__ = "expense_category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(
        String(80), nullable=False, unique=True, index=True
    )
    code: Mapped[Optional[str]] = mapped_column(String(20), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Policy hints (paise). None means no cap enforced.
    per_diem_cap_paise: Mapped[Optional[int]] = mapped_column(Integer)
    receipt_required_above_paise: Mapped[Optional[int]] = mapped_column(
        Integer
    )
    # "warn" or "block" per policy config.
    policy_mode: Mapped[str] = mapped_column(String(8), default="warn")
    notes: Mapped[Optional[str]] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------


class ExpenseClaim(Base):
    __tablename__ = "expense_claim"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employee.id", ondelete=CASCADE), index=True,
    )
    submitter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=SET_NULL),
        nullable=True, index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    claim_date: Mapped[date_type] = mapped_column(
        Date, nullable=False, index=True
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("project.id", ondelete=SET_NULL),
    )
    cost_center: Mapped[Optional[str]] = mapped_column(String(80))
    total_amount_paise: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(
        String(24), default=ExpenseClaimStatus.DRAFT, index=True,
    )
    approval_instance_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("chained_approval_instance.id", ondelete=SET_NULL),
        nullable=True, index=True,
    )
    # Populated when reimbursed / pushed to payroll.
    reimbursement_mode: Mapped[Optional[str]] = mapped_column(String(16))
    reimbursed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    reimbursed_reference: Mapped[Optional[str]] = mapped_column(String(120))
    payroll_run_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("payrollrun.id", ondelete=SET_NULL),
        nullable=True, index=True,
    )

    linked_travel_request_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("travel_request.id", ondelete=SET_NULL),
        nullable=True, index=True,
    )
    policy_flags_json: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    line_items: Mapped[List["ExpenseLineItem"]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        order_by="ExpenseLineItem.id",
    )


class ExpenseLineItem(Base):
    __tablename__ = "expense_line_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    claim_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("expense_claim.id", ondelete=CASCADE), index=True,
    )
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("expense_category.id", ondelete=SET_NULL),
        nullable=True, index=True,
    )
    amount_paise: Mapped[int] = mapped_column(Integer, default=0)
    line_date: Mapped[Optional[date_type]] = mapped_column(Date)
    description: Mapped[Optional[str]] = mapped_column(Text)
    receipt_url: Mapped[Optional[str]] = mapped_column(String(500))
    is_out_of_policy: Mapped[bool] = mapped_column(Boolean, default=False)
    policy_flag_reason: Mapped[Optional[str]] = mapped_column(String(240))

    claim: Mapped[ExpenseClaim] = relationship(back_populates="line_items")


# ---------------------------------------------------------------------------
# Travel
# ---------------------------------------------------------------------------


class TravelRequest(Base):
    __tablename__ = "travel_request"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employee.id", ondelete=CASCADE), index=True,
    )
    submitter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=SET_NULL),
        nullable=True, index=True,
    )
    purpose: Mapped[str] = mapped_column(String(240), nullable=False)
    from_city: Mapped[str] = mapped_column(String(120))
    to_city: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    end_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    estimated_cost_paise: Mapped[int] = mapped_column(Integer, default=0)
    advance_requested_paise: Mapped[int] = mapped_column(Integer, default=0)
    advance_paid_paise: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(
        String(16), default=TravelRequestStatus.DRAFT, index=True,
    )
    approval_instance_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("chained_approval_instance.id", ondelete=SET_NULL),
        nullable=True, index=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
