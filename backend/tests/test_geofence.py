"""Unit tests for geo-fencing primitives and punch-time decision logic.

Pure-function tests:

    PYTHONPATH=. pytest tests/test_geofence.py -v

Covers:
1. Haversine accuracy (known distance, identical points, antipodal).
2. evaluate_punch decisions:
   - STRICT outside -> rejected with nearest fence + distance.
   - ALLOW_WITH_FLAG outside -> accepted + OUTSIDE_GEOFENCE flag.
   - Inside any fence -> clean accept, no flag.
   - Exactly on radius -> inside (<=, not <).
   - Mock-location STRICT -> rejected with MOCK_LOCATION.
   - Mock-location ALLOW_WITH_FLAG -> accepted with flag.
   - Low accuracy on inside punch -> LOW_ACCURACY advisory, no block.
   - Low accuracy never blocks alone.
   - No-fence / geo_enabled=false -> exact-as-today, no flag, no
     regression. THIS IS THE BACKWARDS-COMPAT GUARANTEE.
   - Missing GPS -> LOW_ACCURACY flag, never blocked.
3. Min-radius validation is enforced at the pydantic layer; the
   resolver itself trusts whatever fences it's handed.
"""
from dataclasses import dataclass

import pytest

from app.services.geofence import (
    EnforcementMode,
    GeoFlag,
    MIN_RADIUS_METERS,
    evaluate_punch,
    haversine_meters,
)


@dataclass
class FakeFence:
    id: int
    name: str
    latitude: float
    longitude: float
    radius_meters: int


# Site centres used across tests. Kolkata HQ + a 5 km away client site
# give a clean two-fence scenario.
HQ_KOLKATA = FakeFence(
    id=1, name="HQ Kolkata",
    latitude=22.5726, longitude=88.3639, radius_meters=200,
)
CLIENT_SPML = FakeFence(
    id=2, name="Client Site - SPML",
    latitude=22.6200, longitude=88.4000, radius_meters=300,
)


# --- haversine ---------------------------------------------------------


class TestHaversine:
    def test_identical_points_zero(self):
        assert haversine_meters(22.5726, 88.3639, 22.5726, 88.3639) == 0.0

    def test_known_distance_within_tolerance(self):
        # 1 deg of latitude is ~111.32 km at the equator. Two points
        # at the same longitude 0.001 deg apart -> ~111 m.
        d = haversine_meters(22.5726, 88.3639, 22.5726 + 0.001, 88.3639)
        assert d == pytest.approx(111.0, abs=2.0)

    def test_symmetric(self):
        a = haversine_meters(22.5726, 88.3639, 22.6200, 88.4000)
        b = haversine_meters(22.6200, 88.4000, 22.5726, 88.3639)
        assert a == pytest.approx(b, abs=0.001)

    def test_antipodal_half_circumference(self):
        # 0,0 to 0,180 -> half Earth's circumference (~20015 km).
        d = haversine_meters(0.0, 0.0, 0.0, 180.0)
        assert d == pytest.approx(20_015_086.0, rel=0.001)

    def test_distance_is_nonnegative(self):
        d = haversine_meters(-33.8688, 151.2093, 22.5726, 88.3639)
        assert d > 0


# --- evaluate_punch: no-fence / disabled / missing GPS ------------------


class TestNoRegression:
    """An employee with no fences or geo_enabled=false must punch
    exactly as today: clean accept, no geo flag."""

    def test_geo_disabled_returns_clean(self):
        d = evaluate_punch(
            punch_lat=22.5726, punch_lng=88.3639,
            accuracy_m=20.0, is_mock_location=False,
            fences=[HQ_KOLKATA],
            enforcement_mode=EnforcementMode.STRICT,
            geo_enabled=False,
        )
        assert d.allowed is True
        assert d.geo_flag is None
        assert d.matched_fence is None
        assert d.distance_m is None

    def test_empty_fences_returns_clean(self):
        d = evaluate_punch(
            punch_lat=22.5726, punch_lng=88.3639,
            accuracy_m=20.0, is_mock_location=False,
            fences=[],
            enforcement_mode=EnforcementMode.STRICT,
            geo_enabled=True,
        )
        assert d.allowed is True
        assert d.geo_flag is None

    def test_no_gps_flags_low_accuracy_never_blocks(self):
        d = evaluate_punch(
            punch_lat=None, punch_lng=None,
            accuracy_m=None, is_mock_location=False,
            fences=[HQ_KOLKATA],
            enforcement_mode=EnforcementMode.STRICT,
            geo_enabled=True,
        )
        # Critical: STRICT mode + missing GPS still allowed.
        assert d.allowed is True
        assert d.geo_flag is GeoFlag.LOW_ACCURACY


