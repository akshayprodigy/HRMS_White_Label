from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Integer, ForeignKey, DateTime, Text, Enum as SQLEnum
import enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User
    from .project import Project
    from .task import Task
    from .task import Subtask


class TimerStatus(str, enum.Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class TimeEntrySource(str, enum.Enum):
    TIMER = "timer"
    MANUAL = "manual"


ON_DELETE_SET_NULL = "SET NULL"


class TimerSession(Base):
    __tablename__ = "timer_session"  # type: ignore[assignment]
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("task.id", ondelete=ON_DELETE_SET_NULL),
        index=True,
        nullable=True,
    )
    subtask_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("subtask.id", ondelete=ON_DELETE_SET_NULL),
        index=True,
        nullable=True,
    )
    status: Mapped[TimerStatus] = mapped_column(
        SQLEnum(TimerStatus), default=TimerStatus.RUNNING, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stopped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accumulated_seconds: Mapped[int] = mapped_column(Integer, default=0)
    last_state_change_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User")
    project: Mapped["Project"] = relationship("Project")
    task: Mapped[Optional["Task"]] = relationship("Task")
    subtask: Mapped[Optional["Subtask"]] = relationship("Subtask")


class TimeEntry(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("task.id", ondelete=ON_DELETE_SET_NULL),
        index=True,
        nullable=True,
    )
    subtask_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("subtask.id", ondelete=ON_DELETE_SET_NULL),
        index=True,
        nullable=True,
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    source: Mapped[TimeEntrySource] = mapped_column(
        SQLEnum(TimeEntrySource), default=TimeEntrySource.TIMER
    )
    manual_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_by_user_id: Mapped[int] = mapped_column(Integer)

    user: Mapped["User"] = relationship("User", back_populates="time_entries")
    project: Mapped["Project"] = relationship("Project")
    task: Mapped[Optional["Task"]] = relationship("Task")
    subtask: Mapped[Optional["Subtask"]] = relationship("Subtask")

