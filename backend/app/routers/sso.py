"""The sign-in round trip through an identity provider.

    /login?org=<slug> -> provider -> /callback (GET, or POST for Apple) -> /finish -> app

`/callback` does the checking and decides which account and where it lands;
`/finish` is where the session is actually set, on a plain top-level GET to
this site. Apple's callback arrives as a cross-site POST, and a browser can
decline to store a SameSite=Lax cookie set in reply to one -- the extra hop
sidesteps that for every provider rather than special-casing one.

Each provider type has one callback URL for every organisation: the attempt
recorded at /login says which organisation and which settings it belongs to.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qs, urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..auth import SESSION_KEY
from ..config import settings
from ..db import get_session
from ..membership_flows import request_to_join
from ..models import Organization, SsoIdentity, SsoLoginAttempt, SsoProvider, User
from ..orgs import add_member, ensure_in_main, forget_active, get_main, membership, switch_to
from ..sso import (
    LABELS,
    PROVIDER_TYPES,
    Credentials,
    Identity,
    Provider,
    SsoError,
    build_provider,
    digest,
    env_credentials,
    new_secret,
    pkce_challenge,
    verify_id_token,
)
from .auth import USERNAME_RE

log = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/auth/sso", tags=["sso"])

ATTEMPT_TTL = timedelta(minutes=10)
TICKET_TTL = timedelta(minutes=1)
BINDING_COOKIE = "devnotepad_sso"


def app_url() -> str:
    return (settings.public_url or "").rstrip("/")


def api_url() -> str:
    return (settings.public_api_url or settings.public_url or "").rstrip("/")


def callback_url(provider_type: str) -> str:
    return f"{api_url()}/api/auth/sso/{provider_type}/callback"


def _back_to_app(error: Optional[str] = None, notice: Optional[str] = None) -> RedirectResponse:
    target = f"{app_url()}/"
    if error:
        target += "?" + urlencode({"sso_error": error})
    elif notice:
        target += "?" + urlencode({"sso_notice": notice})
    return RedirectResponse(target, status_code=303)


def _aware(moment: datetime) -> datetime:
    # SQLite hands datetimes back without their zone.
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---- Which providers an organisation offers ----

def row_credentials(row: SsoProvider) -> Credentials:
    return Credentials(
        type=row.type,
        client_id=row.client_id or "",
        client_secret=row.client_secret or "",
        tenant=row.tenant or "common",
        team_id=row.team_id,
        key_id=row.key_id,
        auto_join_domains=tuple(d.strip().lower().lstrip("@") for d in (row.auto_join_domains or "").split(",") if d.strip()),
        row_id=row.id,
    )


def organization_credentials(session: Session, organization: Organization) -> dict[str, Credentials]:
    """Enabled, complete providers. The main organisation falls back to .env
    only while it has no providers saved at all -- once one is saved, the
    database is the whole story."""
    rows = session.exec(select(SsoProvider).where(SsoProvider.organization_id == organization.id)).all()
    if organization.is_main and not rows:
        return env_credentials()
    found = {r.type: row_credentials(r) for r in rows if r.enabled}
    return {t: c for t, c in found.items() if c.complete}


def _organization_by_slug(session: Session, slug: Optional[str]) -> Organization:
    if not slug:
        return get_main(session)
    organization = session.exec(select(Organization).where(Organization.slug == slug.lower())).first()
    if organization is None:
        raise HTTPException(404, "No organization has that link.")
    return organization


@router.get("/providers")
def list_providers(org: Optional[str] = None, session: Session = Depends(get_session)):
    """What a sign-in page should offer: the main organisation's providers,
    or the named organisation's. Nothing until PUBLIC_URL is set."""
    organization = _organization_by_slug(session, org)
    providers = [] if not settings.public_url else [
        {"id": t, "label": LABELS[t]} for t in PROVIDER_TYPES if t in organization_credentials(session, organization)
    ]
    return {
        "organization": None if organization.is_main else {"name": organization.name, "slug": organization.slug},
        "providers": providers,
    }


# ---- The round trip ----

