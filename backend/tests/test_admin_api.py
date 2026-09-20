from sqlmodel import select

from app.config import settings
from app.models import Membership, SsoIdentity
from app.orgs import get_main


def make_instance_admin(session, user):
    main = get_main(session)
    from app.orgs import ensure_in_main  # noqa: PLC0415

    ensure_in_main(session, user)
    row = session.exec(select(Membership).where(Membership.organization_id == main.id, Membership.user_id == user.id)).one()
    row.role = "admin"
    session.add(row)
    session.commit()


def test_only_instance_admins_see_the_admin_area(client, user, session, make_user):
    _, plain = make_user("plain")
    for path in ("/api/admin/overview", "/api/admin/users", "/api/admin/organizations"):
        assert plain.get(path).status_code == 403
    assert client.get("/api/auth/me").json()["is_instance_admin"] is False

    make_instance_admin(session, user)
    assert client.get("/api/auth/me").json()["is_instance_admin"] is True
    assert client.get("/api/admin/overview").status_code == 200


def test_an_admin_of_another_organisation_is_not_an_instance_admin(client, make_user):
    _, founder = make_user("founder")
    founder.post("/api/organizations", json={"name": "Their Own"})
    assert founder.get("/api/admin/users").status_code == 403
    assert founder.get("/api/auth/me").json()["is_instance_admin"] is False


def test_overview_counts(client, user, session, make_user, monkeypatch):
    make_instance_admin(session, user)
    monkeypatch.setattr(settings, "allow_registration", True)
    make_user("second")
    client.post("/api/organizations", json={"name": "Acme"})
    client.post("/api/dashboards", json={"name": "b", "repo_owner": "a", "repo_name": "b"})
    body = client.get("/api/admin/overview").json()
    assert (body["users"], body["organizations"], body["boards"], body["registration_open"]) == (2, 2, 1, True)
    assert body["main_organization_id"] == get_main(session).uuid


def test_users_list_shows_roles_and_sign_in_methods_but_no_secrets(client, user, session, make_user):
    make_instance_admin(session, user)
    other, _ = make_user("other")
    session.add(SsoIdentity(user_id=other.id, provider="google:some-client", subject="s", email="other@example.com"))
    session.commit()
    listed = {u["username"]: u for u in client.get("/api/admin/users").json()}
    assert listed["tester"]["is_instance_admin"] is True
    assert (listed["other"]["is_instance_admin"], listed["other"]["sso_providers"], listed["other"]["has_password"]) == (
        False, ["google"], True
    )
    text = client.get("/api/admin/users").text
    assert "password_hash" not in text and "$2b$" not in text and "some-client" not in text


def test_organisations_list(client, user, session, make_user):
    make_instance_admin(session, user)
    _, founder = make_user("founder")
    founder.post("/api/organizations", json={"name": "Their Own"})
    listed = {o["name"]: o for o in client.get("/api/admin/organizations").json()}
    assert listed["Main"]["is_main"] is True
    assert (listed["Their Own"]["created_by"], listed["Their Own"]["members"], listed["Their Own"]["admins"]) == ("founder", 1, 1)


def test_promoting_goes_through_mains_member_roles(client, user, session, make_user):
    make_instance_admin(session, user)
    other, other_client = make_user("other")
    other_client.get("/api/organizations")
    main_id = client.get("/api/admin/overview").json()["main_organization_id"]
    assert client.patch(f"/api/organizations/{main_id}/members/{other.id}", json={"role": "admin"}).status_code == 200
    assert other_client.get("/api/admin/users").status_code == 200
    assert other_client.get("/api/auth/me").json()["is_instance_admin"] is True
