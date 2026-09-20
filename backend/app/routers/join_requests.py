from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..auth import require_user
from ..db import get_session
from ..membership_flows import decide, request_to_join
from ..models import JoinRequest, Organization, User
from ..orgs import ROLES, get_member_organization, membership
from ..schemas import JoinRequestDecision, JoinRequestOut, OrganizationLookupOut

router = APIRouter(prefix="/api/organizations", tags=["join-requests"])


def _by_slug(session: Session, slug: str) -> Organization:
    """An organisation's link is meant to be shared, so knowing its slug is
    enough to see its name and ask to join."""
    organization = session.exec(select(Organization).where(Organization.slug == slug.lower())).first()
    if organization is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No organization has that link.")
    return organization


def _out(session: Session, request: JoinRequest) -> JoinRequestOut:
    requester = session.get(User, request.user_id)
    return JoinRequestOut(
        id=request.uuid,
        username=requester.username if requester else "(deleted account)",
        status=request.status,
        via=request.via,
        created_at=request.created_at,
    )


@router.get("/by-slug/{slug}", response_model=OrganizationLookupOut)
def lookup(slug: str, session: Session = Depends(get_session), user: User = Depends(require_user)):
    organization = _by_slug(session, slug)
    latest = session.exec(
        select(JoinRequest)
        .where(JoinRequest.organization_id == organization.id, JoinRequest.user_id == user.id)
        .order_by(JoinRequest.created_at.desc())
    ).first()
    return OrganizationLookupOut(
        id=organization.uuid,
        slug=organization.slug,
        name=organization.name,
        is_member=membership(session, organization.id, user.id) is not None,
        request_status=latest.status if latest else None,
    )


@router.post("/by-slug/{slug}/join-requests", response_model=JoinRequestOut, status_code=status.HTTP_201_CREATED)
def ask(slug: str, session: Session = Depends(get_session), user: User = Depends(require_user)):
    return _out(session, request_to_join(session, _by_slug(session, slug), user))


@router.get("/{organization_id}/join-requests", response_model=list[JoinRequestOut])
def pending(organization_id: str, session: Session = Depends(get_session), user: User = Depends(require_user)):
    organization, _ = get_member_organization(session, organization_id, user, admin=True)
    rows = session.exec(
        select(JoinRequest)
        .where(JoinRequest.organization_id == organization.id, JoinRequest.status == "pending")
        .order_by(JoinRequest.created_at)
    ).all()
    return [_out(session, r) for r in rows]


@router.post("/{organization_id}/join-requests/{request_id}/approve", response_model=JoinRequestOut)
def approve(
    organization_id: str,
    request_id: str,
    payload: JoinRequestDecision,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    organization, _ = get_member_organization(session, organization_id, user, admin=True)
    if payload.role not in ROLES:
        raise HTTPException(422, "Role must be 'admin' or 'member'.")
    return _out(session, decide(session, organization, request_id, user, approve=True, role=payload.role))


@router.post("/{organization_id}/join-requests/{request_id}/decline", response_model=JoinRequestOut)
def decline(
    organization_id: str, request_id: str, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    organization, _ = get_member_organization(session, organization_id, user, admin=True)
    return _out(session, decide(session, organization, request_id, user, approve=False))
