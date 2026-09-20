"""Identity providers configured per organisation, and where someone signing
in through an organisation's link ends up."""

import io
import json
from urllib.parse import parse_qs, urlparse

import pytest
import respx
from httpx import Response
from sqlalchemy import text
from sqlmodel import select

from app.config import settings
from app.models import JoinRequest, Membership, Organization, SsoIdentity, SsoProvider, User
from app.orgs import add_member, get_main
from tests.test_sso import APP, PROVIDERS, id_token, jwks, path_of, signed_in_as

GOOGLE = {"enabled": True, "client_id": "org-google-client", "client_secret": "org-google-secret"}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for name, value in {
        "public_url": APP,
        "public_api_url": None,
        "allow_registration": True,
        "google_client_id": None,
        "google_client_secret": None,
        "microsoft_client_id": None,
        "microsoft_client_secret": None,
        "apple_client_id": None,
        "apple_team_id": None,
        "apple_key_id": None,
        "apple_private_key": None,
    }.items():
        monkeypatch.setattr(settings, name, value)
    from app import sso as sso_module  # noqa: PLC0415

    sso_module._jwks_cache.clear()


@pytest.fixture()
def acme(client):
    return client.post("/api/organizations", json={"name": "Acme"}).json()


def configure(c, org, provider="google", **body):
    resp = c.put(f"/api/organizations/{org['id']}/sso/{provider}", json={**GOOGLE, **body})
    assert resp.status_code == 200, resp.text
    return resp.json()


def sso_round_trip(c, org_slug, claims, provider="google", client_id="org-google-client"):
    query = f"?org={org_slug}" if org_slug else ""
    start = c.get(f"/api/auth/sso/{provider}/login{query}", follow_redirects=False)
    assert start.status_code == 302, start.headers.get("location")
    params = {k: v[0] for k, v in parse_qs(urlparse(start.headers["location"]).query).items()}
    assert params["client_id"] == client_id
    token = id_token(provider, params["nonce"], aud=client_id, **claims)
    with respx.mock(assert_all_called=False) as idp:
        idp.post(PROVIDERS[provider]["token"]).mock(return_value=Response(200, json={"id_token": token}))
        idp.get(PROVIDERS[provider]["jwks"]).mock(return_value=Response(200, json=jwks()))
        back = c.get(f"/api/auth/sso/{provider}/callback", params={"code": "c", "state": params["state"]}, follow_redirects=False)
    location = back.headers["location"]
    if "/api/auth/sso/finish" in location:
        return c.get(path_of(location), follow_redirects=False).headers["location"]
    return location


def fresh_browser():
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.main import app  # noqa: PLC0415

    return TestClient(app)


def active_org(c):
    return next(o["name"] for o in c.get("/api/organizations").json() if o["is_active"])


# ---- configuring ----

def test_an_admin_sees_every_provider_type_with_its_callback_url(client, acme):
    body = client.get(f"/api/organizations/{acme['id']}/sso").json()
    assert body["public_url_set"] is True
    assert body["login_url"] == f"{APP}/o/acme"
    assert [(p["type"], p["configured"], p["callback_url"]) for p in body["providers"]] == [
        ("google", False, f"{APP}/api/auth/sso/google/callback"),
        ("microsoft", False, f"{APP}/api/auth/sso/microsoft/callback"),
        ("apple", False, f"{APP}/api/auth/sso/apple/callback"),
    ]


def test_saving_keeps_the_secret_write_only_and_encrypted(client, acme, session):
    body = configure(client, acme, auto_join_domains=[" Acme.example ", "@team.example"])
    google = body["providers"][0]
    assert (google["enabled"], google["ready"], google["has_secret"], google["auto_join_domains"]) == (
        True, True, True, ["acme.example", "team.example"]
    )
    assert "org-google-secret" not in json.dumps(body)
    stored = session.execute(text("SELECT client_secret FROM ssoprovider")).scalar_one()
    assert stored.startswith("enc.v1.") and "org-google-secret" not in stored

    # Saving again without a secret keeps the one already saved.
    kept = client.put(
        f"/api/organizations/{acme['id']}/sso/google", json={"enabled": True, "client_id": "org-google-client"}
    ).json()
    assert kept["providers"][0]["has_secret"] is True


def test_a_provider_cannot_be_switched_on_half_configured(client, acme):
    resp = client.put(f"/api/organizations/{acme['id']}/sso/google", json={"enabled": True, "client_id": "x"})
    assert resp.status_code == 422
    apple = client.put(
        f"/api/organizations/{acme['id']}/sso/apple",
        json={"enabled": True, "client_id": "com.example", "client_secret": "key"},
    )
    assert apple.status_code == 422 and "Team ID" in apple.json()["detail"]
    # Saving it switched off is fine.
    assert client.put(f"/api/organizations/{acme['id']}/sso/google", json={"enabled": False, "client_id": "x"}).status_code == 200


