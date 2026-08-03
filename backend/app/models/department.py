from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Integer, Boolean, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.user import User


class Department(Base):
    """
    Department model for organizing employees.

    A department may have a functional head and an optional deputy head.
    Employees belong to a department via the free-text `Employee.department`
    string, which matches `Department.name` (the established team key).
    """
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    head_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deputy_head_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Two FKs to user -> foreign_keys must be explicit (mirrors Employee).
    head: Mapped[Optional["User"]] = relationship("User", foreign_keys=[head_user_id])
    deputy_head: Mapped[Optional["User"]] = relationship("User", foreign_keys=[deputy_head_user_id])
