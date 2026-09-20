import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import select

from app.auth import hash_password
from app.config import settings
from app.main import app
from app.models import Dashboard, Membership, Organization, User
from app.orgs import ensure_in_main, get_main, migrate_to_organizations

PASSWORD = "a-good-password"


def orgs(c):
    return {o["name"]: o for o in c.get("/api/organizations").json()}


def active(c):
    return next(o for o in c.get("/api/organizations").json() if o["is_active"])


def board(c, name="b"):
    resp = c.post("/api/dashboards", json={"name": name, "repo_owner": "acme", "repo_name": "widgets"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def add(session, org_uuid, user, role="member"):
    from app.orgs import add_member  # noqa: PLC0415

    org = session.exec(select(Organization).where(Organization.uuid == org_uuid)).one()
    add_member(session, org, user, role)


# ---- main ----

def test_every_account_is_in_main(client):
    listed = client.get("/api/organizations").json()
    assert [(o["name"], o["is_main"], o["is_active"]) for o in listed] == [("Main", True, True)]


def test_a_registered_account_joins_main_as_a_plain_member(anon_client, user, session, monkeypatch):
    monkeypatch.setattr(settings, "allow_registration", True)
    resp = anon_client.post("/api/auth/register", json={"username": "newbie", "email": "n@example.com", "password": PASSWORD})
    assert resp.status_code == 201
    assert [(o["name"], o["role"]) for o in anon_client.get("/api/organizations").json()] == [("Main", "member")]


def test_nobody_leaves_or_is_removed_from_main(client, user, session, make_user):
    ensure_in_main(session, user, role="admin")
    other, _ = make_user("other")
    main = get_main(session)
    assert client.delete(f"/api/organizations/{main.uuid}/members/{other.id}").status_code == 409
    assert client.delete(f"/api/organizations/{main.uuid}/members/{user.id}").status_code == 409


# ---- creating and switching ----

def test_creating_makes_you_admin_and_moves_you_in(client):
    resp = client.post("/api/organizations", json={"name": "  Acme Tools  "})
    assert resp.status_code == 201
    created = resp.json()
    assert (created["name"], created["slug"], created["role"], created["is_active"]) == ("Acme Tools", "acme-tools", "admin", True)
    assert active(client)["name"] == "Acme Tools"


def test_slugs_are_unique_and_avoid_reserved_words(client):
    assert client.post("/api/organizations", json={"name": "Acme"}).json()["slug"] == "acme"
    assert client.post("/api/organizations", json={"name": "ACME!"}).json()["slug"] == "acme-2"
    assert client.post("/api/organizations", json={"name": "Admin"}).json()["slug"] == "admin-2"
    assert client.post("/api/organizations", json={"name": "日本"}).json()["slug"] == "org-2"


@pytest.mark.parametrize("name", ["", "   ", "x" * 81])
def test_a_bad_name_is_refused(client, name):
    assert client.post("/api/organizations", json={"name": name}).status_code == 422


def test_boards_belong_to_the_organisation_you_are_working_in(client, session):
    main_board = board(client, "in main")
    acme = client.post("/api/organizations", json={"name": "Acme"}).json()
    acme_board = board(client, "in acme")

    assert [b["name"] for b in client.get("/api/dashboards").json()] == ["in acme"]
    main = orgs(client)["Main"]
    client.post(f"/api/organizations/{main['id']}/switch")
    assert [b["name"] for b in client.get("/api/dashboards").json()] == ["in main"]

    rows = {d.uuid: d.organization_id for d in session.exec(select(Dashboard)).all()}
    acme_row = session.exec(select(Organization).where(Organization.uuid == acme["id"])).one()
    assert rows[acme_board["id"]] == acme_row.id
    assert rows[main_board["id"]] == get_main(session).id


def test_you_cannot_switch_into_an_organisation_you_are_not_in(client, make_user):
    _, stranger = make_user("stranger")
    theirs = stranger.post("/api/organizations", json={"name": "Private"}).json()
    assert client.post(f"/api/organizations/{theirs['id']}/switch").status_code == 404
    assert active(client)["name"] == "Main"


def test_opening_a_board_from_another_of_your_organisations_switches_to_it(client):
    acme = client.post("/api/organizations", json={"name": "Acme"}).json()
    acme_board = board(client)
    client.post(f"/api/organizations/{orgs(client)['Main']['id']}/switch")

    detail = client.get(f"/api/dashboards/{acme_board['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert (body["organization_id"], body["organization_name"], body["switched_organization"]) == (acme["id"], "Acme", True)
    assert active(client)["name"] == "Acme"
    assert client.get(f"/api/dashboards/{acme_board['id']}").json()["switched_organization"] is False


def test_the_session_organisation_is_forgotten_at_sign_in(anon_client, user, session):
    from tests.conftest import TEST_USER  # noqa: PLC0415

    creds = {"identifier": TEST_USER["username"], "password": TEST_USER["password"]}
    anon_client.post("/api/auth/login", json=creds)
    acme = anon_client.post("/api/organizations", json={"name": "Acme"}).json()
    anon_client.post(f"/api/organizations/{orgs(anon_client)['Main']['id']}/switch")
    anon_client.post("/api/auth/logout")

    # No default set: lands where it was last.
    anon_client.post("/api/auth/login", json=creds)
    assert active(anon_client)["name"] == "Main"

    # A default wins over the last one used.
    assert anon_client.put("/api/organizations/default", json={"organization_id": acme["id"]}).status_code == 204
    anon_client.post("/api/auth/logout")
    anon_client.post("/api/auth/login", json=creds)
    assert active(anon_client)["name"] == "Acme"
    assert orgs(anon_client)["Acme"]["is_default"] is True

    anon_client.put("/api/organizations/default", json={"organization_id": None})
    assert orgs(anon_client)["Acme"]["is_default"] is False


def test_a_default_must_be_an_organisation_you_are_in(client, make_user):
    _, stranger = make_user("stranger")
    theirs = stranger.post("/api/organizations", json={"name": "Private"}).json()
    assert client.put("/api/organizations/default", json={"organization_id": theirs["id"]}).status_code == 404


# ---- members and roles ----

def test_only_members_see_the_member_list(client, make_user, session):
    acme = client.post("/api/organizations", json={"name": "Acme"}).json()
    mate, mate_client = make_user("mate")
    _, stranger = make_user("stranger")
    add(session, acme["id"], mate)

    listed = mate_client.get(f"/api/organizations/{acme['id']}/members").json()
    assert [(m["username"], m["role"]) for m in listed] == [("mate", "member"), ("tester", "admin")]
    assert "email" not in listed[0]
    assert stranger.get(f"/api/organizations/{acme['id']}/members").status_code == 404


def test_only_admins_change_roles_rename_or_remove(client, make_user, session, user):
    acme = client.post("/api/organizations", json={"name": "Acme"}).json()
    mate, mate_client = make_user("mate")
    add(session, acme["id"], mate)
    base = f"/api/organizations/{acme['id']}"

    assert mate_client.patch(f"{base}/members/{user.id}", json={"role": "member"}).status_code == 403
    assert mate_client.patch(base, json={"name": "Mine now"}).status_code == 403
    assert mate_client.delete(f"{base}/members/{user.id}").status_code == 403

    assert client.patch(f"{base}/members/{mate.id}", json={"role": "admin"}).json()["role"] == "admin"
    assert client.patch(base, json={"name": "Acme Inc"}).json()["name"] == "Acme Inc"
    assert client.patch(f"{base}/members/{mate.id}", json={"role": "owner"}).status_code == 422


def test_the_last_admin_can_neither_step_down_nor_leave(client, user, make_user, session):
    acme = client.post("/api/organizations", json={"name": "Acme"}).json()
    base = f"/api/organizations/{acme['id']}"
    assert client.patch(f"{base}/members/{user.id}", json={"role": "member"}).status_code == 409
    assert client.delete(f"{base}/members/{user.id}").status_code == 409

    mate, _ = make_user("mate")
    add(session, acme["id"], mate, role="admin")
    assert client.delete(f"{base}/members/{user.id}").status_code == 204
    assert "Acme" not in orgs(client)


def test_a_member_can_leave(client, make_user, session):
    acme = client.post("/api/organizations", json={"name": "Acme"}).json()
    mate, mate_client = make_user("mate")
    add(session, acme["id"], mate)
    assert mate_client.delete(f"/api/organizations/{acme['id']}/members/{mate.id}").status_code == 204
    assert "Acme" not in orgs(mate_client)


def test_removal_hides_your_boards_there_and_re_adding_brings_them_back(client, make_user, session):
    acme = client.post("/api/organizations", json={"name": "Acme"}).json()
    mate, mate_client = make_user("mate")
    add(session, acme["id"], mate)
    mate_client.post(f"/api/organizations/{acme['id']}/switch")
    kept = board(mate_client, "kept")

    assert client.delete(f"/api/organizations/{acme['id']}/members/{mate.id}").status_code == 204
    # Soft: the membership row and the board both still exist.
    assert session.exec(select(Membership).where(Membership.user_id == mate.id, Membership.removed_at != None)).one()  # noqa: E711
    assert mate_client.get(f"/api/dashboards/{kept['id']}").status_code == 404
    assert mate_client.get(f"/api/dashboards/{kept['id']}/columns").status_code == 404
    # Their session was in Acme; it falls back to main rather than staying there.
    assert active(mate_client)["name"] == "Main"
    assert mate_client.get("/api/dashboards").json() == []

    add(session, acme["id"], mate)
    assert mate_client.get(f"/api/dashboards/{kept['id']}").status_code == 200


def test_a_removed_member_does_not_come_back_as_admin_by_accident(client, make_user, session):
    acme = client.post("/api/organizations", json={"name": "Acme"}).json()
    mate, _ = make_user("mate")
    add(session, acme["id"], mate, role="admin")
    client.delete(f"/api/organizations/{acme['id']}/members/{mate.id}")
    add(session, acme["id"], mate)  # re-added as a member
    roles = {m["username"]: m["role"] for m in client.get(f"/api/organizations/{acme['id']}/members").json()}
    assert roles["mate"] == "member"


def test_an_organisation_is_invisible_to_outsiders(client, make_user):
    acme = client.post("/api/organizations", json={"name": "Acme"}).json()
    _, stranger = make_user("stranger")
    base = f"/api/organizations/{acme['id']}"
    for method, path, body in [
        ("patch", base, {"name": "x"}),
        ("get", f"{base}/members", None),
        ("post", f"{base}/switch", None),
    ]:
        kwargs = {"json": body} if body else {}
        assert getattr(stranger, method)(path, **kwargs).status_code == 404


# ---- data from before organisations ----

def test_existing_accounts_and_boards_move_into_main(session):
    session.add(User(username="first", email="first@example.com", password_hash="x"))
    session.add(User(username="second", email="second@example.com", password_hash="x"))
    session.commit()
    session.execute(
        text(
            "INSERT INTO dashboard (uuid, name, repo_owner, repo_name, owner_id, created_at) "
            "VALUES ('u-1', 'old', 'acme', 'widgets', 1, CURRENT_TIMESTAMP)"
        )
    )
    session.commit()

    migrate_to_organizations(session)
    migrate_to_organizations(session)  # idempotent

    main = get_main(session)
    assert len(session.exec(select(Organization)).all()) == 1
    roles = {m.user_id: m.role for m in session.exec(select(Membership)).all()}
    first = session.exec(select(User).where(User.username == "first")).one()
    second = session.exec(select(User).where(User.username == "second")).one()
    assert roles == {first.id: "admin", second.id: "member"}
    assert session.exec(select(Dashboard)).one().organization_id == main.id


def test_the_first_account_created_from_env_runs_main(session, monkeypatch):
    from app.auth import seed_first_user  # noqa: PLC0415

    monkeypatch.setattr(settings, "admin_username", "boss")
    monkeypatch.setattr(settings, "admin_email", "boss@example.com")
    monkeypatch.setattr(settings, "admin_password", PASSWORD)
    seed_first_user(session)
    boss = session.exec(select(User).where(User.username == "boss")).one()
    row = session.exec(select(Membership).where(Membership.user_id == boss.id)).one()
    assert (row.organization_id, row.role) == (get_main(session).id, "admin")


def test_switch_to_refuses_an_organisation_you_are_not_in(session, user):
    """Both API routes check membership before switching; this keeps the
    helper itself from ever being the weak point for a future caller."""
    from fastapi import HTTPException, Response  # noqa: PLC0415

    from app.orgs import switch_to  # noqa: PLC0415

    other = Organization(slug="other", name="Other")
    session.add(other)
    session.commit()
    session.refresh(other)
    response = Response()
    with pytest.raises(HTTPException) as refused:
        switch_to(response, session, user, other)
    assert refused.value.status_code == 404
    assert "set-cookie" not in response.headers


def test_a_switch_survives_a_slower_request_that_started_before_it(client):
    """A board page fires several requests at once. With the organisation
    kept in the session cookie, whichever response landed last rewrote that
    cookie from the copy it read before the switch, undoing it."""
    client.post("/api/organizations", json={"name": "Acme"})
    acme_board = board(client)
    client.post(f"/api/organizations/{orgs(client)['Main']['id']}/switch")
    before = client.cookies.get("devnotepad_session")

    assert client.get(f"/api/dashboards/{acme_board['id']}").json()["switched_organization"] is True
    # The in-flight request's response arrives now, carrying the old session.
    client.cookies.set("devnotepad_session", before)

    assert active(client)["name"] == "Acme"


def test_signing_out_forgets_which_organisation_this_browser_was_in(client):
    client.post("/api/organizations", json={"name": "Acme"})
    assert "devnotepad_org" in client.cookies
    client.post("/api/auth/logout")
    assert "devnotepad_org" not in client.cookies


def test_a_forged_organisation_cookie_gets_nowhere(client, make_user):
    _, stranger = make_user("stranger")
    theirs = stranger.post("/api/organizations", json={"name": "Private"}).json()
    client.cookies.set("devnotepad_org", theirs["id"])
    assert active(client)["name"] == "Main"
    assert client.get("/api/dashboards").status_code == 200
