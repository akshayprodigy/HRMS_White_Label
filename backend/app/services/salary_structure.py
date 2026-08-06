"""Salary-structure resolution (F3).

Turns a salary template (a bundle of components) into the four canonical
earning heads — basic / conveyance / hra / other — that the salary
calculator consumes. This is the opt-in replacement for the flat salary
columns on Employee.

Parity contract: a template built to mirror the legacy structure (a basic
line with value=None so the employee's own basic is used, plus conveyance
30% / hra 50% / other 20% of basic) reproduces the historical flat-column
default path in payroll.py exactly (Python `round` on basic*ratio, basic
itself unrounded), so an employee moved onto it computes byte-identically.
The migration seeds the four canonical *components* only — no ready-made
template ships; HR assembles one.
"""
from dataclasses import dataclass, field
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.salary_component import (
    SalaryComponent, CALC_FLAT, CALC_PERCENT_OF_BASIC, CANONICAL_SLOTS,
)
from app.models.salary_template import SalaryTemplate, SalaryTemplateComponent


@dataclass
class ResolvedLine:
    """A flattened template line: the component's slot plus the effective
    calc method / value / percent (template override in force), and the
    component's hard rupee bounds (clamp applied to the resolved amount)."""
    slot: Optional[str]           # one of CANONICAL_SLOTS, or None (-> other)
    calc_method: str
    value: Optional[float]
    percent: Optional[float]
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None


@dataclass
class ResolvedEarnings:
    basic: float
    conveyance: float
    hra: float
    other_allowance: float
    extras: dict = field(default_factory=dict)

    @property
    def ctc(self) -> float:
        return self.basic + self.conveyance + self.hra + self.other_allowance


def _clamp_amount(amount: float, line: ResolvedLine) -> float:
    """Apply the component's hard rupee floor/cap. NULL bound = no clamp."""
    if line.min_amount is not None:
        amount = max(amount, float(line.min_amount))
    if line.max_amount is not None:
        amount = min(amount, float(line.max_amount))
    return amount


def _line_amount(line: ResolvedLine, basic: float) -> float:
    """Absolute rupee amount contributed by a non-basic line, after clamping
    to the component's [min_amount, max_amount] hard bounds."""
    if line.calc_method == CALC_PERCENT_OF_BASIC and line.percent is not None:
        return _clamp_amount(basic * line.percent / 100.0, line)
    if line.calc_method == CALC_FLAT and line.value is not None:
        return _clamp_amount(float(line.value), line)
    return 0.0


def resolve_earnings_from_template(
    employee_basic: float, lines: Iterable[ResolvedLine],
) -> ResolvedEarnings:
    """Resolve a template's lines into the four canonical earning heads.

    `employee_basic` is the employee's basic (Employee.salary). A line in
    the `basic` slot with a flat value overrides it (a template that pins an
    absolute basic); otherwise the employee's own basic is used and the
    allowance lines are computed against it. Any line whose slot is not a
    canonical head is folded into `other` — preserving the four-slot
    contract the salary calculator depends on.
    """
    resolved_basic = float(employee_basic or 0.0)
    lines = list(lines)

    # First pass: a template may pin an absolute basic. A pinned basic is
    # clamped to its component's bounds too (else basic-slot min/max would be
    # a silent no-op while other slots are clamped).
    for ln in lines:
        if ln.slot == "basic" and ln.calc_method == CALC_FLAT and ln.value is not None:
            resolved_basic = _clamp_amount(float(ln.value), ln)

    slots = {"conveyance": 0.0, "hra": 0.0, "other": 0.0}
    for ln in lines:
        if ln.slot == "basic":
            continue  # already handled
        amount = _line_amount(ln, resolved_basic)
        target = ln.slot if ln.slot in slots else "other"
        slots[target] += amount

    # Basic is NOT rounded: the legacy flat-column path fed emp.salary
    # (a raw Float) straight through, so rounding here would diverge for
    # fractional salaries. Allowances ARE rounded — matching the legacy
    # round(basic*ratio) fallback.
    return ResolvedEarnings(
        basic=float(resolved_basic),
        conveyance=round(slots["conveyance"]),
        hra=round(slots["hra"]),
        other_allowance=round(slots["other"]),
    )


async def load_template_map(db: AsyncSession) -> dict[int, list[ResolvedLine]]:
    """Prefetch every active template's lines into {template_id: [ResolvedLine]}
    with a single join — avoids N+1 in the payroll batch loop.

    Only active templates and active components are included; a template
    component's calc_method/value/percent override the component defaults.
    """
    rows = (await db.execute(
        select(SalaryTemplateComponent, SalaryComponent)
        .join(SalaryComponent, SalaryTemplateComponent.component_id == SalaryComponent.id)
        .join(SalaryTemplate, SalaryTemplateComponent.template_id == SalaryTemplate.id)
        .where(SalaryTemplate.is_active.is_(True))
        .where(SalaryComponent.is_active.is_(True))
        .where(SalaryComponent.component_type == "earning")
        .order_by(SalaryTemplateComponent.display_order)
    )).all()

    out: dict[int, list[ResolvedLine]] = {}
    for tc, comp in rows:
        out.setdefault(tc.template_id, []).append(
            ResolvedLine(
                slot=comp.slot if comp.slot in CANONICAL_SLOTS else None,
                calc_method=tc.calc_method,
                value=tc.value,
                percent=tc.percent,
                min_amount=comp.min_amount,
                max_amount=comp.max_amount,
            )
        )
    return out
