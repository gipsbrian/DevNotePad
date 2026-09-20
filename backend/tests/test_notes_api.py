import respx
from httpx import Response

from tests.conftest import GITHUB_API


def test_create_list_update_delete_note(client, make_dashboard):
    dash = make_dashboard()
    note = client.post(
        f"/api/dashboards/{dash['id']}/notes", json={"issue_number": 5, "body": "first draft"}
    ).json()
    assert note["synced"] is False
    assert note["github_comment_id"] is None

    listed = client.get(f"/api/dashboards/{dash['id']}/notes?issue_number=5").json()
    assert len(listed) == 1

    updated = client.put(f"/api/notes/{note['id']}", json={"body": "revised"}).json()
    assert updated["body"] == "revised"

    resp = client.delete(f"/api/notes/{note['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/dashboards/{dash['id']}/notes").json() == []


def test_note_never_pushed_automatically(client, make_dashboard):
    """A note must stay local until the user explicitly pushes it."""
    dash = make_dashboard()
    note = client.post(
        f"/api/dashboards/{dash['id']}/notes", json={"issue_number": 5, "body": "private thought"}
    ).json()
    assert note["synced"] is False


@respx.mock
def test_push_note_creates_github_comment_first_time(client, make_dashboard):
    dash = make_dashboard(token="ghp_abcdef123456")
    note = client.post(
        f"/api/dashboards/{dash['id']}/notes", json={"issue_number": 5, "body": "please review"}
    ).json()

    create_route = respx.post(f"{GITHUB_API}/repos/acme/widgets/issues/5/comments").mock(
        return_value=Response(200, json={"id": 555, "body": "please review"})
    )

    resp = client.post(f"/api/notes/{note['id']}/push")
    assert resp.status_code == 200
    data = resp.json()
    assert data["synced"] is True
    assert data["github_comment_id"] == 555
    assert create_route.called


@respx.mock
def test_push_note_updates_existing_comment_on_second_push(client, make_dashboard):
    """Editing an already-pushed note should PATCH the same comment, not
    spam a new one."""
    dash = make_dashboard(token="ghp_abcdef123456")
    note = client.post(
        f"/api/dashboards/{dash['id']}/notes", json={"issue_number": 5, "body": "v1"}
    ).json()

    respx.post(f"{GITHUB_API}/repos/acme/widgets/issues/5/comments").mock(
        return_value=Response(200, json={"id": 555, "body": "v1"})
    )
    client.post(f"/api/notes/{note['id']}/push")

    client.put(f"/api/notes/{note['id']}", json={"body": "v2"})

    update_route = respx.patch(f"{GITHUB_API}/repos/acme/widgets/issues/comments/555").mock(
        return_value=Response(200, json={"id": 555, "body": "v2"})
    )

    resp = client.post(f"/api/notes/{note['id']}/push")
    assert resp.status_code == 200
    assert update_route.called
    assert resp.json()["github_comment_id"] == 555


@respx.mock
def test_push_note_without_token_fails_clearly(client, make_dashboard):
    dash = make_dashboard()  # no token at all
    note = client.post(
        f"/api/dashboards/{dash['id']}/notes", json={"issue_number": 5, "body": "x"}
    ).json()

    respx.post(f"{GITHUB_API}/repos/acme/widgets/issues/5/comments").mock(
        return_value=Response(401, json={"message": "Bad credentials"})
    )

    resp = client.post(f"/api/notes/{note['id']}/push")
    assert resp.status_code == 401


@respx.mock
def test_push_note_uses_the_general_token_saved_in_settings(client, make_dashboard):
    """A board without a token of its own pushes with the saved general
    one -- the same token every other call on the board uses."""
    client.put("/api/settings", json={"default_token": "ghp_saved_general"})
    dash = make_dashboard()
    note = client.post(
        f"/api/dashboards/{dash['id']}/notes", json={"issue_number": 5, "body": "hi"}
    ).json()
    route = respx.post(f"{GITHUB_API}/repos/acme/widgets/issues/5/comments").mock(
        return_value=Response(200, json={"id": 9, "body": "hi"})
    )

    assert client.post(f"/api/notes/{note['id']}/push").status_code == 200
    assert route.calls.last.request.headers["Authorization"] == "Bearer ghp_saved_general"


@respx.mock
def test_commenting_directly_posts_to_github_and_keeps_no_local_note(client, make_dashboard):
    dash = make_dashboard(token="ghp_board")
    route = respx.post(f"{GITHUB_API}/repos/acme/widgets/issues/5/comments").mock(
        return_value=Response(
            201,
            json={"id": 77, "body": "on it", "user": {"login": "tester-gh"}, "created_at": "2026-09-15T10:00:00Z"},
        )
    )

    resp = client.post(f"/api/dashboards/{dash['id']}/issues/5/comments", json={"body": "  on it  "})
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == 77
    assert resp.json()["author"] == "tester-gh"
    assert route.calls.last.request.headers["Authorization"] == "Bearer ghp_board"
    assert route.calls.last.request.read() == b'{"body":"on it"}'
    # Nothing private was saved along the way.
    assert client.get(f"/api/dashboards/{dash['id']}/notes").json() == []


@respx.mock
def test_an_empty_comment_never_reaches_github(client, make_dashboard):
    dash = make_dashboard(token="ghp_board")
    route = respx.post(f"{GITHUB_API}/repos/acme/widgets/issues/5/comments")
    resp = client.post(f"/api/dashboards/{dash['id']}/issues/5/comments", json={"body": "   "})
    assert resp.status_code == 422
    assert not route.called


@respx.mock
def test_githubs_refusal_to_comment_is_passed_through(client, make_dashboard):
    dash = make_dashboard(token="ghp_readonly")
    respx.post(f"{GITHUB_API}/repos/acme/widgets/issues/5/comments").mock(
        return_value=Response(403, json={"message": "Resource not accessible by personal access token"})
    )
    resp = client.post(f"/api/dashboards/{dash['id']}/issues/5/comments", json={"body": "hi"})
    assert resp.status_code == 403
    assert "not accessible" in resp.json()["detail"]


@respx.mock
def test_listing_an_issues_comments_costs_one_github_call(client, make_dashboard):
    dash = make_dashboard(token="ghp_board")
    route = respx.get(f"{GITHUB_API}/repos/acme/widgets/issues/5/comments").mock(
        return_value=Response(
            200,
            json=[
                {"id": 1, "body": "first", "user": {"login": "ann"}, "created_at": "2026-09-01T10:00:00Z"},
                {"id": 2, "body": "second", "user": {"login": "bob"}, "created_at": "2026-09-02T10:00:00Z"},
            ],
        )
    )
    resp = client.get(f"/api/dashboards/{dash['id']}/issues/5/comments")
    assert resp.status_code == 200, resp.text
    assert [(c["author"], c["body"]) for c in resp.json()] == [("ann", "first"), ("bob", "second")]
    assert route.call_count == 1
