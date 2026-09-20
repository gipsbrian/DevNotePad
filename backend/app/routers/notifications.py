from fastapi import APIRouter, Depends, Response, status
from sqlmodel import Session, func, select

from ..auth import require_user
from ..db import get_session
from ..membership_flows import now
from ..models import Notification, Organization, User
from ..schemas import NotificationOut, NotificationsOut, NotificationsRead

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

LIMIT = 30


@router.get("", response_model=NotificationsOut)
def list_notifications(session: Session = Depends(get_session), user: User = Depends(require_user)):
    unread = session.exec(
        select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.read_at == None)  # noqa: E711
    ).one()
    rows = session.exec(
        select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(LIMIT)
    ).all()
    items = []
    for n in rows:
        organization = session.get(Organization, n.organization_id) if n.organization_id else None
        actor = session.get(User, n.actor_id) if n.actor_id else None
        items.append(
            NotificationOut(
                id=n.id,
                kind=n.kind,
                organization_id=organization.uuid if organization else None,
                organization_name=organization.name if organization else None,
                actor=actor.username if actor else None,
                created_at=n.created_at,
                read=n.read_at is not None,
            )
        )
    return NotificationsOut(unread=unread, items=items)


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(payload: NotificationsRead, session: Session = Depends(get_session), user: User = Depends(require_user)) -> Response:
    query = select(Notification).where(Notification.user_id == user.id, Notification.read_at == None)  # noqa: E711
    if payload.ids is not None:
        query = query.where(Notification.id.in_(payload.ids))
    for n in session.exec(query).all():
        n.read_at = now()
        session.add(n)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
