from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import AuditMixin

_FK_ITEMS_ID = "items.id"
_FK_PROJECTS_ID = "projects.id"
_FK_UOMS_ID = "uoms.id"
_CASCADE_ALL_DELETE_ORPHAN = "all, delete-orphan"
_FK_DPR_HEADERS_ID = "dpr_headers.id"


class DprHeader(AuditMixin, Base):
    __tablename__ = "dpr_headers"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    project_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_PROJECTS_ID),
        nullable=False,
    )

    dpr_date: Mapped[dt.date] = mapped_column(sa.Date(), nullable=False)
    shift: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    remarks: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)

    drilling_lines: Mapped[list[DprDrillingLine]] = relationship(
        back_populates="header",
        cascade=_CASCADE_ALL_DELETE_ORPHAN,
    )
    activity_lines: Mapped[list[DprActivityLine]] = relationship(
        back_populates="header",
        cascade=_CASCADE_ALL_DELETE_ORPHAN,
    )
    consumption_lines: Mapped[list[DprConsumptionLine]] = relationship(
        back_populates="header",
        cascade=_CASCADE_ALL_DELETE_ORPHAN,
    )

    __table_args__ = (
        sa.Index("ix_dpr_headers_project_id", "project_id"),
        sa.Index("ix_dpr_headers_dpr_date", "dpr_date"),
        sa.Index(
            "ix_dpr_headers_project_id_dpr_date",
            "project_id",
            "dpr_date",
        ),
    )


class DprDrillingLine(AuditMixin, Base):
    __tablename__ = "dpr_drilling_lines"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    header_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_DPR_HEADERS_ID, ondelete="CASCADE"),
        nullable=False,
    )

    line_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    location: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)

    meters_drilled: Mapped[float] = mapped_column(
        sa.Numeric(14, 3),
        nullable=False,
    )
    recovered_meters: Mapped[float | None] = mapped_column(
        sa.Numeric(14, 3),
        nullable=True,
    )

    header: Mapped[DprHeader] = relationship(back_populates="drilling_lines")

    __table_args__ = (
        sa.Index("ix_dpr_drilling_lines_header_id", "header_id"),
        sa.UniqueConstraint("header_id", "line_no"),
    )


class DprActivityLine(AuditMixin, Base):
    __tablename__ = "dpr_activity_lines"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    header_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_DPR_HEADERS_ID, ondelete="CASCADE"),
        nullable=False,
    )

    line_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    activity: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    hours: Mapped[float | None] = mapped_column(
        sa.Numeric(8, 2),
        nullable=True,
    )
    remarks: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)

    header: Mapped[DprHeader] = relationship(back_populates="activity_lines")

    __table_args__ = (
        sa.Index("ix_dpr_activity_lines_header_id", "header_id"),
        sa.UniqueConstraint("header_id", "line_no"),
    )


class DprConsumptionLine(AuditMixin, Base):
    __tablename__ = "dpr_consumption_lines"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    header_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_DPR_HEADERS_ID, ondelete="CASCADE"),
        nullable=False,
    )

    line_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    item_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_ITEMS_ID),
        nullable=True,
    )
    uom_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_UOMS_ID),
        nullable=True,
    )
    qty: Mapped[float] = mapped_column(sa.Numeric(14, 3), nullable=False)
    remarks: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)

    header: Mapped[DprHeader] = relationship(
        back_populates="consumption_lines"
    )

    __table_args__ = (
        sa.Index("ix_dpr_consumption_lines_header_id", "header_id"),
        sa.Index("ix_dpr_consumption_lines_item_id", "item_id"),
        sa.UniqueConstraint("header_id", "line_no"),
    )