def test_only_the_organisations_admins_configure_it(client, acme, make_user, session):
    mate, mate_client = make_user("mate")
    add_member(session, session.exec(select(Organization).where(Organization.uuid == acme["id"])).one(), mate)
    _, stranger = make_user("stranger")
    base = f"/api/organizations/{acme['id']}/sso"
    assert mate_client.get(base).status_code == 403
    assert mate_client.put(f"{base}/google", json=GOOGLE).status_code == 403
    assert stranger.get(base).status_code == 404
    assert client.put(f"{base}/github", json=GOOGLE).status_code == 404


def test_removing_a_provider(client, acme):
    configure(client, acme)
    assert client.delete(f"/api/organizations/{acme['id']}/sso/google").status_code == 204
    assert client.get(f"/api/organizations/{acme['id']}/sso").json()["providers"][0]["configured"] is False


# ---- what a sign-in page offers ----

def test_an_organisations_link_offers_its_own_providers(client, acme, anon_client):
    configure(client, acme)
    browser = fresh_browser()
    assert browser.get("/api/auth/sso/providers?org=acme").json() == {
        "organization": {"name": "Acme", "slug": "acme"},
        "providers": [{"id": "google", "label": "Google"}],
    }
    # The plain sign-in page shows main's, which has none.
    assert browser.get("/api/auth/sso/providers").json() == {"organization": None, "providers": []}
    assert browser.get("/api/auth/sso/providers?org=nope").status_code == 404


def test_disabled_providers_are_not_offered(client, acme):
    configure(client, acme, enabled=False)
    assert fresh_browser().get("/api/auth/sso/providers?org=acme").json()["providers"] == []


def test_main_uses_env_only_until_it_saves_a_provider(client, session, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "env-client")
    monkeypatch.setattr(settings, "google_client_secret", "env-secret")
    browser = fresh_browser()
    assert [p["id"] for p in browser.get("/api/auth/sso/providers").json()["providers"]] == ["google"]

    main = get_main(session)
    client.get("/api/organizations")  # tester is main's member; make them its admin for this
    row = session.exec(select(Membership).where(Membership.organization_id == main.id)).first()
    row.role = "admin"
    session.add(row)
    session.commit()
    client.put(
        f"/api/organizations/{main.uuid}/sso/apple",
        json={"enabled": False, "client_id": "com.example"},
    )
    # A saved (even disabled) provider means the database is now the whole story.
    assert browser.get("/api/auth/sso/providers").json()["providers"] == []


# ---- landing ----

def test_a_member_signing_in_through_the_link_lands_in_the_organisation(client, acme, session, make_user):
    configure(client, acme)
    mate, _ = make_user("mate")
    add_member(session, session.exec(select(Organization).where(Organization.uuid == acme["id"])).one(), mate)

    browser = fresh_browser()
    location = sso_round_trip(browser, "acme", {"email": "mate@example.com", "email_verified": True})
    assert location == f"{APP}/"
    assert signed_in_as(browser) == "mate"
    assert active_org(browser) == "Acme"


def test_anyone_else_lands_in_main_with_a_join_request(client, acme, session):
    configure(client, acme)
    browser = fresh_browser()
    location = sso_round_trip(browser, "acme", {"email": "newcomer@example.com", "email_verified": True})
    assert location == f"{APP}/?sso_notice=join_requested"
    assert signed_in_as(browser) == "newcomer"
    assert [o["name"] for o in browser.get("/api/organizations").json()] == ["Main"]
    request = session.exec(select(JoinRequest)).one()
    assert (request.via, request.status) == ("sso", "pending")
    assert client.get("/api/notifications").json()["items"][0]["kind"] == "join_request"


def test_signing_in_again_does_not_pile_up_requests(client, acme, session):
    configure(client, acme)
    for _ in range(2):
        browser = fresh_browser()
        sso_round_trip(browser, "acme", {"email": "newcomer@example.com", "email_verified": True})
    assert len(session.exec(select(JoinRequest)).all()) == 1


def test_verified_emails_on_auto_join_domains_join_straight_away(client, acme):
    configure(client, acme, auto_join_domains=["acme.example"])
    browser = fresh_browser()
    location = sso_round_trip(browser, "acme", {"email": "Worker@ACME.example", "email_verified": True})
    assert location == f"{APP}/"
    assert active_org(browser) == "Acme"


