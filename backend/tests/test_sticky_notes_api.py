def test_create_and_list(client, make_dashboard):
    dash = make_dashboard()
    note = client.post(
        f"/api/dashboards/{dash['id']}/sticky-notes", json={"body": "- [ ] ship the thing"}
    ).json()
    assert note["body"] == "- [ ] ship the thing"
    assert note["pinned"] is False and note["archived"] is False

    listed = client.get(f"/api/dashboards/{dash['id']}/sticky-notes").json()
    assert [n["id"] for n in listed] == [note["id"]]


def test_newest_first(client, make_dashboard):
    dash = make_dashboard()
    first = client.post(f"/api/dashboards/{dash['id']}/sticky-notes", json={"body": "one"}).json()
    second = client.post(f"/api/dashboards/{dash['id']}/sticky-notes", json={"body": "two"}).json()

    listed = client.get(f"/api/dashboards/{dash['id']}/sticky-notes").json()
    assert [n["id"] for n in listed] == [second["id"], first["id"]]


def test_pinned_note_sits_on_top(client, make_dashboard):
    dash = make_dashboard()
    older = client.post(f"/api/dashboards/{dash['id']}/sticky-notes", json={"body": "older"}).json()
    client.post(f"/api/dashboards/{dash['id']}/sticky-notes", json={"body": "newer"})

    client.put(f"/api/dashboards/{dash['id']}/sticky-notes/{older['id']}", json={"pinned": True})
    listed = client.get(f"/api/dashboards/{dash['id']}/sticky-notes").json()
    assert listed[0]["id"] == older["id"]
    assert listed[0]["pinned"] is True


def test_archiving_hides_a_note_but_keeps_it(client, make_dashboard):
    dash = make_dashboard()
    note = client.post(f"/api/dashboards/{dash['id']}/sticky-notes", json={"body": "done"}).json()

    client.put(f"/api/dashboards/{dash['id']}/sticky-notes/{note['id']}", json={"archived": True})
    assert client.get(f"/api/dashboards/{dash['id']}/sticky-notes").json() == []

    archived = client.get(f"/api/dashboards/{dash['id']}/sticky-notes?archived=true").json()
    assert [n["id"] for n in archived] == [note["id"]]


def test_archiving_unpins(client, make_dashboard):
    """A pinned note that gets archived shouldn't come back still holding
    the top of the stack."""
    dash = make_dashboard()
    note = client.post(f"/api/dashboards/{dash['id']}/sticky-notes", json={"body": "x"}).json()
    client.put(f"/api/dashboards/{dash['id']}/sticky-notes/{note['id']}", json={"pinned": True})

    client.put(f"/api/dashboards/{dash['id']}/sticky-notes/{note['id']}", json={"archived": True})
    restored = client.put(
        f"/api/dashboards/{dash['id']}/sticky-notes/{note['id']}", json={"archived": False}
    ).json()
    assert restored["pinned"] is False


def test_editing_body_touches_updated_at_only(client, make_dashboard):
    dash = make_dashboard()
    note = client.post(f"/api/dashboards/{dash['id']}/sticky-notes", json={"body": "a"}).json()
    edited = client.put(
        f"/api/dashboards/{dash['id']}/sticky-notes/{note['id']}", json={"body": "b"}
    ).json()
    assert edited["body"] == "b"
    assert edited["created_at"] == note["created_at"]
    assert edited["updated_at"] >= note["updated_at"]


def test_delete(client, make_dashboard):
    dash = make_dashboard()
    note = client.post(f"/api/dashboards/{dash['id']}/sticky-notes", json={"body": "x"}).json()
    assert client.delete(f"/api/dashboards/{dash['id']}/sticky-notes/{note['id']}").status_code == 204
    assert client.get(f"/api/dashboards/{dash['id']}/sticky-notes").json() == []


def test_notes_are_scoped_to_their_board(client, make_dashboard):
    a = make_dashboard(name="A")
    b = make_dashboard(name="B")
    note = client.post(f"/api/dashboards/{a['id']}/sticky-notes", json={"body": "a-note"}).json()

    assert client.get(f"/api/dashboards/{b['id']}/sticky-notes").json() == []
    assert client.put(
        f"/api/dashboards/{b['id']}/sticky-notes/{note['id']}", json={"body": "hijack"}
    ).status_code == 404


def test_unknown_dashboard_is_404(client):
    assert client.get("/api/dashboards/999/sticky-notes").status_code == 404
    assert client.post("/api/dashboards/999/sticky-notes", json={"body": "x"}).status_code == 404
