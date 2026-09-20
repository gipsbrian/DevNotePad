"""The instance at a glance, for its admins -- who are the main
organisation's admins. Promoting and demoting them goes through main's
member roles, like any organisation's."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, func, select

from ..auth import require_user
from ..config import settings
from ..db import get_session
from ..models import Dashboard, Membership, Organization, SsoIdentity, User
from ..orgs import get_main, membership

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_instance_admin(session: Session = Depends(get_session), user: User = Depends(require_user)) -> User:
    row = membership(session, get_main(session).id, user.id)
    if row is None or row.role != "admin":
        # Not a 404: an admin area existing isn't a secret, and a clear
        # refusal is kinder to someone who was just demoted.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only instance admins can see this.")
    return user


class InstanceOut(BaseModel):
    main_organization_id: str
    registration_open: bool
    public_url: Optional[str]
    users: int
    organizations: int
    boards: int


class AdminUserOut(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime
    is_instance_admin: bool
    organizations: int
    boards: int
    has_password: bool
    sso_providers: list[str]


class AdminOrganizationOut(BaseModel):
    id: str
    slug: str
    name: str
    is_main: bool
    created_at: datetime
    created_by: Optional[str]
    members: int
    admins: int
    boards: int


def _count(session: Session, model, *where) -> int:
    return session.exec(select(func.count()).select_from(model).where(*where)).one()


@router.get("/overview", response_model=InstanceOut)
def overview(session: Session = Depends(get_session), _: User = Depends(require_instance_admin)):
    return InstanceOut(
        main_organization_id=get_main(session).uuid,
        registration_open=settings.allow_registration,
        public_url=settings.public_url,
        users=_count(session, User),
        organizations=_count(session, Organization),
        boards=_count(session, Dashboard),
    )


@router.get("/users", response_model=list[AdminUserOut])
def users(session: Session = Depends(get_session), _: User = Depends(require_instance_admin)):
    main = get_main(session)
    out = []
    for u in session.exec(select(User).order_by(User.created_at)).all():
        main_row = membership(session, main.id, u.id)
        providers = sorted({i.provider.split(":", 1)[0] for i in session.exec(select(SsoIdentity).where(SsoIdentity.user_id == u.id)).all()})
        out.append(
            AdminUserOut(
                id=u.id,
                username=u.username,
                email=u.email,
                created_at=u.created_at,
                is_instance_admin=bool(main_row and main_row.role == "admin"),
                organizations=_count(session, Membership, Membership.user_id == u.id, Membership.removed_at == None),  # noqa: E711
                boards=_count(session, Dashboard, Dashboard.owner_id == u.id),
                has_password=bool(u.password_hash),
                sso_providers=providers,
            )
        )
    return out


@router.get("/organizations", response_model=list[AdminOrganizationOut])
def organizations(session: Session = Depends(get_session), _: User = Depends(require_instance_admin)):
    out = []
    for o in session.exec(select(Organization).order_by(Organization.is_main.desc(), Organization.created_at)).all():
        creator = session.get(User, o.created_by) if o.created_by else None
        active = (Membership.organization_id == o.id, Membership.removed_at == None)  # noqa: E711
        out.append(
            AdminOrganizationOut(
                id=o.uuid,
                slug=o.slug,
                name=o.name,
                is_main=o.is_main,
                created_at=o.created_at,
                created_by=creator.username if creator else None,
                members=_count(session, Membership, *active),
                admins=_count(session, Membership, *active, Membership.role == "admin"),
                boards=_count(session, Dashboard, Dashboard.organization_id == o.id),
            )
        )
    return out
