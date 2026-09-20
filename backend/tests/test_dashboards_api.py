import respx
from httpx import Response

from tests.conftest import GITHUB_API


def test_create_and_list_dashboard(client):
    resp = client.post(
        "/api/dashboards",
        json={"name": "My board", "repo_owner": "acme", "repo_name": "widgets"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "My board"
    assert data["has_own_token"] is False
    assert data["accent_color"] is None

    listed = client.get("/api/dashboards").json()
    assert len(listed) == 1
    assert listed[0]["repo_owner"] == "acme"


def test_create_dashboard_with_appearance(client):
    resp = client.post(
        "/api/dashboards",
        json={
            "name": "Styled",
            "repo_owner": "acme",
            "repo_name": "widgets",
            "accent_color": "#0052cc",
            "background_url": "https://example.com/bg.jpg",
        },
    )
    data = resp.json()
    assert data["accent_color"] == "#0052cc"
    assert data["background_url"] == "https://example.com/bg.jpg"


def test_update_appearance(client, make_dashboard):
    dash = make_dashboard()
    resp = client.patch(f"/api/dashboards/{dash['id']}/appearance", json={"accent_color": "#de350b"})
    assert resp.status_code == 200
    assert resp.json()["accent_color"] == "#de350b"


def test_delete_dashboard(client, make_dashboard):
    dash = make_dashboard()
    resp = client.delete(f"/api/dashboards/{dash['id']}")
    assert resp.status_code == 204
    assert client.get("/api/dashboards").json() == []


def test_get_dashboard_not_found(client):
    resp = client.get("/api/dashboards/999")
    assert resp.status_code == 404


@respx.mock
def test_dashboard_detail_token_info_classic(client, make_dashboard):
    dash = make_dashboard(token="ghp_abcdef123456")

    respx.get(f"{GITHUB_API}/repos/acme/widgets").mock(
        return_value=Response(
            200,
            json={"permissions": {"pull": True, "push": False}},
            headers={"X-OAuth-Scopes": "repo, read:org"},
        )
    )

    detail = client.get(f"/api/dashboards/{dash['id']}").json()
    info = detail["token_info"]
    assert info["token_type"] == "classic-pat"
    assert info["classic_scopes"] == ["repo", "read:org"]
    assert info["inferred_can_read"] is True
    assert info["inferred_can_write"] is False
    assert "scoped" in info["warning"].lower()


@respx.mock
def test_dashboard_detail_token_info_fine_grained_has_no_scopes(client, make_dashboard):
    dash = make_dashboard(token="github_pat_abcdef123456")
    respx.get(f"{GITHUB_API}/repos/acme/widgets").mock(
        return_value=Response(200, json={"permissions": {"pull": True, "push": True}})
    )
    detail = client.get(f"/api/dashboards/{dash['id']}").json()
    info = detail["token_info"]
    assert info["token_type"] == "fine-grained-pat"
    assert info["classic_scopes"] is None
    assert info["inferred_can_write"] is True


def test_dashboard_detail_no_token_configured(client, make_dashboard):
    dash = make_dashboard()
    detail = client.get(f"/api/dashboards/{dash['id']}").json()
    assert detail["token_info"]["token_type"] == "none"
    assert detail["token_info"]["error"]


@respx.mock
def test_github_metadata_endpoint(client, make_dashboard):
    dash = make_dashboard(token="ghp_abcdef123456")
    respx.get(f"{GITHUB_API}/repos/acme/widgets/labels").mock(
        return_value=Response(200, json=[{"name": "bug", "color": "ff0000", "description": None}])
    )
    respx.get(f"{GITHUB_API}/repos/acme/widgets/milestones").mock(
        return_value=Response(200, json=[{"number": 1, "title": "v1", "state": "open"}])
    )
    respx.get(f"{GITHUB_API}/repos/acme/widgets/assignees").mock(
        return_value=Response(200, json=[{"login": "alice", "avatar_url": "https://x/a.png"}])
    )
    respx.get(f"{GITHUB_API}/orgs/acme/issue-types").mock(
        return_value=Response(200, json=[{"name": "Bug", "color": "red", "description": "A defect"}])
    )
    respx.get(f"{GITHUB_API}/repos/acme/widgets/issues").mock(return_value=Response(200, json=[]))

    resp = client.get(f"/api/dashboards/{dash['id']}/github-metadata")
    assert resp.status_code == 200
    data = resp.json()
    assert data["labels"][0]["name"] == "bug"
    assert data["milestones"][0]["title"] == "v1"
    assert data["assignees"][0]["login"] == "alice"
    assert data["issue_types"][0]["name"] == "Bug"
    assert data["issue_types_source"] == "org"


# ---- Columns ----


def test_create_column_single_label_is_drag_compatible(client, make_dashboard):
    dash = make_dashboard()
    resp = client.post(
        f"/api/dashboards/{dash['id']}/columns",
        json={"name": "Bugs", "state": "open", "labels": ["bug"]},
    )
    assert resp.status_code == 200
    col = resp.json()
    assert col["drag_compatible"] is True
    assert col["position"] == 0


def test_create_column_multi_filter_not_drag_compatible(client, make_dashboard):
    dash = make_dashboard()
    col = client.post(
        f"/api/dashboards/{dash['id']}/columns",
        json={"name": "Bugs in v1", "state": "open", "labels": ["bug"], "milestone": "1"},
    ).json()
    assert col["drag_compatible"] is False


def test_create_closed_only_column_is_drag_compatible(client, make_dashboard):
    dash = make_dashboard()
    col = client.post(
        f"/api/dashboards/{dash['id']}/columns",
        json={"name": "Done", "state": "closed", "labels": []},
    ).json()
    assert col["drag_compatible"] is True


def test_columns_get_incrementing_positions(client, make_dashboard):
    dash = make_dashboard()
    first = client.post(f"/api/dashboards/{dash['id']}/columns", json={"name": "A"}).json()
    second = client.post(f"/api/dashboards/{dash['id']}/columns", json={"name": "B"}).json()
    assert first["position"] == 0
    assert second["position"] == 1


def test_delete_column(client, make_dashboard):
    dash = make_dashboard()
    col = client.post(f"/api/dashboards/{dash['id']}/columns", json={"name": "A"}).json()
    resp = client.delete(f"/api/dashboards/{dash['id']}/columns/{col['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/dashboards/{dash['id']}/columns").json() == []


# ---- Issues ----


def _issue(number, **overrides):
    issue = {
        "number": number,
        "title": f"Issue {number}",
        "body": "Body text",
        "state": "open",
        "html_url": f"https://github.com/acme/widgets/issues/{number}",
        "labels": [{"name": "bug", "color": "ff0000", "description": None}],
        "assignees": [],
        "milestone": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "closed_at": None,
        "comments": 0,
    }
    issue.update(overrides)
    return issue


@respx.mock
def test_list_column_issues_filters_out_pull_requests(client, make_dashboard):
    dash = make_dashboard(token="ghp_abcdef123456")
    col = client.post(
        f"/api/dashboards/{dash['id']}/columns", json={"name": "Bugs", "labels": ["bug"]}
    ).json()

    respx.get(f"{GITHUB_API}/repos/acme/widgets/issues").mock(
        return_value=Response(
            200,
            json=[_issue(1), _issue(2, pull_request={"url": "..."})],
        )
    )

    resp = client.get(f"/api/dashboards/{dash['id']}/columns/{col['id']}/issues")
    assert resp.status_code == 200
    numbers = [i["number"] for i in resp.json()]
    assert numbers == [1]


@respx.mock
def test_list_column_issues_flags_local_note(client, make_dashboard):
    dash = make_dashboard(token="ghp_abcdef123456")
    col = client.post(f"/api/dashboards/{dash['id']}/columns", json={"name": "Bugs", "labels": ["bug"]}).json()
    client.post(f"/api/dashboards/{dash['id']}/notes", json={"issue_number": 1, "body": "remember this"})

    respx.get(f"{GITHUB_API}/repos/acme/widgets/issues").mock(return_value=Response(200, json=[_issue(1)]))

    cards = client.get(f"/api/dashboards/{dash['id']}/columns/{col['id']}/issues").json()
    assert cards[0]["has_local_note"] is True


@respx.mock
def test_close_issue(client, make_dashboard):
    dash = make_dashboard(token="ghp_abcdef123456")
    respx.patch(f"{GITHUB_API}/repos/acme/widgets/issues/1").mock(
        return_value=Response(200, json=_issue(1, state="closed", closed_at="2026-01-05T00:00:00Z"))
    )
    resp = client.post(f"/api/dashboards/{dash['id']}/issues/1/close")
    assert resp.status_code == 200
    assert resp.json()["state"] == "closed"


@respx.mock
def test_move_issue_into_label_column_adds_label(client, make_dashboard):
    dash = make_dashboard(token="ghp_abcdef123456")
    col = client.post(f"/api/dashboards/{dash['id']}/columns", json={"name": "Bugs", "labels": ["bug"]}).json()

    add_label_route = respx.post(f"{GITHUB_API}/repos/acme/widgets/issues/1/labels").mock(
        return_value=Response(200, json=[{"name": "bug", "color": "ff0000"}])
    )
    respx.get(f"{GITHUB_API}/repos/acme/widgets/issues/1").mock(return_value=Response(200, json=_issue(1)))

    resp = client.post(f"/api/dashboards/{dash['id']}/issues/1/move", json={"target_column_id": col["id"]})
    assert resp.status_code == 200
    assert add_label_route.called


@respx.mock
def test_move_issue_into_closed_column_closes_issue(client, make_dashboard):
    dash = make_dashboard(token="ghp_abcdef123456")
    col = client.post(f"/api/dashboards/{dash['id']}/columns", json={"name": "Done", "state": "closed"}).json()

    close_route = respx.patch(f"{GITHUB_API}/repos/acme/widgets/issues/1").mock(
        return_value=Response(200, json=_issue(1, state="closed"))
    )

    resp = client.post(f"/api/dashboards/{dash['id']}/issues/1/move", json={"target_column_id": col["id"]})
    assert resp.status_code == 200
    assert close_route.called


def test_move_issue_into_non_drag_compatible_column_rejected(client, make_dashboard):
    dash = make_dashboard(token="ghp_abcdef123456")
    col = client.post(
        f"/api/dashboards/{dash['id']}/columns",
        json={"name": "Bugs in v1", "labels": ["bug"], "milestone": "1"},
    ).json()

    resp = client.post(f"/api/dashboards/{dash['id']}/issues/1/move", json={"target_column_id": col["id"]})
    assert resp.status_code == 400


@respx.mock
def test_list_closed_issues(client, make_dashboard):
    dash = make_dashboard(token="ghp_abcdef123456")
    respx.get(f"{GITHUB_API}/repos/acme/widgets/issues").mock(
        return_value=Response(200, json=[_issue(1, state="closed", closed_at="2026-01-05T00:00:00Z")])
    )
    # days=0 asks for all time; the default window is deliberately short
    # (see test_closed_defaults_to_the_last_seven_days).
    resp = client.get(f"/api/dashboards/{dash['id']}/closed?days=0")
    assert resp.status_code == 200
    assert resp.json()[0]["state"] == "closed"


@respx.mock
def test_get_issue_detail_includes_comments_and_notes(client, make_dashboard):
    dash = make_dashboard(token="ghp_abcdef123456")
    client.post(f"/api/dashboards/{dash['id']}/notes", json={"issue_number": 1, "body": "a note"})

    respx.get(f"{GITHUB_API}/repos/acme/widgets/issues/1").mock(return_value=Response(200, json=_issue(1)))
    respx.get(f"{GITHUB_API}/repos/acme/widgets/issues/1/comments").mock(
        return_value=Response(
            200,
            json=[{"id": 10, "user": {"login": "bob"}, "body": "hi", "created_at": "2026-01-02T00:00:00Z"}],
        )
    )

    detail = client.get(f"/api/dashboards/{dash['id']}/issues/1").json()
    assert detail["comments"][0]["author"] == "bob"
    assert detail["notes"][0]["body"] == "a note"
