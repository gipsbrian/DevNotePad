import respx
from httpx import Response

from tests.conftest import GITHUB_API


def test_settings_start_empty(client):
    data = client.get("/api/settings").json()
    assert data["github_username"] is None
    assert data["has_default_token"] is False
    assert data["default_token_source"] == "none"
    assert "show_my_columns" not in data


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


# ---- No automatic columns on issue boards ----


def test_issue_boards_have_no_automatic_columns_even_with_a_username(client, make_dashboard):
    client.put("/api/settings", json={"github_username": "octocat"})
    dash = make_dashboard(token="ghp_abcdef123456")
    client.post(f"/api/dashboards/{dash['id']}/columns", json={"name": "Bugs", "labels": ["bug"]})

    cols = client.get(f"/api/dashboards/{dash['id']}/columns").json()
    assert [c["name"] for c in cols] == ["Bugs"]
    # The former "Assigned to me" / "Created by me" ids lead nowhere.
    for virtual_id in (-1, -2):
        assert client.get(f"/api/dashboards/{dash['id']}/columns/{virtual_id}/issues").status_code == 404


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
