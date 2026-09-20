"""Resolution of an account's settings row and the effective token.

Precedence for the "general" token is: whatever the account saved in the
UI, then -- for the instance owner only -- GIT_TOKEN from .env. A board's
own token always wins over both.
"""

from typing import Optional

from sqlmodel import Session, func, select

from .config import settings as env_settings
from .models import AppSettings, User


def get_settings(session: Session, user_id: int) -> AppSettings:
    row = session.exec(select(AppSettings).where(AppSettings.user_id == user_id)).first()
    if row is None:
        row = AppSettings(user_id=user_id)
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def is_instance_owner(session: Session, user_id: int) -> bool:
    """The first account -- the one created from ADMIN_* in .env. The .env
    token and org belong to whoever runs the instance, so they're only
    ever lent to that account, never to anyone who registered later."""
    return session.exec(select(func.min(User.id))).one() == user_id


def general_token(session: Session, user_id: int) -> Optional[str]:
    saved = get_settings(session, user_id).default_token
    if saved:
        return saved
    return (env_settings.git_token or None) if is_instance_owner(session, user_id) else None


def general_org_url(session: Session, user_id: int) -> Optional[str]:
    saved = get_settings(session, user_id).default_org_url
    if saved:
        return saved
    return (env_settings.git_org_url or None) if is_instance_owner(session, user_id) else None


def token_source(session: Session, user_id: int) -> str:
    if get_settings(session, user_id).default_token:
        return "settings"
    if env_settings.git_token and is_instance_owner(session, user_id):
        return "env"
    return "none"
