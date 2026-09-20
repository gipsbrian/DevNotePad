import pytest

from app.config import settings
from tests.conftest import TEST_USER

NEW = {"username": "Teammate", "email": "Mate@Example.com", "password": "long-enough-pw"}


@pytest.fixture()
def open_registration(monkeypatch):
    monkeypatch.setattr(settings, "allow_registration", True)


def test_registration_is_open_by_default():
    from app.config import Settings  # noqa: PLC0415

    assert Settings.model_fields["allow_registration"].default is True


def test_registration_can_be_closed(anon_client):
    assert anon_client.get("/api/auth/registration").json() == {"open": False}
    resp = anon_client.post("/api/auth/register", json=NEW)
    assert resp.status_code == 403
    assert anon_client.post(
        "/api/auth/login", json={"identifier": NEW["username"], "password": NEW["password"]}
    ).status_code == 401


def test_registering_creates_the_account_and_signs_you_in(anon_client, open_registration):
    assert anon_client.get("/api/auth/registration").json() == {"open": True}

    resp = anon_client.post("/api/auth/register", json=NEW)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # Stored lowercased, the same way sign-in looks accounts up.
    assert body["username"] == "teammate"
    assert body["email"] == "mate@example.com"

    assert anon_client.get("/api/auth/me").json()["username"] == "teammate"
    assert anon_client.get("/api/dashboards").json() == []


def test_a_registered_account_can_sign_back_in_with_either_name(anon_client, open_registration):
    anon_client.post("/api/auth/register", json=NEW)
    anon_client.post("/api/auth/logout")

    for identifier in ("teammate", "MATE@example.com"):
        resp = anon_client.post(
            "/api/auth/login", json={"identifier": identifier, "password": NEW["password"]}
        )
        assert resp.status_code == 200, identifier


def test_a_taken_username_is_refused(anon_client, user, open_registration):
    resp = anon_client.post(
        "/api/auth/register", json={**NEW, "username": TEST_USER["username"].upper()}
    )
    assert resp.status_code == 409
    assert "username" in resp.json()["detail"]


def test_a_taken_email_is_refused(anon_client, user, open_registration):
    resp = anon_client.post(
        "/api/auth/register", json={**NEW, "email": TEST_USER["email"].upper()}
    )
    assert resp.status_code == 409
    assert "email" in resp.json()["detail"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("username", "ab"),  # too short
        ("username", "me@example.com"),  # would read as an email at sign-in
        ("username", "has space"),
        ("username", "-leading-dash"),
        ("email", "not-an-email"),
        ("email", "two@@example.com"),
        ("password", "short"),
        ("password", "x" * 73),  # bcrypt would silently ignore the tail
    ],
)
def test_invalid_details_are_refused(anon_client, open_registration, field, value):
    resp = anon_client.post("/api/auth/register", json={**NEW, field: value})
    assert resp.status_code == 422, resp.text
    assert isinstance(resp.json()["detail"], str)
    assert anon_client.get("/api/auth/me").status_code == 401


def test_a_refused_registration_leaves_no_account_behind(anon_client, open_registration):
    anon_client.post("/api/auth/register", json={**NEW, "password": "short"})
    assert anon_client.post("/api/auth/register", json=NEW).status_code == 201
