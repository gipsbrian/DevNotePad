import respx
from httpx import Response

from tests.conftest import GITHUB_API


def test_create_board_from_a_pasted_github_url(client):
    resp = client.post(
        "/api/dashboards",
        json={"name": "Prod images", "repo_ref": "https://github.com/acme/widgets"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["repo_owner"] == "acme"
    assert data["repo_name"] == "widgets"


def test_create_board_still_accepts_owner_and_name(client):
    data = client.post(
        "/api/dashboards", json={"name": "B", "repo_owner": "acme", "repo_name": "widgets"}
    ).json()
    assert (data["repo_owner"], data["repo_name"]) == ("acme", "widgets")


def test_create_board_without_a_repo_is_rejected(client):
    resp = client.post("/api/dashboards", json={"name": "No repo"})
    assert resp.status_code == 422
    assert "repo" in resp.json()["detail"].lower()


def test_create_board_with_unreadable_repo_is_rejected(client):
    resp = client.post("/api/dashboards", json={"name": "Bad", "repo_ref": "just-an-owner"})
    assert resp.status_code == 422


def test_repoint_an_existing_board_at_another_repo(client, make_dashboard):
    dash = make_dashboard()
    resp = client.patch(
        f"/api/dashboards/{dash['id']}",
        json={"repo_ref": "https://github.com/acme/widgets"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert (data["repo_owner"], data["repo_name"]) == ("acme", "widgets")


def test_rename_a_board(client, make_dashboard):
    dash = make_dashboard()
    data = client.patch(f"/api/dashboards/{dash['id']}", json={"name": "Renamed"}).json()
    assert data["name"] == "Renamed"


def test_clearing_a_board_token_falls_back_to_the_general_one(client, make_dashboard):
    dash = make_dashboard(token="ghp_boardtoken")
    assert dash["has_own_token"] is True
    data = client.patch(f"/api/dashboards/{dash['id']}", json={"token": ""}).json()
    assert data["has_own_token"] is False


@respx.mock
def test_column_can_filter_by_creator(client, make_dashboard):
    dash = make_dashboard(token="ghp_abcdef123456")
    col = client.post(
        f"/api/dashboards/{dash['id']}/columns",
        json={"name": "Filed by me", "creator": "octocat"},
    ).json()
    assert col["creator"] == "octocat"

    route = respx.get(f"{GITHUB_API}/repos/acme/widgets/issues").mock(
        return_value=Response(200, json=[])
    )
    client.get(f"/api/dashboards/{dash['id']}/columns/{col['id']}/issues")
    assert route.calls.last.request.url.params["creator"] == "octocat"


def test_editing_a_columns_filters(client, make_dashboard):
    dash = make_dashboard()
    col = client.post(f"/api/dashboards/{dash['id']}/columns", json={"name": "Bugs"}).json()

    updated = client.put(
        f"/api/dashboards/{dash['id']}/columns/{col['id']}",
        json={"name": "Priority bugs", "labels": ["bug", "priority"], "state": "open"},
    ).json()
    assert updated["name"] == "Priority bugs"
    assert updated["labels"] == ["bug", "priority"]
    # Two labels is no longer a single unambiguous mutation.
    assert updated["drag_compatible"] is False


def test_clearing_a_column_filter_back_to_any(client, make_dashboard):
    dash = make_dashboard()
    col = client.post(
        f"/api/dashboards/{dash['id']}/columns",
        json={"name": "Mine", "assignee": "someone", "creator": "someone"},
    ).json()

    updated = client.put(
        f"/api/dashboards/{dash['id']}/columns/{col['id']}",
        json={"assignee": "", "creator": ""},
    ).json()
    assert updated["assignee"] is None
    assert updated["creator"] is None


# ---- Reordering columns ----


def _make_columns(client, dashboard_id, names):
    return [
        client.post(f"/api/dashboards/{dashboard_id}/columns", json={"name": n}).json()
        for n in names
    ]


def test_reorder_columns(client, make_dashboard):
    dash = make_dashboard()
    a, b, c = _make_columns(client, dash["id"], ["A", "B", "C"])

    resp = client.put(
        f"/api/dashboards/{dash['id']}/columns/reorder",
        json={"column_ids": [c["id"], a["id"], b["id"]]},
    )
    assert resp.status_code == 200
    assert [col["name"] for col in resp.json()] == ["C", "A", "B"]

    listed = client.get(f"/api/dashboards/{dash['id']}/columns").json()
    assert [col["name"] for col in listed] == ["C", "A", "B"]
    assert [col["position"] for col in listed] == [0, 1, 2]


def test_reorder_rejects_columns_from_another_board(client, make_dashboard):
    dash = make_dashboard()
    other = make_dashboard(name="Other")
    stray = client.post(f"/api/dashboards/{other['id']}/columns", json={"name": "Stray"}).json()

    resp = client.put(
        f"/api/dashboards/{dash['id']}/columns/reorder", json={"column_ids": [stray["id"]]}
    )
    assert resp.status_code == 404


def test_reorder_keeps_unmentioned_columns_after_the_reordered_ones(client, make_dashboard):
    dash = make_dashboard()
    a, b, c = _make_columns(client, dash["id"], ["A", "B", "C"])

    # Only reorder two of the three.
    client.put(f"/api/dashboards/{dash['id']}/columns/reorder", json={"column_ids": [b["id"], a["id"]]})
    listed = client.get(f"/api/dashboards/{dash['id']}/columns").json()
    assert [col["name"] for col in listed] == ["B", "A", "C"]


def test_reordering_does_not_disturb_the_automatic_columns(client, make_dashboard):
    client.put("/api/settings", json={"github_username": "octocat"})
    dash = make_dashboard()
    a, b = _make_columns(client, dash["id"], ["A", "B"])

    client.put(f"/api/dashboards/{dash['id']}/columns/reorder", json={"column_ids": [b["id"], a["id"]]})
    listed = client.get(f"/api/dashboards/{dash['id']}/columns").json()
    assert [col["name"] for col in listed] == ["B", "A", "Assigned to me", "Created by me"]


# ---- Issue type filter ----


@respx.mock
def test_column_can_filter_by_issue_type(client, make_dashboard):
    dash = make_dashboard(token="ghp_abcdef123456")
    col = client.post(
        f"/api/dashboards/{dash['id']}/columns", json={"name": "Bugs", "issue_type": "Bug"}
    ).json()
    assert col["issue_type"] == "Bug"

    route = respx.get(f"{GITHUB_API}/repos/acme/widgets/issues").mock(
        return_value=Response(200, json=[])
    )
    client.get(f"/api/dashboards/{dash['id']}/columns/{col['id']}/issues")
    assert route.calls.last.request.url.params["type"] == "Bug"


@respx.mock
def test_issue_types_come_from_the_repo_being_processed(client, make_dashboard):
    """Types are an org-level concept, but a board should offer the ones its
    own repo actually uses — and still work when the org registry is
    unreadable, which is the common case."""
    dash = make_dashboard(token="ghp_abcdef123456")
    respx.get(f"{GITHUB_API}/repos/acme/widgets/labels").mock(return_value=Response(200, json=[]))
    respx.get(f"{GITHUB_API}/repos/acme/widgets/milestones").mock(return_value=Response(200, json=[]))
    respx.get(f"{GITHUB_API}/repos/acme/widgets/assignees").mock(return_value=Response(200, json=[]))
    respx.get(f"{GITHUB_API}/orgs/acme/issue-types").mock(return_value=Response(404, json={"message": "Not Found"}))
    respx.get(f"{GITHUB_API}/repos/acme/widgets/issues").mock(
        return_value=Response(
            200,
            json=[
                {"number": 1, "type": {"name": "Bug", "color": "red", "description": "d"}},
                {"number": 2, "type": {"name": "Feature", "color": "blue", "description": None}},
                {"number": 3, "type": {"name": "Bug", "color": "red", "description": "d"}},
                {"number": 4, "type": None},
            ],
        )
    )

    data = client.get(f"/api/dashboards/{dash['id']}/github-metadata").json()
    assert [t["name"] for t in data["issue_types"]] == ["Bug", "Feature"]
    assert data["issue_types_source"] == "repo"


def test_type_filter_makes_a_column_view_only_for_drag(client, make_dashboard):
    dash = make_dashboard()
    col = client.post(
        f"/api/dashboards/{dash['id']}/columns",
        json={"name": "Typed bugs", "labels": ["bug"], "issue_type": "Bug"},
    ).json()
    # A label alone would be draggable; adding a type means a drop can't be
    # satisfied by one mutation.
    assert col["drag_compatible"] is False


@respx.mock
def test_repo_types_are_listed_before_extra_org_types(client, make_dashboard):
    dash = make_dashboard(token="ghp_abcdef123456")
    respx.get(f"{GITHUB_API}/repos/acme/widgets/labels").mock(return_value=Response(200, json=[]))
    respx.get(f"{GITHUB_API}/repos/acme/widgets/milestones").mock(return_value=Response(200, json=[]))
    respx.get(f"{GITHUB_API}/repos/acme/widgets/assignees").mock(return_value=Response(200, json=[]))
    respx.get(f"{GITHUB_API}/repos/acme/widgets/issues").mock(
        return_value=Response(200, json=[{"number": 1, "type": {"name": "Bug", "color": "red"}}])
    )
    respx.get(f"{GITHUB_API}/orgs/acme/issue-types").mock(
        return_value=Response(
            200,
            json=[{"name": "Bug", "color": "red"}, {"name": "Epic", "color": "purple"}],
        )
    )

    data = client.get(f"/api/dashboards/{dash['id']}/github-metadata").json()
    # "Bug" is in use here so it comes first and isn't duplicated; "Epic" is
    # defined org-wide but unused on this repo, so it's still selectable.
    assert [t["name"] for t in data["issue_types"]] == ["Bug", "Epic"]
    assert data["issue_types_source"] == "repo+org"


# ---- Closed-issue time window ----


def _closed_issue(number, closed_at):
    return {
        "number": number,
        "title": f"Issue {number}",
        "body": "",
        "state": "closed",
        "html_url": f"https://github.com/acme/widgets/issues/{number}",
        "labels": [],
        "assignees": [],
        "milestone": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": closed_at,
        "closed_at": closed_at,
        "comments": 0,
    }


@respx.mock
def test_closed_defaults_to_the_last_seven_days(client, make_dashboard):
    from datetime import datetime, timedelta, timezone

    dash = make_dashboard(token="ghp_abcdef123456")
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=2)).isoformat().replace("+00:00", "Z")
    old = (now - timedelta(days=90)).isoformat().replace("+00:00", "Z")

    route = respx.get(f"{GITHUB_API}/repos/acme/widgets/issues").mock(
        return_value=Response(200, json=[_closed_issue(1, recent), _closed_issue(2, old)])
    )

    data = client.get(f"/api/dashboards/{dash['id']}/closed").json()
    # `since` bounds what GitHub sends...
    assert "since" in route.calls.last.request.url.params
    # ...and anything closed outside the window is dropped, since `since`
    # matches on updated_at and would otherwise leak old closures back in.
    assert [i["number"] for i in data] == [1]


@respx.mock
def test_closed_window_is_configurable(client, make_dashboard):
    from datetime import datetime, timedelta, timezone

    dash = make_dashboard(token="ghp_abcdef123456")
    now = datetime.now(timezone.utc)
    within_30 = (now - timedelta(days=20)).isoformat().replace("+00:00", "Z")

    respx.get(f"{GITHUB_API}/repos/acme/widgets/issues").mock(
        return_value=Response(200, json=[_closed_issue(1, within_30)])
    )

    assert client.get(f"/api/dashboards/{dash['id']}/closed?days=7").json() == []
    assert len(client.get(f"/api/dashboards/{dash['id']}/closed?days=30").json()) == 1


@respx.mock
def test_closed_days_zero_means_all_time(client, make_dashboard):
    dash = make_dashboard(token="ghp_abcdef123456")
    route = respx.get(f"{GITHUB_API}/repos/acme/widgets/issues").mock(
        return_value=Response(200, json=[_closed_issue(1, "2019-01-01T00:00:00Z")])
    )

    data = client.get(f"/api/dashboards/{dash['id']}/closed?days=0").json()
    assert [i["number"] for i in data] == [1]
    assert "since" not in route.calls.last.request.url.params
