from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..access import VIEW, board_access, get_board, write_token
from ..auth import require_user
from ..db import get_session
from ..github_client import GitHubClient, GitHubError
from ..models import Dashboard, LocalNote, User
from ..schemas import NoteCreate, NoteOut, NoteUpdate

router = APIRouter(prefix="/api", tags=["notes"])


def _note_out(n: LocalNote, session: Session) -> NoteOut:
    # The dashboard's public id, never its row id.
    dashboard = session.get(Dashboard, n.dashboard_id)
    return NoteOut(
        id=n.id,
        dashboard_id=dashboard.uuid,
        issue_number=n.issue_number,
        body=n.body,
        created_at=n.created_at,
        updated_at=n.updated_at,
        synced=n.synced,
        github_comment_id=n.github_comment_id,
    )


@router.get("/dashboards/{dashboard_uuid}/notes", response_model=list[NoteOut])
def list_notes(dashboard_uuid: str, issue_number: int | None = None, session: Session = Depends(get_session), user: User = Depends(require_user)):
    dashboard = get_board(session, dashboard_uuid, user, VIEW)
    query = select(LocalNote).where(LocalNote.dashboard_id == dashboard.id, LocalNote.user_id == user.id)
    if issue_number is not None:
        query = query.where(LocalNote.issue_number == issue_number)
    notes = session.exec(query).all()
    return [_note_out(n, session) for n in notes]


@router.post("/dashboards/{dashboard_uuid}/notes", response_model=NoteOut)
def create_note(dashboard_uuid: str, payload: NoteCreate, session: Session = Depends(get_session), user: User = Depends(require_user)):
    dashboard = get_board(session, dashboard_uuid, user, VIEW)
    note = LocalNote(
        dashboard_id=dashboard.id,
        user_id=user.id,
        issue_number=payload.issue_number,
        body=payload.body,
    )
    session.add(note)
    session.commit()
    session.refresh(note)
    return _note_out(note, session)


def _get_note_or_404(session: Session, note_id: int, user: User) -> LocalNote:
    """Notes are addressed by a bare, sequential id. A note is its writer's
    alone, and only while they can still reach its board."""
    note = session.get(LocalNote, note_id)
    dashboard = session.get(Dashboard, note.dashboard_id) if note else None
    if not note or not dashboard or note.user_id != user.id or board_access(session, dashboard, user) is None:
        raise HTTPException(404, "Note not found")
    return note


@router.put("/notes/{note_id}", response_model=NoteOut)
def update_note(note_id: int, payload: NoteUpdate, session: Session = Depends(get_session), user: User = Depends(require_user)):
    note = _get_note_or_404(session, note_id, user)
    note.body = payload.body
    note.updated_at = datetime.now(timezone.utc)
    session.add(note)
    session.commit()
    session.refresh(note)
    return _note_out(note, session)


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, session: Session = Depends(get_session), user: User = Depends(require_user)):
    note = _get_note_or_404(session, note_id, user)
    session.delete(note)
    session.commit()


@router.post("/notes/{note_id}/push", response_model=NoteOut)
async def push_note(note_id: int, session: Session = Depends(get_session), user: User = Depends(require_user)):
    """Explicit action only -- never pushed silently. Creates a
    GitHub comment the first time; edits update that same comment on
    later pushes rather than spamming the thread."""
    note = _get_note_or_404(session, note_id, user)
    dashboard = session.get(Dashboard, note.dashboard_id)
    if not dashboard:
        raise HTTPException(404, "Dashboard not found")

    # Pushing is a write to GitHub, so it follows the board's write rules.
    client = GitHubClient(write_token(session, dashboard, user))
    try:
        if note.github_comment_id:
            await client.update_comment(dashboard.repo_owner, dashboard.repo_name, note.github_comment_id, note.body)
        else:
            comment = await client.create_comment(
                dashboard.repo_owner, dashboard.repo_name, note.issue_number, note.body
            )
            note.github_comment_id = comment["id"]
    except GitHubError as exc:
        raise HTTPException(exc.status_code, exc.message)
    finally:
        await client.aclose()

    note.synced = True
    session.add(note)
    session.commit()
    session.refresh(note)
    return _note_out(note, session)
