"""Geo-fencing primitives and punch-time decision logic.

Pure module — no DB, no I/O — so the rules can be unit-tested in
isolation and reused from any endpoint.

Glossary
========
- Fence  : (latitude, longitude, radius_meters) circle around a site.
- Inside : haversine distance to fence centre <= radius_meters.
- Mode   : enforcement policy applied when an employee punches outside
           ALL allowed fences:
             STRICT          -> punch is rejected (returned as an error)
             ALLOW_WITH_FLAG -> punch proceeds but is flagged for review

Constants
=========
MIN_RADIUS_METERS = 100      enforced by schema + the API; smaller
                             radii are noisy under consumer GPS.
LOW_ACCURACY_THRESHOLD_M = 100 reported accuracy worse than this -> a
                               LOW_ACCURACY advisory flag (never blocks
                               on its own; accuracy is too noisy).

Flag precedence (when multiple apply, the higher wins):
  MOCK_LOCATION > OUTSIDE_GEOFENCE > LOW_ACCURACY
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import asin, cos, radians, sin, sqrt
from typing import Iterable, Optional, Protocol


MIN_RADIUS_METERS = 100
LOW_ACCURACY_THRESHOLD_M = 100.0
EARTH_RADIUS_M = 6_371_000.0


class EnforcementMode(str, Enum):
    STRICT = "strict"
    ALLOW_WITH_FLAG = "allow_with_flag"


class GeoFlag(str, Enum):
    """Geo-only attribution. Stored separately from the shift
    attribution_flag so HR can filter / triage by dimension."""
    OUTSIDE_GEOFENCE = "outside_geofence"
    MOCK_LOCATION = "mock_location"
    LOW_ACCURACY = "low_accuracy"


class FenceLike(Protocol):
    """Structural type for any fence-shaped object the resolver accepts.
    A SQLAlchemy GeoFenceLocation row satisfies it; tests can pass
    dataclasses."""
    id: int
    name: str
    latitude: float
    longitude: float
    radius_meters: int


# --- haversine ----------------------------------------------------------


def haversine_meters(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Great-circle distance between two WGS-84 points in metres.

    Uses the standard haversine formula. Accurate to <0.5% for the
    distance scales we care about (metres to a few kilometres). Returns
    a non-negative float; identical points return 0.0.
    """
    phi1 = radians(lat1)
    phi2 = radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2.0) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2.0) ** 2
    c = 2.0 * asin(sqrt(a))
    return EARTH_RADIUS_M * c


# --- decision logic -----------------------------------------------------


@dataclass
class FenceMatch:
    """One fence's distance from a punch point."""
    fence: FenceLike
    distance_m: float

    @property
    def inside(self) -> bool:
        return self.distance_m <= self.fence.radius_meters


@dataclass
class GeoDecision:
    """Output of evaluate_punch().

    Fields
    ------
    allowed       : True when the punch should be persisted as an
                    attendance row. False ONLY in STRICT mode and only
                    when the resolver wants to reject.
    geo_flag      : GeoFlag value, or None when the punch is clean.
    matched_fence : The fence we matched against (closest fence, even
                    if outside; None when no fences are configured).
    distance_m    : Distance to matched_fence (None when no fences).
    reason_code   : Machine-readable code accompanying a rejection;
                    'OUTSIDE_GEOFENCE' or 'MOCK_LOCATION'.
    reason        : Human-readable message — safe to surface to the user.
    """
    allowed: bool
    geo_flag: Optional[GeoFlag]
    matched_fence: Optional[FenceLike]
    distance_m: Optional[float]
    reason_code: Optional[str] = None
    reason: Optional[str] = None


