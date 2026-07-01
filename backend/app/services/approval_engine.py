"""Generic approval-chain engine — pure helpers.

Every function here is DB-free and side-effect-free. Callers assemble
inputs (chain rows, step rows, request context) and receive plans and
decisions. Endpoints handle the persistence + notifications + audit
around this. That split keeps this module cheap to unit-test.

Constants (documented + tested):
- AUTO_APPROVE_BELOW_DEFAULT = 0 (opt-in; chain-level override)
- SAME_PERSON_SKIP_DEFAULT   = True (chain-level default; step override)
- ABSENT_SKIP_HOP_DEFAULT    = False (skip only if step sets a day count)

Rules the engine enforces:
1. Band-coverage validation: over the amount range [0, +inf) no step gap
   is allowed. Callers pre-validate before persisting a chain.
2. Auto-approve short-circuit runs first — if amount < chain.auto_approve_
   below_paise the returned plan is empty (finalized immediately by the
   caller).
3. skip_if_same_person hides steps whose resolved approver is the
   submitter (self-approval prevention).
4. In PARALLEL/ALL, every fan-out approver must approve. Any reject at
   any level rejects the whole instance.
5. In PARALLEL/ANY, first approve moves forward; a reject still stops
   the chain (safer default; documented).
6. On reject at any step the instance moves to REJECTED and no further
   steps are actioned.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

# ----------------------------------------------------------------------
# Documented constants
# ----------------------------------------------------------------------

AUTO_APPROVE_BELOW_DEFAULT = 0
SAME_PERSON_SKIP_DEFAULT = True
ABSENT_SKIP_HOP_DEFAULT = False


# ----------------------------------------------------------------------
# Lightweight value types the engine works over (no ORM dependency).
# Callers convert their ORM rows into these before invoking.
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class StepSpec:
    """Frozen view of an ApprovalChainStep suitable for planning."""
    step_order: int
    approver_type: str
    approver_ref: Optional[str] = None
    mode: str = "sequential"
    parallel_rule: str = "all"
    min_amount_paise: Optional[int] = None
    max_amount_paise: Optional[int] = None
    skip_if_same_person: bool = False
    skip_if_absent_days: Optional[int] = None
    label: Optional[str] = None


@dataclass(frozen=True)
class ChainSpec:
    """Frozen view of an ApprovalChain suitable for planning."""
    id: int
    name: str
    entity_type: str
    steps: Tuple[StepSpec, ...]
    auto_approve_below_paise: Optional[int] = None
    skip_if_same_person: bool = True
    department: Optional[str] = None


@dataclass(frozen=True)
class RequestContext:
    """Everything the engine needs from a submitted request."""
    submitter_id: int
    amount_paise: int
    department: Optional[str] = None


@dataclass
class MaterializedStep:
    """One step after threshold + skip evaluation, ready to be inserted
    as ChainedApprovalStepInstance rows.
    """
    step_order: int
    approver_type: str
    mode: str
    parallel_rule: str
    approver_user_ids: List[int]
    label: Optional[str] = None
    auto_approved: bool = False
    skip_reason: Optional[str] = None


@dataclass
class BandValidationResult:
    """Returned by validate_bands()."""
    ok: bool
    gaps: List[Tuple[int, int]] = field(default_factory=list)
    duplicate_orders: List[int] = field(default_factory=list)
    empty: bool = False


# ----------------------------------------------------------------------
# 1. Band-coverage validation (chain-persist-time)
# ----------------------------------------------------------------------


def validate_bands(steps: Iterable[StepSpec]) -> BandValidationResult:
    """Ensure at least one step is defined, that step_order values are
    unique, and that the [min, max] bands over the amount range don't
    leave a gap that would strand a submitted request.

    Gap detection: sort steps by min. Walk the covered range. A gap
    exists if, at any point in [0, +inf), no step's band covers the
    amount. min=None → 0. max=None → +inf.
    """
    ordered = sorted(steps, key=lambda s: s.step_order)
    if not ordered:
        return BandValidationResult(ok=False, empty=True)

    seen_orders: Set[int] = set()
    dupes: List[int] = []
    for s in ordered:
        if s.step_order in seen_orders:
            dupes.append(s.step_order)
        seen_orders.add(s.step_order)
    if dupes:
        return BandValidationResult(ok=False, duplicate_orders=dupes)

    # Now check coverage by merging the bands over the amount axis.
    bands: List[Tuple[int, int]] = []
    INF = 10**18
    for s in ordered:
        lo = s.min_amount_paise if s.min_amount_paise is not None else 0
        hi = s.max_amount_paise if s.max_amount_paise is not None else INF
        if hi < lo:
            # inverted band = zero-width; skip
            continue
        bands.append((lo, hi))
    if not bands:
        return BandValidationResult(ok=False, gaps=[(0, INF)])

    bands.sort()
    gaps: List[Tuple[int, int]] = []
    covered_hi = -1
    for lo, hi in bands:
        if lo > covered_hi + 1:
            gaps.append((max(covered_hi + 1, 0), lo - 1))
        covered_hi = max(covered_hi, hi)
    if covered_hi < INF:
        gaps.append((covered_hi + 1, INF))

    # A leading gap [0,-1] means we start covered from 0; skip that trivially.
    gaps = [(a, b) for a, b in gaps if b >= a and a >= 0]
    return BandValidationResult(ok=not gaps, gaps=gaps)


# ----------------------------------------------------------------------
# 2. Build the runtime plan
# ----------------------------------------------------------------------


ResolverFn = Callable[[StepSpec, RequestContext], List[int]]


def _step_applies_to_amount(step: StepSpec, amount_paise: int) -> bool:
    lo = step.min_amount_paise if step.min_amount_paise is not None else 0
    hi = step.max_amount_paise if step.max_amount_paise is not None else 10**18
    return lo <= amount_paise <= hi


def build_plan(
    chain: ChainSpec,
    ctx: RequestContext,
    resolver: ResolverFn,
) -> List[MaterializedStep]:
    """Materialize the ordered steps for a given request.

    resolver(step, ctx) → list of user_ids that step should route to.
    Empty list is legitimate (e.g. FINANCE with no finance users seeded)
    but caller should treat it as a chain-config error.

    Auto-approve short-circuit: if amount is below the chain-level
    threshold, return an empty plan. Caller finalizes as APPROVED.
    """
    threshold = chain.auto_approve_below_paise or AUTO_APPROVE_BELOW_DEFAULT
    if threshold and ctx.amount_paise < threshold:
        return []

    applicable = [
        s for s in chain.steps if _step_applies_to_amount(s, ctx.amount_paise)
    ]
    applicable.sort(key=lambda s: s.step_order)

    plan: List[MaterializedStep] = []
    for step in applicable:
        raw_ids = list(resolver(step, ctx))
        skip_self = (
            step.skip_if_same_person or chain.skip_if_same_person
        )
        if skip_self:
            raw_ids = [u for u in raw_ids if u != ctx.submitter_id]

        # Dedup preserving order.
        seen: Set[int] = set()
        dedup_ids: List[int] = []
        for u in raw_ids:
            if u not in seen:
                seen.add(u)
                dedup_ids.append(u)

        skip_reason: Optional[str] = None
        if not dedup_ids:
            skip_reason = "no_eligible_approver"
        plan.append(
            MaterializedStep(
                step_order=step.step_order,
                approver_type=step.approver_type,
                mode=step.mode,
                parallel_rule=step.parallel_rule,
                approver_user_ids=dedup_ids,
                label=step.label,
                skip_reason=skip_reason,
            )
        )

    return plan


# ----------------------------------------------------------------------
# 3. Advance on approve/reject
# ----------------------------------------------------------------------


@dataclass
class ActionOutcome:
    """Returned by advance_state — a pure decision, side-effect-free."""
    next_status: str          # "pending" | "approved" | "rejected"
    advance_to_step: Optional[int] = None
    finalize: bool = False
    should_notify_next: bool = False
    reason: Optional[str] = None


def advance_state(
    *,
    all_step_instances: List[dict],
    acted_step_order: int,
    action: str,
) -> ActionOutcome:
    """Given the current step-instance rows for one instance (each is a
    dict-like: {step_order, approver_user_id, mode, parallel_rule,
    status}), and the just-taken action ("approve" | "reject") at
    acted_step_order, decide the next status.

    Rules:
    - REJECT at any step → finalize REJECTED, stop.
    - SEQUENTIAL step: single row; approve → move to next step_order.
    - PARALLEL/ALL: every row at this order must be APPROVED before
      moving on. If any is REJECTED, finalize REJECTED.
    - PARALLEL/ANY: first APPROVE moves on; a REJECT still finalizes
      REJECTED (conservative default so a single reject blocks).
    - If no next-order rows exist → finalize APPROVED.
    """
    if action == "reject":
        return ActionOutcome(
            next_status="rejected",
            finalize=True,
            reason="rejected_at_step",
        )
    if action != "approve":
        raise ValueError(f"unknown action {action!r}")

    current_rows = [
        r for r in all_step_instances if r["step_order"] == acted_step_order
    ]
    if not current_rows:
        return ActionOutcome(
            next_status="rejected",
            finalize=True,
            reason="no_current_step",
        )

    mode = current_rows[0].get("mode", "sequential")
    parallel_rule = current_rows[0].get("parallel_rule", "all")

    def _can_advance() -> bool:
        if mode == "sequential":
            return True
        if parallel_rule == "any":
            return True
        # parallel/all: every row must be approved
        return all(r["status"] == "approved" for r in current_rows)

    if not _can_advance():
        return ActionOutcome(
            next_status="pending",
            reason="awaiting_other_parallel_approvers",
        )

    # find next step_order
    next_order: Optional[int] = None
    for r in sorted(all_step_instances, key=lambda x: x["step_order"]):
        if r["step_order"] > acted_step_order and r["status"] == "pending":
            next_order = r["step_order"]
            break
    if next_order is None:
        return ActionOutcome(
            next_status="approved",
            finalize=True,
            reason="all_steps_approved",
        )
    return ActionOutcome(
        next_status="pending",
        advance_to_step=next_order,
        should_notify_next=True,
    )


# ----------------------------------------------------------------------
# 4. Effective-chain picker
# ----------------------------------------------------------------------


def pick_effective_chain(
    chains: Iterable[ChainSpec],
    *,
    entity_type: str,
    department: Optional[str] = None,
) -> Optional[ChainSpec]:
    """Pick the best-matching active chain for an entity + department.

    Priority: exact department match beats null (org-wide) chain; ties
    broken by highest chain id (most recently created).
    """
    candidates = [c for c in chains if c.entity_type == entity_type]
    if not candidates:
        return None

    exact = [
        c for c in candidates
        if c.department is not None and c.department == department
    ]
    org_wide = [c for c in candidates if c.department is None]

    pool = exact or org_wide or candidates
    return max(pool, key=lambda c: c.id)


# ----------------------------------------------------------------------
# 5. Skip-if-absent (Section M B5)
# ----------------------------------------------------------------------


@dataclass
class AbsenceCheck:
    """Compact input for is_approver_absent():
    - user_id                 the approver being checked
    - required_window_days    N — the step's skip_if_absent_days
    - attended_work_dates     set of ISO date strings (YYYY-MM-DD) the
                              approver actually punched-in on in the
                              past `required_window_days` days.
    Callers pass raw attendance rows converted to date strings so this
    helper stays DB-free and unit-testable.
    """
    user_id: int
    required_window_days: int
    attended_work_dates: frozenset


def is_approver_absent(chk: AbsenceCheck) -> bool:
    """Return True if the approver has ZERO attended work-dates in the
    lookback window. `required_window_days <= 0` disables the check
    (always False)."""
    if chk.required_window_days <= 0:
        return False
    return len(chk.attended_work_dates) == 0


def filter_absent_approvers(
    approvers_with_attendance: Iterable[AbsenceCheck],
) -> List[int]:
    """Drop absent approvers from a list of candidates. Preserves order.
    Never returns an empty result silently — the caller (endpoint layer)
    is responsible for the 'hold for HR' fallback when everyone is out.
    """
    return [
        c.user_id for c in approvers_with_attendance
        if not is_approver_absent(c)
    ]
