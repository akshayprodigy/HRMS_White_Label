from typing import TYPE_CHECKING, Optional, List
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text, Numeric, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from app.db.base_class import Base

CASCADE_DELETE_ORPHAN = "all, delete-orphan"
USER_ID_FK = "user.id"
TASK_ID_FK = "task.id"

if TYPE_CHECKING:
    from .project import Project
    from .user import User


class Task(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="todo")
    priority: Mapped[str] = mapped_column(String(20), default="medium")

    estimated_hours: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    value: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))

    due_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    creator_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(USER_ID_FK),
        index=True,
    )
    assignee_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey(USER_ID_FK), index=True
    )
    
    project: Mapped["Project"] = relationship(back_populates="tasks")
    creator: Mapped["User"] = relationship(foreign_keys=[creator_id])
    assignee: Mapped["User"] = relationship(foreign_keys=[assignee_id])
    
    subtasks: Mapped[list["Subtask"]] = relationship(
        back_populates="task", cascade=CASCADE_DELETE_ORPHAN
    )
    comments: Mapped[list["TaskComment"]] = relationship(
        back_populates="task", cascade=CASCADE_DELETE_ORPHAN
    )
    attachments: Mapped[list["TaskAttachment"]] = relationship(
        back_populates="task", cascade=CASCADE_DELETE_ORPHAN
    )
    completion_requests: Mapped[List["TaskCompletionRequest"]] = relationship(
        back_populates="task",
        cascade=CASCADE_DELETE_ORPHAN,
        order_by="TaskCompletionRequest.created_at",
    )


class Subtask(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    is_completed: Mapped[bool] = mapped_column(default=False)

    estimated_hours: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(TASK_ID_FK, ondelete="CASCADE"), index=True
    )

    parent_subtask_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("subtask.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )

    assignee_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey(USER_ID_FK, ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    
    task: Mapped["Task"] = relationship(back_populates="subtasks")
    assignee: Mapped[Optional["User"]] = relationship(
        foreign_keys=[assignee_id]
    )

    parent_subtask: Mapped[Optional["Subtask"]] = relationship(
        "Subtask",
        remote_side="Subtask.id",
        back_populates="children",
        foreign_keys=[parent_subtask_id],
    )
    children: Mapped[list["Subtask"]] = relationship(
        back_populates="parent_subtask",
        cascade=CASCADE_DELETE_ORPHAN,
        foreign_keys="Subtask.parent_subtask_id",
    )


class TaskComment(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(TASK_ID_FK, ondelete="CASCADE"), index=True
    )
    subtask_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("subtask.id", ondelete="CASCADE"), index=True, nullable=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(USER_ID_FK),
        index=True,
    )

    task: Mapped["Task"] = relationship(back_populates="comments")
    user: Mapped["User"] = relationship()


class TaskAttachment(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50))
    file_size: Mapped[int] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(TASK_ID_FK, ondelete="CASCADE"), index=True
    )
    uploader_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(USER_ID_FK),
        index=True,
    )
    
    task: Mapped["Task"] = relationship(back_populates="attachments")
    uploader: Mapped["User"] = relationship()


class TaskCompletionRequest(Base):
    """Submitted by an employee to signal a task is done; reviewed by the PM."""

    __tablename__ = "task_completion_request"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(TASK_ID_FK, ondelete="CASCADE"), index=True
    )
    subtask_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("subtask.id", ondelete="SET NULL"), index=True, nullable=True
    )
    submitted_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(USER_ID_FK), index=True
    )
    # pending | approved | rejected | on_hold
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey(USER_ID_FK, ondelete="SET NULL"), index=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    task: Mapped["Task"] = relationship(back_populates="completion_requests")
    subtask: Mapped[Optional["Subtask"]] = relationship(foreign_keys=[subtask_id])
    submitted_by: Mapped["User"] = relationship(foreign_keys=[submitted_by_id])
    reviewed_by: Mapped[Optional["User"]] = relationship(foreign_keys=[reviewed_by_id])
    documents: Mapped[List["TaskCompletionDocument"]] = relationship(
        back_populates="request",
        cascade=CASCADE_DELETE_ORPHAN,
        order_by="TaskCompletionDocument.uploaded_at",
    )


class TaskCompletionDocument(Base):
    """Evidence file attached to a TaskCompletionRequest."""

    __tablename__ = "task_completion_document"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    request_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("task_completion_request.id", ondelete="CASCADE"),
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    uploaded_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(USER_ID_FK), index=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    request: Mapped["TaskCompletionRequest"] = relationship(back_populates="documents")
    uploaded_by: Mapped["User"] = relationship()
