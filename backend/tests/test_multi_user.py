"""One account must never reach another's boards, notes or settings --
including its GitHub token."""

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import text
from sqlmodel import select

from app.auth import claim_unowned_rows, hash_password
from app.config import settings
from app.db import _apply_additive_migrations
from app.insights import _cache, clear_cache
from app.main import app
from app.models import AppSettings, Dashboard, StickyNote, User
from app.access import read_token

MATE = {"username": "mate", "email": "mate@example.com", "password": "mates-password"}


@pytest.fixture()
def mate_client(client, session):
    """A second account, signed in on its own cookie jar. Depends on
    `client` so the first account exists -- and is the instance owner."""
    session.add(
        User(username=MATE["username"], email=MATE["email"], password_hash=hash_password(MATE["password"]))
    )
    session.commit()
    other = TestClient(app)
    resp = other.post(
        "/api/auth/login", json={"identifier": MATE["username"], "password": MATE["password"]}
    )
    assert resp.status_code == 200, resp.text
    return other


def test_each_account_lists_only_its_own_boards(client, mate_client, make_dashboard):
    mine = make_dashboard(name="mine")
    theirs = mate_client.post(
        "/api/dashboards", json={"name": "theirs", "repo_owner": "acme", "repo_name": "gadgets"}
    ).json()

    assert [b["id"] for b in client.get("/api/dashboards").json()] == [mine["id"]]
    assert [b["id"] for b in mate_client.get("/api/dashboards").json()] == [theirs["id"]]


@pytest.mark.parametrize(
    "method,suffix,body",
    [
        ("get", "", None),
        ("patch", "", {"name": "hijacked"}),
        ("patch", "/appearance", {"accent_color": "#000000"}),
        ("delete", "", None),
        ("get", "/columns", None),
        ("post", "/columns", {"name": "x"}),
        ("put", "/columns/reorder", {"column_ids": []}),
        ("get", "/notes", None),
        ("post", "/notes", {"issue_number": 1, "body": "x"}),
        ("get", "/sticky-notes", None),
        ("post", "/sticky-notes", {"body": "x"}),
        ("get", "/closed", None),
        ("get", "/issues/1", None),
        ("get", "/issues/1/comments", None),
        ("post", "/issues/1/close", None),
        ("post", "/issues/1/comments", {"body": "x"}),
        ("get", "/github-metadata", None),
    ],
)
def test_another_accounts_board_reads_as_missing(
    client, mate_client, make_dashboard, method, suffix, body
):
    board = make_dashboard(name="private")
    url = f"/api/dashboards/{board['id']}{suffix}"
    kwargs = {"json": body} if body is not None else {}

    # GitHub answering 404 for a fake repo would pass this test on its own,
    # so it answers 200 here: only the ownership check can produce a 404.
    with respx.mock(assert_all_called=False) as github:
        route = github.route(host="api.github.com").mock(return_value=Response(200, json=[]))
        resp = getattr(mate_client, method)(url, **kwargs)
    # 404, not 403: a uuid mustn't be probe-able for whether it exists.
    assert resp.status_code == 404, resp.text
    assert not route.called

    after = client.get("/api/dashboards").json()
    assert [(b["id"], b["name"], b["accent_color"]) for b in after] == [
        (board["id"], "private", None)
    ]


def test_another_accounts_columns_and_sticky_notes_are_out_of_reach(
    client, mate_client, make_dashboard
):
    board = make_dashboard()
    column = client.post(f"/api/dashboards/{board['id']}/columns", json={"name": "Triage"}).json()
    sticky = client.post(f"/api/dashboards/{board['id']}/sticky-notes", json={"body": "secret"}).json()

    base = f"/api/dashboards/{board['id']}"
    assert mate_client.put(f"{base}/columns/{column['id']}", json={"name": "x"}).status_code == 404
    assert mate_client.delete(f"{base}/columns/{column['id']}").status_code == 404
    assert mate_client.get(f"{base}/columns/{column['id']}/issues").status_code == 404
    assert mate_client.put(f"{base}/sticky-notes/{sticky['id']}", json={"body": "x"}).status_code == 404
    assert mate_client.delete(f"{base}/sticky-notes/{sticky['id']}").status_code == 404

    assert client.get(f"{base}/sticky-notes").json()[0]["body"] == "secret"
    assert client.get(f"{base}/columns").json()[0]["name"] == "Triage"


def test_notes_addressed_by_bare_id_are_checked_against_their_board(
    client, mate_client, make_dashboard
):
    board = make_dashboard()
    note = client.post(
        f"/api/dashboards/{board['id']}/notes", json={"issue_number": 3, "body": "mine"}
    ).json()

    assert mate_client.put(f"/api/notes/{note['id']}", json={"body": "x"}).status_code == 404
    assert mate_client.post(f"/api/notes/{note['id']}/push").status_code == 404
    assert mate_client.delete(f"/api/notes/{note['id']}").status_code == 404

    remaining = client.get(f"/api/dashboards/{board['id']}/notes").json()
    assert [(n["id"], n["body"]) for n in remaining] == [(note["id"], "mine")]


