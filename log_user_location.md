# Spec: Log User Location

Status: Draft · Owner: backend · Last updated: 2026-09-29

## 1. Purpose

Record GPS location points for a user during an activity, so the platform can verify the activity happened, compute distance and pace, and adjust for terrain and elevation when scoring competitions fairly.

A client (web app, phone, or device integration) sends location points in batches while an activity is in progress. The backend validates, stores and flags suspicious points. Raw location data is sensitive and is never exposed to other users.

## 2. Scope

In scope:
- Accepting batches of GPS points for one active activity of the authenticated user.
- Validation, deduplication and plausibility checks (anti-spoofing).
- Storage in Supabase Postgres with Row Level Security.

Out of scope (separate specs):
- Starting and ending activities (`POST /activities`, `POST /activities/{id}/end`).
- Scoring, baselines and handicaps.
- Importing historical tracks from third-party providers (Strava, Garmin).
- Showing maps or routes to friends.

## 3. Interface

### Endpoint

```
POST /api/v1/activities/{activity_id}/locations
Authorization: Bearer <Supabase access token>
Content-Type: application/json
Idempotency-Key: <client-generated UUID>   (optional, recommended)
```

### Request body

```json
{
  "points": [
    {
      "client_point_id": "0b6f0c1e-3a7f-4a55-9e0a-1f3a2c9d8e11",
      "recorded_at": "2026-09-29T07:15:03.120Z",
      "latitude": 5.603717,
      "longitude": -0.186964,
      "accuracy_m": 6.5,
      "altitude_m": 61.2,
      "altitude_accuracy_m": 10.0,
      "speed_mps": 2.9,
      "heading_deg": 184.0,
      "source": "phone_gps"
    }
  ]
}
```

| Field | Type | Required | Rules |
|---|---|---|---|
| `points` | array | yes | 1 to 500 items |
| `client_point_id` | UUID | yes | Unique per activity; used for dedup |
| `recorded_at` | ISO 8601 UTC timestamp | yes | Not more than 60 s in the future (server clock); not before activity `started_at` |
| `latitude` | number | yes | −90 to 90, up to 7 decimals |
| `longitude` | number | yes | −180 to 180, up to 7 decimals |
| `accuracy_m` | number | yes | > 0 and ≤ 1000 |
| `altitude_m` | number | no | −500 to 9000 |
| `altitude_accuracy_m` | number | no | > 0 |
| `speed_mps` | number | no | ≥ 0 |
| `heading_deg` | number | no | 0 to < 360 |
| `source` | enum | yes | `phone_gps`, `watch_gps`, `band`, `import` |

Unknown fields are rejected (`422`), not silently ignored.

### Responses

`201 Created` — batch accepted (some points may be flagged or skipped as duplicates):

```json
{
  "activity_id": "5c1d...",
  "accepted": 48,
  "duplicates": 2,
  "flagged": 1,
  "flags": [
    { "client_point_id": "…", "reason": "implausible_speed" }
  ]
}
```

| Status | When | Body `error.code` |
|---|---|---|
| `400` | Malformed JSON | `bad_request` |
| `401` | Missing, invalid or expired token | `unauthorized` |
| `403` | User has not given location consent | `consent_required` |
| `404` | Activity does not exist, or belongs to another user | `activity_not_found` |
| `409` | Activity is not `in_progress` (ended or cancelled) | `activity_not_active` |
| `413` | More than 500 points or body > 256 KB | `payload_too_large` |
| `422` | Field validation fails (whole batch rejected) | `validation_error`, with per-field `details` |
| `429` | Rate limit exceeded | `rate_limited`, with `Retry-After` header |

Error shape:

```json
{ "error": { "code": "validation_error", "message": "…", "details": [ { "index": 3, "field": "latitude", "issue": "out_of_range" } ] } }
```

Another user's activity returns `404`, not `403`, so callers cannot learn that the activity exists.

## 4. Preconditions

Must be true before the request is processed:

1. Caller has a valid Supabase access token; `user_id` comes from the token `sub` claim only, never from the body or URL.
2. `activity_id` exists and belongs to `user_id`.
3. Activity status is `in_progress`.
4. User has given location consent (`profiles.location_consent = true`). If not, return `403` with `consent_required`.
5. Request passes schema validation (section 3).

## 5. Postconditions

Guaranteed after a `201` response:

1. Every valid, non-duplicate point is stored exactly once in `activity_locations`, linked to `activity_id` and `user_id`.
2. Points are stored with a server `received_at` timestamp; client `recorded_at` is kept unchanged.
3. Points failing plausibility checks are stored with `flagged = true` and a `flag_reason`. They are not deleted, so reviewers and the anti-cheat model can use them.
4. Activity summary fields (`last_point_at`, `point_count`) are updated in the same transaction.
5. Response counts satisfy: `accepted + duplicates = len(points)`, and `flagged ≤ accepted`.

Guaranteed after any error response:

6. Nothing is written. The batch is all-or-nothing.

## 6. Invariants

Always true, before and after, whatever happens:

