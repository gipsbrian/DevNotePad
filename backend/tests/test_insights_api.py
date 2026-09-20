import respx
from httpx import Response

from tests.conftest import GITHUB_API

SEARCH = f"{GITHUB_API}/search/issues"


def _configure(client, org="https://github.com/acme", user="octocat", token="ghp_abcdef123456"):
    client.put(
        "/api/settings",
        json={"github_username": user, "default_org_url": org, "default_token": token},
    )


def test_insights_needs_an_org(client):
    client.put("/api/settings", json={"default_token": "ghp_abcdef123456"})
    resp = client.get("/api/insights?scope=me")
    assert resp.status_code == 400
    assert "organization" in resp.json()["detail"].lower()


def test_insights_needs_a_username_for_personal_scope(client):
    client.put(
        "/api/settings",
        json={"default_org_url": "https://github.com/acme", "default_token": "ghp_abc"},
    )
    resp = client.get("/api/insights?scope=me")
    assert resp.status_code == 400
    assert "username" in resp.json()["detail"].lower()


def test_insights_rejects_an_unknown_scope(client):
    _configure(client)
    assert client.get("/api/insights?scope=everything").status_code == 422


@respx.mock
def test_personal_insights_shape(client):
    _configure(client)
    respx.get(SEARCH).mock(
        return_value=Response(
            200,
            json={
                "total_count": 5,
                "items": [
                    {"repository_url": "https://api.github.com/repos/acme/widgets"},
                    {"repository_url": "https://api.github.com/repos/acme/widgets"},
                    {"repository_url": "https://api.github.com/repos/acme/gadgets"},
                ],
            },
        )
    )

    data = client.get("/api/insights?scope=me").json()
    assert data["scope"] == "me"
    assert data["org"] == "acme"
    assert data["username"] == "octocat"
    assert data["window_days"] == 42
    assert len(data["weekly"]) == 6
    assert {"repo": "widgets", "count": 5} in data["top_repos"]


@respx.mock
def test_personal_scope_filters_by_the_person(client):
    """Opened is attributed to the author, closed to the assignee."""
    _configure(client)
    route = respx.get(SEARCH).mock(return_value=Response(200, json={"total_count": 0, "items": []}))
    client.get("/api/insights?scope=me&username=someone-else")

    queries = [str(call.request.url.params["q"]) for call in route.calls]
    assert any("author:someone-else created:" in q for q in queries)
    assert any("assignee:someone-else closed:" in q for q in queries)
    assert all("org:acme" in q and "type:issue" in q for q in queries)


@respx.mock
def test_org_scope_does_not_filter_by_a_person(client):
    _configure(client)
    route = respx.get(SEARCH).mock(return_value=Response(200, json={"total_count": 9, "items": []}))
    data = client.get("/api/insights?scope=org").json()

    queries = [str(call.request.url.params["q"]) for call in route.calls]
    assert not any("author:" in q or "assignee:" in q for q in queries)
    assert data["username"] is None
    assert data["totals"]["open"] == 9


@respx.mock
def test_search_failures_are_reported_not_rendered_as_zero(client):
    """A swallowed search error used to come back as `total_count: 0`,
    which reads as "this org has no issues" rather than as a failure."""
    _configure(client)
    respx.get(SEARCH).mock(
        return_value=Response(403, json={"message": "API rate limit exceeded"})
    )

    resp = client.get("/api/insights?scope=org")
    assert resp.status_code == 429
    assert "rate limit" in resp.json()["detail"].lower()


@respx.mock
def test_results_are_cached_so_a_revisit_costs_nothing(client):
    _configure(client)
    route = respx.get(SEARCH).mock(return_value=Response(200, json={"total_count": 1, "items": []}))

    client.get("/api/insights?scope=me")
    first = len(route.calls)
    assert first > 0

    client.get("/api/insights?scope=me")
    assert len(route.calls) == first  # served from cache


@respx.mock
def test_members_always_include_the_configured_user(client):
    _configure(client)
    respx.get(f"{GITHUB_API}/orgs/acme/members").mock(
        return_value=Response(200, json=[{"login": "alice", "avatar_url": "https://x/a.png"}])
    )
    logins = [m["login"] for m in client.get("/api/insights/members").json()]
    assert "octocat" in logins and "alice" in logins


@respx.mock
def test_members_degrade_when_the_org_cannot_be_read(client):
    _configure(client)
    respx.get(f"{GITHUB_API}/orgs/acme/members").mock(
        return_value=Response(403, json={"message": "Forbidden"})
    )
    logins = [m["login"] for m in client.get("/api/insights/members").json()]
    assert logins == ["octocat"]
