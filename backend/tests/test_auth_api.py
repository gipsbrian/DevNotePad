import pytest

from app.auth import hash_password, seed_first_user, verify_password
from app.config import settings
from app.models import User
from tests.conftest import TEST_USER

PROTECTED = [
    ("get", "/api/dashboards"),
    ("get", "/api/settings"),
    ("get", "/api/insights/members"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_endpoints_reject_an_anonymous_caller(anon_client, method, path):
    assert getattr(anon_client, method)(path).status_code == 401


def test_health_stays_open(anon_client):
    assert anon_client.get("/api/health").status_code == 200


def test_login_with_username_then_reach_a_protected_endpoint(anon_client, user):
    resp = anon_client.post(
        "/api/auth/login",
        json={"identifier": TEST_USER["username"], "password": TEST_USER["password"]},
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "tours_seen": [],
        "is_instance_admin": False,
    }
    assert anon_client.get("/api/dashboards").status_code == 200


def test_email_also_signs_you_in(anon_client, user):
    resp = anon_client.post(
        "/api/auth/login",
        json={"identifier": TEST_USER["email"], "password": TEST_USER["password"]},
    )
    assert resp.status_code == 200


def test_identifier_is_case_insensitive(anon_client, user):
    resp = anon_client.post(
        "/api/auth/login",
        json={"identifier": "  TeStEr  ", "password": TEST_USER["password"]},
    )
    assert resp.status_code == 200


def test_wrong_password_is_rejected(anon_client, user):
    resp = anon_client.post(
        "/api/auth/login",
        json={"identifier": TEST_USER["username"], "password": "not-it"},
    )
    assert resp.status_code == 401
    assert anon_client.get("/api/dashboards").status_code == 401


def test_unknown_and_wrong_password_are_indistinguishable(anon_client, user):
    unknown = anon_client.post(
        "/api/auth/login", json={"identifier": "nobody", "password": "whatever"}
    )
    wrong = anon_client.post(
        "/api/auth/login", json={"identifier": TEST_USER["username"], "password": "nope"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_logout_ends_the_session(client):
    assert client.get("/api/dashboards").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/dashboards").status_code == 401


def test_me_returns_the_signed_in_user(client):
    assert client.get("/api/auth/me").json()["username"] == TEST_USER["username"]


def test_me_rejects_an_anonymous_caller(anon_client):
    assert anon_client.get("/api/auth/me").status_code == 401


def test_password_hash_is_not_the_password(client, session, user):
    stored = session.get(User, user.id).password_hash
    assert TEST_USER["password"] not in stored
    assert verify_password(TEST_USER["password"], stored)
    assert not verify_password("something-else", stored)


def test_hashes_are_salted(client):
    assert hash_password("same-input") != hash_password("same-input")


def test_a_malformed_hash_reads_as_a_wrong_password():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_seeding_creates_the_first_account(session, monkeypatch):
    monkeypatch.setattr(settings, "admin_username", "Founder")
    monkeypatch.setattr(settings, "admin_email", "Founder@Example.com")
    monkeypatch.setattr(settings, "admin_password", "first-password")

    seed_first_user(session)

    from app.auth import find_user

    created = find_user(session, "founder")
    assert created is not None
    assert created.email == "founder@example.com"
    assert verify_password("first-password", created.password_hash)


def test_seeding_leaves_an_existing_account_alone(session, user, monkeypatch):
    monkeypatch.setattr(settings, "admin_username", "someone-else")
    monkeypatch.setattr(settings, "admin_email", "else@example.com")
    monkeypatch.setattr(settings, "admin_password", "another-password")

    seed_first_user(session)

    from app.auth import find_user

    assert find_user(session, "someone-else") is None
    assert verify_password(TEST_USER["password"], session.get(User, user.id).password_hash)