1. **No unrelated personal data.** This endpoint never reads, writes, logs or returns government IDs (for example, social security or national ID numbers), payment data, contacts, email, phone number or health metrics. Only the fields in section 3 are accepted.
2. **Ownership.** A user can write and read only their own location points. Enforced twice: in the API layer and by Supabase Row Level Security on `activity_locations`.
3. **No raw location in logs.** Application logs, error trackers and analytics never contain latitude, longitude or altitude. Log `activity_id`, counts and flag reasons only.
4. **Immutability.** Stored points are never updated in place. Corrections are new rows; deletion only via the account/data-deletion flow.
5. **Other activities untouched.** A request changes rows for its own `activity_id` only.
6. **Scores untouched.** This endpoint never changes competition scores, baselines or leaderboards directly. Scoring runs later from stored data.
7. **Server trust boundary.** Fairness and plausibility decisions are made on the server. Client-supplied `speed_mps` is stored but never trusted for scoring.

## 7. Behaviour scenarios (Given-When-Then)

**Happy path**
- Given user A is signed in, has location consent, and owns in-progress activity X
- When A posts 50 valid points to `/activities/X/locations`
- Then the response is `201` with `accepted: 50`, and 50 rows exist for X

**Duplicate retry**
- Given A already posted a batch with 50 points to activity X
- When A sends the same batch again (network retry)
- Then the response is `201` with `accepted: 0, duplicates: 50`, and no new rows exist

**Another user's activity**
- Given activity Y belongs to user B
- When A posts points to `/activities/Y/locations`
- Then the response is `404 activity_not_found`, and no rows are written

**Ended activity**
- Given activity X has status `ended`
- When A posts points to X
- Then the response is `409 activity_not_active`

**Invalid coordinate**
- Given a batch where point 3 has `latitude: 95`
- When A posts the batch
- Then the response is `422` with `details[0] = {index: 3, field: "latitude", issue: "out_of_range"}`, and no points from the batch are stored

**Teleport / spoofing**
- Given A's last stored point for X was in Accra 10 seconds ago
- When A posts a point 300 km away
- Then the point is stored with `flagged = true, flag_reason = "implausible_speed"`, and the response lists it under `flags`

**Forbidden field**
- Given a request point includes `"ssn": "123-45-6789"`
- When A posts the batch
- Then the response is `422 validation_error`, and the value is not stored or logged

**No consent**
- Given A has `location_consent = false`
- When A posts points
- Then the response is `403 consent_required`, and no rows are written

**Expired token**
- Given A's access token has expired
- When A posts points
- Then the response is `401 unauthorized`

**Rate limit**
- Given A has sent 60 requests in the last minute
- When A sends another
- Then the response is `429` with a `Retry-After` header

## 8. Plausibility checks (anti-cheat, v1)

Run on the server per point, in order of `recorded_at`, against the previous stored point:

| Check | Rule (v1 default, configurable) | Flag reason |
|---|---|---|
| Implied speed | > 12 m/s for running/walking, > 25 m/s for cycling | `implausible_speed` |
| Accuracy | `accuracy_m` > 100 | `low_accuracy` |
| Time order | `recorded_at` earlier than previous point by > 5 s | `out_of_order` |
| Frozen position | Identical coordinates for > 120 s while `speed_mps` > 1 | `frozen_position` |
| Mock provider | Client reports mock location (future field) | `mock_location` |

Flagged points are kept, not rejected. Later, AI-based review uses them.

## 9. Data model (Supabase)

```sql
create table activity_locations (
  id               bigint generated always as identity primary key,
  activity_id      uuid not null references activities(id) on delete cascade,
  user_id          uuid not null references auth.users(id) on delete cascade,
  client_point_id  uuid not null,
  recorded_at      timestamptz not null,
  received_at      timestamptz not null default now(),
  latitude         double precision not null,
  longitude        double precision not null,
  accuracy_m       real not null,
  altitude_m       real,
  altitude_accuracy_m real,
  speed_mps        real,
  heading_deg      real,
  source           text not null check (source in ('phone_gps','watch_gps','band','import')),
  flagged          boolean not null default false,
  flag_reason      text,
  unique (activity_id, client_point_id)
);

create index on activity_locations (activity_id, recorded_at);

alter table activity_locations enable row level security;

create policy "own rows read" on activity_locations
  for select using (auth.uid() = user_id);
create policy "own rows insert" on activity_locations
  for insert with check (auth.uid() = user_id);
-- No update policy: rows are immutable.
```

Consider PostGIS `geography(Point)` later for distance queries.

## 10. Non-functional requirements

- **Performance:** p95 latency < 300 ms for a 500-point batch.
- **Rate limit:** 60 requests per minute per user.
- **Idempotency:** safe to retry; dedup on `(activity_id, client_point_id)`.
- **Transport:** HTTPS only.
- **Retention:** raw points kept 12 months, then deleted or reduced to a coarse route (decision pending).
- **Privacy / compliance:** explicit opt-in consent before collection; user can export and delete their data (GDPR-style rights). Location of other users is never returned by this endpoint.
- **Observability:** metrics for points accepted, duplicates, flagged-by-reason, and error rates. No coordinates in metrics or logs.

## 11. Testing

- Unit tests: validation rules, each plausibility check, dedup logic.
- API tests (pytest + FastAPI `TestClient`): one test per Given-When-Then scenario in section 7.
- RLS tests: user A cannot read or insert rows for user B through Supabase directly.
- Log test: assert no latitude/longitude values appear in captured logs.

## 12. Open questions

1. Retention: delete raw points after 12 months, or keep a simplified route?
2. Can users mark "private zones" (home, work) where points are blurred or dropped?
3. Upload rate: batch every N seconds on the client, or stream (WebSocket)?
4. Offline support: accept points recorded while offline if the activity has since ended (grace window)?
5. Precision: round stored coordinates (for example, to 5 decimals ≈ 1 m) to reduce sensitivity?