@router.get("/{provider_type}/login")
def start(provider_type: str, org: Optional[str] = None, session: Session = Depends(get_session)):
    try:
        organization = _organization_by_slug(session, org)
    except HTTPException:
        return _back_to_app("unavailable")
    creds = organization_credentials(session, organization).get(provider_type)
    if creds is None or not settings.public_url:
        return _back_to_app("unavailable")
    provider = build_provider(creds)

    # Abandoned attempts would otherwise pile up.
    stale = _now() - ATTEMPT_TTL
    for old in session.exec(select(SsoLoginAttempt)).all():
        if _aware(old.created_at) < stale:
            session.delete(old)

    binding = new_secret()
    attempt = SsoLoginAttempt(
        state=new_secret(),
        provider=provider.id,
        nonce=new_secret(),
        code_verifier=new_secret() if provider.uses_pkce else None,
        binding_hash=digest(binding),
        organization_id=organization.id,
        sso_provider_id=creds.row_id,
    )
    session.add(attempt)
    session.commit()

    params = {
        "client_id": provider.client_id,
        "redirect_uri": callback_url(provider.id),
        "response_type": "code",
        "scope": provider.scope,
        "state": attempt.state,
        "nonce": attempt.nonce,
        **provider.extra_authorize_params,
    }
    if provider.response_mode:
        params["response_mode"] = provider.response_mode
    if attempt.code_verifier:
        params["code_challenge"] = pkce_challenge(attempt.code_verifier)
        params["code_challenge_method"] = "S256"

    response = RedirectResponse(f"{provider.authorize_url}?{urlencode(params)}", status_code=302)
    response.set_cookie(
        BINDING_COOKIE,
        binding,
        max_age=int(ATTEMPT_TTL.total_seconds()),
        httponly=True,
        path="/api/auth/sso",
        # Apple's return is a cross-site POST: only a SameSite=None cookie
        # rides along on it, and browsers only accept those over HTTPS --
        # which Apple insists on anyway.
        samesite="none" if settings.session_https_only else "lax",
        secure=settings.session_https_only,
    )
    return response


async def _callback_params(request: Request) -> dict[str, str]:
    if request.method == "POST":
        # Apple posts a plain urlencoded form.
        parsed = parse_qs((await request.body()).decode(), keep_blank_values=True)
        return {k: v[0] for k, v in parsed.items()}
    return dict(request.query_params)


def _attempt_credentials(session: Session, attempt: SsoLoginAttempt) -> Credentials:
    """The same settings the attempt started with -- re-read, so disabling a
    provider mid-sign-in stops the sign-in."""
    organization = session.get(Organization, attempt.organization_id) if attempt.organization_id else None
    if organization is None:
        raise SsoError("unavailable", "organisation gone")
    creds = organization_credentials(session, organization).get(attempt.provider)
    if creds is None or creds.row_id != attempt.sso_provider_id:
        raise SsoError("unavailable", "provider changed or disabled mid-sign-in")
    return creds


@router.api_route("/{provider_type}/callback", methods=["GET", "POST"])
async def callback(provider_type: str, request: Request, session: Session = Depends(get_session)):
    params = await _callback_params(request)
    try:
        attempt = _claim_attempt(session, provider_type, params.get("state"), request)
        creds = _attempt_credentials(session, attempt)
        provider = build_provider(creds)
        if params.get("error"):
            # Most often the person pressed cancel.
            raise SsoError("denied", params["error"])
        if not params.get("code"):
            raise SsoError("provider", "no authorization code")

        id_token = await _exchange_code(provider, params["code"], attempt.code_verifier)
        claims = await verify_id_token(provider, id_token, attempt.nonce)
        identity = provider.read_identity(claims)
        user = _resolve_account(session, provider, identity)
        land, notice = _landing(session, attempt, creds, user, identity)
    except SsoError as exc:
        log.warning("SSO sign-in via %s refused: %s", provider_type, exc)
        response = _back_to_app(exc.code)
        response.delete_cookie(BINDING_COOKIE, path="/api/auth/sso")
        return response

    attempt.user_id = user.id
    attempt.ticket = new_secret()
    attempt.land_organization_id = land
    attempt.notice = notice
    attempt.created_at = _now()
    session.add(attempt)
    session.commit()

    response = RedirectResponse(f"{api_url()}/api/auth/sso/finish?{urlencode({'ticket': attempt.ticket})}", status_code=303)
    response.delete_cookie(BINDING_COOKIE, path="/api/auth/sso")
    return response


@router.get("/finish")
def finish(ticket: str, request: Request, session: Session = Depends(get_session)):
    attempt = session.exec(select(SsoLoginAttempt).where(SsoLoginAttempt.ticket == ticket)).first() if ticket else None
    if attempt is None or attempt.user_id is None:
        return _back_to_app("expired")
    # Single use, whatever happens next.
    session.delete(attempt)
    session.commit()
    if _now() - _aware(attempt.created_at) > TICKET_TTL:
        return _back_to_app("expired")
    user = session.get(User, attempt.user_id)
    if user is None:
        return _back_to_app("failed")

    request.session.clear()
    request.session[SESSION_KEY] = user.id
    response = _back_to_app(notice=attempt.notice)
    landing = session.get(Organization, attempt.land_organization_id) if attempt.land_organization_id else None
    if landing is not None and membership(session, landing.id, user.id):
        switch_to(response, session, user, landing)
    else:
        forget_active(response)
    return response


