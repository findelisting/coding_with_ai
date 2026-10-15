"""Log User Location endpoint (spec: log_user_location.md)."""

import logging
import os
from datetime import datetime, timezone
from typing import Optional, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.auth import get_current_user
from app.errors import ApiError
from app.plausibility import check_points
from app.rate_limit import RateLimiter, get_rate_limiter
from app.schemas import MAX_POINTS_PER_BATCH, LocationBatch, LocationBatchResult

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 256 * 1024


class LocationStore(Protocol):
    def get_activity(self, activity_id: str) -> Optional[dict]: ...
    def has_consent(self, user_id: str) -> bool: ...
    def existing_client_ids(self, activity_id: str, client_ids: list[str]) -> set[str]: ...
    def last_point(self, activity_id: str) -> Optional[dict]: ...
    def insert_batch(self, activity_id: str, user_id: str, rows: list[dict]) -> None: ...


def _parse_ts(value):
    if isinstance(value, datetime) or value is None:
        return value
    return datetime.fromisoformat(value)


class SupabaseLocationStore:
    """Store backed by Supabase. Uses the caller's token, so Row Level Security applies."""

    def __init__(self, access_token: str):
        from supabase import create_client

        self.client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
        self.client.postgrest.auth(access_token)

    def get_activity(self, activity_id):
        res = (self.client.table("activities")
               .select("id,user_id,status,started_at,type")
               .eq("id", activity_id).limit(1).execute())
        if not res.data:
            return None
        row = res.data[0]
        row["started_at"] = _parse_ts(row["started_at"])
        return row

    def has_consent(self, user_id):
        res = (self.client.table("profiles").select("location_consent")
               .eq("id", user_id).limit(1).execute())
        return bool(res.data and res.data[0]["location_consent"])

    def existing_client_ids(self, activity_id, client_ids):
        res = (self.client.table("activity_locations").select("client_point_id")
               .eq("activity_id", activity_id).in_("client_point_id", client_ids).execute())
        return {row["client_point_id"] for row in res.data}

    def last_point(self, activity_id):
        res = (self.client.table("activity_locations")
               .select("recorded_at,latitude,longitude")
               .eq("activity_id", activity_id)
               .order("recorded_at", desc=True).limit(1).execute())
        if not res.data:
            return None
        row = res.data[0]
        row["recorded_at"] = _parse_ts(row["recorded_at"])
        return row

    def insert_batch(self, activity_id, user_id, rows):
        payload = [
            {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in row.items()}
            for row in rows
        ]
        # One RPC call = one transaction: insert points and update the activity summary.
        self.client.rpc("insert_activity_locations",
                        {"p_activity_id": activity_id, "p_points": payload}).execute()


def get_location_store(request: Request) -> LocationStore:
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return SupabaseLocationStore(token)


router = APIRouter(prefix="/api/v1")


@router.post("/activities/{activity_id}/locations", status_code=201,
             response_model=LocationBatchResult)
def log_locations(
    activity_id: UUID,
    batch: LocationBatch,
    request: Request,
    user_id: str = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_rate_limiter),
    store: LocationStore = Depends(get_location_store),
):
    limiter.check(user_id)
    activity_key = str(activity_id)

    content_length = int(request.headers.get("content-length") or 0)
    if len(batch.points) > MAX_POINTS_PER_BATCH or content_length > MAX_BODY_BYTES:
        raise ApiError(413, "payload_too_large",
                       f"At most {MAX_POINTS_PER_BATCH} points and {MAX_BODY_BYTES} bytes per batch")

    activity = store.get_activity(activity_key)
    # Another user's activity looks the same as a missing one.
    if activity is None or activity["user_id"] != user_id:
        raise ApiError(404, "activity_not_found", "Activity not found")
    if activity["status"] != "in_progress":
        raise ApiError(409, "activity_not_active", "Activity is not in progress")
    if not store.has_consent(user_id):
        raise ApiError(403, "consent_required", "Location consent is required")

    started_at = activity["started_at"]
    early = [{"index": i, "field": "recorded_at", "issue": "before_activity_start"}
             for i, p in enumerate(batch.points) if p.recorded_at < started_at]
    if early:
        raise ApiError(422, "validation_error", "Request validation failed", early)

    ids = [str(p.client_point_id) for p in batch.points]
    existing = store.existing_client_ids(activity_key, ids)
    seen = set(existing)
    new_points = []
    for point, cid in zip(batch.points, ids):
        if cid in seen:
            continue
        seen.add(cid)
        row = point.model_dump()
        row["client_point_id"] = cid
        new_points.append(row)

    flags = check_points(store.last_point(activity_key), new_points,
                         activity.get("type") or "run")

    received_at = datetime.now(timezone.utc)
    rows = []
    for row in new_points:
        reason = flags.get(row["client_point_id"])
        rows.append({
            **row,
            "activity_id": activity_key,
            "user_id": user_id,
            "received_at": received_at,
            "flagged": reason is not None,
            "flag_reason": reason,
        })
    if rows:
        store.insert_batch(activity_key, user_id, rows)

    # Counts and reasons only: never coordinates.
    logger.info("locations logged activity=%s accepted=%d duplicates=%d flagged=%d reasons=%s",
                activity_key, len(rows), len(ids) - len(rows), len(flags),
                sorted(set(flags.values())))

    return LocationBatchResult(
        activity_id=activity_key,
        accepted=len(rows),
        duplicates=len(ids) - len(rows),
        flagged=len(flags),
        flags=[{"client_point_id": cid, "reason": reason} for cid, reason in flags.items()],
    )
