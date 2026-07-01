"""Unit tests for review scoring + calibration helpers."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

import pytest

from app.services.performance import (
    CALIBRATION_SKEW_BAND_PCT, DEFAULT_RATING_SCALE,
    MIN_OVERRIDE_REASON_LEN,
    apply_manager_override, compute_distribution,
    compute_overall_score, compute_section_score,
    filter_to_team, is_visible_to_employee,
)


@dataclass
class FakeQuestion:
    id: int = 1
    weight_within_section: float = 1.0
    question_type: str = "rating"
    is_required: bool = True


@dataclass
class FakeSection:
    id: int = 1
    weight: float = 50.0
    questions: List[FakeQuestion] = field(default_factory=list)


@dataclass
class FakeResponse:
    question_id: int = 1
    self_rating: Optional[float] = None
    manager_rating: Optional[float] = None


@dataclass
class FakeInstance:
    is_released: bool = False


@dataclass
class FakeCycle:
    released_at: Optional[datetime] = None


# ---------- constants ---------------------------------------------


class TestConstants:
    def test_default_scale_1_to_5(self):
        assert DEFAULT_RATING_SCALE["min"] == 1
        assert DEFAULT_RATING_SCALE["max"] == 5
        assert len(DEFAULT_RATING_SCALE["labels"]) == 5

    def test_override_reason_min_len(self):
        assert MIN_OVERRIDE_REASON_LEN >= 5

    def test_skew_band_pct(self):
        assert CALIBRATION_SKEW_BAND_PCT == 5.0


# ---------- section score -----------------------------------------


class TestSectionScore:
    def test_weighted_average(self):
        s = FakeSection(id=1, weight=50, questions=[
            FakeQuestion(id=1, weight_within_section=2.0),
            FakeQuestion(id=2, weight_within_section=1.0),
        ])
        r = {
            1: FakeResponse(question_id=1, self_rating=5),
            2: FakeResponse(question_id=2, self_rating=2),
        }
        # weighted = (2*5 + 1*2)/3 = 4.0
        score = compute_section_score(section=s, responses_by_qid=r, who="self")
        assert score == 4.0

    def test_manager_side_pulled(self):
        s = FakeSection(id=1, weight=50, questions=[
            FakeQuestion(id=1, weight_within_section=1),
            FakeQuestion(id=2, weight_within_section=1),
        ])
        r = {
            1: FakeResponse(question_id=1, self_rating=5, manager_rating=3),
            2: FakeResponse(question_id=2, self_rating=5, manager_rating=4),
        }
        self_s = compute_section_score(section=s, responses_by_qid=r, who="self")
        mgr_s = compute_section_score(section=s, responses_by_qid=r, who="manager")
        assert self_s == 5.0
        assert mgr_s == 3.5

    def test_non_rating_questions_skipped(self):
        s = FakeSection(id=1, weight=50, questions=[
            FakeQuestion(id=1, question_type="free_text", weight_within_section=99),
            FakeQuestion(id=2, question_type="rating", weight_within_section=1),
        ])
        r = {
            1: FakeResponse(question_id=1, self_rating=None),
            2: FakeResponse(question_id=2, self_rating=4),
        }
        assert compute_section_score(section=s, responses_by_qid=r, who="self") == 4.0

    def test_missing_required_returns_none(self):
        s = FakeSection(id=1, weight=50, questions=[
            FakeQuestion(id=1, is_required=True, weight_within_section=1),
            FakeQuestion(id=2, is_required=True, weight_within_section=1),
        ])
        r = {1: FakeResponse(question_id=1, self_rating=4)}
        # question 2 missing entirely → None
        assert compute_section_score(section=s, responses_by_qid=r, who="self") is None

    def test_missing_optional_dropped(self):
        s = FakeSection(id=1, weight=50, questions=[
            FakeQuestion(id=1, is_required=True, weight_within_section=1),
            FakeQuestion(id=2, is_required=False, weight_within_section=1),
        ])
        r = {1: FakeResponse(question_id=1, self_rating=4)}
        assert compute_section_score(section=s, responses_by_qid=r, who="self") == 4.0


# ---------- overall rollup ----------------------------------------


class TestOverallScore:
    def test_two_sections_weighted(self):
        s1 = FakeSection(id=1, weight=60, questions=[
            FakeQuestion(id=1, weight_within_section=1),
        ])
        s2 = FakeSection(id=2, weight=40, questions=[
            FakeQuestion(id=2, weight_within_section=1),
        ])
        r = [
            FakeResponse(question_id=1, self_rating=4, manager_rating=5),
            FakeResponse(question_id=2, self_rating=3, manager_rating=3),
        ]
        overall = compute_overall_score(sections=[s1, s2], responses=r)
        # self: (60*4 + 40*3)/100 = 3.6
        # mgr:  (60*5 + 40*3)/100 = 4.2
        assert overall.computed_self == 3.6
        assert overall.computed_manager == 4.2
        assert len(overall.section_scores) == 2

    def test_zero_section_weight_equal_fallback(self):
        s1 = FakeSection(id=1, weight=0, questions=[
            FakeQuestion(id=1, weight_within_section=1),
        ])
        s2 = FakeSection(id=2, weight=0, questions=[
            FakeQuestion(id=2, weight_within_section=1),
        ])
        r = [
            FakeResponse(question_id=1, self_rating=5, manager_rating=5),
            FakeResponse(question_id=2, self_rating=3, manager_rating=3),
        ]
        overall = compute_overall_score(sections=[s1, s2], responses=r)
        assert overall.computed_self == 4.0

    def test_incomplete_section_blocks_that_side_only(self):
        s1 = FakeSection(id=1, weight=50, questions=[
            FakeQuestion(id=1, is_required=True, weight_within_section=1),
        ])
        s2 = FakeSection(id=2, weight=50, questions=[
            FakeQuestion(id=2, is_required=True, weight_within_section=1),
        ])
        # self only filled section 2; missing 1 → self overall = section 2
        # score (dropped None entries from weighted mean)
        r = [
            FakeResponse(question_id=1, manager_rating=5),
            FakeResponse(question_id=2, self_rating=3, manager_rating=4),
        ]
        overall = compute_overall_score(sections=[s1, s2], responses=r)
        assert overall.computed_self == 3.0
        assert overall.computed_manager == 4.5


# ---------- manager override --------------------------------------


class TestManagerOverride:
    def test_no_override_returns_computed(self):
        d = apply_manager_override(computed=3.5, override=None, reason=None)
        assert d.is_valid is True
        assert d.final_rating == 3.5
        assert d.reason is None

    def test_override_requires_reason(self):
        d = apply_manager_override(computed=3.5, override=4.0, reason=None)
        assert d.is_valid is False
        assert d.error is not None

    def test_override_short_reason_rejected(self):
        d = apply_manager_override(computed=3.5, override=4.0, reason="too")
        assert d.is_valid is False

    def test_override_with_valid_reason(self):
        d = apply_manager_override(
            computed=3.5, override=4.0,
            reason="Consistent stretch beyond scope in Q3.",
        )
        assert d.is_valid is True
        assert d.final_rating == 4.0
        assert "Q3" in (d.reason or "")


# ---------- distribution + skew ----------------------------------


class TestDistribution:
    def test_empty(self):
        d = compute_distribution(ratings=[])
        assert d.total == 0
        assert d.buckets == []

    def test_counts_and_percents(self):
        # Ten ratings: 5,5,4,4,4,4,3,3,2,1  → 5:20, 4:40, 3:20, 2:10, 1:10
        d = compute_distribution(ratings=[5,5,4,4,4,4,3,3,2,1])
        by_lbl = {b.label: b for b in d.buckets}
        assert by_lbl["5"].count == 2 and by_lbl["5"].percent == 20.0
        assert by_lbl["4"].count == 4 and by_lbl["4"].percent == 40.0
        assert by_lbl["1"].count == 1 and by_lbl["1"].percent == 10.0

    def test_mean_stdev(self):
        d = compute_distribution(ratings=[3, 3, 3])
        assert d.mean == 3.0
        assert d.stdev == 0.0

    def test_target_curve_skew_flag(self):
        # 8 ratings, all 5s.  Target says 10% at 5 → observed 100% → skewed
        d = compute_distribution(
            ratings=[5,5,5,5,5,5,5,5],
            target_curve={"5": 0.10, "4": 0.30, "3": 0.40, "2": 0.15, "1": 0.05},
        )
        top = next(b for b in d.buckets if b.label == "5")
        assert top.is_skewed is True
        assert d.skew_warnings   # non-empty

    def test_target_curve_within_band_not_skewed(self):
        # 10 ratings targeting 40% mid → observed 40% mid → no skew
        d = compute_distribution(
            ratings=[3,3,3,3, 4,4,4, 2,2, 5],
            target_curve={"5": 0.10, "4": 0.30, "3": 0.40, "2": 0.15, "1": 0.05},
        )
        mid = next(b for b in d.buckets if b.label == "3")
        assert mid.is_skewed is False

    def test_clamp_out_of_scale(self):
        # A 7 gets clamped to 5.
        d = compute_distribution(ratings=[7, 0, 3])
        by_lbl = {b.label: b for b in d.buckets}
        assert by_lbl["5"].count == 1
        assert by_lbl["1"].count == 1
        assert by_lbl["3"].count == 1


# ---------- release gate -----------------------------------------


class TestReleaseGate:
    def test_hidden_before_release(self):
        cycle = FakeCycle(released_at=None)
        inst = FakeInstance(is_released=False)
        assert is_visible_to_employee(instance=inst, cycle=cycle) is False

    def test_instance_released_but_cycle_not(self):
        cycle = FakeCycle(released_at=None)
        inst = FakeInstance(is_released=True)
        assert is_visible_to_employee(instance=inst, cycle=cycle) is False

    def test_cycle_released_but_instance_not(self):
        cycle = FakeCycle(released_at=datetime.now(timezone.utc))
        inst = FakeInstance(is_released=False)
        assert is_visible_to_employee(instance=inst, cycle=cycle) is False

    def test_both_released(self):
        cycle = FakeCycle(released_at=datetime.now(timezone.utc))
        inst = FakeInstance(is_released=True)
        assert is_visible_to_employee(instance=inst, cycle=cycle) is True


# ---------- manager scope filter ---------------------------------


class TestManagerScope:
    def test_none_scope_returns_all(self):
        rows = [{"employee_id": 1}, {"employee_id": 2}]
        assert filter_to_team(rows, team_user_ids=None) == rows

    def test_team_filter(self):
        rows = [{"employee_id": 1}, {"employee_id": 2}, {"employee_id": 3}]
        out = filter_to_team(rows, team_user_ids=[1, 3])
        assert [r["employee_id"] for r in out] == [1, 3]

    def test_empty_team_empty_out(self):
        rows = [{"employee_id": 1}]
        assert filter_to_team(rows, team_user_ids=[]) == []

    def test_custom_user_key(self):
        rows = [{"user_id": 1}, {"user_id": 2}]
        out = filter_to_team(rows, team_user_ids=[2], user_key="user_id")
        assert [r["user_id"] for r in out] == [2]
