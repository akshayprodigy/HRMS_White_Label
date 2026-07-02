"""Generic Approval-Chain models.

Additive-only. The existing ApprovalItem / ApprovalStep pair
(app/models/approval.py) drives the leave / OT / revision flows and is
NOT touched here. This module introduces a *configurable* chain builder
that new consumers (Expense first, more later) plug into.

Money-typed columns store paise (int). All string-typed status/enums
follow the codebase pattern (plain str constants, not sqlalchemy Enum).
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


# ---------------------------------------------------------------------------
# Enums (plain str constants — matches codebase convention)
# ---------------------------------------------------------------------------


class ChainEntityType:
    EXPENSE = "expense"
    TRAVEL = "travel"
    SHIFT_CHANGE = "shift_change"
    # future consumers add strings here (do NOT re-use for existing
    # leave/OT/revision flows — those live on the legacy engine).


class ApproverType:
    REPORTING_MANAGER = "reporting_manager"
    DEPT_HEAD = "dept_head"
    ROLE = "role"
    SPECIFIC_USER = "specific_user"
    FINANCE = "finance"


class ParallelRule:
    ALL = "all"
    ANY = "any"


class StepMode:
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class ChainedApprovalStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class StepInstanceStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    AUTO_APPROVED = "auto_approved"


class ApproverActionResult:
    APPROVE = "approve"
    REJECT = "reject"


# ---------------------------------------------------------------------------
# Chain definition — HR-configurable
# ---------------------------------------------------------------------------


class ApprovalChain(Base):
    """A named, effective-dated approval chain for a single entity type."""
    __tablename__ = "approval_chain"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    entity_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )
    department: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    effective_from: Mapped[date_type] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[date_type]] = mapped_column(Date)

    # Optional chain-level auto-approve short-circuit. Amounts in paise.
    auto_approve_below_paise: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    skip_if_same_person: Mapped[bool] = mapped_column(Boolean, default=True)

    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=SET_NULL)
    )

    steps: Mapped[List["ApprovalChainStep"]] = relationship(
        back_populates="chain",
        cascade="all, delete-orphan",
        order_by="ApprovalChainStep.step_order",
    )

    __table_args__ = (
        UniqueConstraint(
            "name", "entity_type", name="uq_approval_chain_name_entity"
        ),
    )


class ApprovalChainStep(Base):
    """A single ordered step inside a chain."""
    __tablename__ = "approval_chain_step"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    chain_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("approval_chain.id", ondelete=CASCADE),
        index=True,
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # role name (for ROLE) or user id (for SPECIFIC_USER). Free text so the
    # engine can pick the right resolver.
    approver_ref: Mapped[Optional[str]] = mapped_column(String(120))

    mode: Mapped[str] = mapped_column(
        String(16), default=StepMode.SEQUENTIAL
    )
    parallel_rule: Mapped[str] = mapped_column(
        String(8), default=ParallelRule.ALL
    )

    # Amount band (paise) that gates whether this step applies.
    min_amount_paise: Mapped[Optional[int]] = mapped_column(Integer)
    max_amount_paise: Mapped[Optional[int]] = mapped_column(Integer)

    # skip_if_same_person is a chain-level default; a step can force it too.
    skip_if_same_person: Mapped[bool] = mapped_column(Boolean, default=False)
    # If the resolved approver has been absent > N days, hop to the next
    # step. None = never delegate.
    skip_if_absent_days: Mapped[Optional[int]] = mapped_column(Integer)

    label: Mapped[Optional[str]] = mapped_column(String(120))

    chain: Mapped[ApprovalChain] = relationship(back_populates="steps")

    __table_args__ = (
        UniqueConstraint(
            "chain_id", "step_order", name="uq_chain_step_order"
        ),
    )


# ---------------------------------------------------------------------------
# Runtime — instance per request
# ---------------------------------------------------------------------------


class ChainedApprovalInstance(Base):
    """One approval instance materialized from a chain for a submitted
    entity (an ExpenseClaim, a TravelRequest, ...).
    """
    __tablename__ = "chained_approval_instance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    chain_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("approval_chain.id", ondelete=SET_NULL),
        nullable=True,
    )
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)

    submitter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=SET_NULL),
        nullable=True, index=True,
    )
    amount_paise: Mapped[int] = mapped_column(Integer, default=0)
    context_json: Mapped[dict] = mapped_column(JSON, default=dict)

    status: Mapped[str] = mapped_column(
        String(16), default=ChainedApprovalStatus.PENDING, index=True,
    )
    current_step_order: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    finalized_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    step_instances: Mapped[List["ChainedApprovalStepInstance"]] = relationship(
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="ChainedApprovalStepInstance.step_order",
    )


class ChainedApprovalStepInstance(Base):
    """One materialized step, may fan out to multiple approvers (parallel).
    Each row here corresponds to one (step, approver_user) pair — for
    parallel steps we insert multiple rows sharing step_order.
    """
    __tablename__ = "chained_approval_step_instance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    instance_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chained_approval_instance.id", ondelete=CASCADE),
        index=True,
    )
    step_order: Mapped[int] = mapped_column(Integer, index=True)
    approver_type: Mapped[str] = mapped_column(String(32))
    approver_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=SET_NULL), index=True,
    )
    mode: Mapped[str] = mapped_column(String(16))
    parallel_rule: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(
        String(16), default=StepInstanceStatus.PENDING, index=True,
    )
    comment: Mapped[Optional[str]] = mapped_column(String(500))
    actioned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    label: Mapped[Optional[str]] = mapped_column(String(120))

    instance: Mapped[ChainedApprovalInstance] = relationship(
        back_populates="step_instances"
    )
