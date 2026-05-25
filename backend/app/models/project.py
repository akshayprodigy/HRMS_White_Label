from typing import TYPE_CHECKING, Optional, List
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text, Float, Enum, Numeric
from sqlalchemy.orm import (
    Mapped, mapped_column, relationship, declared_attr
)
from datetime import datetime, timezone
import enum
from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User
    from .task import Task
    from .bd import Lead, Account
    from .project_document import ProjectDocument
    from .functional_area import FunctionalArea

PROJECT_ID_FK = "project.id"


class CostChangeStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CLARIFICATION = "needs_clarification"


class Project(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    code: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active"
    )  # active, archived
    
    lead_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("lead.id", ondelete="SET NULL"), nullable=True
    )

    client_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("account.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    parent_project_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("project.id", ondelete="SET NULL"), nullable=True, index=True
    )

    functional_area_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("functional_area.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    lead: Mapped[Optional["Lead"]] = relationship()
    client: Mapped[Optional["Account"]] = relationship(foreign_keys=[client_id])

    parent_project: Mapped[Optional["Project"]] = relationship(
        "Project", remote_side="Project.id", foreign_keys="Project.parent_project_id"
    )

    functional_area: Mapped[Optional["FunctionalArea"]] = relationship(
        foreign_keys=[functional_area_id]
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    
    members: Mapped[List["ProjectMember"]] = relationship(
        back_populates="project"
    )
    documents: Mapped[List["ProjectDocument"]] = relationship(
        "ProjectDocument", back_populates="project",
        cascade="all, delete-orphan",
    )
    tasks: Mapped[List["Task"]] = relationship(back_populates="project")
    milestones: Mapped[List["Milestone"]] = relationship(
        back_populates="project"
    )
    cost_baselines: Mapped[List["CostBaseline"]] = relationship(
        back_populates="project"
    )
    cost_change_requests: Mapped[List["CostChangeRequest"]] = relationship(
        back_populates="project"
    )


class ProjectMember(Base):
    __tablename__ = "project_member"  # type: ignore

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(PROJECT_ID_FK, ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(
        String(20), default="member"
    )  # owner, manager, member
    
    project: Mapped["Project"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship()


class Milestone(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(PROJECT_ID_FK, ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, completed, delayed
    
    project: Mapped["Project"] = relationship(back_populates="milestones")


class CostBaseline(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(PROJECT_ID_FK, ondelete="CASCADE"), index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    budget_hours: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    
    project: Mapped["Project"] = relationship(back_populates="cost_baselines")


class CostChangeRequest(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(PROJECT_ID_FK, ondelete="CASCADE"), index=True
    )
    baseline_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("costbaseline.id"), nullable=True
    )
    baseline_amount: Mapped[float] = mapped_column(Float, nullable=False)
    proposed_amount: Mapped[float] = mapped_column(Float, nullable=False)
    percent_change: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[CostChangeStatus] = mapped_column(
        Enum(CostChangeStatus), default=CostChangeStatus.SUBMITTED
    )
    created_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    
    project: Mapped["Project"] = relationship(
        back_populates="cost_change_requests"
    )
    created_by: Mapped["User"] = relationship()
