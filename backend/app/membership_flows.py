"""Getting into an organisation: invitations, join requests, and the
notifications they send."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from fastapi import HTTPException, Response, status
from sqlmodel import Session, select

from .models import Invitation, JoinRequest, Membership, Notification, Organization, User
from .orgs import add_member, membership, switch_to

INVITATION_TTL = timedelta(days=7)
# After a decline, how long before the same person may ask again -- so a
# declined request can't be turned into a stream of notifications.
REQUEST_COOLDOWN = timedelta(days=7)


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(moment: Optional[datetime]) -> Optional[datetime]:
    # SQLite hands datetimes back without their zone.
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---- Notifications ----

def notify(session: Session, user_ids: Iterable[int], kind: str, organization: Organization, actor: Optional[User]) -> None:
    for user_id in set(user_ids):
        if actor is not None and user_id == actor.id:
            continue
        session.add(
            Notification(user_id=user_id, kind=kind, organization_id=organization.id, actor_id=actor.id if actor else None)
        )
    session.commit()


def admin_ids(session: Session, organization: Organization) -> list[int]:
    return list(
        session.exec(
            select(Membership.user_id).where(
                Membership.organization_id == organization.id,
                Membership.role == "admin",
                Membership.removed_at == None,  # noqa: E711
            )
        ).all()
    )


# ---- Invitations ----

def create_invitation(session: Session, organization: Organization, inviter: User, role: str, label: Optional[str]) -> tuple[Invitation, str]:
    """Returns the invitation and its token. The token exists only in this
    return value: it's shown to the admin once and never stored."""
    token = secrets.token_urlsafe(32)
    invitation = Invitation(
        organization_id=organization.id,
        role=role,
        label=label,
        token_hash=token_hash(token),
        invited_by=inviter.id,
        expires_at=now() + INVITATION_TTL,
    )
    session.add(invitation)
    session.commit()
    session.refresh(invitation)
    return invitation, token


def invitation_status(invitation: Invitation) -> str:
    if invitation.revoked_at is not None:
        return "revoked"
    if invitation.accepted_at is not None:
        return "accepted"
    if aware(invitation.expires_at) < now():
        return "expired"
    return "pending"


def find_invitation(session: Session, token: str) -> tuple[Invitation, Organization]:
    invitation = session.exec(select(Invitation).where(Invitation.token_hash == token_hash(token))).first() if token else None
    organization = session.get(Organization, invitation.organization_id) if invitation else None
    if invitation is None or organization is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This invitation link isn't valid.")
    return invitation, organization


_UNUSABLE = {
    "revoked": "This invitation was withdrawn. Ask an admin for a new link.",
    "accepted": "This invitation has already been used. Ask an admin for a new link.",
    "expired": "This invitation has expired. Ask an admin for a new link.",
}


def usable_invitation(session: Session, token: str) -> tuple[Invitation, Organization]:
    invitation, organization = find_invitation(session, token)
    state = invitation_status(invitation)
    if state != "pending":
        raise HTTPException(status.HTTP_410_GONE, _UNUSABLE[state])
    return invitation, organization


def accept_invitation(session: Session, response: Response, user: User, token: str) -> tuple[Organization, bool]:
    """Joins the organisation and moves this browser into it. Someone who's
    already a member doesn't use the invitation up, so a link opened by the
    wrong person still works for the right one. Returns (organisation,
    already_member)."""
    invitation, organization = usable_invitation(session, token)
    already = membership(session, organization.id, user.id) is not None
    if not already:
        add_member(session, organization, user, invitation.role)
        invitation.accepted_by = user.id
        invitation.accepted_at = now()
        session.add(invitation)
        session.commit()
        if invitation.invited_by:
            notify(session, [invitation.invited_by], "invitation_accepted", organization, user)
    switch_to(response, session, user, organization)
    return organization, already


# ---- Join requests ----

def request_to_join(session: Session, organization: Organization, user: User, via: str = "link") -> JoinRequest:
    if organization.is_main or membership(session, organization.id, user.id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "You're already a member of this organization.")

    latest = session.exec(
        select(JoinRequest)
        .where(JoinRequest.organization_id == organization.id, JoinRequest.user_id == user.id)
        .order_by(JoinRequest.created_at.desc())
    ).first()
    if latest is not None and latest.status == "pending":
        return latest
    if latest is not None and latest.status == "declined" and now() - aware(latest.decided_at) < REQUEST_COOLDOWN:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Your last request to join was declined recently. You can ask again in a few days.",
        )

    request = JoinRequest(organization_id=organization.id, user_id=user.id, via=via)
    session.add(request)
    session.commit()
    session.refresh(request)
    notify(session, admin_ids(session, organization), "join_request", organization, user)
    return request


def decide(session: Session, organization: Organization, request_uuid: str, admin: User, approve: bool, role: str = "member") -> JoinRequest:
    request = session.exec(
        select(JoinRequest).where(JoinRequest.uuid == request_uuid, JoinRequest.organization_id == organization.id)
    ).first()
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Join request not found")
    if request.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"This request was already {request.status}.")
    requester = session.get(User, request.user_id)
    if requester is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Join request not found")

    if approve and membership(session, organization.id, requester.id) is None:
        add_member(session, organization, requester, role)
    request.status = "approved" if approve else "declined"
    request.decided_by = admin.id
    request.decided_at = now()
    session.add(request)
    session.commit()
    session.refresh(request)
    notify(session, [requester.id], "join_approved" if approve else "join_declined", organization, admin)
    return request