def evaluate_punch(
    *,
    punch_lat: Optional[float],
    punch_lng: Optional[float],
    accuracy_m: Optional[float],
    is_mock_location: bool,
    fences: Iterable[FenceLike],
    enforcement_mode: EnforcementMode,
    geo_enabled: bool,
) -> GeoDecision:
    """Decide whether a punch should be accepted, flagged, or rejected.

    Backward-compat contract
    ------------------------
    If `geo_enabled` is False, or `fences` is empty, this returns a
    clean allowed=True / geo_flag=None decision regardless of the
    other inputs. Employees with no geo configuration must punch
    exactly as today.

    If `geo_enabled` is True but `punch_lat`/`punch_lng` are missing
    (no GPS reading), the punch is treated like LOW_ACCURACY: flagged
    but never blocked. We never want a missing GPS reading to lock
    someone out — a corrupted device should be a flag, not a hard
    block.

    Precedence
    ----------
    MOCK_LOCATION evaluated first: in STRICT mode it rejects, in
    ALLOW_WITH_FLAG it flags. Mock-location is the strongest signal
    of an untrusted reading.

    OUTSIDE_GEOFENCE next: if not mock and the punch is outside every
    fence, STRICT rejects with the nearest fence info; ALLOW_WITH_FLAG
    flags.

    LOW_ACCURACY last: an advisory flag only — never blocks on its own.
    Only applied when the punch is inside a fence AND no stronger flag
    has been set.
    """
    fence_list = list(fences)

    # Back-compat: feature disabled or no fences -> behave as if geo
    # were never wired. This is what protects existing employees.
    if not geo_enabled or not fence_list:
        return GeoDecision(
            allowed=True,
            geo_flag=None,
            matched_fence=None,
            distance_m=None,
        )

    # No GPS reading at all -> LOW_ACCURACY advisory, never block.
    if punch_lat is None or punch_lng is None:
        return GeoDecision(
            allowed=True,
            geo_flag=GeoFlag.LOW_ACCURACY,
            matched_fence=None,
            distance_m=None,
            reason_code="LOW_ACCURACY",
            reason="No GPS fix available — punch flagged for review.",
        )

    # Compute distance to each fence; nearest first.
    matches = sorted(
        (
            FenceMatch(
                fence=f,
                distance_m=haversine_meters(
                    punch_lat, punch_lng, f.latitude, f.longitude
                ),
            )
            for f in fence_list
        ),
        key=lambda m: m.distance_m,
    )
    nearest = matches[0]
    inside_any = any(m.inside for m in matches)

    # Mock-location: strongest signal, always wins. STRICT rejects.
    if is_mock_location:
        if enforcement_mode is EnforcementMode.STRICT:
            return GeoDecision(
                allowed=False,
                geo_flag=GeoFlag.MOCK_LOCATION,
                matched_fence=nearest.fence if inside_any else None,
                distance_m=nearest.distance_m,
                reason_code="MOCK_LOCATION",
                reason=(
                    "Mock-location detected on the device. Disable any "
                    "fake-GPS app and try again."
                ),
            )
        return GeoDecision(
            allowed=True,
            geo_flag=GeoFlag.MOCK_LOCATION,
            matched_fence=nearest.fence if inside_any else None,
            distance_m=nearest.distance_m,
            reason_code="MOCK_LOCATION",
            reason="Mock-location detected; punch flagged for review.",
        )

    # Outside all fences: STRICT rejects, ALLOW_WITH_FLAG flags.
    if not inside_any:
        if enforcement_mode is EnforcementMode.STRICT:
            return GeoDecision(
                allowed=False,
                geo_flag=GeoFlag.OUTSIDE_GEOFENCE,
                matched_fence=nearest.fence,
                distance_m=nearest.distance_m,
                reason_code="OUTSIDE_GEOFENCE",
                reason=(
                    f"You're {int(round(nearest.distance_m))}m from "
                    f"{nearest.fence.name}. Move closer to punch in."
                ),
            )
        return GeoDecision(
            allowed=True,
            geo_flag=GeoFlag.OUTSIDE_GEOFENCE,
            matched_fence=nearest.fence,
            distance_m=nearest.distance_m,
            reason_code="OUTSIDE_GEOFENCE",
            reason=(
                f"Punch flagged: {int(round(nearest.distance_m))}m from "
                f"{nearest.fence.name}."
            ),
        )

    # Inside a fence. Apply LOW_ACCURACY advisory if the accuracy
    # number says the fix is unreliable. Never blocks.
    inside_match = next(m for m in matches if m.inside)
    geo_flag: Optional[GeoFlag] = None
    reason_code: Optional[str] = None
    reason: Optional[str] = None
    if (
        accuracy_m is not None
        and accuracy_m > LOW_ACCURACY_THRESHOLD_M
    ):
        geo_flag = GeoFlag.LOW_ACCURACY
        reason_code = "LOW_ACCURACY"
        reason = (
            f"GPS accuracy was poor ({int(round(accuracy_m))}m); "
            "punch flagged but accepted."
        )

    return GeoDecision(
        allowed=True,
        geo_flag=geo_flag,
        matched_fence=inside_match.fence,
        distance_m=inside_match.distance_m,
        reason_code=reason_code,
        reason=reason,
    )
