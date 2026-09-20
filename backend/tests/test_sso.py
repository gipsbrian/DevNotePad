"""Sign-in through Google, Microsoft and Apple, against a fake provider that
signs real tokens with its own keys."""

import json
import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from httpx import Response
from sqlmodel import select

from app import sso as sso_module
from app.auth import verify_password
from app.config import settings
from app.models import SsoIdentity, SsoLoginAttempt, User
from tests.conftest import TEST_USER

APP = "https://app.test"
TENANT = "11111111-2222-3333-4444-555555555555"
RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
APPLE_KEY = ec.generate_private_key(ec.SECP256R1())

PROVIDERS = {
    "google": {
        "token": "https://oauth2.googleapis.com/token",
        "jwks": "https://www.googleapis.com/oauth2/v3/certs",
        "iss": "https://accounts.google.com",
        "aud": "google-client",
    },
    "microsoft": {
        "token": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "jwks": "https://login.microsoftonline.com/common/discovery/v2.0/keys",
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "aud": "microsoft-client",
    },
    "apple": {
        "token": "https://appleid.apple.com/auth/token",
        "jwks": "https://appleid.apple.com/auth/keys",
        "iss": "https://appleid.apple.com",
        "aud": "com.example.devnotepad",
    },
}


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    for name, value in {
        "public_url": APP,
        "public_api_url": None,
        "allow_registration": True,
        "google_client_id": "google-client",
        "google_client_secret": "google-secret",
        "microsoft_client_id": "microsoft-client",
        "microsoft_client_secret": "microsoft-secret",
        "microsoft_tenant": "common",
        "apple_client_id": "com.example.devnotepad",
        "apple_team_id": "TEAM123456",
        "apple_key_id": "KEY1234567",
        "apple_private_key": APPLE_KEY.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode(),
    }.items():
        monkeypatch.setattr(settings, name, value)
    sso_module._jwks_cache.clear()


def jwks(key=RSA_KEY, kid="k1"):
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    return {"keys": [{**public, "kid": kid, "alg": "RS256", "use": "sig"}]}


def id_token(provider, nonce, key=RSA_KEY, kid="k1", **overrides):
    now = int(time.time())
    claims = {
        "iss": PROVIDERS[provider]["iss"],
        "aud": PROVIDERS[provider]["aud"],
        "sub": f"{provider}-subject-1",
        "iat": now,
        "exp": now + 600,
        "nonce": nonce,
    }
    if provider == "microsoft":
        claims["tid"] = TENANT
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


def start(client, provider):
    resp = client.get(f"/api/auth/sso/{provider}/login", follow_redirects=False)
    assert resp.status_code == 302, resp.text
    location = urlparse(resp.headers["location"])
    return {k: v[0] for k, v in parse_qs(location.query).items()}, location


def path_of(url):
    parsed = urlparse(url)
    return f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path


def sign_in(client, provider, token_kwargs=None, *, callback_extra=None, token_response=None, method=None):
    """Runs the whole round trip; returns the final redirect's location."""
    params, _ = start(client, provider)
    token = id_token(provider, params["nonce"], **(token_kwargs or {}))
    with respx.mock(assert_all_called=False) as idp:
        token_route = idp.post(PROVIDERS[provider]["token"]).mock(
            return_value=token_response or Response(200, json={"id_token": token})
        )
        idp.get(PROVIDERS[provider]["jwks"]).mock(return_value=Response(200, json=jwks()))
        query = {"code": "the-code", "state": params["state"], **(callback_extra or {})}
        method = method or ("post" if provider == "apple" else "get")
        if method == "post":
            resp = client.post(
                f"/api/auth/sso/{provider}/callback",
                content="&".join(f"{k}={v}" for k, v in query.items()),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                follow_redirects=False,
            )
        else:
            resp = client.get(f"/api/auth/sso/{provider}/callback", params=query, follow_redirects=False)
    sign_in.token_route = token_route
    assert resp.status_code == 303, resp.text
    location = resp.headers["location"]
    if "/api/auth/sso/finish" in location:
        finished = client.get(path_of(location), follow_redirects=False)
        assert finished.status_code == 303
        return finished.headers["location"]
    return location


