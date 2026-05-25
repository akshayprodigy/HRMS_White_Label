import enum
from datetime import datetime, date, timezone
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import (
    String, Integer, ForeignKey, DateTime, Text, Enum as SQLEnum,
    Float, Date, Numeric, JSON, LargeBinary
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base


if TYPE_CHECKING:
    from .user import User


FK_ACCOUNT = "account.id"
FK_USER = "user.id"
FK_ESTIMATE_VERSION = "estimateversion.id"
FK_LEAD = "lead.id"

CASCADE_DELETE_ORPHAN = "all, delete-orphan"
ONDELETE_SET_NULL = "SET NULL"


class LeadStage(str, enum.Enum):
    NEW = "new"
    QUALIFIED = "qualified"
    DISCOVERY = "discovery"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"


class ActivityType(str, enum.Enum):
    CALL = "call"
    EMAIL = "email"
    MEETING = "meeting"
    NOTE = "note"


class EstimateStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class Account(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    domain: Mapped[Optional[str]] = mapped_column(String(100))
    industry: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    details: Mapped[Optional["ClientDetails"]] = relationship(
        back_populates="account",
        uselist=False,
        cascade=CASCADE_DELETE_ORPHAN,
    )
    contacts: Mapped[List["Contact"]] = relationship(back_populates="account")
    leads: Mapped[List["Lead"]] = relationship(back_populates="account")


class ClientDetails(Base):
    __tablename__ = "client_details"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(FK_ACCOUNT, ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    address: Mapped[Optional[str]] = mapped_column(Text)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    website: Mapped[Optional[str]] = mapped_column(String(255))
    contact_person_name: Mapped[Optional[str]] = mapped_column(String(255))
    contact_person_phone: Mapped[Optional[str]] = mapped_column(String(50))
    contact_person_email: Mapped[Optional[str]] = mapped_column(String(255))
    gst_number: Mapped[Optional[str]] = mapped_column(String(30), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    account: Mapped["Account"] = relationship(back_populates="details")


class Contact(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(FK_ACCOUNT, ondelete="CASCADE")
    )
    full_name: Mapped[str] = mapped_column(
        String(100), index=True, nullable=False
    )
    email: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    job_title: Mapped[Optional[str]] = mapped_column(String(100))

    account: Mapped["Account"] = relationship(back_populates="contacts")
    leads: Mapped[List["Lead"]] = relationship(back_populates="contact")


class Lead(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    account_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey(FK_ACCOUNT, ondelete=ONDELETE_SET_NULL)
    )
    contact_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("contact.id", ondelete=ONDELETE_SET_NULL)
    )
    source: Mapped[Optional[str]] = mapped_column(String(100))
    industry: Mapped[Optional[str]] = mapped_column(String(50))
    owner_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(FK_USER), index=True
    )

    stage: Mapped[LeadStage] = mapped_column(
        SQLEnum(LeadStage), default=LeadStage.NEW, index=True
    )
    probability_percent: Mapped[int] = mapped_column(Integer, default=0)
    expected_close_date: Mapped[Optional[date]] = mapped_column(Date)
    estimated_value: Mapped[float] = mapped_column(Float, default=0.0)
    current_version_id: Mapped[Optional[str]] = mapped_column(String(50))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    account: Mapped[Optional["Account"]] = relationship(back_populates="leads")
    contact: Mapped[Optional["Contact"]] = relationship(back_populates="leads")
    owner: Mapped["User"] = relationship()
    activities: Mapped[List["ActivityLog"]] = relationship(
        back_populates="lead", cascade=CASCADE_DELETE_ORPHAN
    )
    estimates: Mapped[List["EstimateVersion"]] = relationship(
        back_populates="lead", cascade=CASCADE_DELETE_ORPHAN
    )

    documents: Mapped[List["LeadDocument"]] = relationship(
        back_populates="lead",
        cascade=CASCADE_DELETE_ORPHAN,
    )


class LeadDocument(Base):
    __tablename__ = "lead_document"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(FK_LEAD, ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(
        String(80), default="application/octet-stream", nullable=False
    )
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    uploader_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(FK_USER),
        index=True,
        nullable=False,
    )

    lead: Mapped["Lead"] = relationship(back_populates="documents")
    uploader: Mapped["User"] = relationship()


class ActivityLog(Base):
    # Unique name to avoid conflicts if generic ActivityLog exists
    __tablename__ = "bd_activity_log"  # type: ignore[assignment]
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(FK_LEAD, ondelete="CASCADE"), index=True
    )
    type: Mapped[ActivityType] = mapped_column(
        SQLEnum(ActivityType), index=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    next_follow_up_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    created_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(FK_USER), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    lead: Mapped["Lead"] = relationship(back_populates="activities")
    created_by: Mapped["User"] = relationship()


class EstimateVersion(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(FK_LEAD, ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[EstimateStatus] = mapped_column(
        SQLEnum(EstimateStatus), default=EstimateStatus.DRAFT, index=True
    )
    assumptions: Mapped[Optional[str]] = mapped_column(Text)
    scope_included: Mapped[Optional[str]] = mapped_column(Text)
    scope_excluded: Mapped[Optional[str]] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    total_cost_decimal: Mapped[float] = mapped_column(
        Numeric(12, 2), default=0.0
    )
    contingency_percent: Mapped[float] = mapped_column(Float, default=0.0)
    margin_percent: Mapped[float] = mapped_column(Float, default=0.0)
    total_price_decimal: Mapped[float] = mapped_column(
        Numeric(12, 2), default=0.0
    )
    created_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(FK_USER), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    lead: Mapped["Lead"] = relationship(back_populates="estimates")
    created_by: Mapped["User"] = relationship()
    phases: Mapped[List["EstimatePhase"]] = relationship(
        back_populates="version", cascade=CASCADE_DELETE_ORPHAN
    )
    resource_lines: Mapped[List["EstimateResourceLine"]] = relationship(
        back_populates="version", cascade=CASCADE_DELETE_ORPHAN
    )
    proposal_snapshots: Mapped[List["ProposalSnapshot"]] = relationship(
        back_populates="version", cascade=CASCADE_DELETE_ORPHAN
    )

    quotation_versions: Mapped[List["QuotationVersion"]] = relationship(
        back_populates="estimate_version", cascade=CASCADE_DELETE_ORPHAN
    )


class ProposalSnapshot(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    version_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(FK_ESTIMATE_VERSION, ondelete="CASCADE"),
        index=True,
    )
    snapshot_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    version: Mapped["EstimateVersion"] = relationship(
        back_populates="proposal_snapshots"
    )


class QuotationVersion(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    estimate_version_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(FK_ESTIMATE_VERSION, ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="generated", nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(
        String(80), default="application/pdf", nullable=False
    )
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    snapshot_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    pdf_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(FK_USER), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    estimate_version: Mapped["EstimateVersion"] = relationship(
        back_populates="quotation_versions"
    )
    created_by: Mapped["User"] = relationship()


class EstimatePhase(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    version_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(FK_ESTIMATE_VERSION, ondelete="CASCADE"),
        index=True,
    )
    phase_name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_offset_days: Mapped[Optional[int]] = mapped_column(Integer)
    duration_days: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[Optional[str]] = mapped_column(Text)
    assigned_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey(FK_USER, ondelete=ONDELETE_SET_NULL),
        nullable=True,
    )

    version: Mapped["EstimateVersion"] = relationship(back_populates="phases")
    assigned_user: Mapped[Optional["User"]] = relationship()


class EstimateResourceLine(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    version_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(FK_ESTIMATE_VERSION, ondelete="CASCADE"),
        index=True,
    )
    role_name: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    hours: Mapped[float] = mapped_column(Float, default=0.0)
    rate: Mapped[float] = mapped_column(Float, default=0.0)
    cost_decimal: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)

    version: Mapped["EstimateVersion"] = relationship(
        back_populates="resource_lines"
    )
