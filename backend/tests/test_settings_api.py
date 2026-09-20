import respx
from httpx import Response

from tests.conftest import GITHUB_API


def test_settings_start_empty(client):
    data = client.get("/api/settings").json()
    assert data["github_username"] is None
    assert data["has_default_token"] is False
    assert data["default_token_source"] == "none"
    assert data["show_my_columns"] is True


def test_settings_round_trip(client):
    resp = client.put(
        "/api/settings",
        json={"github_username": "octocat", "default_org_url": "https://github.com/acme"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["github_username"] == "octocat"
    assert data["default_org_url"] == "https://github.com/acme"
    assert client.get("/api/settings").json()["github_username"] == "octocat"


def test_username_is_normalized(client):
    data = client.put("/api/settings", json={"github_username": " @octocat "}).json()
    assert data["github_username"] == "octocat"


def test_default_token_is_never_returned(client):
    data = client.put("/api/settings", json={"default_token": "ghp_supersecret123"}).json()
    assert data["has_default_token"] is True
    assert data["default_token_source"] == "settings"
    assert "ghp_supersecret123" not in str(data)


def test_empty_token_clears_it(client):
    client.put("/api/settings", json={"default_token": "ghp_supersecret123"})
    data = client.put("/api/settings", json={"default_token": ""}).json()
    assert data["has_default_token"] is False


# ---- The two automatic columns ----


def test_no_my_columns_until_a_username_is_set(client, make_dashboard):
    dash = make_dashboard()
    cols = client.get(f"/api/dashboards/{dash['id']}/columns").json()
    assert cols == []


def test_my_columns_are_appended_last_on_every_board(client, make_dashboard):
    client.put("/api/settings", json={"github_username": "octocat"})
    dash = make_dashboard()
    client.post(f"/api/dashboards/{dash['id']}/columns", json={"name": "Bugs", "labels": ["bug"]})

    cols = client.get(f"/api/dashboards/{dash['id']}/columns").json()
    assert [c["name"] for c in cols] == ["Bugs", "Assigned to me", "Created by me"]

    assigned, created = cols[1], cols[2]
    assert assigned["virtual"] is True and created["virtual"] is True
    assert assigned["assignee"] == "octocat"
    assert created["creator"] == "octocat"
    # Virtual columns are never a drop target — there's no single
    # unambiguous mutation for "make this mine".
    assert assigned["drag_compatible"] is False
    assert created["drag_compatible"] is False


def test_my_columns_follow_a_username_change(client, make_dashboard):
    client.put("/api/settings", json={"github_username": "old-name"})
    dash = make_dashboard()
    client.put("/api/settings", json={"github_username": "new-name"})
    cols = client.get(f"/api/dashboards/{dash['id']}/columns").json()
    assert cols[0]["assignee"] == "new-name"


def test_my_columns_can_be_switched_off(client, make_dashboard):
    client.put("/api/settings", json={"github_username": "octocat", "show_my_columns": False})
    dash = make_dashboard()
    assert client.get(f"/api/dashboards/{dash['id']}/columns").json() == []


@respx.mock
def test_assigned_to_me_column_queries_github_by_assignee(client, make_dashboard):
    client.put("/api/settings", json={"github_username": "octocat"})
    dash = make_dashboard(token="ghp_abcdef123456")

    route = respx.get(f"{GITHUB_API}/repos/acme/widgets/issues").mock(
        return_value=Response(200, json=[])
    )
    resp = client.get(f"/api/dashboards/{dash['id']}/columns/-1/issues")
    assert resp.status_code == 200
    assert route.calls.last.request.url.params["assignee"] == "octocat"


@respx.mock
def test_created_by_me_column_queries_github_by_creator(client, make_dashboard):
    client.put("/api/settings", json={"github_username": "octocat"})
    dash = make_dashboard(token="ghp_abcdef123456")

    route = respx.get(f"{GITHUB_API}/repos/acme/widgets/issues").mock(
        return_value=Response(200, json=[])
    )
    resp = client.get(f"/api/dashboards/{dash['id']}/columns/-2/issues")
    assert resp.status_code == 200
    assert route.calls.last.request.url.params["creator"] == "octocat"


def test_virtual_column_without_username_explains_itself(client, make_dashboard):
    dash = make_dashboard(token="ghp_abcdef123456")
    resp = client.get(f"/api/dashboards/{dash['id']}/columns/-1/issues")
    assert resp.status_code == 404
    assert "username" in resp.json()["detail"].lower()


# ---- The general token falls through to boards ----


@respx.mock
def test_board_without_own_token_uses_the_general_one(client, make_dashboard):
    client.put("/api/settings", json={"default_token": "ghp_generaltoken"})
    dash = make_dashboard()  # no per-board token

    route = respx.get(f"{GITHUB_API}/repos/acme/widgets").mock(
        return_value=Response(200, json={"permissions": {"pull": True, "push": False}})
    )
    detail = client.get(f"/api/dashboards/{dash['id']}").json()

    assert route.calls.last.request.headers["authorization"] == "Bearer ghp_generaltoken"
    assert detail["token_info"]["token_type"] == "classic-pat"


@respx.mock
def test_board_token_wins_over_the_general_one(client, make_dashboard):
    client.put("/api/settings", json={"default_token": "ghp_generaltoken"})
    dash = make_dashboard(token="ghp_boardtoken")

    route = respx.get(f"{GITHUB_API}/repos/acme/widgets").mock(
        return_value=Response(200, json={"permissions": {"pull": True, "push": True}})
    )
    client.get(f"/api/dashboards/{dash['id']}")
    assert route.calls.last.request.headers["authorization"] == "Bearer ghp_boardtoken"