def test_settings_and_the_saved_token_are_per_account(client, mate_client):
    client.put(
        "/api/settings",
        json={"github_username": "owner-gh", "default_token": "ghp_owner", "default_org_url": "https://github.com/acme"},
    )

    theirs = mate_client.get("/api/settings").json()
    assert theirs["github_username"] is None
    assert theirs["default_org_url"] is None
    assert theirs["has_default_token"] is False

    mate_client.put("/api/settings", json={"github_username": "mate-gh"})
    assert client.get("/api/settings").json()["github_username"] == "owner-gh"
    assert client.get("/api/settings").json()["has_default_token"] is True


def test_a_teammates_board_never_borrows_the_owners_general_token(
    client, mate_client, session, make_dashboard
):
    client.put("/api/settings", json={"default_token": "ghp_owner"})
    board = mate_client.post(
        "/api/dashboards", json={"name": "b", "repo_owner": "acme", "repo_name": "gadgets"}
    ).json()

    row = session.exec(select(Dashboard).where(Dashboard.uuid == board["id"])).one()
    assert read_token(session, row) is None


def test_the_env_token_is_lent_only_to_the_instance_owner(
    client, mate_client, session, make_dashboard, monkeypatch
):
    monkeypatch.setattr(settings, "git_token", "ghp_from_env")
    monkeypatch.setattr(settings, "git_org_url", "https://github.com/acme")

    owner = client.get("/api/settings").json()
    assert owner["default_token_source"] == "env"
    assert owner["default_org_url"] == "https://github.com/acme"

    mate = mate_client.get("/api/settings").json()
    assert mate["default_token_source"] == "none"
    assert mate["has_default_token"] is False
    assert mate["default_org_url"] is None

    mine = make_dashboard()
    theirs = mate_client.post(
        "/api/dashboards", json={"name": "b", "repo_owner": "acme", "repo_name": "gadgets"}
    ).json()
    by_uuid = {d.uuid: d for d in session.exec(select(Dashboard)).all()}
    assert read_token(session, by_uuid[mine["id"]]) == "ghp_from_env"
    assert read_token(session, by_uuid[theirs["id"]]) is None


def test_deleting_a_board_takes_its_sticky_notes_with_it(client, session, make_dashboard):
    """SQLite can reuse the newest deleted id, so a leftover note would turn
    up on whichever board -- whoever's -- is created next."""
    board = make_dashboard()
    client.post(f"/api/dashboards/{board['id']}/sticky-notes", json={"body": "gone"})
    assert client.delete(f"/api/dashboards/{board['id']}").status_code == 204
    assert session.exec(select(StickyNote)).all() == []


def test_clearing_one_accounts_analytics_leaves_anothers(user):
    _cache[(1, "acme", "me", "a")] = (0.0, object())
    _cache[(2, "acme", "me", "a")] = (0.0, object())
    clear_cache(1)
    assert list(_cache) == [(2, "acme", "me", "a")]


# ---- rows from before accounts owned anything ----

def test_legacy_boards_and_settings_go_to_the_first_account(session, user):
    session.add(User(username="later", email="later@example.com", password_hash="x"))
    session.execute(
        text(
            "INSERT INTO dashboard (uuid, name, repo_owner, repo_name, created_at) "
            "VALUES ('u-1', 'old', 'acme', 'widgets', CURRENT_TIMESTAMP)"
        )
    )
    session.execute(text("INSERT INTO appsettings (github_username, show_my_columns) VALUES ('old-gh', 1)"))
    session.commit()

    claim_unowned_rows(session)
    claim_unowned_rows(session)  # idempotent

    assert session.exec(select(Dashboard)).one().owner_id == user.id
    assert session.exec(select(AppSettings)).one().user_id == user.id


def test_claiming_does_nothing_without_an_account(session):
    session.execute(
        text(
            "INSERT INTO dashboard (uuid, name, repo_owner, repo_name, created_at) "
            "VALUES ('u-1', 'old', 'acme', 'widgets', CURRENT_TIMESTAMP)"
        )
    )
    session.commit()
    claim_unowned_rows(session)
    assert session.exec(select(Dashboard)).one().owner_id is None


def test_the_additive_migration_adds_ownership_to_a_pre_accounts_database(session):
    """The shape a database had before this change: no owner, no user_id."""
    connection = session.connection()
    connection.execute(text('DROP TABLE "dashboard"'))
    connection.execute(text('DROP TABLE "appsettings"'))
    connection.execute(
        text(
            'CREATE TABLE "dashboard" (id INTEGER PRIMARY KEY, uuid VARCHAR, name VARCHAR, '
            "repo_owner VARCHAR, repo_name VARCHAR, token VARCHAR, created_at DATETIME, "
            "accent_color VARCHAR, background_url VARCHAR)"
        )
    )
    connection.execute(
        text(
            'CREATE TABLE "appsettings" (id INTEGER PRIMARY KEY, github_username VARCHAR, '
            "default_token VARCHAR, default_org_url VARCHAR, show_my_columns BOOLEAN)"
        )
    )

    _apply_additive_migrations(connection)

    def columns(table):
        return {r[1] for r in connection.execute(text(f"PRAGMA table_info('{table}')"))}

    def indexes(table):
        return {r[1]: r[2] for r in connection.execute(text(f"PRAGMA index_list('{table}')"))}

    assert "owner_id" in columns("dashboard")
    assert "user_id" in columns("appsettings")
    assert "ix_dashboard_owner_id" in indexes("dashboard")
    assert indexes("appsettings").get("ix_appsettings_user_id") == 1  # unique
