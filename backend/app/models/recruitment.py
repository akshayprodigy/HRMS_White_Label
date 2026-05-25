from datetime import datetime, timezone
import enum
from typing import Optional, TYPE_CHECKING, List
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text, Enum, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User


class RequisitionPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class RequisitionStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELED = "canceled"


class EmploymentType(str, enum.Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERN = "intern"


class ApplicantStatus(str, enum.Enum):
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW = "interview"
    OFFERED = "offered"
    HIRED = "hired"
    REJECTED = "rejected"


class ManpowerRequisition(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    req_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    department: Mapped[str] = mapped_column(String(100), index=True)
    
    positions_count: Mapped[int] = mapped_column(Integer, default=1)
    priority: Mapped[RequisitionPriority] = mapped_column(
        Enum(RequisitionPriority), default=RequisitionPriority.MEDIUM
    )
    employment_type: Mapped[EmploymentType] = mapped_column(
        Enum(EmploymentType), default=EmploymentType.FULL_TIME
    )
    
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # e.g. "Replacement", "New Project"
    budget_range: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    job_description: Mapped[str] = mapped_column(Text)
    qualifications: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    status: Mapped[RequisitionStatus] = mapped_column(
        Enum(RequisitionStatus), default=RequisitionStatus.DRAFT
    )
    
    creator_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    creator: Mapped["User"] = relationship("User", foreign_keys=[creator_id])
    applicants: Mapped[List["Applicant"]] = relationship("Applicant", back_populates="requisition")


class Applicant(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    requisition_id: Mapped[int] = mapped_column(Integer, ForeignKey("manpowerrequisition.id"))
    
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    resume_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[ApplicantStatus] = mapped_column(Enum(ApplicantStatus), default=ApplicantStatus.APPLIED)
    
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    experience_years: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    requisition: Mapped["ManpowerRequisition"] = relationship("ManpowerRequisition", back_populates="applicants")
    interviews: Mapped[List["Interview"]] = relationship("Interview", back_populates="applicant")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Interview(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    applicant_id: Mapped[int] = mapped_column(Integer, ForeignKey("applicant.id"))
    
    interview_type: Mapped[str] = mapped_column(String(50), default="technical")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    interviewer_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"))
    
    round_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), default="scheduled")
    
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Briefing/Notes
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Post-interview
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    applicant: Mapped["Applicant"] = relationship("Applicant", back_populates="interviews")
    interviewer: Mapped["User"] = relationship("User")
