"""Sign up / create profile (spec: spec.md).

Supabase is swapped for an in-memory FakeBackend, so these tests need no network.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.profile_service import EmailTakenError, ProfileError, ProfileService
from app.signup import get_profile_service

PASSWORD = "secret123"


class FakeBackend:
    """Stands in for Supabase Auth + the profiles trigger."""

    def __init__(self):
        self.profiles: dict[str, dict] = {}

    def sign_up(self, email, password, metadata):
        if any(p["email"] == email for p in self.profiles.values()):
            raise EmailTakenError()
        user = {"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc)}
        self.profiles[user["id"]] = {**user, "email": email, **metadata}
        return user

    def get_profile(self, profile_id, access_token):
        return self.profiles.get(profile_id)


@pytest.fixture
def backend():
    return FakeBackend()


@pytest.fixture
def service(backend):
    return ProfileService(backend)


def test_signup_creates_user_in_database(service, backend):
    # Given: input form is presented (with the user's details filled in)
    form = {"display_name": "John Doe", "email": "john@example.com",
            "password": PASSWORD, "location_consent": True}

    # When: the user clicks signup
    profile = service.create_profile(**form)

    # Then: the data is saved to the database and a user is created
    saved = backend.profiles[profile.id]
    assert saved["display_name"] == "John Doe"
    assert saved["email"] == "john@example.com"
    assert saved["location_consent"] is True


def test_input_is_trimmed_and_email_lower_cased(service):
    profile = service.create_profile("  John Doe  ", "  John@Example.COM ", PASSWORD)

    assert profile.display_name == "John Doe"
    assert profile.email == "john@example.com"
    assert profile.location_consent is False


@pytest.mark.parametrize("name, email, password, message", [
    ("J", "john@example.com", PASSWORD, "display_name must be 2-40 characters"),
    ("x" * 41, "john@example.com", PASSWORD, "display_name must be 2-40 characters"),
    ("John Doe", "john@", PASSWORD, "invalid email"),
    ("John Doe", "jo hn@example.com", PASSWORD, "invalid email"),
    ("John Doe", "john@example.com", "12345", "password must be at least 6 characters"),
])
def test_invalid_input_is_rejected_and_nothing_stored(service, backend, name, email, password, message):
    with pytest.raises(ProfileError, match=message):
        service.create_profile(name, email, password)
    assert backend.profiles == {}


def test_duplicate_email_is_rejected(service):
    service.create_profile("John Doe", "john@example.com", PASSWORD)

    with pytest.raises(ProfileError, match="email already registered"):
        service.create_profile("Johnny", "  JOHN@Example.com ", PASSWORD)


# ---------------------------------------------------------------------------
# API: POST /api/v1/signup
# ---------------------------------------------------------------------------

@pytest.fixture
def client(service):
    app.dependency_overrides[get_profile_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_signup_endpoint_returns_201_with_profile(client):
    res = client.post("/api/v1/signup", json={
        "display_name": "John Doe", "email": "john@example.com", "password": PASSWORD,
    })

    assert res.status_code == 201
    body = res.json()
    assert body["email"] == "john@example.com"
    assert "password" not in body


def test_signup_endpoint_rejects_duplicate_with_409(client):
    form = {"display_name": "John Doe", "email": "john@example.com", "password": PASSWORD}
    client.post("/api/v1/signup", json=form)

    res = client.post("/api/v1/signup", json=form)

    assert res.status_code == 409
    assert res.json()["error"]["code"] == "email_taken"


def test_signup_endpoint_rejects_bad_input_with_422(client):
    res = client.post("/api/v1/signup", json={
        "display_name": "J", "email": "john@example.com", "password": PASSWORD,
    })

    assert res.status_code == 422
    assert res.json()["error"]["message"] == "display_name must be 2-40 characters"
