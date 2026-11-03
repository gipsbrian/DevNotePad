"""Creating an issue from a board, in the board's repo."""

import json

import respx
from httpx import Response

from tests.conftest import GITHUB_API
from tests.test_sharing import BOARD, personal, team  # noqa: F401 -- fixture

ISSUES = f"{GITHUB_API}/repos/acme/widgets/issues"


def _created(number=42, **overrides):
    issue = {
        "number": number,
        "title": "Login fails",
        "body": "Steps",
        "state": "open",
        "html_url": f"https://github.com/acme/widgets/issues/{number}",
        "labels": [{"name": "bug", "color": "ff0000", "description": None}],
        "assignees": [],
        "milestone": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "closed_at": None,
        "comments": 0,
    }
    issue.update(overrides)
    return issue


@respx.mock
def test_an_issue_is_created_in_the_boards_repo_with_what_was_picked(client, make_dashboard):
    board = make_dashboard(token="ghp_board")
    route = respx.post(ISSUES).mock(return_value=Response(201, json=_created()))

    resp = client.post(
        f"/api/dashboards/{board['id']}/issues",
        json={"title": "  Login fails ", "body": "Steps", "labels": ["bug"], "assignees": ["octocat"],
              "milestone": 3, "issue_type": "Bug"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["number"] == 42
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"title": "Login fails", "body": "Steps", "labels": ["bug"], "assignees": ["octocat"],
                    "milestone": 3, "type": "Bug"}
    assert route.calls.last.request.headers["Authorization"] == "Bearer ghp_board"


@respx.mock
def test_only_the_title_is_required(client, make_dashboard):
    board = make_dashboard(token="ghp_board")
    route = respx.post(ISSUES).mock(return_value=Response(201, json=_created()))
    assert client.post(f"/api/dashboards/{board['id']}/issues", json={"title": "Just this", "body": "  "}).status_code == 201
    assert json.loads(route.calls.last.request.content) == {"title": "Just this"}

    assert client.post(f"/api/dashboards/{board['id']}/issues", json={"title": "   "}).status_code == 422


@respx.mock
def test_githubs_refusal_comes_back(client, make_dashboard):
    board = make_dashboard(token="ghp_board")
    respx.post(ISSUES).mock(return_value=Response(422, json={"message": "Validation Failed"}))
    resp = client.post(f"/api/dashboards/{board['id']}/issues", json={"title": "x", "labels": ["nope"]})
    assert resp.status_code == 422
    assert "Validation Failed" in resp.json()["detail"]


def test_viewers_of_a_shared_board_cannot_create(team):
    mate_row, mate = team["mate"]
    other_row, other = team["other"]
    mate.put("/api/settings", json={"default_token": "ghp_mate"})
    board = personal(mate)
    mate.put(f"/api/dashboards/{board['id']}/sharing", json={"user_ids": [other_row.id]})
    with respx.mock(assert_all_called=False) as github:
        route = github.post(ISSUES).mock(return_value=Response(201, json=_created()))
        assert other.post(f"/api/dashboards/{board['id']}/issues", json={"title": "x"}).status_code == 403
        assert not route.called


def test_members_create_on_organisation_boards_as_themselves(team):
    _, admin = team["admin"]
    _, mate = team["mate"]
    admin.put(f"/api/organizations/{team['org']['id']}/token", json={"token": "ghp_org"})
    mate.put("/api/settings", json={"default_token": "ghp_mate"})
    board = admin.post("/api/dashboards", json={**BOARD, "kind": "organization"}).json()
    with respx.mock() as github:
        route = github.post(ISSUES).mock(return_value=Response(201, json=_created()))
        assert mate.post(f"/api/dashboards/{board['id']}/issues", json={"title": "x"}).status_code == 201
        # Their own token, not the organisation's, so GitHub shows them as the author.
        assert route.calls.last.request.headers["Authorization"] == "Bearer ghp_mate"


def test_pr_boards_have_no_repo_to_create_in(client):
    board = client.post("/api/dashboards", json={"name": "PRs", "subject": "pulls", "org_ref": "acme"}).json()
    assert client.post(f"/api/dashboards/{board['id']}/issues", json={"title": "x"}).status_code == 400
