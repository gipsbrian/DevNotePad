"""Board sharing, organisation boards, private notes, and whose GitHub token
each read and write goes out with."""

import pytest
import respx
from httpx import Response
from sqlmodel import select

from app.access import read_token
from app.models import Dashboard, Membership, Organization
from app.orgs import add_member
from tests.conftest import GITHUB_API

BOARD = {"name": "b", "repo_owner": "acme", "repo_name": "widgets"}


@pytest.fixture()
def team(client, make_user, session, user):
    """`client` (tester) admins Acme; mate and other are members; outsider
    isn't in Acme at all. Everyone is working in Acme."""
    acme = client.post("/api/organizations", json={"name": "Acme"}).json()
    org = session.exec(select(Organization).where(Organization.uuid == acme["id"])).one()
    people = {}
    for name in ("mate", "other"):
        row, c = make_user(name)
        add_member(session, org, row)
        c.post(f"/api/organizations/{acme['id']}/switch")
        people[name] = (row, c)
    outsider = make_user("outsider")
    return {"org": acme, "admin": (user, client), **people, "outsider": outsider}


def boards_by_name(c):
    return {b["name"]: b for b in c.get("/api/dashboards").json()}


def personal(c, name="mine", **extra):
    resp = c.post("/api/dashboards", json={**BOARD, "name": name, **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---- organisation boards ----

def test_only_admins_create_organisation_boards(team):
    _, admin = team["admin"]
    _, mate = team["mate"]
    assert mate.post("/api/dashboards", json={**BOARD, "kind": "organization"}).status_code == 403
    created = admin.post("/api/dashboards", json={**BOARD, "name": "team", "kind": "organization"}).json()
    assert (created["kind"], created["access"]) == ("organization", "manage")
    assert admin.post("/api/dashboards", json={**BOARD, "kind": "company"}).status_code == 422


def test_every_member_sees_an_organisation_board_but_only_admins_manage_it(team):
    _, admin = team["admin"]
    _, mate = team["mate"]
    board = admin.post("/api/dashboards", json={**BOARD, "name": "team", "kind": "organization"}).json()

    seen = boards_by_name(mate)["team"]
    assert (seen["access"], seen["owner"]) == ("view", "tester")
    assert mate.get(f"/api/dashboards/{board['id']}").status_code == 200
    for method, suffix, body in [
        ("patch", "", {"name": "x"}),
        ("patch", "/appearance", {"accent_color": "#000000"}),
        ("post", "/columns", {"name": "x"}),
        ("delete", "", None),
    ]:
        kwargs = {"json": body} if body else {}
        assert getattr(mate, method)(f"/api/dashboards/{board['id']}{suffix}", **kwargs).status_code == 403
    assert admin.patch(f"/api/dashboards/{board['id']}", json={"name": "renamed"}).status_code == 200


def test_outsiders_never_see_organisation_boards(team):
    _, admin = team["admin"]
    _, outsider = team["outsider"]
    board = admin.post("/api/dashboards", json={**BOARD, "kind": "organization"}).json()
    assert outsider.get(f"/api/dashboards/{board['id']}").status_code == 404


# ---- sharing personal boards ----

def test_a_personal_board_is_private_until_shared(team):
    _, mate = team["mate"]
    _, other = team["other"]
    board = personal(mate)
    assert other.get(f"/api/dashboards/{board['id']}").status_code == 404
    assert "mine" not in boards_by_name(other)


def test_sharing_with_one_member_lets_only_them_view(team):
    mate_row, mate = team["mate"]
    other_row, other = team["other"]
    admin_row, admin = team["admin"]
    board = personal(mate)

    resp = mate.put(f"/api/dashboards/{board['id']}/sharing", json={"user_ids": [other_row.id]})
    assert resp.json() == {"shared_with_organization": False, "user_ids": [other_row.id]}
    assert boards_by_name(other)["mine"]["access"] == "view"
    assert boards_by_name(mate)["mine"]["is_shared"] is True
    # Admins get no special view of personal boards.
    assert admin.get(f"/api/dashboards/{board['id']}").status_code == 404

    mate.put(f"/api/dashboards/{board['id']}/sharing", json={"user_ids": []})
    assert other.get(f"/api/dashboards/{board['id']}").status_code == 404


def test_sharing_with_the_organisation_lets_every_member_view(team):
    _, mate = team["mate"]
    _, other = team["other"]
    _, admin = team["admin"]
    _, outsider = team["outsider"]
    board = personal(mate)
    mate.put(f"/api/dashboards/{board['id']}/sharing", json={"shared_with_organization": True})
    for c in (other, admin):
        assert c.get(f"/api/dashboards/{board['id']}").json()["access"] == "view"
    assert outsider.get(f"/api/dashboards/{board['id']}").status_code == 404


def test_a_viewer_cannot_change_or_reshare_a_shared_board(team):
    _, mate = team["mate"]
    other_row, other = team["other"]
    board = personal(mate)
    mate.put(f"/api/dashboards/{board['id']}/sharing", json={"user_ids": [other_row.id]})
    base = f"/api/dashboards/{board['id']}"
    assert other.patch(base, json={"name": "mine now"}).status_code == 403
    assert other.post(f"{base}/columns", json={"name": "x"}).status_code == 403
    assert other.put(f"{base}/sharing", json={"shared_with_organization": True}).status_code == 403
    assert other.get(f"{base}/sharing").status_code == 403
    assert other.delete(base).status_code == 403


def test_sharing_only_reaches_members_of_the_boards_organisation(team):
    _, mate = team["mate"]
    outsider_row, _ = team["outsider"]
    board = personal(mate)
    resp = mate.put(f"/api/dashboards/{board['id']}/sharing", json={"user_ids": [outsider_row.id]})
    assert resp.status_code == 422


def test_organisation_boards_have_no_sharing_controls(team):
    _, admin = team["admin"]
    board = admin.post("/api/dashboards", json={**BOARD, "kind": "organization"}).json()
    assert admin.get(f"/api/dashboards/{board['id']}/sharing").status_code == 409


def test_leaving_the_organisation_ends_access_to_what_was_shared(team, session):
    mate_row, mate = team["mate"]
    other_row, other = team["other"]
    _, admin = team["admin"]
    board = personal(mate)
    mate.put(f"/api/dashboards/{board['id']}/sharing", json={"user_ids": [other_row.id]})
    admin.delete(f"/api/organizations/{team['org']['id']}/members/{other_row.id}")
    base = f"/api/dashboards/{board['id']}"
    # Every way in, not just the board itself.
    for path in ("", "/columns", "/notes", "/sticky-notes", "/closed", "/issues/1"):
        assert other.get(f"{base}{path}").status_code == 404, path
    assert "mine" not in boards_by_name(other)


def test_viewers_see_no_token_details(team, session):
    _, mate = team["mate"]
    other_row, other = team["other"]
    board = personal(mate, token="ghp_mates_board_token")
    mate.put(f"/api/dashboards/{board['id']}/sharing", json={"user_ids": [other_row.id]})
    with respx.mock(assert_all_called=False) as github:
        github.route(host="api.github.com").mock(return_value=Response(200, json={}))
        viewed = other.get(f"/api/dashboards/{board['id']}").json()
    assert viewed["token_info"] is None
    assert viewed["has_own_token"] is False
    assert "ghp_" not in str(viewed)


# ---- whose token ----

def test_viewers_read_with_the_owners_token_but_cannot_write(team, session):
    mate_row, mate = team["mate"]
    other_row, other = team["other"]
    mate.put("/api/settings", json={"default_token": "ghp_mate"})
    other.put("/api/settings", json={"default_token": "ghp_other"})
    board = personal(mate)
    mate.put(f"/api/dashboards/{board['id']}/sharing", json={"user_ids": [other_row.id]})

    with respx.mock(assert_all_called=False) as github:
        issues = github.get(f"{GITHUB_API}/repos/acme/widgets/issues").mock(return_value=Response(200, json=[]))
        close = github.patch(f"{GITHUB_API}/repos/acme/widgets/issues/5").mock(return_value=Response(200, json={}))
        comment = github.post(f"{GITHUB_API}/repos/acme/widgets/issues/5/comments").mock(return_value=Response(201, json={}))
        other.get(f"/api/dashboards/{board['id']}/closed")
        assert issues.calls.last.request.headers["Authorization"] == "Bearer ghp_mate"

        detail = other.get(f"/api/dashboards/{board['id']}").json()
        assert detail["can_write"] is False
        assert "Only its owner" in detail["write_block_reason"]
        assert other.post(f"/api/dashboards/{board['id']}/issues/5/close").status_code == 403
        assert other.post(f"/api/dashboards/{board['id']}/issues/5/comments", json={"body": "hi"}).status_code == 403
        assert not close.called and not comment.called


def test_members_write_on_organisation_boards_with_their_own_token(team, session):
    _, admin = team["admin"]
    mate_row, mate = team["mate"]
    _, other = team["other"]
    admin.put(f"/api/organizations/{team['org']['id']}/token", json={"token": "ghp_org"})
    mate.put("/api/settings", json={"default_token": "ghp_mate"})
    board = admin.post("/api/dashboards", json={**BOARD, "kind": "organization"}).json()

    with respx.mock(assert_all_called=False) as github:
        issues = github.get(f"{GITHUB_API}/repos/acme/widgets/issues").mock(return_value=Response(200, json=[]))
        close = github.patch(f"{GITHUB_API}/repos/acme/widgets/issues/5").mock(
            return_value=Response(200, json={"number": 5, "title": "t", "state": "closed", "html_url": "", "labels": [],
                                             "assignees": [], "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
                                             "closed_at": "2026-01-02T00:00:00Z", "comments": 0, "body": ""})
        )
        mate.get(f"/api/dashboards/{board['id']}/closed")
        assert issues.calls.last.request.headers["Authorization"] == "Bearer ghp_org"

        assert mate.get(f"/api/dashboards/{board['id']}").json()["can_write"] is True
        assert mate.post(f"/api/dashboards/{board['id']}/issues/5/close").status_code == 200
        assert close.calls.last.request.headers["Authorization"] == "Bearer ghp_mate"

        # Without a token of their own, a member can't write -- not even with the organisation's.
        detail = other.get(f"/api/dashboards/{board['id']}").json()
        assert detail["can_write"] is False
        assert "your own GitHub token" in detail["write_block_reason"]
        assert other.post(f"/api/dashboards/{board['id']}/issues/5/close").status_code == 403
        assert close.call_count == 1


def test_the_organisation_token_is_admin_only_and_never_returned(team, session):
    _, admin = team["admin"]
    _, mate = team["mate"]
    org_id = team["org"]["id"]
    assert mate.put(f"/api/organizations/{org_id}/token", json={"token": "ghp_x"}).status_code == 403
    assert admin.put(f"/api/organizations/{org_id}/token", json={"token": "ghp_org"}).json()["has_token"] is True
    listed = {o["name"]: o for o in admin.get("/api/organizations").json()}
    assert listed["Acme"]["has_token"] is True
    assert {o["name"]: o for o in mate.get("/api/organizations").json()}["Acme"]["has_token"] is None
    assert "ghp_org" not in admin.get("/api/organizations").text
    board = admin.post("/api/dashboards", json={**BOARD, "kind": "organization"}).json()
    row = session.exec(select(Dashboard).where(Dashboard.uuid == board["id"])).one()
    assert read_token(session, row) == "ghp_org"
    from sqlalchemy import text  # noqa: PLC0415

    stored = session.execute(text("SELECT token FROM organization WHERE uuid = :u"), {"u": org_id}).scalar_one()
    assert stored.startswith("enc.v1.") and "ghp_org" not in stored  # encrypted at rest


def test_a_new_organisation_has_no_token_of_its_own(client, session):
    client.put("/api/settings", json={"default_token": "ghp_creator"})
    created = client.post("/api/organizations", json={"name": "Fresh"}).json()
    assert created["has_token"] is False


# ---- private notes ----

def test_notes_on_a_shared_board_are_private_to_their_writer(team):
    _, mate = team["mate"]
    other_row, other = team["other"]
    board = personal(mate)
    mate.put(f"/api/dashboards/{board['id']}/sharing", json={"shared_with_organization": True})
    base = f"/api/dashboards/{board['id']}"

    mine = mate.post(f"{base}/notes", json={"issue_number": 1, "body": "owner's thought"}).json()
    theirs = other.post(f"{base}/notes", json={"issue_number": 1, "body": "viewer's thought"}).json()
    assert [n["body"] for n in mate.get(f"{base}/notes").json()] == ["owner's thought"]
    assert [n["body"] for n in other.get(f"{base}/notes").json()] == ["viewer's thought"]
    assert other.put(f"/api/notes/{mine['id']}", json={"body": "x"}).status_code == 404
    assert mate.delete(f"/api/notes/{theirs['id']}").status_code == 404

    mate.post(f"{base}/sticky-notes", json={"body": "owner sticky"})
    other.post(f"{base}/sticky-notes", json={"body": "viewer sticky"})
    assert [n["body"] for n in mate.get(f"{base}/sticky-notes").json()] == ["owner sticky"]
    assert [n["body"] for n in other.get(f"{base}/sticky-notes").json()] == ["viewer sticky"]


def test_a_viewer_cannot_push_even_their_own_note_on_a_shared_board(team):
    _, mate = team["mate"]
    _, other = team["other"]
    board = personal(mate)
    mate.put(f"/api/dashboards/{board['id']}/sharing", json={"shared_with_organization": True})
    note = other.post(f"/api/dashboards/{board['id']}/notes", json={"issue_number": 1, "body": "x"}).json()
    with respx.mock(assert_all_called=False) as github:
        route = github.route(host="api.github.com").mock(return_value=Response(201, json={"id": 1}))
        assert other.post(f"/api/notes/{note['id']}/push").status_code == 403
    assert not route.called


def test_the_me_columns_follow_the_viewer(team):
    _, mate = team["mate"]
    other_row, other = team["other"]
    mate.put("/api/settings", json={"github_username": "mate-gh"})
    other.put("/api/settings", json={"github_username": "other-gh"})
    board = personal(mate)
    mate.put(f"/api/dashboards/{board['id']}/sharing", json={"user_ids": [other_row.id]})
    virtual = [c for c in other.get(f"/api/dashboards/{board['id']}/columns").json() if c["virtual"]]
    assert {c["assignee"] or c["creator"] for c in virtual} == {"other-gh"}


# ---- member page ----

def test_a_members_page_shows_only_what_they_shared_with_you(team):
    mate_row, mate = team["mate"]
    other_row, other = team["other"]
    _, admin = team["admin"]
    private = personal(mate, "private")
    to_other = personal(mate, "for other")
    to_all = personal(mate, "for everyone")
    mate.put(f"/api/dashboards/{to_other['id']}/sharing", json={"user_ids": [other_row.id]})
    mate.put(f"/api/dashboards/{to_all['id']}/sharing", json={"shared_with_organization": True})

    url = f"/api/organizations/{team['org']['id']}/members/{mate_row.id}/boards"
    assert sorted(b["name"] for b in other.get(url).json()) == ["for everyone", "for other"]
    assert [b["name"] for b in admin.get(url).json()] == ["for everyone"]
    assert mate.get(url).json() == []  # your own page isn't a view of your boards
    _, outsider = team["outsider"]
    assert outsider.get(url).status_code == 404
    assert private["id"] not in str(other.get(url).json())


def test_existing_notes_are_given_to_their_boards_owner(session, user):
    from sqlalchemy import text  # noqa: PLC0415

    from app.orgs import migrate_to_organizations  # noqa: PLC0415

    session.execute(text(
        "INSERT INTO dashboard (uuid, name, repo_owner, repo_name, owner_id, created_at) "
        f"VALUES ('u-1', 'old', 'acme', 'widgets', {user.id}, CURRENT_TIMESTAMP)"
    ))
    session.execute(text("INSERT INTO localnote (dashboard_id, issue_number, body, created_at, updated_at, synced) VALUES (1, 1, 'n', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0)"))
    session.execute(text("INSERT INTO stickynote (dashboard_id, body, pinned, archived, created_at, updated_at) VALUES (1, 's', 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    session.commit()
    migrate_to_organizations(session)
    assert session.execute(text("SELECT user_id FROM localnote")).scalar_one() == user.id
    assert session.execute(text("SELECT user_id FROM stickynote")).scalar_one() == user.id
    assert session.exec(select(Membership)).first() is not None
