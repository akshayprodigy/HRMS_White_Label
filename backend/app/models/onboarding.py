from datetime import datetime, timezone
import enum
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text, Enum, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User
    from .recruitment import Applicant

class OnboardingStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class OnboardingProcess(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    applicant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("applicant.id"), unique=True
    )
    status: Mapped[OnboardingStatus] = mapped_column(
        Enum(OnboardingStatus), default=OnboardingStatus.PENDING
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    current_step: Mapped[int] = mapped_column(Integer, default=1)
    
    applicant: Mapped["Applicant"] = relationship("Applicant")
    tasks: Mapped[List["OnboardingTask"]] = relationship(
        "OnboardingTask", back_populates="process", cascade="all, delete-orphan"
    )

class OnboardingTask(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    process_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("onboardingprocess.id", ondelete="CASCADE"), index=True
    )
    step_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[OnboardingStatus] = mapped_column(
        Enum(OnboardingStatus), default=OnboardingStatus.PENDING
    )
    actor_role: Mapped[str] = mapped_column(String(100)) # e.g. 'HR', 'IT', 'Manager'
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id"), nullable=True
    )

    process: Mapped["OnboardingProcess"] = relationship(
        "OnboardingProcess", back_populates="tasks"
    )
