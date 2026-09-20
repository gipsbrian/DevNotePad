"""Password hashing, the session-backed current user, ownership checks,
and first-run seeding."""

import hashlib
import logging
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session, select

from .config import settings
from .db import get_session
from .models import AppSettings, Dashboard, User
from .orgs import ensure_in_main

log = logging.getLogger("uvicorn.error")

SESSION_KEY = "user_id"


def session_secret() -> str:
    """Derived from SECRET_KEY rather than reused verbatim, so the cookie
    signing key and the token encryption key are never the same bytes."""
    return hashlib.sha256(f"session:{settings.secret_key}".encode()).hexdigest()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        # A malformed hash must read as "wrong password", never as an error
        # that distinguishes this account from any other.
        return False


def find_user(session: Session, identifier: str) -> Optional[User]:
    """Either the username or the email signs you in."""
    ident = identifier.strip().lower()
    return session.exec(
        select(User).where((User.username == ident) | (User.email == ident))
    ).first()


def require_user(request: Request, session: Session = Depends(get_session)) -> User:
    user_id = request.session.get(SESSION_KEY)
    user = session.get(User, user_id) if user_id else None
    if user is None:
        # Covers a signed cookie naming an account that has since gone.
        request.session.clear()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


def claim_unowned_rows(session: Session) -> None:
    """Boards and settings from before accounts owned anything have no
    owner. They were the instance owner's, so they go to the first account.
    A no-op once everything has one."""
    first = session.exec(select(User).order_by(User.id)).first()
    if first is None:
        return
    for board in session.exec(select(Dashboard).where(Dashboard.owner_id == None)):  # noqa: E711
        board.owner_id = first.id
        session.add(board)
    # There was only ever one settings row, so at most one lacks an owner.
    legacy = session.exec(select(AppSettings).where(AppSettings.user_id == None)).first()  # noqa: E711
    has_own = session.exec(select(AppSettings).where(AppSettings.user_id == first.id)).first()
    if legacy is not None and has_own is None:
        legacy.user_id = first.id
        session.add(legacy)
    session.commit()


def seed_first_user(session: Session) -> None:
    """Creates the initial account from the environment. Only ever runs
    into an empty user table, so it can't overwrite a changed password."""
    if session.exec(select(User)).first() is not None:
        return

    username = (settings.admin_username or "").strip().lower()
    email = (settings.admin_email or "").strip().lower()
    password = settings.admin_password or ""
    if not (username and email and password):
        log.warning(
            "No account exists and ADMIN_USERNAME / ADMIN_EMAIL / ADMIN_PASSWORD "
            "are not all set, so nobody can sign in. Set them in .env and restart."
        )
        return

    user = User(username=username, email=email, password_hash=hash_password(password))
    session.add(user)
    session.commit()
    session.refresh(user)
    # The first account runs the instance.
    ensure_in_main(session, user, role="admin")
    log.info("Created the initial account %r.", username)
