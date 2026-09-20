from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..access import VIEW, get_board
from ..auth import require_user
from ..db import get_session
from ..models import StickyNote, User
from ..schemas import StickyNoteCreate, StickyNoteOut, StickyNoteUpdate

router = APIRouter(prefix="/api/dashboards/{dashboard_uuid}/sticky-notes", tags=["sticky-notes"])


def _out(n: StickyNote, dashboard_uuid: str) -> StickyNoteOut:
    return StickyNoteOut(
        id=n.id,
        dashboard_id=dashboard_uuid,
        body=n.body,
        pinned=n.pinned,
        archived=n.archived,
        created_at=n.created_at,
        updated_at=n.updated_at,
    )


def _get_or_404(session: Session, dashboard_pk: int, note_id: int, user: User) -> StickyNote:
    note = session.get(StickyNote, note_id)
    # Sticky notes are private to whoever wrote them, even on a shared board.
    if not note or note.dashboard_id != dashboard_pk or note.user_id != user.id:
        raise HTTPException(404, "Sticky note not found")
    return note


@router.get("", response_model=list[StickyNoteOut])
def list_sticky_notes(
    dashboard_uuid: str, archived: bool = False, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    """Pinned first, then newest — the order the stack is drawn in."""
    dashboard = get_board(session, dashboard_uuid, user, VIEW)
    notes = session.exec(
        select(StickyNote)
        .where(StickyNote.dashboard_id == dashboard.id, StickyNote.user_id == user.id, StickyNote.archived == archived)
        .order_by(StickyNote.pinned.desc(), StickyNote.created_at.desc())
    ).all()
    return [_out(n, dashboard_uuid) for n in notes]


@router.post("", response_model=StickyNoteOut)
def create_sticky_note(
    dashboard_uuid: str, payload: StickyNoteCreate, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    dashboard = get_board(session, dashboard_uuid, user, VIEW)
    note = StickyNote(dashboard_id=dashboard.id, user_id=user.id, body=payload.body)
    session.add(note)
    session.commit()
    session.refresh(note)
    return _out(note, dashboard_uuid)


@router.put("/{note_id}", response_model=StickyNoteOut)
def update_sticky_note(
    dashboard_uuid: str,
    note_id: int,
    payload: StickyNoteUpdate,
    session: Session = Depends(get_session), user: User = Depends(require_user),
):
    dashboard = get_board(session, dashboard_uuid, user, VIEW)
    note = _get_or_404(session, dashboard.id, note_id, user)

    if payload.body is not None:
        note.body = payload.body
        note.updated_at = datetime.now(timezone.utc)
    if payload.archived is not None:
        note.archived = payload.archived
        # An archived note shouldn't keep occupying the top of the stack.
        if payload.archived:
            note.pinned = False
    if payload.pinned is not None:
        note.pinned = payload.pinned

    session.add(note)
    session.commit()
    session.refresh(note)
    return _out(note, dashboard_uuid)


@router.delete("/{note_id}", status_code=204)
def delete_sticky_note(dashboard_uuid: str, note_id: int, session: Session = Depends(get_session), user: User = Depends(require_user)):
    dashboard = get_board(session, dashboard_uuid, user, VIEW)
    session.delete(_get_or_404(session, dashboard.id, note_id, user))
    session.commit()
