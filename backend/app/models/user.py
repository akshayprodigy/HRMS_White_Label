from datetime import datetime, date as date_type
from typing import Any, TYPE_CHECKING, Optional
from sqlalchemy import String, Integer, ForeignKey, Table, Column, Text, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base

if TYPE_CHECKING:
    from .attendance import Attendance
    from .timesheet import TimeEntry
    from .notification import Notification


# Association tables for RBAC
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permission.id", ondelete="CASCADE"), primary_key=True),
)

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
)

class Permission(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(200))

class Role(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(200))

    permissions: Mapped[list["Permission"]] = relationship(
        secondary=role_permissions, lazy="selectin"
    )

class User(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(default=True)
    is_superuser: Mapped[bool] = mapped_column(default=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kra: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_of_birth: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    manager_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    roles: Mapped[list["Role"]] = relationship(
        secondary=user_roles, lazy="selectin"
    )
    
    manager: Mapped[Optional["User"]] = relationship(
        "User", remote_side=[id], backref="subordinates"
    )

    attendances: Mapped[list["Attendance"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        # Attendance has two FK paths to user (user_id + edited_by_id);
        # this collection is the ownership path.
        foreign_keys="[Attendance.user_id]",
    )
    
    time_entries: Mapped[list["TimeEntry"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
