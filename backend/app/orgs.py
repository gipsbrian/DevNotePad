"""Organisations: the main one, memberships, and which one a person is in.

Invariants this module keeps:
- exactly one main organisation exists, and every account is an active
  member of it;
- the main organisation always has an admin (its admins run the instance);
- the organisation someone is working in is remembered per browser, and is
  only ever one they're an active member of.
"""

import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request, Response, status
from sqlmodel import Session, select

from .config import settings
from .models import Dashboard, LocalNote, Membership, Organization, StickyNote, User

# The organisation a browser is working in. A cookie of its own rather than a
# key in the session: Starlette rewrites the whole session cookie on every
# response from the copy it read when the request started, so a switch made
# by one request was undone by any other already in flight -- and a board
# page sends several at once. This cookie is only ever written by a switch.
# It holds nothing secret: membership is checked on every read.
ORG_COOKIE = "devnotepad_org"
ORG_COOKIE_MAX_AGE = 60 * 60 * 24 * 14
MAIN_SLUG = "main"
ROLES = ("admin", "member")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")
# Paths an organisation's sign-in link must never shadow.
# Nor collide with the fixed words in /api/organizations/... paths, where a
# slug named "members" would be routed as a sub-resource.
RESERVED_SLUGS = {
    "main", "api", "admin", "login", "new", "o", "org", "orgs", "settings", "sso",
    "by-slug", "default", "invitations", "join-requests", "members", "switch",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_main(session: Session) -> Organization:
    main = session.exec(select(Organization).where(Organization.is_main == True)).first()  # noqa: E712
    if main is None:
        main = Organization(slug=MAIN_SLUG, name="Main", is_main=True)
        session.add(main)
        session.commit()
        session.refresh(main)
    return main


def membership(session: Session, organization_id: int, user_id: int, *, include_removed: bool = False) -> Optional[Membership]:
    row = session.exec(
        select(Membership).where(Membership.organization_id == organization_id, Membership.user_id == user_id)
    ).first()
    if row is not None and row.removed_at is not None and not include_removed:
        return None
    return row


def add_member(session: Session, organization: Organization, user: User, role: str = "member") -> Membership:
    """Adds, or restores a removed membership -- which also brings back the
    boards that person left there."""
    row = membership(session, organization.id, user.id, include_removed=True)
    if row is None:
        row = Membership(organization_id=organization.id, user_id=user.id, role=role)
    else:
        row.removed_at = None
        row.role = role
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def ensure_in_main(session: Session, user: User, role: str = "member") -> None:
    main = get_main(session)
    if membership(session, main.id, user.id, include_removed=True) is None:
        add_member(session, main, user, role)


def migrate_to_organizations(session: Session) -> None:
    """Brings data from before organisations into the main one. Safe to run
    on every startup: it only fills in what's missing."""
    main = get_main(session)
    users = session.exec(select(User).order_by(User.id)).all()
    for user in users:
        ensure_in_main(session, user)
    for board in session.exec(select(Dashboard).where(Dashboard.organization_id == None)):  # noqa: E711
        board.organization_id = main.id
        session.add(board)
    # Notes from before they were per person were written by the board's owner.
    for model in (LocalNote, StickyNote):
        for note in session.exec(select(model).where(model.user_id == None)):  # noqa: E711
            board = session.get(Dashboard, note.dashboard_id)
            if board is not None and board.owner_id is not None:
                note.user_id = board.owner_id
                session.add(note)
    session.commit()
    ensure_main_has_admin(session)


def ensure_main_has_admin(session: Session) -> None:
    """The instance has to be run by somebody: when main has no admin, its
    longest-standing member becomes one."""
    main = get_main(session)
    members = session.exec(
        select(Membership)
        .where(Membership.organization_id == main.id, Membership.removed_at == None)  # noqa: E711
        .order_by(Membership.user_id)
    ).all()
    if members and not any(m.role == "admin" for m in members):
        members[0].role = "admin"
        session.add(members[0])
        session.commit()


def active_organizations(session: Session, user: User) -> list[tuple[Organization, Membership]]:
    rows = session.exec(
        select(Organization, Membership)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == user.id, Membership.removed_at == None)  # noqa: E711
        .order_by(Organization.is_main.desc(), Organization.name)
    ).all()
    return list(rows)


def current_organization(request: Request, session: Session, user: User) -> Organization:
    """The organisation this request works in. Falls back -- default, then
    last used, then main -- whenever this browser names none, or names one
    the person has since left."""
    ensure_in_main(session, user)
    chosen = None
    cookie_uuid = request.cookies.get(ORG_COOKIE)
    if cookie_uuid:
        chosen = session.exec(select(Organization).where(Organization.uuid == cookie_uuid)).first()
    candidates = [chosen.id if chosen else None, user.default_organization_id, user.last_organization_id]
    for candidate in candidates:
        if candidate and membership(session, candidate, user.id):
            organization = session.get(Organization, candidate)
            if organization is not None:
                return _record_last(session, user, organization)
    return _record_last(session, user, get_main(session))


def switch_to(response: Response, session: Session, user: User, organization: Organization) -> Organization:
    if membership(session, organization.id, user.id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    response.set_cookie(
        ORG_COOKIE,
        organization.uuid,
        max_age=ORG_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.session_https_only,
    )
    return _record_last(session, user, organization)


def forget_active(response: Response) -> None:
    """At sign-in and sign-out, so the next session starts from the default
    or last-used organisation rather than a previous visitor's choice."""
    response.delete_cookie(ORG_COOKIE)


def _record_last(session: Session, user: User, organization: Organization) -> Organization:
    if user.last_organization_id != organization.id:
        user.last_organization_id = organization.id
        session.add(user)
        session.commit()
    return organization


def get_member_organization(session: Session, organization_uuid: str, user: User, *, admin: bool = False) -> tuple[Organization, Membership]:
    """An organisation the caller is in -- as an admin, when asked. Anything
    else reads as not found, so organisations can't be probed for."""
    organization = session.exec(select(Organization).where(Organization.uuid == organization_uuid)).first()
    row = membership(session, organization.id, user.id) if organization else None
    if organization is None or row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    if admin and row.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only this organization's admins can do that.")
    return organization, row


def active_admin_count(session: Session, organization_id: int) -> int:
    return len(
        session.exec(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.role == "admin",
                Membership.removed_at == None,  # noqa: E711
            )
        ).all()
    )


def remove_member(session: Session, row: Membership) -> None:
    row.removed_at = _now()
    session.add(row)
    session.commit()


def available_slug(session: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:36] or "org"
    if len(base) < 3:
        base = f"{base}-org"
    candidate, n = base, 1
    while candidate in RESERVED_SLUGS or not SLUG_RE.match(candidate) or session.exec(
        select(Organization).where(Organization.slug == candidate)
    ).first():
        n += 1
        candidate = f"{base}-{n}"
    return candidate
