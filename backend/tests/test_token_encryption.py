from sqlalchemy import text
from sqlmodel import select

from app.crypto import PREFIX, decrypt, encrypt
from app.db import _encrypt_stored_tokens
from app.models import Dashboard


def _raw_token(session, dashboard_uuid: str) -> str:
    """The value as SQLite actually holds it, bypassing the column type."""
    return session.execute(
        text("SELECT token FROM dashboard WHERE uuid = :uuid"), {"uuid": dashboard_uuid}
    ).scalar_one()


def _row(session, dashboard_uuid: str) -> Dashboard:
    return session.exec(select(Dashboard).where(Dashboard.uuid == dashboard_uuid)).one()


def test_token_is_not_stored_in_plaintext(session, client, make_dashboard):
    board = make_dashboard(token="ghp_supersecretvalue")

    stored = _raw_token(session, board["id"])
    assert "ghp_supersecretvalue" not in stored
    assert stored.startswith(PREFIX)


def test_token_round_trips_through_the_column(session, client, make_dashboard):
    board = make_dashboard(token="ghp_supersecretvalue")

    assert _row(session, board["id"]).token == "ghp_supersecretvalue"


def test_plaintext_rows_written_before_encryption_still_read(session, make_dashboard):
    board = make_dashboard(token="ghp_placeholder")
    session.execute(
        text("UPDATE dashboard SET token = :t WHERE uuid = :uuid"),
        {"t": "ghp_legacyplaintext", "uuid": board["id"]},
    )
    session.commit()
    session.expire_all()

    assert _row(session, board["id"]).token == "ghp_legacyplaintext"


def test_backfill_encrypts_legacy_plaintext(session, make_dashboard):
    board = make_dashboard(token="ghp_placeholder")
    session.execute(
        text("UPDATE dashboard SET token = :t WHERE uuid = :uuid"),
        {"t": "ghp_legacyplaintext", "uuid": board["id"]},
    )
    session.commit()

    _encrypt_stored_tokens(session.connection())
    session.commit()
    session.expire_all()

    assert _raw_token(session, board["id"]).startswith(PREFIX)
    assert _row(session, board["id"]).token == "ghp_legacyplaintext"


def test_value_encrypted_with_another_key_reads_as_absent(monkeypatch):
    from cryptography.fernet import Fernet

    from app import crypto

    ciphertext = encrypt("ghp_written_under_the_old_key")
    monkeypatch.setattr(crypto.settings, "secret_key", Fernet.generate_key().decode())

    assert decrypt(ciphertext) is None
