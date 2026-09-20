"""Sign-in through external identity providers: Google, Microsoft and Apple.

Every provider speaks OpenID Connect's authorization-code flow, so one flow
serves all three (see routers/sso.py). What differs lives here: endpoints,
how a token's issuer is checked, how the client authenticates, and which
emails can be trusted.
"""

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import httpx
import jwt

from .config import settings

APPLE_ISSUER = "https://appleid.apple.com"
# Microsoft's own tenant for personal accounts.
MICROSOFT_CONSUMERS_TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"
MICROSOFT_MULTI_TENANT = ("common", "organizations", "consumers")


class SsoError(Exception):
    """A sign-in that must stop. `code` is one of a fixed set the sign-in
    page turns into a message -- never free text, so a crafted link can't
    put words of its choosing on that page."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass
class Identity:
    subject: str
    email: Optional[str]
    # True only when the provider vouches the address belongs to this person.
    email_verified: bool


@dataclass
class Provider:
    """The protocol details of one provider type, bound to one set of
    credentials."""

    id: str
    label: str
    authorize_url: str
    token_url: str
    jwks_url: str
    client_id: str
    scope: str
    check_issuer: Callable[[dict], None]
    read_identity: Callable[[dict], Identity]
    client_secret: Callable[[], str]
    credentials: Optional["Credentials"] = None
    uses_pkce: bool = True
    # Apple returns with a POST when names or emails are asked for.
    response_mode: Optional[str] = None
    extra_authorize_params: dict = field(default_factory=dict)


def _truthy(value) -> bool:
    """Apple sends booleans as booleans or as the strings "true"/"false"."""
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.strip().lower() == "true"


def _email_or_none(value) -> Optional[str]:
    return value.strip().lower() if isinstance(value, str) and "@" in value else None


@dataclass
class Credentials:
    """One identity provider's settings, from an organisation's SsoProvider
    row, or from .env for the main organisation."""

    type: str  # "google" | "microsoft" | "apple"
    client_id: str
    client_secret: str  # for Apple: the .p8 private key
    tenant: str = "common"  # Microsoft
    team_id: Optional[str] = None  # Apple
    key_id: Optional[str] = None  # Apple
    auto_join_domains: tuple[str, ...] = ()
    row_id: Optional[int] = None  # None: from .env

    @property
    def complete(self) -> bool:
        if not (self.client_id and self.client_secret):
            return False
        if self.type == "apple":
            return bool(self.team_id and self.key_id)
        return self.type in PROVIDER_TYPES


PROVIDER_TYPES = ("google", "microsoft", "apple")
LABELS = {"google": "Google", "microsoft": "Microsoft", "apple": "Apple"}


# ---- Google ----

def _google_issuer(claims: dict) -> None:
    if claims.get("iss") not in ("https://accounts.google.com", "accounts.google.com"):
        raise SsoError("provider", "unexpected issuer")


def _google_identity(claims: dict) -> Identity:
    return Identity(
        subject=str(claims["sub"]),
        email=_email_or_none(claims.get("email")),
        email_verified=_truthy(claims.get("email_verified")),
    )


# ---- Microsoft ----

def _microsoft_issuer_check(tenant: str) -> Callable[[dict], None]:
    def check(claims: dict) -> None:
        """A multi-tenant endpoint signs for every tenant with the same keys,
        so the issuer has to name the tenant the token claims to come from --
        and when one tenant is configured, it has to be that one."""
        tid = claims.get("tid")
        if not tid or claims.get("iss") != f"https://login.microsoftonline.com/{tid}/v2.0":
            raise SsoError("provider", "unexpected issuer")
        if tenant == "consumers" and tid != MICROSOFT_CONSUMERS_TENANT:
            raise SsoError("provider", "not a personal account")
        if tenant == "organizations" and tid == MICROSOFT_CONSUMERS_TENANT:
            raise SsoError("provider", "not a work or school account")
        if tenant not in MICROSOFT_MULTI_TENANT and tid != tenant:
            raise SsoError("provider", "account from another organisation")

    return check


def _microsoft_identity(claims: dict) -> Identity:
    """Microsoft doesn't verify the email it reports: an organisation's admin
    can set it to anything, including someone else's address. So it can name
    a new account but never unlock an existing one."""
    email = _email_or_none(claims.get("email"))
    if email is None:
        upn = claims.get("preferred_username")
        # Guest accounts carry an identifier shaped like an email that isn't
        # a real mailbox.
        if isinstance(upn, str) and "#EXT#" not in upn:
            email = _email_or_none(upn)
    return Identity(subject=str(claims["sub"]), email=email, email_verified=False)


# ---- Apple ----

def _apple_issuer(claims: dict) -> None:
    if claims.get("iss") != APPLE_ISSUER:
        raise SsoError("provider", "unexpected issuer")


def _apple_identity(claims: dict) -> Identity:
    return Identity(
        subject=str(claims["sub"]),
        email=_email_or_none(claims.get("email")),
        email_verified=_truthy(claims.get("email_verified")),
    )


def apple_client_secret(creds: Credentials) -> str:
    """Apple has no fixed client secret: each token request carries a short
    JWT signed with the Sign in with Apple key."""
    now = int(time.time())
    return jwt.encode(
        {"iss": creds.team_id, "iat": now, "exp": now + 300, "aud": APPLE_ISSUER, "sub": creds.client_id},
        # .env files often hold the key on one line with literal \n.
        (creds.client_secret or "").replace("\\n", "\n"),
        algorithm="ES256",
        headers={"kid": creds.key_id},
    )


def build_provider(creds: Credentials) -> Provider:
    if creds.type == "google":
        return Provider(
            id="google",
            label="Google",
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            jwks_url="https://www.googleapis.com/oauth2/v3/certs",
            client_id=creds.client_id,
            scope="openid email profile",
            check_issuer=_google_issuer,
            read_identity=_google_identity,
            client_secret=lambda: creds.client_secret,
            credentials=creds,
            extra_authorize_params={"prompt": "select_account"},
        )
    if creds.type == "microsoft":
        base = f"https://login.microsoftonline.com/{creds.tenant or 'common'}"
        return Provider(
            id="microsoft",
            label="Microsoft",
            authorize_url=f"{base}/oauth2/v2.0/authorize",
            token_url=f"{base}/oauth2/v2.0/token",
            jwks_url=f"{base}/discovery/v2.0/keys",
            client_id=creds.client_id,
            scope="openid email profile",
            check_issuer=_microsoft_issuer_check(creds.tenant or "common"),
            read_identity=_microsoft_identity,
            client_secret=lambda: creds.client_secret,
            credentials=creds,
            extra_authorize_params={"prompt": "select_account"},
        )
    if creds.type == "apple":
        return Provider(
            id="apple",
            label="Apple",
            authorize_url=f"{APPLE_ISSUER}/auth/authorize",
            token_url=f"{APPLE_ISSUER}/auth/token",
            jwks_url=f"{APPLE_ISSUER}/auth/keys",
            client_id=creds.client_id,
            scope="name email",
            check_issuer=_apple_issuer,
            read_identity=_apple_identity,
            client_secret=lambda: apple_client_secret(creds),
            credentials=creds,
            uses_pkce=False,
            response_mode="form_post",
        )
    raise ValueError(f"unknown provider type {creds.type!r}")


def env_credentials() -> dict[str, Credentials]:
    """The main organisation's fallback, while it has no providers saved."""
    s = settings
    found = {
        "google": Credentials("google", s.google_client_id or "", s.google_client_secret or ""),
        "microsoft": Credentials(
            "microsoft", s.microsoft_client_id or "", s.microsoft_client_secret or "", tenant=s.microsoft_tenant or "common"
        ),
        "apple": Credentials(
            "apple", s.apple_client_id or "", s.apple_private_key or "", team_id=s.apple_team_id, key_id=s.apple_key_id
        ),
    }
    return {t: c for t, c in found.items() if c.complete}


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