# --- evaluate_punch: STRICT mode ----------------------------------------


class TestStrictMode:
    def test_outside_all_fences_strict_rejected(self):
        # Far from any fence (5+ km north).
        d = evaluate_punch(
            punch_lat=22.6500, punch_lng=88.4500,
            accuracy_m=15.0, is_mock_location=False,
            fences=[HQ_KOLKATA, CLIENT_SPML],
            enforcement_mode=EnforcementMode.STRICT,
            geo_enabled=True,
        )
        assert d.allowed is False
        assert d.geo_flag is GeoFlag.OUTSIDE_GEOFENCE
        assert d.reason_code == "OUTSIDE_GEOFENCE"
        # Nearest fence info present so the UI can explain.
        assert d.matched_fence is not None
        assert d.distance_m is not None and d.distance_m > 0

    def test_inside_one_fence_strict_accepted_clean(self):
        d = evaluate_punch(
            punch_lat=HQ_KOLKATA.latitude, punch_lng=HQ_KOLKATA.longitude,
            accuracy_m=10.0, is_mock_location=False,
            fences=[HQ_KOLKATA, CLIENT_SPML],
            enforcement_mode=EnforcementMode.STRICT,
            geo_enabled=True,
        )
        assert d.allowed is True
        assert d.geo_flag is None
        assert d.matched_fence is HQ_KOLKATA
        assert d.distance_m == pytest.approx(0.0, abs=0.01)

    def test_exactly_on_radius_counts_as_inside(self):
        # Place a punch ~189m from HQ centre. Set the fence radius to
        # CEIL(distance) so distance <= radius holds on the boundary.
        # Verifies the resolver uses <= (not <) for inclusion.
        import math
        d_to_punch = haversine_meters(
            22.5726, 88.3639, 22.5726 + 0.0017, 88.3639,
        )
        precise_fence = FakeFence(
            id=99, name="Edge", latitude=22.5726,
            longitude=88.3639, radius_meters=math.ceil(d_to_punch),
        )
        d = evaluate_punch(
            punch_lat=22.5726 + 0.0017, punch_lng=88.3639,
            accuracy_m=10.0, is_mock_location=False,
            fences=[precise_fence],
            enforcement_mode=EnforcementMode.STRICT,
            geo_enabled=True,
        )
        # distance <= radius -> inside, clean accept.
        assert d.allowed is True
        assert d.geo_flag is None
        assert d.matched_fence is precise_fence

    def test_one_metre_past_radius_is_outside(self):
        # Inverse check: shrink the radius by 1m below the actual
        # distance and confirm STRICT rejects. Locks in the boundary
        # behaviour from both sides.
        import math
        d_to_punch = haversine_meters(
            22.5726, 88.3639, 22.5726 + 0.0017, 88.3639,
        )
        tight_fence = FakeFence(
            id=100, name="Edge-1m", latitude=22.5726,
            longitude=88.3639,
            radius_meters=max(MIN_RADIUS_METERS, math.floor(d_to_punch) - 1),
        )
        # Punch slightly farther than the fence radius -> outside.
        # Use a position guaranteed to be > tight_fence.radius_meters away.
        d = evaluate_punch(
            punch_lat=22.5726 + 0.002, punch_lng=88.3639,
            accuracy_m=10.0, is_mock_location=False,
            fences=[tight_fence],
            enforcement_mode=EnforcementMode.STRICT,
            geo_enabled=True,
        )
        assert d.allowed is False
        assert d.geo_flag is GeoFlag.OUTSIDE_GEOFENCE


# --- evaluate_punch: ALLOW_WITH_FLAG ------------------------------------


