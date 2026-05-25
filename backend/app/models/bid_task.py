import enum
from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
    Numeric,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


if TYPE_CHECKING:
    from .user import User
    from .bd import Lead, EstimateVersion, LeadDocument


FK_USER = "user.id"
ONDELETE_SET_NULL = "SET NULL"
CASCADE_DELETE_ORPHAN = "all, delete-orphan"


class LeadBidTaskReviewStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REVISION_REQUESTED = "revision_requested"


class BidLineItem(Base):
    __tablename__ = "bid_line_item"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class LeadBidTask(Base):
    __tablename__ = "lead_bid_task"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lead.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    bd_estimated_hours: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    bd_estimated_cost: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    delivery_pm_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey(FK_USER, ondelete=ONDELETE_SET_NULL),
        index=True,
        nullable=True,
    )

    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey(FK_USER, ondelete=ONDELETE_SET_NULL),
        index=True,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    lead: Mapped["Lead"] = relationship("Lead")
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_id]
    )
    delivery_pm_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[delivery_pm_user_id]
    )

    assignments: Mapped[List["LeadBidTaskAssignment"]] = relationship(
        back_populates="bid_task",
        cascade=CASCADE_DELETE_ORPHAN,
    )


class LeadBidTaskAssignment(Base):
    __tablename__ = "lead_bid_task_assignment"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    bid_task_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lead_bid_task.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    pm_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(FK_USER, ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    assigned_by_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey(FK_USER, ondelete=ONDELETE_SET_NULL),
        index=True,
        nullable=True,
    )

    deadline: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    bid_task: Mapped["LeadBidTask"] = relationship(
        back_populates="assignments"
    )
    pm_user: Mapped["User"] = relationship("User", foreign_keys=[pm_user_id])
    assigned_by: Mapped["User"] = relationship(
        "User", foreign_keys=[assigned_by_id]
    )

    reviews: Mapped[List["LeadBidTaskReview"]] = relationship(
        back_populates="assignment",
        cascade=CASCADE_DELETE_ORPHAN,
        order_by="LeadBidTaskReview.revision_number",
    )

    __table_args__ = (
        UniqueConstraint(
            "bid_task_id",
            "pm_user_id",
            name="uq_lead_bid_task_assignment_task_pm",
        ),
    )


class LeadBidTaskAssignmentDocument(Base):
    __tablename__ = "bid_task_assignment_document"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    assignment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lead_bid_task_assignment.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    lead_document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lead_document.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    assignment: Mapped["LeadBidTaskAssignment"] = relationship(
        "LeadBidTaskAssignment"
    )
    lead_document: Mapped["LeadDocument"] = relationship("LeadDocument")

    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "lead_document_id",
            name="uq_bid_task_assignment_document_assignment_doc",
        ),
    )


class LeadBidTaskReview(Base):
    __tablename__ = "lead_bid_task_review"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    assignment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lead_bid_task_assignment.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    estimate_version_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("estimateversion.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    revision_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    status: Mapped[LeadBidTaskReviewStatus] = mapped_column(
        SQLEnum(LeadBidTaskReviewStatus, values_callable=lambda x: [e.value for e in x]),
        default=LeadBidTaskReviewStatus.DRAFT,
        index=True,
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(10), default="INR", nullable=False
    )
    total_hours: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)
    total_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)

    pm_notes: Mapped[Optional[str]] = mapped_column(Text)
    bd_notes: Mapped[Optional[str]] = mapped_column(Text)

    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey(FK_USER, ondelete=ONDELETE_SET_NULL),
        index=True,
        nullable=True,
    )

    previous_review_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("lead_bid_task_review.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    assignment: Mapped["LeadBidTaskAssignment"] = relationship(
        back_populates="reviews"
    )
    estimate_version: Mapped["EstimateVersion"] = relationship(
        "EstimateVersion"
    )
    created_by: Mapped["User"] = relationship(
        "User", foreign_keys=[created_by_id]
    )

    previous_review: Mapped[Optional["LeadBidTaskReview"]] = relationship(
        "LeadBidTaskReview",
        remote_side=[id],
    )

    lines: Mapped[List["LeadBidTaskReviewLine"]] = relationship(
        back_populates="review",
        cascade=CASCADE_DELETE_ORPHAN,
        order_by="LeadBidTaskReviewLine.sort_order",
    )

    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "estimate_version_id",
            "revision_number",
            name="uq_lead_bid_task_review_assignment_version_revision",
        ),
    )


class LeadBidTaskReviewLine(Base):
    __tablename__ = "lead_bid_task_review_line"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    review_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lead_bid_task_review.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    hours: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)
    cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    review: Mapped["LeadBidTaskReview"] = relationship(back_populates="lines")
