"""Goal scoring — pure helpers.

Every knob is a documented constant so policy changes touch one place.

# Documented constants

## WEIGHT_SUM_TOLERANCE_PCT = 5.0
An owner's active goals should sum to ~100% weight. Deviations within
±5 percentage points are treated as normal (rounding, drafts in
progress). Outside that band we WARN — never block. Blocking would
frustrate mid-cycle editing.

## PROGRESS_ROLLUP_RULE
Goal progress can be computed two ways:
1. `from_key_results`  : weighted average of KR progress by KR weight
2. `from_check_ins`    : latest check-in's progress percent

Precedence: KEY_RESULTS > CHECK_INS. If a goal has any KR rows, KR
math wins; otherwise fall back to the latest check-in. Both callers +
tests pass so a goal type without KRs (KPI, KRA) still gets a
reliable number.

## AT_RISK_RULE = "two consecutive RED check-ins"
Not automatic in the DB — the endpoint computes and stamps the flag
so it can be overridden manually.

## PARENT_ROLLUP_RULE = "weighted average of child.latest_progress"
When a parent goal is set (company → dept → individual), the parent's
progress is the weighted average of its children's `latest_progress`
using the child weights. Missing weights fall back to equal.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable, List, Optional, Protocol


WEIGHT_SUM_TOLERANCE_PCT = 5.0


class ConfidenceRAG(str, Enum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


# --------- protocols (dataclasses can satisfy these in tests) ---------


class KeyResultLike(Protocol):
    id: int
    weight: float
    progress_percent: float


class CheckInLike(Protocol):
    created_at: datetime
    progress_percent: float
    confidence: str


class ChildGoalLike(Protocol):
    id: int
    weight: float
    latest_progress: float


# --------- DTOs ---------------------------------------------------


@dataclass
class WeightSumWarning:
    total: float
    delta: float
    within_tolerance: bool
    message: str


# --------- weight-sum validation -----------------------------------


def validate_weight_sum(
    weights: Iterable[float],
    tolerance_pct: float = WEIGHT_SUM_TOLERANCE_PCT,
    target: float = 100.0,
) -> WeightSumWarning:
    """Return a warning DTO. Never raises — the API layer surfaces this
    to the UI as a soft warning."""
    total = float(sum(w or 0.0 for w in weights))
    delta = round(total - target, 2)
    within = abs(delta) <= tolerance_pct
    if within:
        msg = ""
    else:
        direction = "over" if delta > 0 else "under"
        msg = (
            f"Weights sum to {total:.1f}% "
            f"({abs(delta):.1f} {direction}). Aim for ~{target:.0f}%."
        )
    return WeightSumWarning(
        total=round(total, 2), delta=delta,
        within_tolerance=within, message=msg,
    )


# --------- goal progress from key results --------------------------


def compute_progress_from_key_results(
    key_results: List[KeyResultLike],
) -> float:
    """Weighted average of KR progress by KR.weight. When all weights
    are zero, degrade to an equal-weight simple average.

    Returns 0.0 when the list is empty.
    """
    kr_list = [kr for kr in key_results if kr is not None]
    if not kr_list:
        return 0.0
    total_w = sum((kr.weight or 0.0) for kr in kr_list)
    if total_w <= 0:
        # equal weight fallback
        return round(
            sum((kr.progress_percent or 0.0) for kr in kr_list) / len(kr_list),
            2,
        )
    weighted = sum(
        (kr.weight or 0.0) * (kr.progress_percent or 0.0) for kr in kr_list
    )
    return round(weighted / total_w, 2)


def compute_progress_from_check_ins(
    check_ins: List[CheckInLike],
) -> tuple[float, Optional[str]]:
    """Latest check-in wins. Returns (progress, confidence-or-None).
    Empty list → (0.0, None).
    """
    if not check_ins:
        return 0.0, None
    latest = max(check_ins, key=lambda c: c.created_at)
    return round(float(latest.progress_percent or 0.0), 2), latest.confidence


def compute_goal_progress(
    *,
    key_results: List[KeyResultLike],
    check_ins: List[CheckInLike],
) -> tuple[float, Optional[str]]:
    """Composite: KR math wins when any KRs exist; otherwise the
    latest check-in. Confidence always comes from the check-in
    stream because KRs don't carry a confidence signal.
    """
    _, confidence = compute_progress_from_check_ins(check_ins)
    if key_results:
        return compute_progress_from_key_results(key_results), confidence
    progress, _ = compute_progress_from_check_ins(check_ins)
    return progress, confidence


# --------- parent rollup -------------------------------------------


def rollup_parent_progress(children: List[ChildGoalLike]) -> float:
    """Weighted average of `children.latest_progress` by weight.
    Same fallback: equal-weight when all weights are zero.
    """
    if not children:
        return 0.0
    total_w = sum((c.weight or 0.0) for c in children)
    if total_w <= 0:
        return round(
            sum((c.latest_progress or 0.0) for c in children) / len(children),
            2,
        )
    weighted = sum(
        (c.weight or 0.0) * (c.latest_progress or 0.0) for c in children
    )
    return round(weighted / total_w, 2)


# --------- at-risk detection ---------------------------------------


def is_at_risk(check_ins: List[CheckInLike], *, threshold: int = 2) -> bool:
    """True when the last `threshold` consecutive check-ins are RED.

    We consider the check-ins in reverse-chronological order; the
    first non-RED breaks the streak.
    """
    if not check_ins:
        return False
    ordered = sorted(check_ins, key=lambda c: c.created_at, reverse=True)
    red_streak = 0
    for c in ordered:
        if (c.confidence or "").lower() == ConfidenceRAG.RED.value:
            red_streak += 1
            if red_streak >= threshold:
                return True
        else:
            return False
    return False
