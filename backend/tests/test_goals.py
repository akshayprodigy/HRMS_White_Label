"""Unit tests for goals scoring helpers."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pytest

from app.services.goals import (
    WEIGHT_SUM_TOLERANCE_PCT, ConfidenceRAG,
    compute_goal_progress, compute_progress_from_check_ins,
    compute_progress_from_key_results,
    is_at_risk, rollup_parent_progress, validate_weight_sum,
)


@dataclass
class FakeKR:
    id: int = 1
    weight: float = 50.0
    progress_percent: float = 0.0


@dataclass
class FakeCheckIn:
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    progress_percent: float = 0.0
    confidence: str = "green"


@dataclass
class FakeChildGoal:
    id: int = 1
    weight: float = 50.0
    latest_progress: float = 0.0


# ---------- weight sum ---------------------------------------------


class TestWeightSum:
    def test_documented_tolerance(self):
        assert WEIGHT_SUM_TOLERANCE_PCT == 5.0

    def test_exactly_100_is_within(self):
        r = validate_weight_sum([40, 30, 30])
        assert r.total == 100.0
        assert r.within_tolerance is True
        assert r.message == ""

    def test_within_tolerance_band(self):
        r = validate_weight_sum([40, 30, 33])   # total 103
        assert r.within_tolerance is True

    def test_over_by_more_than_5pp_warns(self):
        r = validate_weight_sum([40, 40, 40])   # total 120
        assert r.within_tolerance is False
        assert "over" in r.message

    def test_under_by_more_than_5pp_warns(self):
        r = validate_weight_sum([30, 30, 30])   # total 90
        assert r.within_tolerance is False
        assert "under" in r.message

    def test_never_raises_on_none(self):
        r = validate_weight_sum([None, 50, 50])
        assert r.total == 100.0


# ---------- progress from KRs -------------------------------------


class TestProgressFromKRs:
    def test_empty_returns_zero(self):
        assert compute_progress_from_key_results([]) == 0.0

    def test_weighted_mean(self):
        krs = [
            FakeKR(weight=25, progress_percent=100),
            FakeKR(weight=75, progress_percent=0),
        ]
        # weighted = (25*100 + 75*0) / 100 = 25
        assert compute_progress_from_key_results(krs) == 25.0

    def test_zero_weight_falls_back_to_equal_average(self):
        krs = [
            FakeKR(weight=0, progress_percent=100),
            FakeKR(weight=0, progress_percent=0),
        ]
        assert compute_progress_from_key_results(krs) == 50.0


# ---------- progress from check-ins -------------------------------


class TestProgressFromCheckIns:
    def test_empty(self):
        p, c = compute_progress_from_check_ins([])
        assert (p, c) == (0.0, None)

    def test_latest_wins(self):
        now = datetime.now(timezone.utc)
        cis = [
            FakeCheckIn(created_at=now - timedelta(days=10),
                        progress_percent=30, confidence="green"),
            FakeCheckIn(created_at=now - timedelta(days=5),
                        progress_percent=60, confidence="amber"),
            FakeCheckIn(created_at=now,
                        progress_percent=75, confidence="green"),
        ]
        p, c = compute_progress_from_check_ins(cis)
        assert p == 75.0
        assert c == "green"


# ---------- composite compute_goal_progress -----------------------


class TestCompositeCompute:
    def test_kr_wins_when_present(self):
        krs = [FakeKR(weight=100, progress_percent=80)]
        cis = [FakeCheckIn(progress_percent=30, confidence="amber")]
        p, c = compute_goal_progress(key_results=krs, check_ins=cis)
        # KR value picked; confidence still from check-in
        assert p == 80.0
        assert c == "amber"

    def test_check_in_fallback_when_no_krs(self):
        cis = [FakeCheckIn(progress_percent=42, confidence="green")]
        p, c = compute_goal_progress(key_results=[], check_ins=cis)
        assert p == 42.0
        assert c == "green"

    def test_both_empty(self):
        p, c = compute_goal_progress(key_results=[], check_ins=[])
        assert p == 0.0 and c is None


# ---------- parent rollup -----------------------------------------


class TestParentRollup:
    def test_empty_returns_zero(self):
        assert rollup_parent_progress([]) == 0.0

    def test_weighted_rollup(self):
        children = [
            FakeChildGoal(weight=60, latest_progress=80),
            FakeChildGoal(weight=40, latest_progress=40),
        ]
        # weighted = 0.6*80 + 0.4*40 = 48 + 16 = 64
        assert rollup_parent_progress(children) == 64.0

    def test_zero_weight_equal_average(self):
        children = [
            FakeChildGoal(weight=0, latest_progress=100),
            FakeChildGoal(weight=0, latest_progress=0),
        ]
        assert rollup_parent_progress(children) == 50.0


# ---------- at-risk detection -------------------------------------


class TestAtRisk:
    def test_two_consecutive_red_flags(self):
        now = datetime.now(timezone.utc)
        cis = [
            FakeCheckIn(created_at=now - timedelta(days=10), confidence="green"),
            FakeCheckIn(created_at=now - timedelta(days=5), confidence="red"),
            FakeCheckIn(created_at=now, confidence="red"),
        ]
        assert is_at_risk(cis) is True

    def test_single_red_not_at_risk(self):
        now = datetime.now(timezone.utc)
        cis = [
            FakeCheckIn(created_at=now - timedelta(days=5), confidence="green"),
            FakeCheckIn(created_at=now, confidence="red"),
        ]
        assert is_at_risk(cis) is False

    def test_broken_streak(self):
        now = datetime.now(timezone.utc)
        cis = [
            FakeCheckIn(created_at=now - timedelta(days=10), confidence="red"),
            FakeCheckIn(created_at=now - timedelta(days=5), confidence="green"),
            FakeCheckIn(created_at=now, confidence="red"),
        ]
        assert is_at_risk(cis) is False

    def test_empty(self):
        assert is_at_risk([]) is False

    def test_custom_threshold(self):
        now = datetime.now(timezone.utc)
        cis = [
            FakeCheckIn(created_at=now - timedelta(days=15), confidence="red"),
            FakeCheckIn(created_at=now - timedelta(days=10), confidence="red"),
            FakeCheckIn(created_at=now - timedelta(days=5), confidence="red"),
            FakeCheckIn(created_at=now, confidence="red"),
        ]
        assert is_at_risk(cis, threshold=4) is True
        assert is_at_risk(cis, threshold=5) is False
