# F3 — Salary component + template master

**Status:** Built, tested (13 F3 tests, full suite 38 passed / 2 skipped / 0 failed), migration `p4q5r6s7t8u9` applied to dev DB. Committed on `feature/workforce-expansion`.

## Goal
Re-platform salary earnings onto a configurable **component + template master** — **opt-in and regression-locked**. Existing employees (no template) must compute byte-identically.

## Design (locked)
- **`salary_component`** master: earnings-only catalogue. `slot` ∈ {basic, conveyance, hra, other} maps a component onto a canonical head; `slot=NULL` = extra earning folded into `other` (preserves the 4-slot dict contract `calculate_salary` depends on). `default_calc_method` ∈ {flat, percent_of_basic}. Seeded 4 canonical heads at today's ratios (basic flat, conveyance 30%, hra 50%, other 20%).
- **`salary_template`** + **`salary_template_component`**: a reusable structure; per-line `calc_method`/`value`/`percent` override the component default. `uq(template_id, component_id)`.
- **`Employee.salary_template_id`** — nullable FK (SET NULL), the opt-in switch. NULL for every existing row.
- **Resolver** `services/salary_structure.py`:
  - `resolve_earnings_from_template(employee_basic, lines) -> ResolvedEarnings` — pure. A `basic`-slot flat line pins an absolute basic; otherwise employee's own basic is used and allowances computed against it. Rounds with Python `round` to match the legacy `round(basic*ratio)` path exactly.
  - `load_template_map(db)` — one join, prefetch active templates → `{template_id: [ResolvedLine]}`; filters active template + active earning components. Avoids N+1 in the payroll loop.
- **Payroll wire** (`generate_draft`): if `emp.salary_template_id` is set → resolver governs the 4 heads; else the pre-F3 flat-column/ratio path verbatim. Non-template employees are byte-identical.

## Parity contract
Standard 30/50/20 template ⇒ `conveyance=round(basic*0.30)`, `hra=round(basic*0.50)`, `other=round(basic*0.20)` — identical to legacy. Covered by `tests/test_salary_structure.py::test_standard_template_matches_legacy_ratio_path` and the DB round-trip test.

## Endpoints (HR-gated, perm `hr employee write`)
- `GET/POST/PATCH /hr/salary-components`
- `GET /hr/salary-templates`, `GET /hr/salary-templates/{id}`, `POST`, `PATCH`
- `PUT /hr/salary-templates/{id}/components` — wholesale replace (idempotent editor)

## Deferred / follow-ups
- **`update_payroll_line` editor path** NOT wired to templates — the per-line manual editor recomputes from stored line values, not employee master; templates are opt-in and unused by existing data, so no regression. Wire it when template assignment ships as a workstream.
- Employee create/update + revision `_apply_one` still write the flat columns; template assignment is not yet exposed on employee CRUD (foundation only). A later workstream assigns templates to employees/grades and reconciles the flat columns.
- Deduction/statutory components intentionally out of scope — the unified payroll engine still owns PF/ESI/PT/TDS.

## Review — fixes applied
Code review verdict: **regression contract holds (PASS)** — NULL-template employees take the character-for-character pre-F3 path; `load_template_map` mutates nothing; migration chain/FK/downgrade correct.

Findings addressed:
- **[Important] Basic-head rounding divergence** — resolver rounded `basic`, but the legacy path fed `emp.salary` unrounded. Fixed: `basic=float(resolved_basic)` (unrounded); allowances still rounded to match legacy `round(basic*ratio)`. Locked by `test_basic_head_is_not_rounded`.
- **[Important] `update_payroll_line` editor not template-aware** — the HR line editor recomputed allowances from flat ratios, silently overwriting template-derived heads on any edit. Fixed: editor now mirrors `generate_draft` (resolves from the template when assigned). Non-template lines unchanged.
- **[Minor] percent_of_basic with no percent → silent zero pay** — added a Pydantic `model_validator` rejecting it (422). Locked by `test_create_template_rejects_percent_line_without_percent`.
- **[Minor] Templates accepted deduction/inactive components (silently dropped at resolve)** — `_assert_component_usable` now rejects non-earning / inactive components at write time (400).
- **[Minor] Docstring implied a seeded standard template** — reworded; only the four components seed, HR assembles the template.

Tracked (not changed):
- **[Minor] Assigned-but-unresolvable template silently falls back to flat columns** (inactive template / all-deduction lines). Fail-safe toward legacy; surface a warning when template assignment ships as a workstream.
- **[Minor] Float associativity** (`basic*pct/100` vs `basic*ratio`) — ±1 rupee only in pathological half-way cases; negligible.
- `update_payroll_line` uses `is_statutory_employee`/`flat_tds_rate_for` single-emp async helpers (not the batch map) — fine for a single line.

Final: **15 F3 tests, full suite 38 passed / 2 skipped / 0 failed**; migration head `p4q5r6s7t8u9`.
