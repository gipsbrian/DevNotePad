"""Organisation admins configure their organisation's identity providers.
Secrets go in and never come back out."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import require_user
from ..config import settings
from ..db import get_session
from ..models import Organization, SsoProvider, User
from ..orgs import get_member_organization
from ..sso import LABELS, PROVIDER_TYPES
from .sso import app_url, callback_url, row_credentials

router = APIRouter(prefix="/api/organizations/{organization_id}/sso", tags=["sso-admin"])


class SsoProviderOut(BaseModel):
    type: str
    label: str
    configured: bool
    enabled: bool
    client_id: str
    has_secret: bool
    tenant: Optional[str] = None
    team_id: Optional[str] = None
    key_id: Optional[str] = None
    auto_join_domains: list[str]
    # Complete enough to offer on the sign-in page.
    ready: bool
    # To register with the provider. Null until PUBLIC_URL is set.
    callback_url: Optional[str] = None


class SsoSettingsOut(BaseModel):
    public_url_set: bool
    # Where this organisation's members sign in.
    login_url: Optional[str] = None
    providers: list[SsoProviderOut]


class SsoProviderUpdate(BaseModel):
    enabled: bool = False
    client_id: str = ""
    # Left out (or null) keeps the saved secret; for Apple, the .p8 key.
    client_secret: Optional[str] = None
    tenant: Optional[str] = None
    team_id: Optional[str] = None
    key_id: Optional[str] = None
    auto_join_domains: list[str] = []


def _out(provider_type: str, row: Optional[SsoProvider]) -> SsoProviderOut:
    creds = row_credentials(row) if row else None
    return SsoProviderOut(
        type=provider_type,
        label=LABELS[provider_type],
        configured=row is not None,
        enabled=bool(row and row.enabled),
        client_id=row.client_id if row else "",
        has_secret=bool(row and row.client_secret),
        tenant=row.tenant if row else None,
        team_id=row.team_id if row else None,
        key_id=row.key_id if row else None,
        auto_join_domains=list(creds.auto_join_domains) if creds else [],
        ready=bool(row and row.enabled and creds.complete),
        callback_url=callback_url(provider_type) if settings.public_url else None,
    )


def _settings(session: Session, organization: Organization) -> SsoSettingsOut:
    rows = {r.type: r for r in session.exec(select(SsoProvider).where(SsoProvider.organization_id == organization.id)).all()}
    login = None
    if settings.public_url:
        login = f"{app_url()}/" if organization.is_main else f"{app_url()}/o/{organization.slug}"
    return SsoSettingsOut(
        public_url_set=bool(settings.public_url),
        login_url=login,
        providers=[_out(t, rows.get(t)) for t in PROVIDER_TYPES],
    )


@router.get("", response_model=SsoSettingsOut)
def read_sso(organization_id: str, session: Session = Depends(get_session), user: User = Depends(require_user)):
    organization, _ = get_member_organization(session, organization_id, user, admin=True)
    return _settings(session, organization)


def save_provider(session: Session, organization: Organization, provider_type: str, payload: SsoProviderUpdate) -> SsoProvider:
    """Shared by the API and the command line."""
    if provider_type not in PROVIDER_TYPES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown provider type")
    row = session.exec(
        select(SsoProvider).where(SsoProvider.organization_id == organization.id, SsoProvider.type == provider_type)
    ).first()
    if row is None:
        row = SsoProvider(organization_id=organization.id, type=provider_type)

    row.client_id = payload.client_id.strip()
    if payload.client_secret is not None:
        row.client_secret = payload.client_secret.strip() or None
    row.tenant = (payload.tenant or "").strip() or None if provider_type == "microsoft" else None
    row.team_id = (payload.team_id or "").strip() or None if provider_type == "apple" else None
    row.key_id = (payload.key_id or "").strip() or None if provider_type == "apple" else None
    row.auto_join_domains = ",".join(d.strip().lower().lstrip("@") for d in payload.auto_join_domains if d.strip())
    row.enabled = payload.enabled
    if row.enabled and not row_credentials(row).complete:
        needs = "client ID, secret, Team ID and Key ID" if provider_type == "apple" else "client ID and secret"
        raise HTTPException(422, f"{LABELS[provider_type]} needs a {needs} before it can be switched on.")
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.put("/{provider_type}", response_model=SsoSettingsOut)
def update_provider(
    organization_id: str,
    provider_type: str,
    payload: SsoProviderUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    organization, _ = get_member_organization(session, organization_id, user, admin=True)
    save_provider(session, organization, provider_type, payload)
    return _settings(session, organization)


@router.delete("/{provider_type}", status_code=status.HTTP_204_NO_CONTENT)
def remove_provider(
    organization_id: str, provider_type: str, session: Session = Depends(get_session), user: User = Depends(require_user)
) -> Response:
    organization, _ = get_member_organization(session, organization_id, user, admin=True)
    row = session.exec(
        select(SsoProvider).where(SsoProvider.organization_id == organization.id, SsoProvider.type == provider_type)
    ).first()
    if row is not None:
        session.delete(row)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