def _claim_attempt(session: Session, provider_type: str, state: Optional[str], request: Request) -> SsoLoginAttempt:
    """The attempt this callback belongs to, consumed so it can't be replayed.
    It must have been started for this provider, recently, in this browser."""
    attempt = session.get(SsoLoginAttempt, state) if state else None
    if attempt is None or attempt.ticket is not None:
        raise SsoError("expired", "unknown or already used state")
    # Copied before deleting: the committed delete expires the loaded row.
    snapshot = SsoLoginAttempt.model_validate(attempt.model_dump())
    session.delete(attempt)
    session.commit()
    attempt = snapshot
    if attempt.provider != provider_type:
        raise SsoError("expired", "state belongs to another provider")
    if _now() - _aware(attempt.created_at) > ATTEMPT_TTL:
        raise SsoError("expired", "state too old")
    binding = request.cookies.get(BINDING_COOKIE)
    if not binding or digest(binding) != attempt.binding_hash:
        # Started in a different browser: finishing it here would sign this
        # browser into whichever account the other one chose.
        raise SsoError("expired", "browser binding missing or wrong")
    # Re-added under the same state once it gains a ticket.
    return attempt


async def _exchange_code(provider: Provider, code: str, code_verifier: Optional[str]) -> str:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": callback_url(provider.id),
        "client_id": provider.client_id,
        "client_secret": provider.client_secret(),
    }
    if code_verifier:
        form["code_verifier"] = code_verifier
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(provider.token_url, data=form, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise SsoError("provider", f"token endpoint unreachable: {exc}")
    if resp.status_code != 200:
        raise SsoError("provider", f"token endpoint returned {resp.status_code}: {resp.text[:200]}")
    id_token = resp.json().get("id_token")
    if not id_token:
        raise SsoError("provider", "no id_token in token response")
    return id_token


def identity_key(provider: Provider) -> str:
    """Subjects are only unique within one client of one provider, so that's
    what a link is keyed by. Moving the same client from .env into the
    dashboard keeps everyone's links."""
    return f"{provider.id}:{provider.client_id}"


def _resolve_account(session: Session, provider: Provider, identity: Identity) -> User:
    """Which account this person signs in to, in order:

    1. the account already linked to this provider identity;
    2. an account with the same email -- only when the provider has
       verified that email, since otherwise anyone able to set their email
       at the provider could walk into someone else's account;
    3. a new account, when registration is open. It joins only the main
       organisation.
    """
    key = identity_key(provider)
    linked = session.exec(
        select(SsoIdentity).where(SsoIdentity.provider == key, SsoIdentity.subject == identity.subject)
    ).first()
    if linked is not None:
        user = session.get(User, linked.user_id)
        if user is None:
            raise SsoError("failed", "linked account no longer exists")
        if identity.email and linked.email != identity.email:
            linked.email = identity.email
            session.add(linked)
            session.commit()
        return user

    if not identity.email:
        raise SsoError("no_email")

    existing = session.exec(select(User).where(User.email == identity.email)).first()
    if existing is not None:
        if not identity.email_verified:
            raise SsoError("unverified")
        _link(session, existing, key, identity)
        return existing

    if not settings.allow_registration:
        raise SsoError("closed")

    user = User(
        username=_available_username(session, identity.email),
        email=identity.email,
        # No password: this account signs in through its provider. An empty
        # hash never verifies (auth.verify_password).
        password_hash="",
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise SsoError("failed", "account creation raced another")
    session.refresh(user)
    ensure_in_main(session, user)
    _link(session, user, key, identity)
    log.info("Created account %r through %s sign-in.", user.username, provider.id)
    return user


def _landing(
    session: Session, attempt: SsoLoginAttempt, creds: Credentials, user: User, identity: Identity
) -> tuple[Optional[int], Optional[str]]:
    """Where someone arriving through an organisation's sign-in lands.
    Members land in it. Verified emails on its auto-join domains become
    members. Anyone else is signed in to main, with a join request filed for
    the organisation's admins."""
    organization = session.get(Organization, attempt.organization_id)
    if organization is None or organization.is_main:
        return None, None
    if membership(session, organization.id, user.id):
        return organization.id, None
    domain = (identity.email or "").rsplit("@", 1)[-1]
    if identity.email_verified and domain and domain in creds.auto_join_domains:
        add_member(session, organization, user)
        return organization.id, None
    try:
        request_to_join(session, organization, user, via="sso")
    except HTTPException:
        # Already asked recently, or declined within the cooldown: still
        # signed in to main, just without a new request.
        pass
    return None, "join_requested"


def _link(session: Session, user: User, key: str, identity: Identity) -> None:
    session.add(SsoIdentity(user_id=user.id, provider=key, subject=identity.subject, email=identity.email))
    session.commit()


def _available_username(session: Session, email: str) -> str:
    """The email's local part, made into a valid username and made unique."""
    base = re.sub(r"[^a-z0-9._-]+", "-", email.split("@", 1)[0].lower())
    base = re.sub(r"^[^a-z0-9]+", "", base)[:28] or "user"
    if len(base) < 3:
        base = f"{base}-user"
    candidate, n = base, 1
    while not USERNAME_RE.match(candidate) or session.exec(select(User).where(User.username == candidate)).first():
        n += 1
        candidate = f"{base}-{n}"
        if n > 1000:
            raise SsoError("failed", "no free username")
    return candidate
