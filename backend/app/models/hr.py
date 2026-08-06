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
    CUSTOM = "custom"
    BIRTHDAY = "birthday_greeting"
    WORK_ANNIVERSARY = "work_anniversary_letter"


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


class LetterTemplate(Base):
    """HR-authored custom letter template. Body holds free text with
    {{token}} placeholders that are filled from the employee record at
    render time (see services/letter_template.py). Rendered output is
    persisted as an EmployeeLetter row with letter_type='custom' so it
    reuses the existing letters list / download / send flow unchanged."""
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), index=True, nullable=False)
    category: Mapped[str] = mapped_column(
        String(50), index=True, nullable=False, default="custom"
    )
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    created_by: Mapped[Optional["User"]] = relationship("User")
