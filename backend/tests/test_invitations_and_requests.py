from datetime import timedelta

import pytest
from sqlmodel import select

from app.config import settings
from app.membership_flows import token_hash
from app.models import Invitation, JoinRequest, Membership, Notification, Organization

PASSWORD = "a-good-password"


def create_org(c, name="Acme"):
    resp = c.post("/api/organizations", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def invite(c, org, **body):
    resp = c.post(f"/api/organizations/{org['id']}/invitations", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def org_names(c):
    return sorted(o["name"] for o in c.get("/api/organizations").json())


def active(c):
    return next(o["name"] for o in c.get("/api/organizations").json() if o["is_active"])


def unread(c):
    return c.get("/api/notifications").json()


# ---- invitations ----

def test_an_admin_invites_and_the_link_joins_with_the_role_chosen(client, make_user):
    acme = create_org(client)
    created = invite(client, acme, role="admin", label="  for Mate  ")
    assert (created["role"], created["label"], created["status"]) == ("admin", "for Mate", "pending")

    mate, mate_client = make_user("mate")
    preview = mate_client.get(f"/api/invitations/{created['token']}").json()
    assert preview == {"organization_name": "Acme", "role": "admin", "status": "pending"}

    accepted = mate_client.post(f"/api/invitations/{created['token']}/accept").json()
    assert (accepted["organization_name"], accepted["already_member"]) == ("Acme", False)
    assert org_names(mate_client) == ["Acme", "Main"]
    assert active(mate_client) == "Acme"  # moved straight in
    roles = {m["username"]: m["role"] for m in client.get(f"/api/organizations/{acme['id']}/members").json()}
    assert roles["mate"] == "admin"


def test_the_token_is_shown_once_and_only_its_hash_is_stored(client, session):
    acme = create_org(client)
    created = invite(client, acme)
    row = session.exec(select(Invitation)).one()
    assert row.token_hash == token_hash(created["token"])
    assert created["token"] not in row.token_hash
    listed = client.get(f"/api/organizations/{acme['id']}/invitations").json()
    assert "token" not in listed[0]


def test_an_invitation_works_once(client, make_user):
    acme = create_org(client)
    token = invite(client, acme)["token"]
    _, first = make_user("first")
    _, second = make_user("second")
    assert first.post(f"/api/invitations/{token}/accept").status_code == 200
    refused = second.post(f"/api/invitations/{token}/accept")
    assert refused.status_code == 410
    assert "already been used" in refused.json()["detail"]
    assert org_names(second) == ["Main"]
    listed = client.get(f"/api/organizations/{acme['id']}/invitations").json()
    assert (listed[0]["status"], listed[0]["accepted_by"]) == ("accepted", "first")


def test_a_member_opening_the_link_does_not_use_it_up(client, make_user):
    acme = create_org(client)
    token = invite(client, acme)["token"]
    assert client.post(f"/api/invitations/{token}/accept").json()["already_member"] is True
    _, mate = make_user("mate")
    assert mate.post(f"/api/invitations/{token}/accept").status_code == 200


def test_an_expired_invitation_is_refused(client, make_user, session):
    acme = create_org(client)
    token = invite(client, acme)["token"]
    row = session.exec(select(Invitation)).one()
    row.expires_at = row.expires_at - timedelta(days=8)
    session.add(row)
    session.commit()
    _, mate = make_user("mate")
    assert mate.get(f"/api/invitations/{token}").json()["status"] == "expired"
    assert mate.post(f"/api/invitations/{token}/accept").status_code == 410


def test_a_revoked_invitation_is_refused(client, make_user):
    acme = create_org(client)
    created = invite(client, acme)
    assert client.delete(f"/api/organizations/{acme['id']}/invitations/{created['id']}").status_code == 204
    _, mate = make_user("mate")
    assert mate.post(f"/api/invitations/{created['token']}/accept").status_code == 410


def test_an_unknown_token_is_a_404(anon_client):
    assert anon_client.get("/api/invitations/not-a-real-token").status_code == 404


def test_previewing_needs_no_account_but_accepting_does(client, anon_client):
    token = invite(client, create_org(client))["token"]
    anon_client.cookies.clear()
    assert anon_client.get(f"/api/invitations/{token}").status_code == 200


def test_accepting_needs_a_session(client, session):
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.main import app  # noqa: PLC0415

    token = invite(client, create_org(client))["token"]
    assert TestClient(app).post(f"/api/invitations/{token}/accept").status_code == 401


def test_only_admins_manage_invitations(client, make_user, session):
    acme = create_org(client)
    created = invite(client, acme)
    mate, mate_client = make_user("mate")
    mate_client.post(f"/api/invitations/{invite(client, acme)['token']}/accept")
    base = f"/api/organizations/{acme['id']}/invitations"
    assert mate_client.post(base, json={}).status_code == 403
    assert mate_client.get(base).status_code == 403
    assert mate_client.delete(f"{base}/{created['id']}").status_code == 403

    _, stranger = make_user("stranger")
    assert stranger.get(base).status_code == 404


def test_an_invitation_cannot_be_revoked_through_another_organisation(client):
    acme = create_org(client, "Acme")
    other = create_org(client, "Other")
    created = invite(client, acme)
    assert client.delete(f"/api/organizations/{other['id']}/invitations/{created['id']}").status_code == 404
    assert client.get(f"/api/invitations/{created['token']}").json()["status"] == "pending"


@pytest.mark.parametrize("body", [{"role": "owner"}, {"label": "x" * 81}])
def test_bad_invitation_details_are_refused(client, body):
    acme = create_org(client)
    assert client.post(f"/api/organizations/{acme['id']}/invitations", json=body).status_code == 422


def test_rejoining_through_an_invitation_restores_a_removed_member(client, make_user, session):
    acme = create_org(client)
    mate, mate_client = make_user("mate")
    mate_client.post(f"/api/invitations/{invite(client, acme)['token']}/accept")
    board = mate_client.post("/api/dashboards", json={"name": "kept", "repo_owner": "a", "repo_name": "b"}).json()
    client.delete(f"/api/organizations/{acme['id']}/members/{mate.id}")
    assert mate_client.get(f"/api/dashboards/{board['id']}").status_code == 404

    mate_client.post(f"/api/invitations/{invite(client, acme)['token']}/accept")
    assert mate_client.get(f"/api/dashboards/{board['id']}").status_code == 200
    assert len(session.exec(select(Membership).where(Membership.user_id == mate.id)).all()) == 2  # main + acme, one row each


def test_the_inviter_hears_when_their_invitation_is_used(client, make_user):
    acme = create_org(client)
    _, mate = make_user("mate")
    mate.post(f"/api/invitations/{invite(client, acme)['token']}/accept")
    feed = unread(client)
    assert feed["unread"] == 1
    item = feed["items"][0]
    assert (item["kind"], item["organization_name"], item["actor"], item["read"]) == ("invitation_accepted", "Acme", "mate", False)


# ---- registering from an invitation ----

def test_registering_from_an_invitation_joins_and_moves_in(client, anon_client, monkeypatch):
    acme = create_org(client)
    token = invite(client, acme)["token"]
    client.post("/api/auth/logout")

    monkeypatch.setattr(settings, "allow_registration", True)
    resp = anon_client.post(
        "/api/auth/register",
        json={"username": "invited", "email": "invited@example.com", "password": PASSWORD, "invitation_token": token},
    )
    assert resp.status_code == 201, resp.text
    assert org_names(anon_client) == ["Acme", "Main"]
    assert active(anon_client) == "Acme"


def test_an_invitation_lets_someone_register_while_registration_is_closed(client, anon_client, monkeypatch):
    token = invite(client, create_org(client))["token"]
    client.post("/api/auth/logout")
    monkeypatch.setattr(settings, "allow_registration", False)

    without = anon_client.post("/api/auth/register", json={"username": "nope", "email": "nope@example.com", "password": PASSWORD})
    assert without.status_code == 403
    with_it = anon_client.post(
        "/api/auth/register",
        json={"username": "invited", "email": "invited@example.com", "password": PASSWORD, "invitation_token": token},
    )
    assert with_it.status_code == 201


def test_a_dead_invitation_registers_nobody(client, anon_client, session, monkeypatch):
    acme = create_org(client)
    created = invite(client, acme)
    client.delete(f"/api/organizations/{acme['id']}/invitations/{created['id']}")
    client.post("/api/auth/logout")
    monkeypatch.setattr(settings, "allow_registration", True)

    resp = anon_client.post(
        "/api/auth/register",
        json={"username": "late", "email": "late@example.com", "password": PASSWORD, "invitation_token": created["token"]},
    )
    assert resp.status_code == 410
    from app.models import User  # noqa: PLC0415

    assert session.exec(select(User).where(User.username == "late")).first() is None


# ---- join requests ----

def test_asking_to_join_notifies_every_admin(client, make_user, session):
    acme = create_org(client)
    co_admin, co_client = make_user("coadmin")
    co_client.post(f"/api/invitations/{invite(client, acme, role='admin')['token']}/accept")
    client.post("/api/notifications/read", json={})

    _, asker = make_user("asker")
    looked = asker.get(f"/api/organizations/by-slug/{acme['slug']}").json()
    assert (looked["name"], looked["is_member"], looked["request_status"]) == ("Acme", False, None)

    resp = asker.post(f"/api/organizations/by-slug/{acme['slug']}/join-requests")
    assert resp.status_code == 201
    assert (resp.json()["username"], resp.json()["status"]) == ("asker", "pending")
    for admin in (client, co_client):
        item = unread(admin)["items"][0]
        assert (item["kind"], item["actor"], item["organization_name"]) == ("join_request", "asker", "Acme")
    assert asker.get(f"/api/organizations/by-slug/{acme['slug']}").json()["request_status"] == "pending"


def test_asking_twice_keeps_one_request_and_one_round_of_notifications(client, make_user, session):
    acme = create_org(client)
    _, asker = make_user("asker")
    first = asker.post(f"/api/organizations/by-slug/{acme['slug']}/join-requests").json()
    second = asker.post(f"/api/organizations/by-slug/{acme['slug']}/join-requests").json()
    assert first["id"] == second["id"]
    assert len(session.exec(select(JoinRequest)).all()) == 1
    assert unread(client)["unread"] == 1


def test_members_and_main_cannot_be_asked_to_join(client, make_user):
    acme = create_org(client)
    assert client.post(f"/api/organizations/by-slug/{acme['slug']}/join-requests").status_code == 409
    _, asker = make_user("asker")
    asker.get("/api/organizations")  # main exists from startup in a real instance
    assert asker.post("/api/organizations/by-slug/main/join-requests").status_code == 409
    assert asker.post("/api/organizations/by-slug/no-such-org/join-requests").status_code == 404


def test_approving_adds_the_member_and_tells_them(client, make_user):
    acme = create_org(client)
    asker_row, asker = make_user("asker")
    request_id = asker.post(f"/api/organizations/by-slug/{acme['slug']}/join-requests").json()["id"]

    listed = client.get(f"/api/organizations/{acme['id']}/join-requests").json()
    assert [r["username"] for r in listed] == ["asker"]
    decided = client.post(f"/api/organizations/{acme['id']}/join-requests/{request_id}/approve", json={"role": "member"})
    assert decided.json()["status"] == "approved"

    assert org_names(asker) == ["Acme", "Main"]
    assert unread(asker)["items"][0]["kind"] == "join_approved"
    assert client.get(f"/api/organizations/{acme['id']}/join-requests").json() == []
    assert client.post(f"/api/organizations/{acme['id']}/join-requests/{request_id}/decline").status_code == 409


def test_declining_tells_them_and_holds_off_repeat_requests(client, make_user, session):
    acme = create_org(client)
    _, asker = make_user("asker")
    request_id = asker.post(f"/api/organizations/by-slug/{acme['slug']}/join-requests").json()["id"]
    assert client.post(f"/api/organizations/{acme['id']}/join-requests/{request_id}/decline").json()["status"] == "declined"
    assert org_names(asker) == ["Main"]
    assert unread(asker)["items"][0]["kind"] == "join_declined"

    assert asker.post(f"/api/organizations/by-slug/{acme['slug']}/join-requests").status_code == 429

    row = session.exec(select(JoinRequest)).one()
    row.decided_at = row.decided_at - timedelta(days=8)
    session.add(row)
    session.commit()
    assert asker.post(f"/api/organizations/by-slug/{acme['slug']}/join-requests").status_code == 201


def test_only_admins_decide(client, make_user):
    acme = create_org(client)
    _, member = make_user("member")
    member.post(f"/api/invitations/{invite(client, acme)['token']}/accept")
    _, asker = make_user("asker")
    request_id = asker.post(f"/api/organizations/by-slug/{acme['slug']}/join-requests").json()["id"]
    base = f"/api/organizations/{acme['id']}/join-requests"
    assert member.get(base).status_code == 403
    assert member.post(f"{base}/{request_id}/approve", json={}).status_code == 403
    # Nor can the asker approve themselves.
    assert asker.post(f"{base}/{request_id}/approve", json={}).status_code == 404
    assert org_names(asker) == ["Main"]


def test_a_request_cannot_be_decided_through_another_organisation(client, make_user):
    acme = create_org(client, "Acme")
    mine = create_org(client, "Mine")
    _, asker = make_user("asker")
    request_id = asker.post(f"/api/organizations/by-slug/{acme['slug']}/join-requests").json()["id"]
    resp = client.post(f"/api/organizations/{mine['id']}/join-requests/{request_id}/approve", json={})
    assert resp.status_code == 404
    assert org_names(asker) == ["Main"]


def test_approving_someone_who_already_joined_another_way_is_harmless(client, make_user, session):
    acme = create_org(client)
    asker_row, asker = make_user("asker")
    request_id = asker.post(f"/api/organizations/by-slug/{acme['slug']}/join-requests").json()["id"]
    asker.post(f"/api/invitations/{invite(client, acme, role='admin')['token']}/accept")
    client.post(f"/api/organizations/{acme['id']}/join-requests/{request_id}/approve", json={"role": "member"})
    row = session.exec(
        select(Membership)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(Membership.user_id == asker_row.id, Organization.is_main == False)  # noqa: E712
    ).one()
    assert row.role == "admin"  # not downgraded by the late approval


# ---- notifications ----

def test_notifications_are_private_and_marking_read_is_too(client, make_user, session):
    acme = create_org(client)
    _, asker = make_user("asker")
    asker.post(f"/api/organizations/by-slug/{acme['slug']}/join-requests")
    theirs = session.exec(select(Notification)).one()

    assert asker.get("/api/notifications").json() == {"unread": 0, "items": []}
    asker.post("/api/notifications/read", json={"ids": [theirs.id]})
    assert unread(client)["unread"] == 1

    client.post("/api/notifications/read", json={"ids": [theirs.id]})
    feed = unread(client)
    assert (feed["unread"], feed["items"][0]["read"]) == (0, True)


def test_mark_all_read(client, make_user):
    acme = create_org(client)
    for name in ("a1", "a2"):
        _, asker = make_user(name)
        asker.post(f"/api/organizations/by-slug/{acme['slug']}/join-requests")
    assert unread(client)["unread"] == 2
    assert client.post("/api/notifications/read", json={}).status_code == 204
    assert unread(client)["unread"] == 0


def test_reserved_words_never_become_slugs(client):
    assert client.post("/api/organizations", json={"name": "Members"}).json()["slug"] == "members-2"
    assert client.post("/api/organizations", json={"name": "By Slug"}).json()["slug"] == "by-slug-2"
