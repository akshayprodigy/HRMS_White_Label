"""Performance Management domain.

Goals + review cycles + calibration + 1:1s. Net-new domain — this
module does NOT modify or read from payroll, statutory, revision, or
salary_calculator. The revision module (Prompt 5) reads rating via
the `GET /performance/ratings/{user_id}` endpoint (read-only bridge).

Release gating
==============
Nothing in a `ReviewInstance` is visible to the reviewee until
`released_at IS NOT NULL` on the parent cycle AND the instance itself
has `is_released = True`. The get-own-review endpoint enforces this;
the calibration board is HR-only until release.
"""
from datetime import datetime, date as pydate, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean, DateTime, Date, Float, ForeignKey, Integer, JSON, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


if TYPE_CHECKING:
    from .user import User


# ---------- string-constant enums (surfaced to the frontend as-is) ----


class GoalType:
    OKR = "okr"
    KRA = "kra"
    KPI = "kpi"
    PROJECT = "project"


class GoalStatus:
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    AT_RISK = "at_risk"     # RAG=RED for two check-ins in a row


class ConfidenceRAG:
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class CycleType:
    ANNUAL = "annual"
    HALF_YEARLY = "half_yearly"
    QUARTERLY = "quarterly"
    PROBATION = "probation"


class CycleStatus:
    DRAFT = "draft"
    ACTIVE = "active"
    CALIBRATION = "calibration"
    RELEASED = "released"
    CLOSED = "closed"


class ReviewPhase:
    NOT_STARTED = "not_started"
    SELF = "self"
    MANAGER = "manager"
    SKIP_LEVEL = "skip_level"
    CALIBRATION = "calibration"
    RELEASED = "released"


class QuestionType:
    RATING = "rating"        # scale answer
    GOAL_ASSESSMENT = "goal_assessment"   # auto-pulls goals; only self/mgr comments
    FREE_TEXT = "free_text"


class OneOnOneCadence:
    ONCE = "once"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


class ActionItemStatus:
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


# =====================================================================
# Goals
# =====================================================================


class Goal(Base):
    __tablename__ = "goal"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    goal_type: Mapped[str] = mapped_column(
        String(16), default=GoalType.OKR, nullable=False, index=True,
    )
    parent_goal_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("goal.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    weight: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False,
    )               # % contribution to owner's total, 0-100
    target: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)

    start_date: Mapped[pydate] = mapped_column(Date, nullable=False)
    due_date: Mapped[pydate] = mapped_column(Date, nullable=False)

    cycle_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("review_cycle.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    status: Mapped[str] = mapped_column(
        String(16), default=GoalStatus.DRAFT, nullable=False, index=True,
    )

    # Latest snapshot values maintained by the endpoint on check-in +
    # KR write so reads stay cheap. Recomputation lives in the pure
    # goals service.
    latest_progress: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False,
    )
    latest_confidence: Mapped[Optional[str]] = mapped_column(
        String(8), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
    )

    parent: Mapped[Optional["Goal"]] = relationship(
        "Goal", remote_side="Goal.id",
    )
    key_results: Mapped[List["KeyResult"]] = relationship(
        back_populates="goal", cascade="all, delete-orphan",
    )
    check_ins: Mapped[List["GoalCheckIn"]] = relationship(
        back_populates="goal", cascade="all, delete-orphan",
    )


class KeyResult(Base):
    __tablename__ = "key_result"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    goal_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("goal.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    target: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    weight: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False,
    )
    progress_percent: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16), default=GoalStatus.ACTIVE, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )

    goal: Mapped["Goal"] = relationship(back_populates="key_results")


class GoalCheckIn(Base):
    """History of periodic progress updates. The latest check-in feeds
    Goal.latest_progress + latest_confidence."""
    __tablename__ = "goal_check_in"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    goal_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("goal.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    progress_percent: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False,
    )
    confidence: Mapped[str] = mapped_column(
        String(8), default=ConfidenceRAG.GREEN, nullable=False,
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False, index=True,
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
    )

    goal: Mapped["Goal"] = relationship(back_populates="check_ins")


# =====================================================================
# Review cycles / forms / instances
# =====================================================================


class ReviewCycle(Base):
    __tablename__ = "review_cycle"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(
        String(160), unique=True, nullable=False, index=True,
    )
    cycle_type: Mapped[str] = mapped_column(
        String(16), default=CycleType.ANNUAL, nullable=False,
    )
    start_date: Mapped[pydate] = mapped_column(Date, nullable=False)
    end_date: Mapped[pydate] = mapped_column(Date, nullable=False)

    # Phase deadlines — kept in a JSON blob so HR can add optional
    # phases (e.g. skip-level) without schema churn.
    phases_json: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False,
    )                       # {"self_end": "...", "manager_end": "...", ...}

    # Population filter — resolved at launch. Shape:
    # {"departments": ["Eng","HR"], "employee_ids": [...], "all": false}
    population_json: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(16), default=CycleStatus.DRAFT, nullable=False, index=True,
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
    )


