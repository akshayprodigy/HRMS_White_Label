"""Review scoring + calibration — pure helpers.

# Documented constants

## DEFAULT_RATING_SCALE = "1-5 numeric"
When a form/section/question does not specify a scale, we default to
a numeric 1-5 scale with the labels below. Ratings outside [min, max]
are clamped by the CALLER (endpoints validate on write); the pure
helpers here trust the input range.

## OVERALL_RATING_BASIS = "weighted sections × their weighted questions"
For a review instance:
1. For each SECTION, average its questions using
   `weight_within_section` (weighted mean).
2. Take a weighted mean of section-scores using SECTION.weight.
Sections with weight 0 fall back to equal weighting. Questions with
`is_required=False` and no rating supplied are dropped from their
section's average.

## MANAGER_OVERRIDE_RULE = "must supply reason ≥ 10 chars"
Overriding the computed rating requires a reason. The pure helper
returns a validated tuple so the endpoint can 400 without a manual
check.

## CALIBRATION_SKEW_BAND_PCT = 5.0
Distribution vs target curve within ±5pp per bucket is normal noise.
Outside that we flag the bucket as skewed. Warning only — HR is never
forced to conform.

## RELEASE_GATE_RULE = "instance.is_released AND cycle.released_at"
Employees may see their review only when BOTH the instance is
released AND the parent cycle has a released_at timestamp. Enforced
by `is_visible_to_employee` — the endpoint short-circuits any read
that fails it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Protocol, Tuple


DEFAULT_RATING_SCALE = {"min": 1, "max": 5, "labels": [
    "Below expectations", "Needs improvement",
    "Meets expectations", "Exceeds expectations", "Outstanding",
]}
MIN_OVERRIDE_REASON_LEN = 10
CALIBRATION_SKEW_BAND_PCT = 5.0


# ---------- protocols ---------------------------------------------


class QuestionLike(Protocol):
    id: int
    weight_within_section: float
    question_type: str
    is_required: bool


class SectionLike(Protocol):
    id: int
    weight: float
    questions: List[QuestionLike]


class ResponseLike(Protocol):
    question_id: int
    self_rating: Optional[float]
    manager_rating: Optional[float]


# ---------- DTOs --------------------------------------------------


@dataclass
class SectionScore:
    section_id: int
    weight: float
    self_score: Optional[float]
    manager_score: Optional[float]


@dataclass
class OverallScore:
    computed_self: Optional[float]
    computed_manager: Optional[float]
    section_scores: List[SectionScore]


@dataclass
class RatingBucket:
    label: str
    count: int
    percent: float
    target_percent: Optional[float] = None
    skew_percent: Optional[float] = None
    is_skewed: bool = False


@dataclass
class DistributionReport:
    total: int
    buckets: List[RatingBucket]
    mean: float
    stdev: float
    skew_warnings: List[str] = field(default_factory=list)


# ---------- weighted section score --------------------------------


def _weighted_mean(pairs: Iterable[Tuple[float, float]]) -> Optional[float]:
    """(weight, value) tuples → weighted mean. None when no valid
    entries. Zero-weight falls back to equal weighting across the
    non-empty entries."""
    items = [(float(w or 0.0), float(v)) for w, v in pairs if v is not None]
    if not items:
        return None
    total_w = sum(w for w, _ in items)
    if total_w <= 0:
        return round(sum(v for _, v in items) / len(items), 4)
    return round(sum(w * v for w, v in items) / total_w, 4)


def compute_section_score(
    *,
    section: SectionLike,
    responses_by_qid: Dict[int, ResponseLike],
    who: str,       # "self" | "manager"
) -> Optional[float]:
    """Weighted mean of a section's question ratings from one side.

    Non-required questions with no rating are dropped. Non-RATING
    questions (goal assessment, free text) are excluded from the
    numeric average — they carry no scale.
    """
    pairs: List[Tuple[float, float]] = []
    for q in section.questions:
        if q.question_type != "rating":
            continue
        r = responses_by_qid.get(q.id)
        if r is None:
            if q.is_required:
                # Missing required response — treat section as incomplete.
                return None
            continue
        rating = r.self_rating if who == "self" else r.manager_rating
        if rating is None:
            if q.is_required:
                return None
            continue
        pairs.append((q.weight_within_section, float(rating)))
    return _weighted_mean(pairs)


def compute_overall_score(
    *,
    sections: List[SectionLike],
    responses: List[ResponseLike],
) -> OverallScore:
    """Whole-instance rollup.

    Returns computed self + manager overall scores + per-section
    breakdown. None values propagate — an incomplete section blocks
    that side's overall but not the other side.
    """
    responses_by_qid = {r.question_id: r for r in responses}
    section_scores: List[SectionScore] = []
    for s in sections:
        section_scores.append(SectionScore(
            section_id=s.id, weight=float(s.weight or 0.0),
            self_score=compute_section_score(
                section=s, responses_by_qid=responses_by_qid, who="self",
            ),
            manager_score=compute_section_score(
                section=s, responses_by_qid=responses_by_qid, who="manager",
            ),
        ))

    def _overall(side_key: str) -> Optional[float]:
        pairs: List[Tuple[float, float]] = []
        for ss in section_scores:
            v = getattr(ss, side_key)
            if v is None:
                continue
            pairs.append((ss.weight, v))
        return _weighted_mean(pairs)

    return OverallScore(
        computed_self=_overall("self_score"),
        computed_manager=_overall("manager_score"),
        section_scores=section_scores,
    )


# ---------- manager override --------------------------------------


@dataclass
class OverrideDecision:
    is_valid: bool
    final_rating: Optional[float]
    reason: Optional[str]
    error: Optional[str] = None


def apply_manager_override(
    *,
    computed: Optional[float],
    override: Optional[float],
    reason: Optional[str],
) -> OverrideDecision:
    """Returns the decision + a validation error string when invalid.

    - When override is None → computed value wins, no reason needed.
    - When override is set  → reason ≥ MIN_OVERRIDE_REASON_LEN required.
    """
    if override is None:
        return OverrideDecision(
            is_valid=True, final_rating=computed, reason=None,
        )
    if not reason or len(reason.strip()) < MIN_OVERRIDE_REASON_LEN:
        return OverrideDecision(
            is_valid=False, final_rating=computed, reason=None,
            error=(
                f"Override reason must be at least "
                f"{MIN_OVERRIDE_REASON_LEN} characters."
            ),
        )
    return OverrideDecision(
        is_valid=True, final_rating=float(override), reason=reason.strip(),
    )


# ---------- calibration ------------------------------------------


def compute_distribution(
    *,
    ratings: Iterable[float],
    scale_min: int = 1, scale_max: int = 5,
    target_curve: Optional[Dict[str, float]] = None,
) -> DistributionReport:
    """Bucket ratings by rounding to the nearest scale integer.

    `target_curve` shape: {"5": 0.10, "4": 0.30, ...} — fractions
    summing to ~1.0. When supplied, each bucket carries the
    target_percent + delta + skew flag.
    """
    values = [float(r) for r in ratings if r is not None]
    total = len(values)
    if total == 0:
        return DistributionReport(
            total=0, buckets=[], mean=0.0, stdev=0.0,
        )
    labels = list(range(scale_min, scale_max + 1))
    counts = {lbl: 0 for lbl in labels}
    for v in values:
        r = int(round(v))
        r = max(scale_min, min(scale_max, r))
        counts[r] += 1

    mean = sum(values) / total
    var = sum((v - mean) ** 2 for v in values) / total
    stdev = var ** 0.5

    buckets: List[RatingBucket] = []
    skew_warnings: List[str] = []
    for lbl in labels:
        pct = round(counts[lbl] / total * 100.0, 2)
        target = None
        skew = None
        is_skewed = False
        if target_curve:
            t_frac = float(target_curve.get(str(lbl), 0.0))
            target = round(t_frac * 100.0, 2)
            skew = round(pct - target, 2)
            if abs(skew) > CALIBRATION_SKEW_BAND_PCT:
                is_skewed = True
                skew_warnings.append(
                    f"Rating {lbl}: {pct}% vs target {target}% "
                    f"(skew {'+' if skew > 0 else ''}{skew}pp)"
                )
        buckets.append(RatingBucket(
            label=str(lbl), count=counts[lbl], percent=pct,
            target_percent=target, skew_percent=skew, is_skewed=is_skewed,
        ))

    return DistributionReport(
        total=total, buckets=buckets,
        mean=round(mean, 3), stdev=round(stdev, 3),
        skew_warnings=skew_warnings,
    )


# ---------- release gate ------------------------------------------


class InstanceLike(Protocol):
    is_released: bool


class CycleLike(Protocol):
    released_at: Optional[datetime]


def is_visible_to_employee(
    *, instance: InstanceLike, cycle: CycleLike,
) -> bool:
    """Employees can see their review ONLY when the instance is marked
    released AND the parent cycle has a released_at.

    Managers and HR can see pre-release via separate authorization on
    the endpoint side; this helper is specifically for the employee's
    own-review view.
    """
    return bool(instance.is_released and cycle.released_at is not None)


# ---------- manager scope filter ---------------------------------


def filter_to_team(
    rows: Iterable[dict], *,
    team_user_ids: Optional[Iterable[int]],
    user_key: str = "employee_id",
) -> List[dict]:
    """Manager scope enforcement. Returns rows unchanged when team_user_ids
    is None (HR view). Otherwise keeps only rows whose `user_key` is in
    the team set.
    """
    if team_user_ids is None:
        return list(rows)
    team = set(team_user_ids)
    return [r for r in rows if r.get(user_key) in team]
