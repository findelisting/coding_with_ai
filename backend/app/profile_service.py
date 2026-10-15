"""Sign up a new user and create their profile (spec: spec.md)."""

import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

DISPLAY_NAME_MIN = 2
DISPLAY_NAME_MAX = 40
PASSWORD_MIN = 6  # Supabase Auth default minimum
# One "@", text on both sides, no spaces.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+$")

PROFILE_COLUMNS = "id,display_name,email,location_consent,created_at"


class ProfileError(Exception):
    pass


class EmailTakenError(Exception):
    pass


@dataclass
class UserProfile:
    id: str
    display_name: str
    email: str
    location_consent: bool
    created_at: datetime


class AuthBackend(Protocol):
    def sign_up(self, email: str, password: str, metadata: dict) -> dict: ...
    def get_profile(self, profile_id: str, access_token: str) -> Optional[dict]: ...


class SupabaseAuthBackend:
    """Supabase Auth plus the profiles table. Uses the anon key only, never the service key."""

    def _client(self):
        from supabase import create_client

        # New client per call: sign_up stores a session on the client, which must not leak
        # between requests.
        return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])

    def sign_up(self, email, password, metadata):
        from supabase_auth.errors import AuthError

        try:
            res = self._client().auth.sign_up(
                {"email": email, "password": password, "options": {"data": metadata}}
            )
        except AuthError as exc:
            if exc.code in ("user_already_exists", "email_exists"):
                raise EmailTakenError() from exc
            raise ProfileError("signup failed") from exc
        user = res.user
        # With email confirmation on, Supabase hides duplicates by returning a user
        # with no identities instead of an error.
        if user is None or not user.identities:
            raise EmailTakenError()
        # The database trigger has created the profiles row in the same transaction.
        return {"id": user.id, "created_at": user.created_at}

    def get_profile(self, profile_id, access_token):
        client = self._client()
        client.postgrest.auth(access_token)  # caller's token, so Row Level Security applies
        res = (client.table("profiles").select(PROFILE_COLUMNS)
               .eq("id", profile_id).limit(1).execute())
        return res.data[0] if res.data else None


class ProfileService:
    def __init__(self, backend: AuthBackend):
        self._backend = backend

    def create_profile(self, display_name: str, email: str, password: str,
                       location_consent: bool = False) -> UserProfile:
        display_name = display_name.strip()
        email = email.strip().lower()

        # Validate everything before calling Supabase, so a failure stores nothing.
        if not DISPLAY_NAME_MIN <= len(display_name) <= DISPLAY_NAME_MAX:
            raise ProfileError("display_name must be 2-40 characters")
        if not EMAIL_PATTERN.match(email):
            raise ProfileError("invalid email")
        if len(password) < PASSWORD_MIN:
            raise ProfileError("password must be at least 6 characters")

        try:
            user = self._backend.sign_up(
                email, password,
                {"display_name": display_name, "location_consent": location_consent},
            )
        except EmailTakenError:
            raise ProfileError("email already registered") from None

        return UserProfile(user["id"], display_name, email, location_consent, user["created_at"])

    def get_profile(self, profile_id: str, access_token: str) -> Optional[UserProfile]:
        row = self._backend.get_profile(profile_id, access_token)
        return UserProfile(**row) if row else None
