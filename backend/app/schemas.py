from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

MAX_FUTURE_SKEW = timedelta(seconds=60)
MAX_POINTS_PER_BATCH = 500

Source = Literal["phone_gps", "watch_gps", "band", "import"]


class LocationPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_point_id: UUID
    recorded_at: AwareDatetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(gt=0, le=1000)
    altitude_m: Optional[float] = Field(default=None, ge=-500, le=9000)
    altitude_accuracy_m: Optional[float] = Field(default=None, gt=0)
    speed_mps: Optional[float] = Field(default=None, ge=0)
    heading_deg: Optional[float] = Field(default=None, ge=0, lt=360)
    source: Source

    @field_validator("recorded_at")
    @classmethod
    def not_in_future(cls, value: datetime) -> datetime:
        if value > datetime.now(timezone.utc) + MAX_FUTURE_SKEW:
            raise PydanticCustomError("in_future", "recorded_at is too far in the future")
        return value


class LocationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Upper bound is checked in the route so it can return 413, not 422.
    points: list[LocationPoint] = Field(min_length=1)


class PointFlag(BaseModel):
    client_point_id: str
    reason: str


class LocationBatchResult(BaseModel):
    activity_id: str
    accepted: int
    duplicates: int
    flagged: int
    flags: list[PointFlag]