def test_an_unverified_email_never_auto_joins(client, acme, session):
    configure(client, acme, auto_join_domains=["acme.example"])
    browser = fresh_browser()
    location = sso_round_trip(browser, "acme", {"email": "worker@acme.example", "email_verified": False})
    assert location == f"{APP}/?sso_notice=join_requested"
    assert [o["name"] for o in browser.get("/api/organizations").json()] == ["Main"]


def test_organisation_sso_creates_no_account_while_registration_is_closed(client, acme, session, monkeypatch):
    configure(client, acme)
    monkeypatch.setattr(settings, "allow_registration", False)
    browser = fresh_browser()
    assert sso_round_trip(browser, "acme", {"email": "stranger@example.com", "email_verified": True}) == f"{APP}/?sso_error=closed"
    assert session.exec(select(User).where(User.email == "stranger@example.com")).first() is None


def test_disabling_a_provider_mid_sign_in_stops_it(client, acme):
    configure(client, acme)
    browser = fresh_browser()
    start = browser.get("/api/auth/sso/google/login?org=acme", follow_redirects=False)
    params = {k: v[0] for k, v in parse_qs(urlparse(start.headers["location"]).query).items()}
    client.put(f"/api/organizations/{acme['id']}/sso/google", json={**GOOGLE, "enabled": False})
    back = browser.get("/api/auth/sso/google/callback", params={"code": "c", "state": params["state"]}, follow_redirects=False)
    assert back.headers["location"] == f"{APP}/?sso_error=unavailable"


def test_the_same_client_in_env_and_database_keeps_identity_links(client, session, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "shared-client")
    monkeypatch.setattr(settings, "google_client_secret", "s")
    browser = fresh_browser()
    sso_round_trip(browser, None, {"email": "person@example.com", "email_verified": True}, client_id="shared-client")
    browser.post("/api/auth/logout")

    main = get_main(session)
    session.add(SsoProvider(organization_id=main.id, type="google", enabled=True, client_id="shared-client", client_secret="s"))
    session.commit()
    # A different email now: only the identity link can find the account.
    sso_round_trip(browser, None, {"email": "changed@example.com", "email_verified": False}, client_id="shared-client")
    assert signed_in_as(browser) == "person"
    assert len(session.exec(select(SsoIdentity)).all()) == 1


def test_identities_from_different_clients_never_meet(client, acme, session, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "main-client")
    monkeypatch.setattr(settings, "google_client_secret", "s")
    configure(client, acme)
    first = fresh_browser()
    sso_round_trip(first, None, {"sub": "same-sub", "email": "a@example.com", "email_verified": True}, client_id="main-client")
    second = fresh_browser()
    # Same subject from a different client, unverified email: no link to the first.
    location = sso_round_trip(second, "acme", {"sub": "same-sub", "email": "b@example.com", "email_verified": False})
    assert signed_in_as(second) == "b-user"
    assert location == f"{APP}/?sso_notice=join_requested"


def test_the_callback_path_names_the_type_the_attempt_started_with(client, acme):
    configure(client, acme)
    browser = fresh_browser()
    start = browser.get("/api/auth/sso/google/login?org=acme", follow_redirects=False)
    params = {k: v[0] for k, v in parse_qs(urlparse(start.headers["location"]).query).items()}
    back = browser.get("/api/auth/sso/apple/callback", params={"code": "c", "state": params["state"]}, follow_redirects=False)
    assert back.headers["location"] == f"{APP}/?sso_error=expired"


# ---- command line ----

@pytest.fixture()
def cli(session, monkeypatch):
    from app import cli as cli_module  # noqa: PLC0415

    monkeypatch.setattr(cli_module, "engine", session.get_bind())
    monkeypatch.setattr(cli_module, "init_db", lambda: None)

    def run(*argv, stdin=""):
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        out = io.StringIO()
        monkeypatch.setattr("sys.stdout", out)
        cli_module.main(list(argv))
        return out.getvalue()

    return run


def test_cli_imports_providers_without_printing_secrets(cli, session, user):
    payload = json.dumps([
        {"type": "google", "client_id": "cli-client", "client_secret": "cli-secret-value"},
        {"type": "apple", "client_id": "com.example", "client_secret": "-----BEGIN PRIVATE KEY-----x", "team_id": "T", "key_id": "K"},
    ])
    out = cli("sso", "import", "--org", "main", stdin=payload)
    assert "cli-secret-value" not in out and "PRIVATE KEY" not in out
    rows = {r.type: r for r in session.exec(select(SsoProvider)).all()}
    assert rows["google"].client_secret == "cli-secret-value" and rows["google"].enabled
    assert (rows["apple"].team_id, rows["apple"].key_id) == ("T", "K")
    listed = cli("sso", "list", "--org", "main")
    assert "cli-secret-value" not in listed and "secret=set" in listed


