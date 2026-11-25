"""Delegation of Powers (D1): manager kinds and assignments, posts, acting."""
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

CASCADE, SET_NULL, RESTRICT = "CASCADE", "SET NULL", "RESTRICT"


def _now():
    return datetime.now(timezone.utc)


class ManagerKind(Base):
    __tablename__ = "manager_kind"  # type: ignore[assignment]
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


class Post(Base):
    __tablename__ = "post"  # type: ignore[assignment]
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    department_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("department.id", ondelete=SET_NULL))
    location: Mapped[Optional[str]] = mapped_column(String(100))
    parent_post_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("post.id", ondelete=SET_NULL))
    heads_department_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("department.id", ondelete=SET_NULL), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now)


class PostHolder(Base):
    __tablename__ = "post_holder"  # type: ignore[assignment]
    __table_args__ = (Index("ix_post_holder_post", "post_id", "starts_on"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("post.id", ondelete=CASCADE))
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=CASCADE), index=True)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[Optional[date]] = mapped_column(Date)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=SET_NULL))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now)


class ManagerAssignment(Base):
    __tablename__ = "manager_assignment"  # type: ignore[assignment]
    __table_args__ = (
        Index("ix_mgr_asg_kind_scope", "manager_kind_id", "scope_type"),
        Index("ix_mgr_asg_user", "scope_user_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    manager_kind_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("manager_kind.id", ondelete=RESTRICT))
    scope_type: Mapped[str] = mapped_column(String(16))
    scope_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=CASCADE))
    scope_department_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("department.id", ondelete=CASCADE))
    scope_location: Mapped[Optional[str]] = mapped_column(String(100))
    manager_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=CASCADE), index=True)
    manager_post_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("post.id", ondelete=CASCADE), index=True)
    # JSON list of codes; [] = all. Replaces the spec's child table: rows are
    # always read whole.
    subdomains: Mapped[list] = mapped_column(JSON, default=list)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[Optional[date]] = mapped_column(Date)
    note: Mapped[Optional[str]] = mapped_column(String(255))
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=SET_NULL))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now)
    # removed before it ever started
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True))


class ActingAssignment(Base):
    __tablename__ = "acting_assignment"  # type: ignore[assignment]
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    covers_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=CASCADE), index=True)
    covers_post_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("post.id", ondelete=CASCADE), index=True)
    acting_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=CASCADE), index=True)
    subdomains: Mapped[list] = mapped_column(JSON, default=list)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[Optional[date]] = mapped_column(Date)
    original_can_act: Mapped[bool] = mapped_column(Boolean, default=False)
    only_when_on_leave: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255))
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=SET_NULL))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True))
    revoked_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=SET_NULL))
