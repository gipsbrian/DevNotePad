from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session, select

from ..auth import require_user
from ..db import get_session
from ..access import VIEW, board_access
from ..models import Dashboard, Membership, Organization, User
from ..orgs import (
    ROLES,
    active_admin_count,
    active_organizations,
    add_member,
    available_slug,
    current_organization,
    get_member_organization,
    membership,
    remove_member,
    switch_to,
)
from ..schemas import (
    DefaultOrganizationUpdate,
    OrganizationMemberOut,
    OrganizationMemberUpdate,
    OrganizationCreate,
    OrganizationOut,
    OrganizationTokenUpdate,
    OrganizationUpdate,
    DashboardOut,
)

router = APIRouter(prefix="/api/organizations", tags=["organizations"])

MAX_NAME = 80


def _out(organization: Organization, row: Membership, user: User, active_id: int) -> OrganizationOut:
    return OrganizationOut(
        id=organization.uuid,
        slug=organization.slug,
        name=organization.name,
        is_main=organization.is_main,
        role=row.role,
        is_active=organization.id == active_id,
        is_default=user.default_organization_id == organization.id,
        has_token=bool(organization.token) if row.role == "admin" else None,
    )


def _clean_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > MAX_NAME:
        raise HTTPException(422, f"An organization's name needs 1-{MAX_NAME} characters.")
    return name


@router.get("", response_model=list[OrganizationOut])
def list_organizations(request: Request, session: Session = Depends(get_session), user: User = Depends(require_user)):
    """Every organisation you're in, main first, with the one you're working
    in marked."""
    active = current_organization(request, session, user)
    return [_out(o, m, user, active.id) for o, m in active_organizations(session, user)]


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate, response: Response, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    """Anyone can start one. The creator is its admin and is moved into it."""
    name = _clean_name(payload.name)
    organization = Organization(name=name, slug=available_slug(session, name), created_by=user.id)
    session.add(organization)
    session.commit()
    session.refresh(organization)
    row = add_member(session, organization, user, role="admin")
    switch_to(response, session, user, organization)
    return _out(organization, row, user, organization.id)


@router.post("/{organization_id}/switch", response_model=OrganizationOut)
def switch_organization(
    organization_id: str, response: Response, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    organization, row = get_member_organization(session, organization_id, user)
    switch_to(response, session, user, organization)
    return _out(organization, row, user, organization.id)


@router.patch("/{organization_id}", response_model=OrganizationOut)
def update_organization(
    organization_id: str,
    payload: OrganizationUpdate,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    organization, row = get_member_organization(session, organization_id, user, admin=True)
    if payload.name is not None:
        organization.name = _clean_name(payload.name)
    session.add(organization)
    session.commit()
    session.refresh(organization)
    return _out(organization, row, user, current_organization(request, session, user).id)


@router.put("/default", status_code=status.HTTP_204_NO_CONTENT)
def set_default_organization(
    payload: DefaultOrganizationUpdate, session: Session = Depends(get_session), user: User = Depends(require_user)
) -> Response:
    if payload.organization_id is None:
        user.default_organization_id = None
    else:
        organization, _ = get_member_organization(session, payload.organization_id, user)
        user.default_organization_id = organization.id
    session.add(user)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- Members ----

@router.get("/{organization_id}/members", response_model=list[OrganizationMemberOut])
def list_members(organization_id: str, session: Session = Depends(get_session), user: User = Depends(require_user)):
    organization, _ = get_member_organization(session, organization_id, user)
    rows = session.exec(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == organization.id, Membership.removed_at == None)  # noqa: E711
        .order_by(User.username)
    ).all()
    return [OrganizationMemberOut(user_id=u.id, username=u.username, role=m.role, joined_at=m.created_at) for m, u in rows]


def _target(session: Session, organization: Organization, user_id: int) -> Membership:
    row = membership(session, organization.id, user_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return row


def _keeps_an_admin(session: Session, organization: Organization, row: Membership) -> None:
    if row.role == "admin" and active_admin_count(session, organization.id) <= 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An organization needs at least one admin. Make someone else an admin first.",
        )


@router.patch("/{organization_id}/members/{user_id}", response_model=OrganizationMemberOut)
def update_member(
    organization_id: str,
    user_id: int,
    payload: OrganizationMemberUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    organization, _ = get_member_organization(session, organization_id, user, admin=True)
    if payload.role not in ROLES:
        raise HTTPException(422, "Role must be 'admin' or 'member'.")
    row = _target(session, organization, user_id)
    if payload.role != "admin":
        _keeps_an_admin(session, organization, row)
    row.role = payload.role
    session.add(row)
    session.commit()
    member = session.get(User, user_id)
    return OrganizationMemberOut(user_id=member.id, username=member.username, role=row.role, joined_at=row.created_at)


@router.delete("/{organization_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_organization_member(
    organization_id: str, user_id: int, session: Session = Depends(get_session), user: User = Depends(require_user)
) -> Response:
    """Admins remove anyone; anybody can remove themselves (leave). Removal is
    soft, so boards left behind come back if the person is added again. The
    main organisation is everyone's, so nobody leaves or is removed from it."""
    organization, caller = get_member_organization(session, organization_id, user, admin=user_id != user.id)
    if organization.is_main:
        raise HTTPException(status.HTTP_409_CONFLICT, "Every account belongs to the main organization.")
    row = _target(session, organization, user_id)
    _keeps_an_admin(session, organization, row)
    remove_member(session, row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{organization_id}/token", response_model=OrganizationOut)
def set_organization_token(
    organization_id: str,
    payload: OrganizationTokenUpdate,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    """The token organisation boards read GitHub with. Write-only: it's
    never returned. Changes on GitHub are always made with each member's own
    token, not this one."""
    organization, row = get_member_organization(session, organization_id, user, admin=True)
    organization.token = payload.token.strip() or None
    session.add(organization)
    session.commit()
    session.refresh(organization)
    return _out(organization, row, user, current_organization(request, session, user).id)


@router.get("/{organization_id}/members/{user_id}/boards", response_model=list[DashboardOut])
def member_boards(
    organization_id: str, user_id: int, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    """A member's personal boards that they've shared with you -- directly or
    with the whole organisation. View only; nothing else of theirs shows."""
    from .dashboards import _dashboard_out  # noqa: PLC0415

    organization, _ = get_member_organization(session, organization_id, user)
    if membership(session, organization.id, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    boards = session.exec(
        select(Dashboard).where(
            Dashboard.organization_id == organization.id,
            Dashboard.owner_id == user_id,
            Dashboard.kind == "personal",
        )
    ).all()
    return [_dashboard_out(session, b, user) for b in boards if user_id != user.id and board_access(session, b, user) == VIEW]
