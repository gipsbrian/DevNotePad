import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..auth import SESSION_KEY, find_user, hash_password, require_user, verify_password
from ..config import settings
from ..db import get_session
from ..models import User
from ..membership_flows import accept_invitation, usable_invitation
from ..orgs import ensure_in_main, forget_active, get_main, membership
from ..schemas import LoginRequest, RegisterRequest, RegistrationStatusOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


# The guided tours the frontend defines. Anything else is a typo, not a tour.
KNOWN_TOURS = ("home", "board")


def _tours(user: User) -> list[str]:
    return [t for t in (user.tours_seen or "").split(",") if t]


def _user_out(user: User, session: Optional[Session] = None) -> UserOut:
    is_admin = False
    if session is not None:
        row = membership(session, get_main(session).id, user.id)
        is_admin = bool(row and row.role == "admin")
    return UserOut(
        id=user.id, username=user.username, email=user.email, tours_seen=_tours(user), is_instance_admin=is_admin
    )


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, request: Request, response: Response, session: Session = Depends(get_session)):
    user = find_user(session, payload.identifier)
    # One message for both halves, so this can't be used to learn which
    # usernames exist.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")

    request.session.clear()
    request.session[SESSION_KEY] = user.id
    # Land wherever this account's default or last organisation says.
    forget_active(response)
    return _user_out(user, session)


# No "@" allowed, so a username can never read as someone's email when
# signing in with either.
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8
# bcrypt only reads the first 72 bytes; anything past that would be
# silently ignored, which is worse than refusing it.
MAX_PASSWORD_BYTES = 72


@router.get("/registration", response_model=RegistrationStatusOut)
def registration_status():
    """Whether the sign-in page should offer to create an account."""
    return RegistrationStatusOut(open=settings.allow_registration)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, response: Response, session: Session = Depends(get_session)):
    if payload.invitation_token:
        # Checked before anything is created, so a dead link doesn't leave
        # an account behind -- and it's what lets an invited person register
        # while registration is closed.
        usable_invitation(session, payload.invitation_token)
    elif not settings.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This instance isn't taking new accounts.")

    username = payload.username.strip().lower()
    email = payload.email.strip().lower()
    if not USERNAME_RE.match(username):
        raise HTTPException(
            422,
            "Usernames are 3-32 characters: letters, numbers, dots, dashes and "
            "underscores, starting with a letter or number.",
        )
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise HTTPException(422, "That doesn't look like an email address.")
    if len(payload.password) < MIN_PASSWORD:
        raise HTTPException(422, f"Passwords need at least {MIN_PASSWORD} characters.")
    if len(payload.password.encode()) > MAX_PASSWORD_BYTES:
        raise HTTPException(422, f"Passwords can be at most {MAX_PASSWORD_BYTES} bytes long.")

    if session.exec(select(User).where(User.username == username)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is taken.")
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.")

    user = User(username=username, email=email, password_hash=hash_password(payload.password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        # Two sign-ups racing for the same name get past the checks above;
        # the unique index settles it.
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "That username or email is already in use.")
    session.refresh(user)
    ensure_in_main(session, user)

    request.session.clear()
    request.session[SESSION_KEY] = user.id
    if payload.invitation_token:
        # Joins, and moves this browser into, the organisation.
        accept_invitation(session, response, user, payload.invitation_token)
    else:
        forget_active(response)
    return _user_out(user, session)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> Response:
    request.session.clear()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    forget_active(response)
    return response


@router.post("/tours/{name}/seen", response_model=UserOut)
def mark_tour_seen(name: str, user: User = Depends(require_user), session: Session = Depends(get_session)):
    """Finishing a tour and dismissing it both count: either way, don't
    start it on its own again. It can still be replayed on request."""
    if name not in KNOWN_TOURS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such tour")
    seen = _tours(user)
    if name not in seen:
        user.tours_seen = ",".join([*seen, name])
        session.add(user)
        session.commit()
        session.refresh(user)
    return _user_out(user, session)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(require_user), session: Session = Depends(get_session)):
    return _user_out(user, session)
