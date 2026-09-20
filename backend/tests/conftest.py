import os

# Keep the test DB fully in-memory and never let a test pick up the
# developer's real .env (which may hold a live GitHub token) — set this
# before `app.config` is imported anywhere.
os.environ["DATABASE_PATH"] = ":memory:"
os.environ["GIT_TOKEN"] = ""
os.environ["GIT_ORG_URL"] = ""

from cryptography.fernet import Fernet  # noqa: E402

# Token encryption is mandatory, so the suite needs a key of its own —
# never the developer's real one.
os.environ["SECRET_KEY"] = Fernet.generate_key().decode()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402

# Belt-and-suspenders: even if a .env file were picked up, force no
# default token for the whole test session.
settings.git_token = None
settings.git_org_url = None
# Closed unless a test opens it, whatever a developer's .env says.
settings.allow_registration = False

GITHUB_API = "https://api.github.com"


@pytest.fixture(autouse=True)
def _isolate_insights_cache():
    """The analytics cache is process-global, so it would otherwise carry
    results between tests."""
    from app.insights import clear_cache

    clear_cache()
    yield
    clear_cache()


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


TEST_USER = {
    "username": "tester",
    "email": "tester@example.com",
    "password": "correct-horse-battery",
}


@pytest.fixture()
def user(session):
    from app.auth import hash_password  # noqa: PLC0415
    from app.models import User  # noqa: PLC0415

    row = User(
        username=TEST_USER["username"],
        email=TEST_USER["email"],
        password_hash=hash_password(TEST_USER["password"]),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@pytest.fixture()
def anon_client(session):
    """A client with no session — for the endpoints that should reject it."""

    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def client(anon_client, user):
    """Signed in for real rather than by overriding the guard, so every
    test goes through the same path a browser does."""
    resp = anon_client.post(
        "/api/auth/login",
        json={"identifier": TEST_USER["username"], "password": TEST_USER["password"]},
    )
    assert resp.status_code == 200, resp.text
    return anon_client


@pytest.fixture()
def make_dashboard(client):
    def _make(**overrides):
        payload = {
            "name": "Test dashboard",
            "repo_owner": "acme",
            "repo_name": "widgets",
        }
        payload.update(overrides)
        resp = client.post("/api/dashboards", json=payload)
        assert resp.status_code == 200, resp.text
        return resp.json()

    return _make


OTHER_PASSWORD = "a-good-password"


@pytest.fixture()
def make_user(session, anon_client):
    """Accounts beyond `user`, each with a signed-in client of its own."""
    from app.auth import hash_password  # noqa: PLC0415
    from app.models import User  # noqa: PLC0415

    def _make(username):
        row = User(username=username, email=f"{username}@example.com", password_hash=hash_password(OTHER_PASSWORD))
        session.add(row)
        session.commit()
        session.refresh(row)
        c = TestClient(app)
        resp = c.post("/api/auth/login", json={"identifier": username, "password": OTHER_PASSWORD})
        assert resp.status_code == 200, resp.text
        return row, c

    return _make