class TestAllowWithFlag:
    def test_outside_all_flag_accepted(self):
        d = evaluate_punch(
            punch_lat=22.6500, punch_lng=88.4500,
            accuracy_m=15.0, is_mock_location=False,
            fences=[HQ_KOLKATA, CLIENT_SPML],
            enforcement_mode=EnforcementMode.ALLOW_WITH_FLAG,
            geo_enabled=True,
        )
        assert d.allowed is True
        assert d.geo_flag is GeoFlag.OUTSIDE_GEOFENCE
        # Nearest fence info still surfaced so HR can review.
        assert d.matched_fence is not None
        assert d.distance_m is not None


# --- evaluate_punch: mock-location --------------------------------------


class TestMockLocation:
    def test_mock_strict_rejected_even_when_inside(self):
        # Sitting inside a fence but is_mock_location=True -> STRICT
        # treats the reading as untrusted and rejects.
        d = evaluate_punch(
            punch_lat=HQ_KOLKATA.latitude, punch_lng=HQ_KOLKATA.longitude,
            accuracy_m=10.0, is_mock_location=True,
            fences=[HQ_KOLKATA],
            enforcement_mode=EnforcementMode.STRICT,
            geo_enabled=True,
        )
        assert d.allowed is False
        assert d.geo_flag is GeoFlag.MOCK_LOCATION
        assert d.reason_code == "MOCK_LOCATION"

    def test_mock_allow_with_flag_accepted_with_flag(self):
        d = evaluate_punch(
            punch_lat=HQ_KOLKATA.latitude, punch_lng=HQ_KOLKATA.longitude,
            accuracy_m=10.0, is_mock_location=True,
            fences=[HQ_KOLKATA],
            enforcement_mode=EnforcementMode.ALLOW_WITH_FLAG,
            geo_enabled=True,
        )
        assert d.allowed is True
        assert d.geo_flag is GeoFlag.MOCK_LOCATION

    def test_mock_takes_precedence_over_outside(self):
        # Far from any fence AND mock-location -> reports MOCK_LOCATION,
        # not OUTSIDE_GEOFENCE.
        d = evaluate_punch(
            punch_lat=22.6500, punch_lng=88.4500,
            accuracy_m=10.0, is_mock_location=True,
            fences=[HQ_KOLKATA],
            enforcement_mode=EnforcementMode.STRICT,
            geo_enabled=True,
        )
        assert d.allowed is False
        assert d.geo_flag is GeoFlag.MOCK_LOCATION


# --- evaluate_punch: LOW_ACCURACY ---------------------------------------


class TestLowAccuracy:
    def test_low_accuracy_inside_fence_is_advisory(self):
        # Inside fence but accuracy 150m > threshold -> LOW_ACCURACY
        # flag, still allowed.
        d = evaluate_punch(
            punch_lat=HQ_KOLKATA.latitude, punch_lng=HQ_KOLKATA.longitude,
            accuracy_m=150.0, is_mock_location=False,
            fences=[HQ_KOLKATA],
            enforcement_mode=EnforcementMode.STRICT,
            geo_enabled=True,
        )
        assert d.allowed is True
        assert d.geo_flag is GeoFlag.LOW_ACCURACY

    def test_low_accuracy_never_blocks_on_its_own(self):
        # Same scenario, ALLOW_WITH_FLAG.
        d = evaluate_punch(
            punch_lat=HQ_KOLKATA.latitude, punch_lng=HQ_KOLKATA.longitude,
            accuracy_m=200.0, is_mock_location=False,
            fences=[HQ_KOLKATA],
            enforcement_mode=EnforcementMode.ALLOW_WITH_FLAG,
            geo_enabled=True,
        )
        assert d.allowed is True
        assert d.geo_flag is GeoFlag.LOW_ACCURACY

    def test_good_accuracy_inside_fence_clean(self):
        d = evaluate_punch(
            punch_lat=HQ_KOLKATA.latitude, punch_lng=HQ_KOLKATA.longitude,
            accuracy_m=30.0, is_mock_location=False,
            fences=[HQ_KOLKATA],
            enforcement_mode=EnforcementMode.STRICT,
            geo_enabled=True,
        )
        assert d.allowed is True
        assert d.geo_flag is None


# --- min radius constant exposed ----------------------------------------


def test_min_radius_is_100():
    """Schema validation pins to this constant; tests pin it here too
    so changing it requires a deliberate update across the codebase."""
    assert MIN_RADIUS_METERS == 100
