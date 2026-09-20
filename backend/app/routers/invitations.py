from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, select

from ..auth import require_user
from ..db import get_session
from ..membership_flows import (
    accept_invitation,
    create_invitation,
    find_invitation,
    invitation_status,
    now,
)
from ..models import Invitation, User
from ..orgs import ROLES, get_member_organization
from ..schemas import (
    InvitationAcceptOut,
    InvitationCreate,
    InvitationCreatedOut,
    InvitationOut,
    InvitationPreviewOut,
)

# Managing invitations belongs to an organisation's admins.
manage = APIRouter(prefix="/api/organizations/{organization_id}/invitations", tags=["invitations"])
# Following a link starts before anyone is signed in.
public = APIRouter(prefix="/api/invitations", tags=["invitations"])

MAX_LABEL = 80


def _out(session: Session, invitation: Invitation) -> InvitationOut:
    def name(user_id):
        user = session.get(User, user_id) if user_id else None
        return user.username if user else None

    return InvitationOut(
        id=invitation.uuid,
        role=invitation.role,
        label=invitation.label,
        status=invitation_status(invitation),
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        invited_by=name(invitation.invited_by),
        accepted_by=name(invitation.accepted_by),
    )


@manage.post("", response_model=InvitationCreatedOut, status_code=status.HTTP_201_CREATED)
def create(
    organization_id: str, payload: InvitationCreate, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    organization, _ = get_member_organization(session, organization_id, user, admin=True)
    if payload.role not in ROLES:
        raise HTTPException(422, "Role must be 'admin' or 'member'.")
    label = (payload.label or "").strip() or None
    if label and len(label) > MAX_LABEL:
        raise HTTPException(422, f"Keep the label under {MAX_LABEL} characters.")
    invitation, token = create_invitation(session, organization, user, payload.role, label)
    return InvitationCreatedOut(**_out(session, invitation).model_dump(), token=token)


@manage.get("", response_model=list[InvitationOut])
def list_invitations(organization_id: str, session: Session = Depends(get_session), user: User = Depends(require_user)):
    """Newest first. Tokens are never listed -- only shown when created."""
    organization, _ = get_member_organization(session, organization_id, user, admin=True)
    rows = session.exec(
        select(Invitation).where(Invitation.organization_id == organization.id).order_by(Invitation.created_at.desc())
    ).all()
    return [_out(session, i) for i in rows]


@manage.delete("/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke(
    organization_id: str, invitation_id: str, session: Session = Depends(get_session), user: User = Depends(require_user)
) -> Response:
    organization, _ = get_member_organization(session, organization_id, user, admin=True)
    invitation = session.exec(
        select(Invitation).where(Invitation.uuid == invitation_id, Invitation.organization_id == organization.id)
    ).first()
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")
    if invitation_status(invitation) == "pending":
        invitation.revoked_at = now()
        session.add(invitation)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public.get("/{token}", response_model=InvitationPreviewOut)
def preview(token: str, session: Session = Depends(get_session)):
    invitation, organization = find_invitation(session, token)
    return InvitationPreviewOut(
        organization_name=organization.name, role=invitation.role, status=invitation_status(invitation)
    )


@public.post("/{token}/accept", response_model=InvitationAcceptOut)
def accept(token: str, response: Response, session: Session = Depends(get_session), user: User = Depends(require_user)):
    organization, already = accept_invitation(session, response, user, token)
    return InvitationAcceptOut(
        organization_id=organization.uuid, organization_name=organization.name, already_member=already
    )