# ---- Token verification ----

JWKS_TTL_SECONDS = 3600
_jwks_cache: dict[str, tuple[float, dict]] = {}


async def _signing_key(jwks_url: str, kid: Optional[str]):
    """Keys are cached, but an unknown key id triggers one refetch --
    providers rotate keys, and a stale cache mustn't lock everyone out."""
    for attempt in range(2):
        cached = _jwks_cache.get(jwks_url)
        if attempt == 1 or cached is None or time.time() - cached[0] > JWKS_TTL_SECONDS:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(jwks_url)
            if resp.status_code != 200:
                raise SsoError("provider", f"key set returned {resp.status_code}")
            cached = (time.time(), resp.json())
            _jwks_cache[jwks_url] = cached
        for key in cached[1].get("keys", []):
            if key.get("kid") == kid:
                return jwt.PyJWK(key).key
    raise SsoError("provider", "token signed with an unknown key")


async def verify_id_token(provider: Provider, id_token: str, nonce: str) -> dict:
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError:
        raise SsoError("provider", "malformed id_token")
    if header.get("alg") != "RS256":
        # Pinning the algorithm stops a token from choosing how it's checked.
        raise SsoError("provider", "unexpected signing algorithm")
    key = await _signing_key(provider.jwks_url, header.get("kid"))
    try:
        claims = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=provider.client_id,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            leeway=60,
        )
    except jwt.PyJWTError as exc:
        raise SsoError("provider", f"id_token rejected: {exc}")
    provider.check_issuer(claims)
    if not nonce or claims.get("nonce") != nonce:
        raise SsoError("provider", "nonce mismatch")
    return claims
