"""Salary template master (F3).

A named, reusable salary structure: a bundle of salary components with
per-component calc method / value / percent. An employee opts in via
`Employee.salary_template_id`; when set, the template governs the four
canonical earning heads for payroll (see services/salary_structure.py).
When unset (the default for every existing employee) payroll falls back
to the historical flat-column path, so output is unchanged.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class SalaryTemplate(Base):
    __tablename__ = "salary_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )

    components: Mapped[list["SalaryTemplateComponent"]] = relationship(
        "SalaryTemplateComponent", back_populates="template",
        cascade="all, delete-orphan",
    )


class SalaryTemplateComponent(Base):
    __tablename__ = "salary_template_component"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("salary_template.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    component_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("salary_component.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Per-template override of the component's calc method / value.
    calc_method: Mapped[str] = mapped_column(String(20), default="flat", nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)      # flat amount
    percent: Mapped[float | None] = mapped_column(Float, nullable=True)    # percent_of_basic
    # Per-line hard rupee floor/cap; overrides the component's bounds when set.
    min_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    template: Mapped["SalaryTemplate"] = relationship(
        "SalaryTemplate", back_populates="components",
    )
    component: Mapped["SalaryComponent"] = relationship("SalaryComponent")

    __table_args__ = (
        UniqueConstraint("template_id", "component_id", name="uq_template_component"),
    )
