"""Tests for the Log User Location spec (log_user_location.md).

Written before the implementation (test-first), so these fail until the
endpoint exists. They assume these seams in the backend:

- `app.main.app`: the FastAPI app.
- `app.auth.get_current_user`: dependency that returns the caller's user id
  from the Supabase token, or raises 401.
- `app.locations.get_location_store`: dependency that returns the storage
  object. Tests swap it for `FakeStore` below, so no real Supabase is needed.

RLS tests against a real Supabase database are out of scope here.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.locations import get_location_store
from app.main import app

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"

# Coordinates in Accra, used across tests.
ACCRA_LAT, ACCRA_LON = 5.603717, -0.186964


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class FakeStore:
    """In-memory stand-in for the Supabase-backed location store."""

    def __init__(self):
        self.activities = {}   # activity_id -> {"user_id", "status", "started_at"}
        self.consent = {}      # user_id -> bool
        self.rows = []         # stored location points (dicts)

    def add_activity(self, user_id, status="in_progress", started_at=None):
        activity_id = str(uuid.uuid4())
        self.activities[activity_id] = {
            "user_id": user_id,
            "status": status,
            "started_at": started_at or datetime.now(timezone.utc) - timedelta(hours=1),
        }
        return activity_id

    def rows_for(self, activity_id):
        return [r for r in self.rows if r["activity_id"] == activity_id]

    # LocationStore protocol (app.locations.LocationStore)

    def get_activity(self, activity_id):
        activity = self.activities.get(activity_id)
        return dict(activity) if activity else None

    def has_consent(self, user_id):
        return self.consent.get(user_id, False)

    def existing_client_ids(self, activity_id, client_ids):
        wanted = set(client_ids)
        return {r["client_point_id"] for r in self.rows_for(activity_id)
                if r["client_point_id"] in wanted}

    def last_point(self, activity_id):
        rows = self.rows_for(activity_id)
        return max(rows, key=lambda r: r["recorded_at"]) if rows else None

    def insert_batch(self, activity_id, user_id, rows):
        self.rows.extend(dict(r) for r in rows)
        summary = self.activities[activity_id]
        summary["point_count"] = summary.get("point_count", 0) + len(rows)
        latest = max(r["recorded_at"] for r in rows)
        if summary.get("last_point_at") is None or latest > summary["last_point_at"]:
            summary["last_point_at"] = latest


@pytest.fixture
def store():
    s = FakeStore()
    s.consent[USER_A] = True
    s.consent[USER_B] = True
    return s


@pytest.fixture
def current_user():
    """Mutable holder so a test can switch the caller or simulate a bad token."""
    return {"id": USER_A}


@pytest.fixture
def client(store, current_user):
    def fake_user():
        if current_user["id"] is None:
            raise HTTPException(status_code=401, detail="unauthorized")
        return current_user["id"]

    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[get_location_store] = lambda: store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_point(seconds_ago=0, lat=ACCRA_LAT, lon=ACCRA_LON, **overrides):
    recorded = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    point = {
        "client_point_id": str(uuid.uuid4()),
        "recorded_at": recorded.isoformat().replace("+00:00", "Z"),
        "latitude": lat,
        "longitude": lon,
        "accuracy_m": 6.5,
        "altitude_m": 61.2,
        "speed_mps": 2.9,
        "heading_deg": 184.0,
        "source": "phone_gps",
    }
    point.update(overrides)
    return point


def make_track(n, start_seconds_ago=600):
    """n points about 1 s apart, moving slowly north (plausible walking)."""
    return [
        make_point(seconds_ago=start_seconds_ago - i, lat=ACCRA_LAT + i * 0.00001)
        for i in range(n)
    ]


def post(client, activity_id, points, headers=None):
    return client.post(
        f"/api/v1/activities/{activity_id}/locations",
        json={"points": points},
        headers=headers or {"Authorization": "Bearer test"},
    )


def error_code(resp):
    return resp.json()["error"]["code"]


# ---------------------------------------------------------------------------
# Section 7: Given-When-Then scenarios
# ---------------------------------------------------------------------------

def test_happy_path_stores_all_points(client, store):
    activity = store.add_activity(USER_A)

    resp = post(client, activity, make_track(50))

    assert resp.status_code == 201
    body = resp.json()
    assert body["activity_id"] == activity
    assert body["accepted"] == 50
    assert body["duplicates"] == 0
    assert body["flagged"] == 0
    assert len(store.rows_for(activity)) == 50


def test_duplicate_retry_writes_nothing_new(client, store):
    activity = store.add_activity(USER_A)
    points = make_track(50)
    post(client, activity, points)

    resp = post(client, activity, points)

    assert resp.status_code == 201
    assert resp.json()["accepted"] == 0
    assert resp.json()["duplicates"] == 50
    assert len(store.rows_for(activity)) == 50


def test_other_users_activity_returns_404(client, store):
    activity_b = store.add_activity(USER_B)

    resp = post(client, activity_b, make_track(3))

    assert resp.status_code == 404
    assert error_code(resp) == "activity_not_found"
    assert store.rows_for(activity_b) == []


def test_unknown_activity_returns_404(client, store):
    resp = post(client, str(uuid.uuid4()), make_track(3))

    assert resp.status_code == 404
    assert error_code(resp) == "activity_not_found"


@pytest.mark.parametrize("status", ["ended", "cancelled"])
def test_inactive_activity_returns_409(client, store, status):
    activity = store.add_activity(USER_A, status=status)

    resp = post(client, activity, make_track(3))

    assert resp.status_code == 409
    assert error_code(resp) == "activity_not_active"
    assert store.rows_for(activity) == []


def test_invalid_coordinate_rejects_whole_batch(client, store):
    activity = store.add_activity(USER_A)
    points = make_track(5)
    points[3]["latitude"] = 95

    resp = post(client, activity, points)

    assert resp.status_code == 422
    assert error_code(resp) == "validation_error"
    detail = resp.json()["error"]["details"][0]
    assert detail == {"index": 3, "field": "latitude", "issue": "out_of_range"}
    assert store.rows_for(activity) == []


def test_teleport_point_is_flagged_not_rejected(client, store):
    activity = store.add_activity(USER_A)
    post(client, activity, [make_point(seconds_ago=10)])
    # About 300 km north of Accra, 10 seconds later.
    far_point = make_point(seconds_ago=0, lat=ACCRA_LAT + 2.7)

    resp = post(client, activity, [far_point])

    assert resp.status_code == 201
    body = resp.json()
    assert body["accepted"] == 1
    assert body["flagged"] == 1
    assert body["flags"] == [
        {"client_point_id": far_point["client_point_id"], "reason": "implausible_speed"}
    ]
    stored = store.rows_for(activity)[-1]
    assert stored["flagged"] is True
    assert stored["flag_reason"] == "implausible_speed"


def test_forbidden_field_is_rejected_and_not_logged(client, store, caplog):
    activity = store.add_activity(USER_A)
    point = make_point(ssn="123-45-6789")

    with caplog.at_level(logging.DEBUG):
        resp = post(client, activity, [point])

    assert resp.status_code == 422
    assert error_code(resp) == "validation_error"
    assert store.rows_for(activity) == []
    assert "123-45-6789" not in caplog.text
    assert "123-45-6789" not in resp.text


def test_no_consent_returns_403(client, store):
    store.consent[USER_A] = False
    activity = store.add_activity(USER_A)

    resp = post(client, activity, make_track(3))

    assert resp.status_code == 403
    assert error_code(resp) == "consent_required"
    assert store.rows_for(activity) == []


def test_missing_or_expired_token_returns_401(client, store, current_user):
    activity = store.add_activity(USER_A)
    current_user["id"] = None

    resp = post(client, activity, make_track(3))

    assert resp.status_code == 401
    assert store.rows_for(activity) == []


def test_rate_limit_returns_429_with_retry_after(client, store):
    activity = store.add_activity(USER_A)
    for _ in range(60):
        assert post(client, activity, [make_point()]).status_code == 201

    resp = post(client, activity, [make_point()])

    assert resp.status_code == 429
    assert error_code(resp) == "rate_limited"
    assert "Retry-After" in resp.headers


# ---------------------------------------------------------------------------
# Section 3: interface validation
# ---------------------------------------------------------------------------

def test_empty_batch_is_rejected(client, store):
    activity = store.add_activity(USER_A)

    resp = post(client, activity, [])

    assert resp.status_code == 422


def test_more_than_500_points_returns_413(client, store):
    activity = store.add_activity(USER_A)

    resp = post(client, activity, make_track(501, start_seconds_ago=1000))

    assert resp.status_code == 413
    assert error_code(resp) == "payload_too_large"
    assert store.rows_for(activity) == []


def test_exactly_500_points_is_accepted(client, store):
    activity = store.add_activity(USER_A)

    resp = post(client, activity, make_track(500, start_seconds_ago=1000))

    assert resp.status_code == 201
    assert resp.json()["accepted"] == 500


@pytest.mark.parametrize(
    "field, value",
    [
        ("latitude", -90.0001),
        ("longitude", 180.0001),
        ("longitude", -180.0001),
        ("accuracy_m", 0),
        ("accuracy_m", 1001),
        ("altitude_m", -501),
        ("altitude_m", 9001),
        ("speed_mps", -1),
        ("heading_deg", 360),
        ("source", "carrier_pigeon"),
        ("client_point_id", "not-a-uuid"),
    ],
)
def test_out_of_range_fields_are_rejected(client, store, field, value):
    activity = store.add_activity(USER_A)

    resp = post(client, activity, [make_point(**{field: value})])

    assert resp.status_code == 422
    assert resp.json()["error"]["details"][0]["field"] == field


@pytest.mark.parametrize(
    "field", ["client_point_id", "recorded_at", "latitude", "longitude", "accuracy_m", "source"]
)
def test_missing_required_field_is_rejected(client, store, field):
    activity = store.add_activity(USER_A)
    point = make_point()
    del point[field]

    resp = post(client, activity, [point])

    assert resp.status_code == 422


def test_optional_fields_can_be_omitted(client, store):
    activity = store.add_activity(USER_A)
    point = make_point()
    for field in ("altitude_m", "speed_mps", "heading_deg"):
        del point[field]

    resp = post(client, activity, [point])

    assert resp.status_code == 201


def test_point_too_far_in_future_is_rejected(client, store):
    activity = store.add_activity(USER_A)

    resp = post(client, activity, [make_point(seconds_ago=-120)])

    assert resp.status_code == 422


def test_point_before_activity_start_is_rejected(client, store):
    activity = store.add_activity(
        USER_A, started_at=datetime.now(timezone.utc) - timedelta(minutes=5)
    )

    resp = post(client, activity, [make_point(seconds_ago=600)])

    assert resp.status_code == 422


def test_malformed_json_returns_400(client, store):
    activity = store.add_activity(USER_A)

    resp = client.post(
        f"/api/v1/activities/{activity}/locations",
        content=b"{not json",
        headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
    )

    assert resp.status_code == 400
    assert error_code(resp) == "bad_request"


# ---------------------------------------------------------------------------
# Section 5: postconditions
# ---------------------------------------------------------------------------

def test_response_counts_add_up(client, store):
    activity = store.add_activity(USER_A)
    first = make_track(10)
    post(client, activity, first)
    batch = first[:4] + make_track(6, start_seconds_ago=300)

    body = post(client, activity, batch).json()

    assert body["accepted"] + body["duplicates"] == len(batch)
    assert body["flagged"] <= body["accepted"]


def test_stored_rows_keep_client_time_and_add_server_time(client, store):
    activity = store.add_activity(USER_A)
    point = make_point(seconds_ago=30)

    post(client, activity, [point])

    row = store.rows_for(activity)[0]
    assert row["user_id"] == USER_A
    assert row["recorded_at"] == datetime.fromisoformat(point["recorded_at"])
    assert row["received_at"] is not None


def test_activity_summary_is_updated(client, store):
    activity = store.add_activity(USER_A)

    post(client, activity, make_track(5))

    summary = store.activities[activity]
    assert summary["point_count"] == 5
    assert summary["last_point_at"] is not None


# ---------------------------------------------------------------------------
# Section 6: invariants
# ---------------------------------------------------------------------------

def test_user_id_comes_from_token_not_body(client, store):
    activity = store.add_activity(USER_A)
    point = make_point()

    resp = client.post(
        f"/api/v1/activities/{activity}/locations",
        json={"user_id": USER_B, "points": [point]},
        headers={"Authorization": "Bearer test"},
    )

    # Unknown top-level field is rejected; nothing is written for USER_B.
    assert resp.status_code == 422
    assert not any(r["user_id"] == USER_B for r in store.rows)


def test_coordinates_never_appear_in_logs(client, store, caplog):
    activity = store.add_activity(USER_A)
    point = make_point(lat=5.6123456, lon=-0.1987654)

    with caplog.at_level(logging.DEBUG):
        post(client, activity, [point])
        points = make_track(3)
        points[0]["latitude"] = 95  # error path must not log coordinates either
        post(client, activity, points)

    assert "5.6123456" not in caplog.text
    assert "-0.1987654" not in caplog.text
    assert str(ACCRA_LON) not in caplog.text


def test_other_activities_are_untouched(client, store):
    activity_1 = store.add_activity(USER_A)
    activity_2 = store.add_activity(USER_A)
    post(client, activity_2, make_track(3))
    before = list(store.rows_for(activity_2))

    post(client, activity_1, make_track(5))

    assert store.rows_for(activity_2) == before


def test_no_endpoint_to_update_or_delete_points(client, store):
    activity = store.add_activity(USER_A)
    url = f"/api/v1/activities/{activity}/locations"

    assert client.put(url, json={"points": []}).status_code == 405
    assert client.patch(url, json={"points": []}).status_code == 405
    assert client.delete(url).status_code == 405


# ---------------------------------------------------------------------------
# Section 8: plausibility checks
# ---------------------------------------------------------------------------

def test_low_accuracy_point_is_flagged(client, store):
    activity = store.add_activity(USER_A)
    point = make_point(accuracy_m=150)

    body = post(client, activity, [point]).json()

    assert body["flags"] == [
        {"client_point_id": point["client_point_id"], "reason": "low_accuracy"}
    ]


def test_out_of_order_point_is_flagged(client, store):
    activity = store.add_activity(USER_A)
    post(client, activity, [make_point(seconds_ago=10)])
    late = make_point(seconds_ago=30)

    body = post(client, activity, [late]).json()

    assert body["flags"] == [
        {"client_point_id": late["client_point_id"], "reason": "out_of_order"}
    ]


def test_frozen_position_while_moving_is_flagged(client, store):
    activity = store.add_activity(USER_A)
    # Same coordinates for 180 s while reporting 3 m/s.
    points = [make_point(seconds_ago=200 - i * 10, speed_mps=3.0) for i in range(19)]

    body = post(client, activity, points).json()

    assert any(f["reason"] == "frozen_position" for f in body["flags"])


def test_client_speed_is_not_trusted(client, store):
    """Client claims slow speed, but the implied speed between points is huge."""
    activity = store.add_activity(USER_A)
    post(client, activity, [make_point(seconds_ago=10, speed_mps=1.0)])
    far = make_point(seconds_ago=0, lat=ACCRA_LAT + 2.7, speed_mps=1.0)

    body = post(client, activity, [far]).json()

    assert body["flags"][0]["reason"] == "implausible_speed"