class ReviewForm(Base):
    """Reusable form template. Concrete sections + questions are
    stored as related rows so the form builder UI can drag/drop."""
    __tablename__ = "review_form"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(
        String(160), unique=True, nullable=False, index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Form-level default rating scale (5-star, 1-5, 0-10 etc.).
    # Sections/questions can override.
    scale_json: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False,
    )                     # {"min": 1, "max": 5, "labels": ["Poor",...]}

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )

    sections: Mapped[List["ReviewSection"]] = relationship(
        back_populates="form", cascade="all, delete-orphan",
        order_by="ReviewSection.sequence",
    )


class ReviewSection(Base):
    __tablename__ = "review_section"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    form_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("review_form.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    weight: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False,
    )     # % contribution to overall rating

    form: Mapped["ReviewForm"] = relationship(back_populates="sections")
    questions: Mapped[List["ReviewQuestion"]] = relationship(
        back_populates="section", cascade="all, delete-orphan",
        order_by="ReviewQuestion.sequence",
    )


class ReviewQuestion(Base):
    __tablename__ = "review_question"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    section_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("review_section.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    question_type: Mapped[str] = mapped_column(
        String(20), default=QuestionType.RATING, nullable=False,
    )
    weight_within_section: Mapped[float] = mapped_column(
        Float, default=1.0, nullable=False,
    )
    scale_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True,
    )              # optional per-question scale override
    is_required: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )

    section: Mapped["ReviewSection"] = relationship(back_populates="questions")


class ReviewTemplateAssignment(Base):
    """Which form applies to which population inside a cycle.
    Populations narrower than the cycle's population are allowed
    (department + grade slice)."""
    __tablename__ = "review_template_assignment"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cycle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("review_cycle.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    form_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("review_form.id", ondelete="RESTRICT"),
        index=True, nullable=False,
    )
    filter_json: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False,
    )                # {"departments": [...], "grades": [...]}
    priority: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )        # first-match wins; higher priority evaluated first


class ReviewInstance(Base):
    __tablename__ = "review_instance"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint(
            "cycle_id", "employee_id", name="uq_review_cycle_emp",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cycle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("review_cycle.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    manager_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    skip_level_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
    form_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("review_form.id", ondelete="RESTRICT"),
        nullable=False,
    )

    current_phase: Mapped[str] = mapped_column(
        String(20), default=ReviewPhase.NOT_STARTED,
        nullable=False, index=True,
    )
    self_submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    manager_submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    skip_level_submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    calibration_done_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    is_released: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True,
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Computed by the pure helper; manager may override.
    computed_overall_rating: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True,
    )
    manager_override_rating: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True,
    )
    manager_override_reason: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
    )
    calibrated_rating: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True,
    )
    final_rating: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True,
    )       # the number actually released

    approval_item_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("approvalitem.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )

    responses: Mapped[List["ReviewResponse"]] = relationship(
        back_populates="instance", cascade="all, delete-orphan",
    )


class ReviewResponse(Base):
    __tablename__ = "review_response"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint(
            "instance_id", "question_id", name="uq_review_response_iq",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("review_instance.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("review_question.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )

    self_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    self_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manager_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    manager_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    skip_level_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    skip_level_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # For GOAL_ASSESSMENT question type — the goal snapshot at review.
    goal_snapshot_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )

    instance: Mapped["ReviewInstance"] = relationship(back_populates="responses")


# =====================================================================
# Calibration
# =====================================================================


class CalibrationSession(Base):
    __tablename__ = "calibration_session"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cycle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("review_cycle.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    target_curve_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True,
    )       # {"5": 0.10, "4": 0.30, "3": 0.40, "2": 0.15, "1": 0.05}

    status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False, index=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    facilitator_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )


class CalibrationAdjustment(Base):
    __tablename__ = "calibration_adjustment"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("calibration_session.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("review_instance.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    old_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    new_rating: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)

    adjusted_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
    )
    adjusted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )


# =====================================================================
# 1:1s
# =====================================================================


class OneOnOne(Base):
    __tablename__ = "one_on_one"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    manager_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    reportee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
    )
    cadence: Mapped[str] = mapped_column(
        String(20), default=OneOnOneCadence.ONCE, nullable=False,
    )
    duration_minutes: Mapped[int] = mapped_column(
        Integer, default=30, nullable=False,
    )
    agenda_json: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
    )         # list of {topic, added_by}
    shared_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manager_private_notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )    # visible to manager only
    reportee_private_notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )    # visible to reportee only

    status: Mapped[str] = mapped_column(
        String(20), default="scheduled", nullable=False, index=True,
    )     # scheduled | completed | cancelled | skipped
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )

    action_items: Mapped[List["OneOnOneActionItem"]] = relationship(
        back_populates="one_on_one", cascade="all, delete-orphan",
    )


class OneOnOneActionItem(Base):
    __tablename__ = "one_on_one_action_item"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    one_on_one_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("one_on_one.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    due_date: Mapped[Optional[pydate]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=ActionItemStatus.OPEN,
        nullable=False, index=True,
    )
    done_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    # Optional link to a goal so coaching ties to objectives.
    goal_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("goal.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )

    one_on_one: Mapped["OneOnOne"] = relationship(back_populates="action_items")
