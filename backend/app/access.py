"""Who may do what with a board, and with whose GitHub token.

Every board route asks here. The rules:

| Board                               | Owner  | Org admin | Shared-with | Other member |
|-------------------------------------|--------|-----------|-------------|--------------|
| organization board                  | -      | manage    | -           | view         |
| personal, private                   | manage | -         | -           | -            |
| personal, shared with members       | manage | -         | view        | -            |
| personal, shared with organisation  | manage | view      | view        | view         |

Nobody outside the board's organisation (or removed from it) reaches it.

Reading GitHub uses the board's own token, else -- for a personal board --
its owner's token, or for an organisation board the organisation's token.
Writing to GitHub always uses the acting person's own token, and is only
allowed on your own personal boards and on organisation boards.
"""

from typing import Optional

from fastapi import HTTPException, status
from sqlmodel import Session, select

from .models import BoardShare, Dashboard, Organization, User
from .orgs import membership
from .settings_store import general_token

VIEW = "view"
MANAGE = "manage"


def board_access(session: Session, board: Dashboard, user: User) -> Optional[str]:
    if board.organization_id is None:
        return None
    member = membership(session, board.organization_id, user.id)
    if member is None:
        return None
    if board.kind == "organization":
        return MANAGE if member.role == "admin" else VIEW
    if board.owner_id == user.id:
        return MANAGE
    if board.shared_with_organization:
        return VIEW
    shared = session.exec(
        select(BoardShare).where(BoardShare.dashboard_id == board.id, BoardShare.user_id == user.id)
    ).first()
    return VIEW if shared else None


def get_board(session: Session, board_uuid: str, user: User, need: str = VIEW) -> Dashboard:
    """A board this person may reach. Without access it reads as missing, so
    a uuid can't be probed; with view access, managing is plainly refused."""
    board = session.exec(select(Dashboard).where(Dashboard.uuid == board_uuid)).first()
    access = board_access(session, board, user) if board else None
    if access is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dashboard not found")
    if need == MANAGE and access != MANAGE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can view this board, but not change it.")
    return board


def read_token(session: Session, board: Dashboard) -> Optional[str]:
    if board.token:
        return board.token
    if board.kind == "organization":
        organization = session.get(Organization, board.organization_id)
        return organization.token if organization else None
    return general_token(session, board.owner_id)


def write_block_reason(session: Session, board: Dashboard, user: User) -> Optional[str]:
    """Why this person can't make changes on GitHub from this board, or None
    when they can."""
    access = board_access(session, board, user)
    if board.kind == "organization":
        if access is None:
            return "You don't have access to this board."
        if not general_token(session, user.id):
            return "Add your own GitHub token in settings to make changes from this board."
        return None
    if access != MANAGE:
        return "This board is shared with you to view. Only its owner can make changes."
    return None


def write_token(session: Session, board: Dashboard, user: User) -> Optional[str]:
    """The token a GitHub write from this board goes out with: always the
    acting person's own, so GitHub records who did it and nobody acts
    through someone else's token."""
    reason = write_block_reason(session, board, user)
    if reason:
        raise HTTPException(status.HTTP_403_FORBIDDEN, reason)
    if board.kind == "organization":
        return general_token(session, user.id)
    # Your own personal board: its own token if it has one -- yours too.
    return board.token or general_token(session, user.id)
