from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..auth import require_user
from ..db import get_session
from ..github_client import GitHubClient
from ..insights import clear_cache as clear_insights_cache
from ..models import User
from ..schemas import SettingsOut, SettingsUpdate
from ..settings_store import general_org_url, general_token, get_settings, token_source

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _out(session: Session, user: User) -> SettingsOut:
    row = get_settings(session, user.id)
    return SettingsOut(
        github_username=row.github_username,
        default_org_url=general_org_url(session, user.id),
        show_my_columns=row.show_my_columns,
        has_default_token=bool(general_token(session, user.id)),
        default_token_source=token_source(session, user.id),
    )


@router.get("", response_model=SettingsOut)
def read_settings(session: Session = Depends(get_session), user: User = Depends(require_user)):
    return _out(session, user)


@router.get("/detect-username")
async def detect_username(session: Session = Depends(get_session), user: User = Depends(require_user)):
    """Who the general token belongs to, so the settings form can offer it
    instead of making the user look it up."""
    token = general_token(session, user.id)
    if not token:
        return {"login": None}
    client = GitHubClient(token)
    try:
        return {"login": await client.get_authenticated_login()}
    finally:
        await client.aclose()


@router.put("", response_model=SettingsOut)
def update_settings(payload: SettingsUpdate, session: Session = Depends(get_session), user: User = Depends(require_user)):
    row = get_settings(session, user.id)

    if payload.github_username is not None:
        row.github_username = payload.github_username.strip().lstrip("@") or None
    if payload.default_org_url is not None:
        row.default_org_url = payload.default_org_url.strip() or None
    if payload.default_token is not None:
        # An empty string clears the saved token and falls back to .env.
        row.default_token = payload.default_token.strip() or None
    if payload.show_my_columns is not None:
        row.show_my_columns = payload.show_my_columns

    session.add(row)
    session.commit()
    # The username, org and token all feed analytics queries.
    clear_insights_cache(user.id)
    return _out(session, user)
