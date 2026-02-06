from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import AuditMixin

_CASCADE_ALL_DELETE_ORPHAN = "all, delete-orphan"
_FK_ORGANIZATIONS_ID = "organizations.id"


class Organization(AuditMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    code: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
        unique=True,
    )
    name: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
        unique=True,
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("1"),
    )

    sites: Mapped[list[Site]] = relationship(
        back_populates="organization",
        cascade=_CASCADE_ALL_DELETE_ORPHAN,
    )
    projects: Mapped[list[Project]] = relationship(
        back_populates="organization",
        cascade=_CASCADE_ALL_DELETE_ORPHAN,
    )
    cost_centers: Mapped[list[CostCenter]] = relationship(
        back_populates="organization",
        cascade=_CASCADE_ALL_DELETE_ORPHAN,
    )


class Site(AuditMixin, Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    organization_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_ORGANIZATIONS_ID),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("1"),
    )

    organization: Mapped[Organization] = relationship(back_populates="sites")
    projects: Mapped[list[Project]] = relationship(
        back_populates="site",
        cascade=_CASCADE_ALL_DELETE_ORPHAN,
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id",
            "code",
            name="uq_sites_org_id_code",
        ),
        sa.Index("ix_sites_organization_id", "organization_id"),
    )


class Project(AuditMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    organization_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_ORGANIZATIONS_ID),
        nullable=False,
    )
    site_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("sites.id"),
        nullable=True,
    )
    code: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("1"),
    )

    organization: Mapped[Organization] = relationship(back_populates="projects")
    site: Mapped[Site | None] = relationship(back_populates="projects")

    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id",
            "code",
            name="uq_projects_org_id_code",
        ),
        sa.Index("ix_projects_organization_id", "organization_id"),
        sa.Index("ix_projects_site_id", "site_id"),
    )


class CostCenter(AuditMixin, Base):
    __tablename__ = "cost_centers"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    organization_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_ORGANIZATIONS_ID),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("1"),
    )

    organization: Mapped[Organization] = relationship(back_populates="cost_centers")

    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id",
            "code",
            name="uq_cost_centers_org_id_code",
        ),
        sa.Index("ix_cost_centers_organization_id", "organization_id"),
    )
