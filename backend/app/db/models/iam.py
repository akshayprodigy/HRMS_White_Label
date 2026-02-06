from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import AuditMixin


class User(AuditMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    email: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
        unique=True,
    )
    password_hash: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("1"),
    )

    user_roles: Mapped[list[UserRole]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    roles: Mapped[list[Role]] = relationship(
        secondary="user_roles",
        viewonly=True,
    )


class Role(AuditMixin, Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(
        sa.String(100),
        nullable=False,
        unique=True,
    )

    role_permissions: Mapped[list[RolePermission]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
    )

    permissions: Mapped[list[Permission]] = relationship(
        secondary="role_permissions",
        viewonly=True,
    )


class Permission(AuditMixin, Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    code: Mapped[str] = mapped_column(
        sa.String(150),
        nullable=False,
        unique=True,
    )
    description: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
    )


class UserRole(AuditMixin, Base):
    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("users.id"),
        nullable=False,
    )
    role_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("roles.id"),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="user_roles")
    role: Mapped[Role] = relationship()

    __table_args__ = (
        sa.UniqueConstraint(
            "user_id",
            "role_id",
            name="uq_user_roles_user_id_role_id",
        ),
        sa.Index("ix_user_roles_user_id", "user_id"),
        sa.Index("ix_user_roles_role_id", "role_id"),
    )


class RolePermission(AuditMixin, Base):
    __tablename__ = "role_permissions"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    role_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("roles.id"),
        nullable=False,
    )
    permission_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("permissions.id"),
        nullable=False,
    )

    role: Mapped[Role] = relationship(back_populates="role_permissions")
    permission: Mapped[Permission] = relationship()

    __table_args__ = (
        sa.UniqueConstraint(
            "role_id",
            "permission_id",
            name="uq_role_permissions_role_id_permission_id",
        ),
        sa.Index("ix_role_permissions_role_id", "role_id"),
        sa.Index("ix_role_permissions_permission_id", "permission_id"),
    )
