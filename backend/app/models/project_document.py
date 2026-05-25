from typing import Optional, TYPE_CHECKING
from datetime import datetime, timezone

from sqlalchemy import String, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from .project import Project
    from .user import User


class ProjectDocument(Base):
    __tablename__ = "project_document"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    doc_type: Mapped[str] = mapped_column(String(50), default="Workorder", nullable=False)

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(
        String(100), default="application/octet-stream", nullable=False
    )
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    uploaded_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
    )

    project: Mapped["Project"] = relationship(
        "Project", back_populates="documents"
    )
    uploaded_by: Mapped[Optional["User"]] = relationship("User")