def test_cli_set_reads_the_secret_from_stdin_and_keeps_other_fields(cli, session, user):
    cli("sso", "set", "--type", "microsoft", "--client-id", "ms", "--client-secret-file", "-", "--tenant", "organizations", "--enable", stdin="ms-secret\n")
    cli("sso", "set", "--type", "microsoft", "--auto-join-domains", "acme.example")
    row = session.exec(select(SsoProvider)).one()
    assert (row.client_id, row.client_secret, row.tenant, row.enabled, row.auto_join_domains) == (
        "ms", "ms-secret", "organizations", True, "acme.example"
    )


def test_cli_promotes_and_demotes_instance_admins(cli, session, user):
    other = User(username="other", email="other@example.com", password_hash="x")
    session.add(other)
    session.commit()
    cli("admin", "promote", "other")
    main = get_main(session)
    roles = {m.user_id: m.role for m in session.exec(select(Membership).where(Membership.organization_id == main.id)).all()}
    assert roles[other.id] == "admin"
    cli("admin", "demote", "other")
    session.expire_all()
    roles = {m.user_id: m.role for m in session.exec(select(Membership).where(Membership.organization_id == main.id)).all()}
    assert roles[other.id] == "member"


def test_cli_creates_an_organisation(cli, session, user):
    out = cli("org", "create", "--name", "Tooling Team", "--admin", user.username)
    assert "tooling-team" in out
    org = session.exec(select(Organization).where(Organization.slug == "tooling-team")).one()
    row = session.exec(select(Membership).where(Membership.organization_id == org.id)).one()
    assert (row.user_id, row.role) == (user.id, "admin")


def test_a_sign_in_cannot_finish_under_credentials_it_did_not_start_with(client, session, monkeypatch):
    """Started with main's .env client; an admin saves a database provider
    before the person comes back. The attempt belongs to settings that no
    longer apply, so it stops rather than finishing under different ones."""
    monkeypatch.setattr(settings, "google_client_id", "env-client")
    monkeypatch.setattr(settings, "google_client_secret", "env-secret")
    browser = fresh_browser()
    start = browser.get("/api/auth/sso/google/login", follow_redirects=False)
    params = {k: v[0] for k, v in parse_qs(urlparse(start.headers["location"]).query).items()}

    main = get_main(session)
    session.add(SsoProvider(organization_id=main.id, type="google", enabled=True, client_id="db-client", client_secret="db-secret"))
    session.commit()

    with respx.mock(assert_all_called=False) as idp:
        token = idp.post(PROVIDERS["google"]["token"]).mock(return_value=Response(200, json={"id_token": "x"}))
        back = browser.get("/api/auth/sso/google/callback", params={"code": "c", "state": params["state"]}, follow_redirects=False)
    assert back.headers["location"] == f"{APP}/?sso_error=unavailable"
    assert not token.called


def test_losing_membership_before_finishing_lands_in_main(client, acme, session, make_user):
    configure(client, acme)
    mate, _ = make_user("mate")
    org = session.exec(select(Organization).where(Organization.uuid == acme["id"])).one()
    add_member(session, org, mate)

    browser = fresh_browser()
    start = browser.get("/api/auth/sso/google/login?org=acme", follow_redirects=False)
    params = {k: v[0] for k, v in parse_qs(urlparse(start.headers["location"]).query).items()}
    token = id_token("google", params["nonce"], aud="org-google-client", email="mate@example.com", email_verified=True)
    with respx.mock(assert_all_called=False) as idp:
        idp.post(PROVIDERS["google"]["token"]).mock(return_value=Response(200, json={"id_token": token}))
        idp.get(PROVIDERS["google"]["jwks"]).mock(return_value=Response(200, json=jwks()))
        back = browser.get("/api/auth/sso/google/callback", params={"code": "c", "state": params["state"]}, follow_redirects=False)

    # Removed in the moment between the provider's answer and the handover.
    client.delete(f"/api/organizations/{acme['id']}/members/{mate.id}")
    finished = browser.get(path_of(back.headers["location"]), follow_redirects=False)
    assert finished.status_code == 303
    assert finished.headers["location"] == f"{APP}/"
    assert signed_in_as(browser) == "mate"
    assert active_org(browser) == "Main"
