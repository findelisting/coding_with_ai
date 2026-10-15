"""Server-side plausibility checks for location points (spec section 8).

Points are flagged, never rejected. Client-reported speed is never used for
the speed check; implied speed comes from distance over time.
"""

import math
from datetime import datetime
from typing import Optional

EARTH_RADIUS_M = 6_371_000

MAX_SPEED_MPS = {"run": 12.0, "walk": 12.0, "cycle": 25.0}
LOW_ACCURACY_M = 100.0
OUT_OF_ORDER_S = 5.0
FROZEN_S = 120.0
FROZEN_MIN_SPEED_MPS = 1.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def check_points(prev: Optional[dict], points: list[dict], activity_type: str) -> dict[str, str]:
    """Return {client_point_id: flag_reason} for points that fail a check.

    `prev` is the last stored point (or None). Each point dict needs
    client_point_id, recorded_at (datetime), latitude, longitude, accuracy_m,
    and optionally speed_mps. Points are checked in the order received.
    """
    max_speed = MAX_SPEED_MPS.get(activity_type, MAX_SPEED_MPS["run"])
    flags: dict[str, str] = {}
    frozen_since: Optional[datetime] = None

    for point in points:
        reason = None
        if prev is not None:
            dt = (point["recorded_at"] - prev["recorded_at"]).total_seconds()
            dist = haversine_m(prev["latitude"], prev["longitude"],
                               point["latitude"], point["longitude"])
            if dt < -OUT_OF_ORDER_S:
                flags[point["client_point_id"]] = "out_of_order"
                continue  # keep the later point as the reference
            if dt > 0 and dist / dt > max_speed:
                reason = "implausible_speed"

            same_spot = dist == 0
            moving = (point.get("speed_mps") or 0) > FROZEN_MIN_SPEED_MPS
            if same_spot and moving:
                frozen_since = frozen_since or prev["recorded_at"]
                if (point["recorded_at"] - frozen_since).total_seconds() > FROZEN_S:
                    reason = reason or "frozen_position"
            else:
                frozen_since = None

        if reason is None and point["accuracy_m"] > LOW_ACCURACY_M:
            reason = "low_accuracy"
        if reason:
            flags[point["client_point_id"]] = reason
        prev = point

    return flags
