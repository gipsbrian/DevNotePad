"""Tracking columns: no filter, just the issues dropped into them."""

import respx
from httpx import Response
from sqlmodel import select

from app.models import TrackedIssue
from tests.conftest import GITHUB_API
from tests.test_sharing import personal, team  # noqa: F401 -- fixture

REPO = f"{GITHUB_API}/repos/acme/widgets"


def _issue(number, **overrides):
    issue = {
        "number": number,
        "title": f"Issue {number}",
        "body": "Body text",
        "state": "open",
        "html_url": f"https://github.com/acme/widgets/issues/{number}",
        "repository_url": REPO,
        "labels": [],
        "assignees": [],
        "milestone": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "closed_at": None,
        "comments": 0,
    }
    issue.update(overrides)
    return issue


def _column(client, board, name="Watching", kind="tracking", **extra):
    resp = client.post(f"/api/dashboards/{board['id']}/columns", json={"name": name, "kind": kind, **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _track(client, board, column, number, **extra):
    return client.post(
        f"/api/dashboards/{board['id']}/columns/{column['id']}/tracked", json={"issue_number": number, **extra}
    )


def _issues(client, board, column):
    resp = client.get(f"/api/dashboards/{board['id']}/columns/{column['id']}/issues")
    assert resp.status_code == 200, resp.text
    return [i["number"] for i in resp.json()]


def test_a_tracking_column_ignores_filters_and_takes_no_label_moves(client, make_dashboard):
    board = make_dashboard()
    column = _column(client, board, labels=["bug"], assignee="someone", state="closed")
    assert column["kind"] == "tracking"
    assert column["labels"] == [] and column["assignee"] is None and column["state"] == "open"
    assert column["drag_compatible"] is False

    # Editing keeps it filterless; only the name changes.
    updated = client.put(
        f"/api/dashboards/{board['id']}/columns/{column['id']}", json={"name": "Mine", "labels": ["bug"]}
    ).json()
    assert updated["name"] == "Mine" and updated["labels"] == []
    assert client.post(
        f"/api/dashboards/{board['id']}/issues/1/move", json={"target_column_id": column["id"]}
    ).status_code == 400


def test_filter_columns_default_to_filter_kind(client, make_dashboard):
    board = make_dashboard()
    assert _column(client, board, kind="filter", labels=["bug"])["kind"] == "filter"
    created = client.post(f"/api/dashboards/{board['id']}/columns", json={"name": "plain"}).json()
    assert created["kind"] == "filter"


@respx.mock
def test_dropped_issues_are_listed_newest_first(client, make_dashboard):
    board = make_dashboard()
    column = _column(client, board)
    for n in (3, 7, 5):
        respx.get(f"{REPO}/issues/{n}").mock(return_value=Response(200, json=_issue(n)))
        assert _track(client, board, column, n).json()["number"] == n
    assert _issues(client, board, column) == [5, 7, 3]
    # Dropping it again changes nothing.
    _track(client, board, column, 7)
    assert _issues(client, board, column) == [5, 7, 3]


@respx.mock
def test_only_open_issues_from_this_repo_can_be_tracked(client, make_dashboard, session):
    board = make_dashboard()
    column = _column(client, board)
    respx.get(f"{REPO}/issues/1").mock(return_value=Response(200, json=_issue(1, state="closed")))
    respx.get(f"{REPO}/issues/2").mock(return_value=Response(200, json=_issue(2, pull_request={"url": "x"})))
    respx.get(f"{REPO}/issues/3").mock(return_value=Response(404, json={"message": "Not Found"}))
    respx.get(f"{REPO}/issues/4").mock(
        return_value=Response(200, json=_issue(4, repository_url=f"{GITHUB_API}/repos/acme/elsewhere"))
    )
    assert _track(client, board, column, 1).status_code == 422
    assert _track(client, board, column, 2).status_code == 422
    assert _track(client, board, column, 3).status_code == 404
    assert _track(client, board, column, 4).status_code == 422
    assert session.exec(select(TrackedIssue)).all() == []


@respx.mock
def test_closed_deleted_and_transferred_issues_drop_out(client, make_dashboard, session):
    board = make_dashboard()
    column = _column(client, board)
    for n in (1, 2, 3, 4):
        respx.get(f"{REPO}/issues/{n}").mock(return_value=Response(200, json=_issue(n)))
        _track(client, board, column, n)

    respx.get(f"{REPO}/issues/1").mock(return_value=Response(200, json=_issue(1, state="closed")))
    respx.get(f"{REPO}/issues/2").mock(return_value=Response(410, json={"message": "This issue was deleted"}))
    respx.get(f"{REPO}/issues/3").mock(
        return_value=Response(301, json={"message": "Moved Permanently", "url": "https://api.github.com/x"})
    )
    assert _issues(client, board, column) == [4]
    assert [r.issue_number for r in session.exec(select(TrackedIssue)).all()] == [4]


@respx.mock
def test_a_github_failure_while_loading_keeps_every_tracked_issue(client, make_dashboard, session):
    board = make_dashboard()
    column = _column(client, board)
    respx.get(f"{REPO}/issues/1").mock(return_value=Response(200, json=_issue(1)))
    _track(client, board, column, 1)
    respx.get(f"{REPO}/issues/1").mock(return_value=Response(403, json={"message": "rate limited"}))
    assert client.get(f"/api/dashboards/{board['id']}/columns/{column['id']}/issues").status_code == 403
    assert len(session.exec(select(TrackedIssue)).all()) == 1


@respx.mock
def test_dragging_between_tracking_columns_moves_but_from_a_filter_column_copies(client, make_dashboard):
    board = make_dashboard()
    first, second = _column(client, board, "First"), _column(client, board, "Second")
    bugs = _column(client, board, "Bugs", kind="filter", labels=["bug"])
    respx.get(f"{REPO}/issues/9").mock(return_value=Response(200, json=_issue(9)))

    _track(client, board, first, 9, from_column_id=bugs["id"])
    assert _issues(client, board, first) == [9]

    _track(client, board, second, 9, from_column_id=first["id"])
    assert _issues(client, board, second) == [9]
    assert _issues(client, board, first) == []


@respx.mock
def test_moving_never_reaches_into_another_board(client, make_dashboard):
    mine, theirs = make_dashboard(name="mine"), make_dashboard(name="theirs")
    here, there = _column(client, mine), _column(client, theirs)
    respx.get(f"{REPO}/issues/9").mock(return_value=Response(200, json=_issue(9)))
    _track(client, theirs, there, 9)
    _track(client, mine, here, 9, from_column_id=there["id"])
    assert _issues(client, theirs, there) == [9]


@respx.mock
def test_untracking_removes_only_that_issue(client, make_dashboard):
    board = make_dashboard()
    column = _column(client, board)
    for n in (1, 2):
        respx.get(f"{REPO}/issues/{n}").mock(return_value=Response(200, json=_issue(n)))
        _track(client, board, column, n)
    assert client.delete(f"/api/dashboards/{board['id']}/columns/{column['id']}/tracked/1").status_code == 204
    assert _issues(client, board, column) == [2]


def test_filter_columns_refuse_drops(client, make_dashboard):
    board = make_dashboard()
    bugs = _column(client, board, "Bugs", kind="filter", labels=["bug"])
    assert _track(client, board, bugs, 1).status_code == 400
    assert client.delete(f"/api/dashboards/{board['id']}/columns/{bugs['id']}/tracked/1").status_code == 400


@respx.mock
def test_a_column_holds_a_bounded_number(client, make_dashboard, session, monkeypatch):
    from app.routers import dashboards

    monkeypatch.setattr(dashboards, "TRACKING_LIMIT", 2)
    board = make_dashboard()
    column = _column(client, board)
    for n in (1, 2, 3):
        respx.get(f"{REPO}/issues/{n}").mock(return_value=Response(200, json=_issue(n)))
    assert _track(client, board, column, 1).status_code == 200
    assert _track(client, board, column, 2).status_code == 200
    assert _track(client, board, column, 3).status_code == 409
    # Re-dropping one already there isn't adding.
    assert _track(client, board, column, 2).status_code == 200


@respx.mock
def test_deleting_a_column_or_board_forgets_its_issues(client, make_dashboard, session):
    board = make_dashboard()
    column = _column(client, board)
    respx.get(f"{REPO}/issues/1").mock(return_value=Response(200, json=_issue(1)))
    _track(client, board, column, 1)
    client.delete(f"/api/dashboards/{board['id']}/columns/{column['id']}")
    assert session.exec(select(TrackedIssue)).all() == []

    column = _column(client, board)
    _track(client, board, column, 1)
    client.delete(f"/api/dashboards/{board['id']}")
    assert session.exec(select(TrackedIssue)).all() == []


@respx.mock
def test_only_board_managers_can_drop_or_remove(team):
    _, mate = team["mate"]
    other_row, other = team["other"]
    board = personal(mate)
    column = _column(mate, board)
    respx.get(f"{REPO}/issues/1").mock(return_value=Response(200, json=_issue(1)))
    assert _track(mate, board, column, 1).status_code == 200

    mate.put(f"/api/dashboards/{board['id']}/sharing", json={"user_ids": [other_row.id]})
    assert _issues(other, board, column) == [1]  # a viewer sees them
    assert _track(other, board, column, 1).status_code == 403
    assert other.delete(f"/api/dashboards/{board['id']}/columns/{column['id']}/tracked/1").status_code == 403

    _, outsider = team["outsider"]
    assert _track(outsider, board, column, 1).status_code == 404


@respx.mock
def test_a_filter_column_can_become_a_tracking_one_and_back(client, make_dashboard, session):
    board = make_dashboard()
    column = _column(client, board, "Look out", kind="filter", labels=["bug"], assignee="someone")
    url = f"/api/dashboards/{board['id']}/columns/{column['id']}"

    tracking = client.put(url, json={"kind": "tracking", "labels": ["bug"]}).json()
    assert tracking["kind"] == "tracking"
    assert tracking["labels"] == [] and tracking["assignee"] is None and tracking["state"] == "open"
    respx.get(f"{REPO}/issues/1").mock(return_value=Response(200, json=_issue(1)))
    assert _track(client, board, column, 1).status_code == 200

    back = client.put(url, json={"kind": "filter", "labels": ["bug"]}).json()
    assert back["kind"] == "filter" and back["labels"] == ["bug"]
    assert session.exec(select(TrackedIssue)).all() == []
    assert _track(client, board, column, 1).status_code == 400
