from datetime import datetime, timezone, date as pydate
from typing import Optional, TYPE_CHECKING
from sqlalchemy import (
    String, Integer, ForeignKey, DateTime, Text, Date, Boolean
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User
    from .employee import Employee


class HolidayCalendar(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    date: Mapped[pydate] = mapped_column(Date, index=True)
    location: Mapped[str] = mapped_column(
        String(100), index=True
    )  # e.g., 'HQ', 'Remote', 'All'
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class PolicyDocument(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_url: Mapped[str] = mapped_column(String(512))
    version: Mapped[str] = mapped_column(String(20), default="1.0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    
    acknowledgements: Mapped[list["PolicyAcknowledgement"]] = relationship(
        "PolicyAcknowledgement", back_populates="policy"
    )


class PolicyAcknowledgement(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    policy_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("policydocument.id", ondelete="CASCADE"),
        index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    policy: Mapped["PolicyDocument"] = relationship(
        "PolicyDocument", back_populates="acknowledgements"
    )
    user: Mapped["User"] = relationship("User")


class LetterType:
    OFFER = "offer_letter"
    APPOINTMENT = "appointment_letter"
    CONFIRMATION = "confirmation_letter"
    RELEASE = "release_experience_order"
    RELIEVING = "relieving_letter"
    PROMOTION = "promotion_letter"
    SALARY_REVISION = "salary_revision_letter"


class EmployeeLetter(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employee.id", ondelete="CASCADE"), index=True
    )
    letter_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    reference_number: Mapped[Optional[str]] = mapped_column(String(50), unique=True, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    generated_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE")
    )
    file_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    # Store template data as JSON for regeneration
    template_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")

    employee: Mapped["Employee"] = relationship("Employee")
    generated_by: Mapped["User"] = relationship("User")
