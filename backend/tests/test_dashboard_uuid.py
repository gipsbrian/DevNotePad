import re
from uuid import uuid4

from sqlalchemy import text
from sqlmodel import select

from app.db import _backfill_dashboard_uuids
from app.models import Dashboard

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def test_the_public_id_is_a_uuid(make_dashboard):
    assert UUID_RE.match(make_dashboard()["id"])


def test_the_row_id_is_not_accepted_in_the_url(client, session, make_dashboard):
    board = make_dashboard()
    row = session.exec(select(Dashboard).where(Dashboard.uuid == board["id"])).one()

    # The point of the change: the sequential key opens nothing.
    assert client.get(f"/api/dashboards/{row.id}").status_code == 404
    assert client.get(f"/api/dashboards/{board['id']}").status_code == 200


def test_an_unknown_uuid_is_a_404(client):
    assert client.get(f"/api/dashboards/{uuid4()}").status_code == 404


def test_two_boards_get_different_uuids(make_dashboard):
    assert make_dashboard(name="one")["id"] != make_dashboard(name="two")["id"]


def test_nested_resources_are_reached_by_uuid(client, make_dashboard):
    board = make_dashboard()
    uuid = board["id"]

    created = client.post(
        f"/api/dashboards/{uuid}/columns", json={"name": "Triage", "labels": ["bug"]}
    )
    assert created.status_code == 200
    assert created.json()["dashboard_id"] == uuid

    sticky = client.post(f"/api/dashboards/{uuid}/sticky-notes", json={"body": "hello"})
    assert sticky.status_code == 200
    assert sticky.json()["dashboard_id"] == uuid

    note = client.post(
        f"/api/dashboards/{uuid}/notes", json={"issue_number": 4, "body": "a note"}
    )
    assert note.status_code == 200
    assert note.json()["dashboard_id"] == uuid


def test_backfill_gives_a_pre_existing_row_a_uuid(session, make_dashboard):
    """A board that predates the column. Blanked rather than NULLed: on a
    freshly created table the column is NOT NULL, whereas the ALTER that
    adds it to an existing database leaves it nullable. The backfill
    treats both as "no uuid yet"."""
    board = make_dashboard()
    session.execute(
        text("UPDATE dashboard SET uuid = '' WHERE uuid = :uuid"), {"uuid": board["id"]}
    )
    session.commit()

    _backfill_dashboard_uuids(session.connection())
    session.commit()

    filled = session.execute(text("SELECT uuid FROM dashboard")).scalars().all()
    assert all(u and UUID_RE.match(u) for u in filled)