def signed_in_as(client):
    resp = client.get("/api/auth/me")
    return resp.json()["username"] if resp.status_code == 200 else None


# ---- what's offered ----

def test_only_fully_configured_providers_are_offered(anon_client, monkeypatch):
    assert [p["id"] for p in anon_client.get("/api/auth/sso/providers").json()["providers"]] == ["google", "microsoft", "apple"]
    monkeypatch.setattr(settings, "apple_key_id", None)
    monkeypatch.setattr(settings, "microsoft_client_secret", "")
    assert anon_client.get("/api/auth/sso/providers").json() == {"organization": None, "providers": [{"id": "google", "label": "Google"}]}


def test_nothing_is_offered_without_a_public_url(anon_client, monkeypatch):
    monkeypatch.setattr(settings, "public_url", None)
    assert anon_client.get("/api/auth/sso/providers").json()["providers"] == []


def test_an_unconfigured_provider_bounces_back_to_the_app(anon_client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", None)
    resp = anon_client.get("/api/auth/sso/google/login", follow_redirects=False)
    assert resp.headers["location"] == f"{APP}/?sso_error=unavailable"


# ---- the outbound redirect ----

def test_login_sends_state_nonce_and_pkce_to_google(anon_client):
    params, location = start(anon_client, "google")
    assert location.netloc == "accounts.google.com"
    assert params["client_id"] == "google-client"
    assert params["redirect_uri"] == f"{APP}/api/auth/sso/google/callback"
    assert params["scope"] == "openid email profile"
    assert params["code_challenge_method"] == "S256"
    assert len(params["state"]) >= 32 and len(params["nonce"]) >= 32
    assert "devnotepad_sso" in anon_client.cookies


def test_apple_is_asked_to_post_back(anon_client):
    params, location = start(anon_client, "apple")
    assert location.netloc == "appleid.apple.com"
    assert params["response_mode"] == "form_post"
    assert params["scope"] == "name email"
    assert "code_challenge" not in params


def test_callback_urls_follow_the_api_url_when_it_differs(anon_client, monkeypatch):
    monkeypatch.setattr(settings, "public_api_url", "http://localhost:8010/")
    params, _ = start(anon_client, "google")
    assert params["redirect_uri"] == "http://localhost:8010/api/auth/sso/google/callback"


# ---- signing in ----

@pytest.mark.parametrize("provider", ["google", "microsoft", "apple"])
def test_a_new_person_gets_an_account_and_a_session(anon_client, session, provider):
    location = sign_in(anon_client, provider, {"email": f"New.Person@{provider}.example", "email_verified": True})
    assert location == f"{APP}/"
    assert signed_in_as(anon_client) == "new.person"

    user = session.exec(select(User).where(User.username == "new.person")).one()
    assert user.email == f"new.person@{provider}.example"
    link = session.exec(select(SsoIdentity)).one()
    assert (link.provider, link.subject, link.user_id) == (f"{provider}:{PROVIDERS[provider]['aud']}", f"{provider}-subject-1", user.id)


def test_returning_matches_on_the_provider_id_not_the_email(anon_client, session):
    sign_in(anon_client, "google", {"email": "first@example.com", "email_verified": True})
    anon_client.post("/api/auth/logout")
    sign_in(anon_client, "google", {"email": "changed@example.com", "email_verified": True})
    assert signed_in_as(anon_client) == "first"
    assert len(session.exec(select(User)).all()) == 1


def test_apple_leaving_out_the_email_on_a_later_sign_in_still_works(anon_client):
    sign_in(anon_client, "apple", {"email": "once@example.com", "email_verified": "true"})
    anon_client.post("/api/auth/logout")
    sign_in(anon_client, "apple", {})
    assert signed_in_as(anon_client) == "once"


def test_a_verified_email_links_to_an_existing_password_account(anon_client, user, session):
    sign_in(anon_client, "google", {"email": TEST_USER["email"].upper(), "email_verified": True})
    assert signed_in_as(anon_client) == TEST_USER["username"]
    assert session.exec(select(SsoIdentity)).one().user_id == user.id


@pytest.mark.parametrize(
    "provider,claims",
    [
        ("google", {"email_verified": False}),
        ("apple", {"email_verified": "false"}),  # Apple's string form
        ("google", {}),  # no claim at all is not a yes
        ("microsoft", {"email_verified": True}),  # Microsoft's never trusted
    ],
)
def test_an_unverified_email_never_unlocks_an_existing_account(anon_client, user, session, provider, claims):
    location = sign_in(anon_client, provider, {"email": TEST_USER["email"], **claims})
    assert location == f"{APP}/?sso_error=unverified"
    assert signed_in_as(anon_client) is None
    assert session.exec(select(SsoIdentity)).all() == []


def test_microsoft_email_falls_back_to_preferred_username_but_not_guest_ids(anon_client, session):
    sign_in(anon_client, "microsoft", {"preferred_username": "worker@contoso.example"})
    assert signed_in_as(anon_client) == "worker"
    anon_client.post("/api/auth/logout")

    location = sign_in(
        anon_client, "microsoft", {"sub": "guest", "preferred_username": "a_gmail.com#EXT#@contoso.onmicrosoft.com"}
    )
    assert location == f"{APP}/?sso_error=no_email"


def test_registration_closed_refuses_new_people(anon_client, session, monkeypatch):
    monkeypatch.setattr(settings, "allow_registration", False)
    location = sign_in(anon_client, "google", {"email": "stranger@example.com", "email_verified": True})
    assert location == f"{APP}/?sso_error=closed"
    assert session.exec(select(User)).all() == []


def test_a_taken_username_gets_a_suffix(anon_client, user, session):
    sign_in(anon_client, "google", {"email": f"{TEST_USER['username']}@elsewhere.example", "email_verified": True})
    assert signed_in_as(anon_client) == f"{TEST_USER['username']}-2"


def test_awkward_local_parts_still_make_valid_usernames(anon_client):
    sign_in(anon_client, "google", {"email": "_x+tag@example.com", "email_verified": True})
    assert signed_in_as(anon_client) == "x-tag"


def test_an_sso_account_cannot_sign_in_with_a_password(anon_client, session):
    sign_in(anon_client, "google", {"email": "nopass@example.com", "email_verified": True})
    user = session.exec(select(User).where(User.username == "nopass")).one()
    assert verify_password("", user.password_hash) is False
    anon_client.post("/api/auth/logout")
    for guess in ("", "x"):
        resp = anon_client.post("/api/auth/login", json={"identifier": "nopass", "password": guess})
        assert resp.status_code == 401


# ---- what must be refused ----

def test_the_person_cancelling_comes_back_as_denied(anon_client):
    location = sign_in(anon_client, "google", {}, callback_extra={"error": "access_denied"})
    assert location == f"{APP}/?sso_error=denied"
    assert sign_in.token_route.called is False


def test_state_is_single_use(anon_client):
    params, _ = start(anon_client, "google")
    token = id_token("google", params["nonce"], email="a@example.com", email_verified=True)
    with respx.mock(assert_all_called=False) as idp:
        idp.post(PROVIDERS["google"]["token"]).mock(return_value=Response(200, json={"id_token": token}))
        idp.get(PROVIDERS["google"]["jwks"]).mock(return_value=Response(200, json=jwks()))
        # The binding cookie is removed after the first use; put it back to
        # prove state alone refuses the replay.
        cookie = anon_client.cookies.get("devnotepad_sso")
        first = anon_client.get("/api/auth/sso/google/callback", params={"code": "c", "state": params["state"]}, follow_redirects=False)
        anon_client.cookies.set("devnotepad_sso", cookie, path="/api/auth/sso")
        second = anon_client.get("/api/auth/sso/google/callback", params={"code": "c", "state": params["state"]}, follow_redirects=False)
    assert "/api/auth/sso/finish" in first.headers["location"]
    assert second.headers["location"] == f"{APP}/?sso_error=expired"


def test_an_unknown_state_is_refused(anon_client):
    start(anon_client, "google")
    resp = anon_client.get("/api/auth/sso/google/callback", params={"code": "c", "state": "made-up"}, follow_redirects=False)
    assert resp.headers["location"] == f"{APP}/?sso_error=expired"


def test_a_callback_in_another_browser_is_refused(anon_client):
    """Login CSRF: an attacker starts a sign-in and sends someone the
    callback link, to sign that person's browser into the attacker's account."""
    params, _ = start(anon_client, "google")
    anon_client.cookies.clear()
    resp = anon_client.get("/api/auth/sso/google/callback", params={"code": "c", "state": params["state"]}, follow_redirects=False)
    assert resp.headers["location"] == f"{APP}/?sso_error=expired"


def test_state_for_one_provider_is_refused_by_another(anon_client):
    params, _ = start(anon_client, "google")
    resp = anon_client.get("/api/auth/sso/microsoft/callback", params={"code": "c", "state": params["state"]}, follow_redirects=False)
    assert resp.headers["location"] == f"{APP}/?sso_error=expired"


def test_a_stale_attempt_is_refused(anon_client, session):
    params, _ = start(anon_client, "google")
    attempt = session.get(SsoLoginAttempt, params["state"])
    attempt.created_at = attempt.created_at.replace(year=2000)
    session.add(attempt)
    session.commit()
    resp = anon_client.get("/api/auth/sso/google/callback", params={"code": "c", "state": params["state"]}, follow_redirects=False)
    assert resp.headers["location"] == f"{APP}/?sso_error=expired"


@pytest.mark.parametrize(
    "overrides",
    [
        {"nonce": "not-the-nonce"},
        {"aud": "someone-elses-client"},
        {"iss": "https://evil.example"},
        {"exp": 1000},
        {"key": OTHER_RSA_KEY},  # signed by a key the provider never published
        {"kid": "unknown-kid"},
    ],
)
def test_a_bad_id_token_is_refused(anon_client, session, overrides):
    params, _ = start(anon_client, "google")
    nonce = overrides.pop("nonce", params["nonce"])
    token = id_token("google", nonce, email="x@example.com", email_verified=True, **overrides)
    with respx.mock(assert_all_called=False) as idp:
        idp.post(PROVIDERS["google"]["token"]).mock(return_value=Response(200, json={"id_token": token}))
        idp.get(PROVIDERS["google"]["jwks"]).mock(return_value=Response(200, json=jwks()))
        resp = anon_client.get("/api/auth/sso/google/callback", params={"code": "c", "state": params["state"]}, follow_redirects=False)
    assert resp.headers["location"] == f"{APP}/?sso_error=provider"
    assert signed_in_as(anon_client) is None
    assert session.exec(select(User)).all() == []


def test_an_unsigned_token_is_refused(anon_client):
    params, _ = start(anon_client, "google")
    now = int(time.time())
    token = jwt.encode(
        {"iss": PROVIDERS["google"]["iss"], "aud": "google-client", "sub": "s", "iat": now, "exp": now + 600,
         "nonce": params["nonce"], "email": "x@example.com", "email_verified": True},
        key=None, algorithm="none",
    )
    with respx.mock(assert_all_called=False) as idp:
        idp.post(PROVIDERS["google"]["token"]).mock(return_value=Response(200, json={"id_token": token}))
        idp.get(PROVIDERS["google"]["jwks"]).mock(return_value=Response(200, json=jwks()))
        resp = anon_client.get("/api/auth/sso/google/callback", params={"code": "c", "state": params["state"]}, follow_redirects=False)
    assert resp.headers["location"] == f"{APP}/?sso_error=provider"


def test_a_refused_code_exchange_is_refused(anon_client):
    location = sign_in(anon_client, "google", {}, token_response=Response(400, json={"error": "invalid_grant"}))
    assert location == f"{APP}/?sso_error=provider"


@pytest.mark.parametrize(
    "tenant,tid,ok",
    [
        (TENANT, TENANT, True),
        (TENANT, "99999999-9999-9999-9999-999999999999", False),
        ("consumers", sso_module.MICROSOFT_CONSUMERS_TENANT, True),
        ("consumers", TENANT, False),
        ("organizations", sso_module.MICROSOFT_CONSUMERS_TENANT, False),
    ],
)
def test_microsoft_tenant_restrictions(anon_client, monkeypatch, tenant, tid, ok):
    monkeypatch.setattr(settings, "microsoft_tenant", tenant)
    PROVIDERS["microsoft"]["token"] = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    PROVIDERS["microsoft"]["jwks"] = f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
    try:
        location = sign_in(
            anon_client,
            "microsoft",
            {"tid": tid, "iss": f"https://login.microsoftonline.com/{tid}/v2.0", "email": "m@contoso.example"},
        )
    finally:
        PROVIDERS["microsoft"]["token"] = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        PROVIDERS["microsoft"]["jwks"] = "https://login.microsoftonline.com/common/discovery/v2.0/keys"
    assert (location == f"{APP}/") is ok, location


def test_microsoft_issuer_must_name_the_tokens_own_tenant(anon_client):
    location = sign_in(
        anon_client,
        "microsoft",
        {"iss": "https://login.microsoftonline.com/99999999-9999-9999-9999-999999999999/v2.0", "email": "m@x.example"},
    )
    assert location == f"{APP}/?sso_error=provider"


# ---- Apple's client secret, and the handover ----

def test_apple_authenticates_with_a_signed_client_secret(anon_client):
    sign_in(anon_client, "apple", {"email": "a@example.com", "email_verified": True})
    form = parse_qs(sign_in.token_route.calls.last.request.content.decode())
    secret = form["client_secret"][0]
    assert jwt.get_unverified_header(secret)["kid"] == "KEY1234567"
    claims = jwt.decode(secret, APPLE_KEY.public_key(), algorithms=["ES256"], audience="https://appleid.apple.com")
    assert claims["iss"] == "TEAM123456"
    assert claims["sub"] == "com.example.devnotepad"
    assert claims["exp"] - claims["iat"] <= 300
    assert "code_verifier" not in form


def test_google_exchanges_the_code_with_its_pkce_verifier(anon_client):
    sign_in(anon_client, "google", {"email": "p@example.com", "email_verified": True})
    form = parse_qs(sign_in.token_route.calls.last.request.content.decode())
    assert form["client_secret"] == ["google-secret"]
    assert form["redirect_uri"] == [f"{APP}/api/auth/sso/google/callback"]
    assert len(form["code_verifier"][0]) >= 43


def test_the_session_ticket_is_single_use(anon_client, session):
    params, _ = start(anon_client, "google")
    token = id_token("google", params["nonce"], email="t@example.com", email_verified=True)
    with respx.mock(assert_all_called=False) as idp:
        idp.post(PROVIDERS["google"]["token"]).mock(return_value=Response(200, json={"id_token": token}))
        idp.get(PROVIDERS["google"]["jwks"]).mock(return_value=Response(200, json=jwks()))
        resp = anon_client.get("/api/auth/sso/google/callback", params={"code": "c", "state": params["state"]}, follow_redirects=False)
    finish = path_of(resp.headers["location"])
    assert anon_client.get(finish, follow_redirects=False).headers["location"] == f"{APP}/"
    anon_client.post("/api/auth/logout")
    assert anon_client.get(finish, follow_redirects=False).headers["location"] == f"{APP}/?sso_error=expired"
    assert signed_in_as(anon_client) is None
    assert session.exec(select(SsoLoginAttempt)).all() == []


def test_signing_keys_are_refetched_when_the_provider_rotates_them(anon_client):
    params, _ = start(anon_client, "google")
    token = id_token("google", params["nonce"], kid="rotated", email="r@example.com", email_verified=True)
    with respx.mock(assert_all_called=False) as idp:
        idp.post(PROVIDERS["google"]["token"]).mock(return_value=Response(200, json={"id_token": token}))
        keys = idp.get(PROVIDERS["google"]["jwks"]).mock(
            side_effect=[Response(200, json=jwks(kid="old")), Response(200, json=jwks(kid="rotated"))]
        )
        resp = anon_client.get("/api/auth/sso/google/callback", params={"code": "c", "state": params["state"]}, follow_redirects=False)
    assert "/api/auth/sso/finish" in resp.headers["location"]
    assert keys.call_count == 2
