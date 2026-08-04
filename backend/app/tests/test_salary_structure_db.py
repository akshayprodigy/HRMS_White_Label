"""DB-backed test for the F3 template loader.

Builds a template against the seeded canonical components, loads it via the
payroll prefetch helper, and asserts the resolved earnings reproduce the
legacy flat-column ratios (30/50/20) — the no-regression contract.
"""
import pytest
from sqlalchemy import select

from app.models.salary_component import SalaryComponent
from app.models.salary_template import SalaryTemplate, SalaryTemplateComponent
from app.services import salary_structure as svc


async def _component_id(db, code: str) -> int:
    row = (await db.execute(
        select(SalaryComponent).where(SalaryComponent.code == code)
    )).scalars().first()
    assert row is not None, f"seed component {code!r} missing — run migrations"
    return row.id


@pytest.mark.asyncio
async def test_load_template_map_and_resolve_matches_legacy(db):
    tmpl = SalaryTemplate(code="test_std_f3", name="Test Standard")
    db.add(tmpl)
    await db.flush()

    for code, pct, order in [("conveyance", 30.0, 1), ("hra", 50.0, 2), ("other", 20.0, 3)]:
        db.add(SalaryTemplateComponent(
            template_id=tmpl.id, component_id=await _component_id(db, code),
            calc_method="percent_of_basic", percent=pct, display_order=order,
        ))
    await db.flush()

    tmap = await svc.load_template_map(db)
    assert tmpl.id in tmap
    lines = tmap[tmpl.id]
    assert len(lines) == 3
    slots = {ln.slot for ln in lines}
    assert slots == {"conveyance", "hra", "other"}

    basic = 40000
    r = svc.resolve_earnings_from_template(basic, lines)
    assert r.basic == basic
    assert r.conveyance == round(basic * 0.30)
    assert r.hra == round(basic * 0.50)
    assert r.other_allowance == round(basic * 0.20)


@pytest.mark.asyncio
async def test_inactive_template_excluded_from_map(db):
    tmpl = SalaryTemplate(code="test_inactive_f3", name="Inactive", is_active=False)
    db.add(tmpl)
    await db.flush()
    db.add(SalaryTemplateComponent(
        template_id=tmpl.id, component_id=await _component_id(db, "hra"),
        calc_method="percent_of_basic", percent=50.0,
    ))
    await db.flush()

    tmap = await svc.load_template_map(db)
    assert tmpl.id not in tmap
