"""PR boards: open PRs across a GitHub org, per viewer, plus tracking columns."""

from urllib.parse import parse_qs, urlparse

import respx
from httpx import Response
from sqlmodel import select

from app.models import TrackedPull
from tests.conftest import GITHUB_API
from tests.test_sharing import personal, team  # noqa: F401 -- fixture

SEARCH = f"{GITHUB_API}/search/issues"


def _pr(number, repo="acme/widgets", **overrides):
    item = {
        "number": number,
        "title": f"PR {number}",
        "state": "open",
        "draft": False,
        "html_url": f"https://github.com/{repo}/pull/{number}",
        "repository_url": f"{GITHUB_API}/repos/{repo}",
        "pull_request": {"url": f"{GITHUB_API}/repos/{repo}/pulls/{number}", "merged_at": None},
        "user": {"login": "octocat", "avatar_url": "https://avatars/octocat"},
        "labels": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "comments": 2,
    }
    item.update(overrides)
    return item


def _pull_board(client, org_ref="acme", **extra):
    resp = client.post("/api/dashboards", json={"name": "PRs", "subject": "pulls", "org_ref": org_ref, **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _tracking(client, board, name="Watching"):
    resp = client.post(f"/api/dashboards/{board['id']}/columns", json={"name": name, "kind": "tracking"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _track(client, board, column, repo, number, **extra):
    return client.post(
        f"/api/dashboards/{board['id']}/columns/{column['id']}/tracked-pulls",
        json={"repo": repo, "number": number, **extra},
    )


def _pulls(client, board, column_id):
    resp = client.get(f"/api/dashboards/{board['id']}/columns/{column_id}/pulls")
    assert resp.status_code == 200, resp.text
    return [(p["repo"], p["number"]) for p in resp.json()]


def test_a_pr_board_names_an_org_from_a_login_or_url(client):
    board = _pull_board(client, "https://github.com/acme/")
    assert board["subject"] == "pulls"
    assert board["repo_owner"] == "acme" and board["repo_name"] == ""

    for bad in ("", "not a login", "acme org:other"):
        resp = client.post("/api/dashboards", json={"name": "PRs", "subject": "pulls", "org_ref": bad})
        assert resp.status_code == 422, bad


def test_auto_columns_need_a_username_and_ignore_the_my_columns_setting(client):
    board = _pull_board(client)
    assert client.get(f"/api/dashboards/{board['id']}/columns").json() == []

    client.put("/api/settings", json={"github_username": "octocat", "show_my_columns": False})
    columns = client.get(f"/api/dashboards/{board['id']}/columns").json()
    assert [(c["id"], c["name"], c["virtual"]) for c in columns] == [
        (-3, "My open PRs", True),
        (-4, "Review requested", True),
    ]


@respx.mock
def test_auto_columns_search_the_org_for_the_viewer(client):
    client.put("/api/settings", json={"github_username": "octocat"})
    board = _pull_board(client)
    route = respx.get(SEARCH).mock(return_value=Response(200, json={"items": [_pr(7, "acme/api")]}))

    assert _pulls(client, board, -3) == [("acme/api", 7)]
    assert _pulls(client, board, -4) == [("acme/api", 7)]
    queries = [parse_qs(urlparse(str(c.request.url)).query)["q"][0] for c in route.calls]
    assert queries == [
        "is:pr is:open archived:false org:acme author:octocat",
        "is:pr is:open archived:false org:acme review-requested:octocat",
    ]


@respx.mock
def test_a_shared_pr_board_shows_each_viewer_their_own(team):
    _, owner = team["admin"]
    _, mate = team["mate"]
    owner.put("/api/settings", json={"github_username": "owner-gh"})
    mate.put("/api/settings", json={"github_username": "mate-gh"})
    board = personal(owner, subject="pulls", org_ref="acme")
    owner.put(f"/api/dashboards/{board['id']}/sharing", json={"shared_with_organization": True, "user_ids": []})
    route = respx.get(SEARCH).mock(return_value=Response(200, json={"items": []}))

    assert mate.get(f"/api/dashboards/{board['id']}/columns/-4/pulls").status_code == 200
    assert "review-requested:mate-gh" in parse_qs(urlparse(str(route.calls.last.request.url)).query)["q"][0]


def test_a_username_that_would_change_the_query_is_refused(client):
    client.put("/api/settings", json={"github_username": "octocat org:elsewhere"})
    board = _pull_board(client)
    assert client.get(f"/api/dashboards/{board['id']}/columns/-3/pulls").status_code == 422


def test_a_pr_board_only_takes_tracking_columns(client):
    board = _pull_board(client)
    resp = client.post(f"/api/dashboards/{board['id']}/columns", json={"name": "Bugs", "labels": ["bug"]})
    assert resp.status_code == 422
    column = _tracking(client, board)
    resp = client.put(f"/api/dashboards/{board['id']}/columns/{column['id']}", json={"kind": "filter"})
    assert resp.status_code == 422


@respx.mock
def test_tracking_a_pr_keeps_its_repo_and_moves_between_columns(client, session):
    board = _pull_board(client)
    first, second = _tracking(client, board, "First"), _tracking(client, board, "Second")
    for repo in ("acme/api", "acme/web"):
        respx.get(f"{GITHUB_API}/repos/{repo}/issues/5").mock(return_value=Response(200, json=_pr(5, repo)))

    # Same number in two repos: two different PRs.
    assert _track(client, board, first, "acme/api", 5).status_code == 200
    assert _track(client, board, first, "acme/web", 5).status_code == 200
    assert sorted(_pulls(client, board, first["id"])) == [("acme/api", 5), ("acme/web", 5)]

    assert _track(client, board, second, "acme/api", 5, from_column_id=first["id"]).status_code == 200
    assert _pulls(client, board, first["id"]) == [("acme/web", 5)]
    assert _pulls(client, board, second["id"]) == [("acme/api", 5)]

    resp = client.delete(f"/api/dashboards/{board['id']}/columns/{second['id']}/tracked-pulls/acme/api/5")
    assert resp.status_code == 204
    assert _pulls(client, board, second["id"]) == []

    client.delete(f"/api/dashboards/{board['id']}/columns/{first['id']}")
    assert session.exec(select(TrackedPull)).all() == []


@respx.mock
def test_only_open_prs_in_the_org_can_be_tracked(client):
    board = _pull_board(client)
    column = _tracking(client, board)
    respx.get(f"{GITHUB_API}/repos/other/api/issues/1").mock(return_value=Response(200, json=_pr(1, "other/api")))
    respx.get(f"{GITHUB_API}/repos/acme/api/issues/2").mock(
        return_value=Response(200, json={k: v for k, v in _pr(2, "acme/api").items() if k != "pull_request"})
    )
    respx.get(f"{GITHUB_API}/repos/acme/api/issues/3").mock(return_value=Response(200, json=_pr(3, "acme/api", state="closed")))

    assert _track(client, board, column, "other/api", 1).status_code == 422
    assert _track(client, board, column, "acme/api", 2).status_code == 422  # an issue
    assert _track(client, board, column, "acme/api", 3).status_code == 422  # merged/closed
    assert _track(client, board, column, "../../user", 1).status_code == 422


@respx.mock
def test_merged_and_deleted_prs_drop_out_of_tracking_columns(client, session):
    board = _pull_board(client)
    column = _tracking(client, board)
    a = respx.get(f"{GITHUB_API}/repos/acme/api/issues/1").mock(return_value=Response(200, json=_pr(1, "acme/api")))
    b = respx.get(f"{GITHUB_API}/repos/acme/api/issues/2").mock(return_value=Response(200, json=_pr(2, "acme/api")))
    _track(client, board, column, "acme/api", 1)
    _track(client, board, column, "acme/api", 2)

    a.mock(return_value=Response(200, json=_pr(1, "acme/api", state="closed")))
    b.mock(return_value=Response(404, json={"message": "Not Found"}))
    assert _pulls(client, board, column["id"]) == []
    assert session.exec(select(TrackedPull)).all() == []


def test_viewers_cannot_track_and_issue_boards_have_no_pull_routes(team):
    _, owner = team["admin"]
    _, mate = team["mate"]
    board = personal(owner, subject="pulls", org_ref="acme")
    owner.put(f"/api/dashboards/{board['id']}/sharing", json={"shared_with_organization": True, "user_ids": []})
    column = _tracking(owner, board)
    assert _track(mate, board, column, "acme/api", 1).status_code == 403

    issues = personal(owner, name="issues")
    assert owner.get(f"/api/dashboards/{issues['id']}/columns/-3/pulls").status_code == 400
