"""Sign-up and own-profile endpoints (spec: spec.md)."""

from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from app.auth import get_current_user
from app.errors import ApiError
from app.profile_service import ProfileError, ProfileService, SupabaseAuthBackend

# ProfileError message -> (HTTP status, error code). Anything else is a validation error.
_ERRORS = {
    "email already registered": (409, "email_taken"),
    "signup failed": (502, "signup_failed"),
}


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    email: str
    password: str
    location_consent: bool = False


class ProfileOut(BaseModel):
    id: str
    display_name: str
    email: str
    location_consent: bool
    created_at: datetime


def get_profile_service() -> ProfileService:
    return ProfileService(SupabaseAuthBackend())


router = APIRouter(prefix="/api/v1")


@router.post("/signup", status_code=201, response_model=ProfileOut)
def signup(body: SignupRequest, service: ProfileService = Depends(get_profile_service)):
    try:
        profile = service.create_profile(**body.model_dump())
    except ProfileError as exc:
        status, code = _ERRORS.get(str(exc), (422, "validation_error"))
        raise ApiError(status, code, str(exc))
    return asdict(profile)


@router.get("/profiles/me", response_model=ProfileOut)
def my_profile(
    request: Request,
    user_id: str = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    profile = service.get_profile(user_id, token)
    if profile is None:
        raise ApiError(404, "profile_not_found", "Profile not found")
    return asdict(profile)
