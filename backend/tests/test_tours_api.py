from sqlalchemy import text

from app.db import _apply_additive_migrations


def test_a_new_account_has_seen_no_tours(client):
    assert client.get("/api/auth/me").json()["tours_seen"] == []


def test_marking_a_tour_seen_sticks_and_is_idempotent(client):
    assert client.post("/api/auth/tours/home/seen").json()["tours_seen"] == ["home"]
    assert client.post("/api/auth/tours/home/seen").json()["tours_seen"] == ["home"]
    assert client.post("/api/auth/tours/board/seen").json()["tours_seen"] == ["home", "board"]
    assert client.get("/api/auth/me").json()["tours_seen"] == ["home", "board"]


def test_an_unknown_tour_is_refused(client):
    assert client.post("/api/auth/tours/nope/seen").status_code == 404
    assert client.get("/api/auth/me").json()["tours_seen"] == []


def test_marking_a_tour_needs_a_session(anon_client):
    assert anon_client.post("/api/auth/tours/home/seen").status_code == 401


def test_accounts_that_predate_tours_start_with_them_all_seen(session):
    """Existing users already know the app, so the column that tracks tours
    arrives pre-filled for them rather than ambushing them on next visit."""
    connection = session.connection()
    connection.execute(text('DROP TABLE "user"'))
    connection.execute(
        text(
            'CREATE TABLE "user" (id INTEGER PRIMARY KEY, username VARCHAR, email VARCHAR, '
            "password_hash VARCHAR, created_at DATETIME)"
        )
    )
    connection.execute(
        text("INSERT INTO \"user\" (username, email, password_hash) VALUES ('old', 'old@example.com', 'x')")
    )

    _apply_additive_migrations(connection)

    assert connection.execute(text('SELECT tours_seen FROM "user"')).scalar_one() == "home,board"
