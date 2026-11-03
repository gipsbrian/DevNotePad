"""PR boards: pull requests across a GitHub org.

Two automatic columns per viewer (their open PRs, and PRs waiting on their
review) built from their saved GitHub username, plus tracking columns that
hold whatever PRs are dropped into them.
"""

import asyncio
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..access import MANAGE, VIEW, get_board, read_token
from ..auth import require_user
from ..db import get_session
from ..github_client import GitHubClient, GitHubError
from ..repo_ref import parse_org_ref
from ..models import Column, Dashboard, TrackedPull, User
from ..schemas import AssigneeOut, LabelOut, PullCardOut, TrackPullRequest
from ..serializers import _parse_dt, age_in_days
from ..settings_store import get_settings
from .dashboards import TRACKING_LIMIT, VIRTUAL_MY_PULLS_ID, VIRTUAL_REVIEW_ID, _get_column_or_404

router = APIRouter(prefix="/api/dashboards", tags=["pulls"])

# owner/name as GitHub allows them; it goes into API paths.
_REPO = re.compile(r"^[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}$")


def _pull_board(session: Session, dashboard_uuid: str, user: User, level: str) -> Dashboard:
    dashboard = get_board(session, dashboard_uuid, user, level)
    if dashboard.subject != "pulls":
        raise HTTPException(400, "This isn't a PR board.")
    return dashboard


def _repo_of(item: dict) -> str:
    # ".../repos/owner/name" on both search results and issue payloads.
    return "/".join(item["repository_url"].rsplit("/", 2)[-2:])


def _to_card(item: dict) -> PullCardOut:
    created_at = _parse_dt(item["created_at"])
    author = item.get("user")
    return PullCardOut(
        repo=_repo_of(item),
        number=item["number"],
        title=item["title"],
        html_url=item["html_url"],
        author=AssigneeOut(login=author["login"], avatar_url=author["avatar_url"]) if author else None,
        draft=bool(item.get("draft")),
        labels=[LabelOut(name=l["name"], color=l["color"], description=l.get("description")) for l in item.get("labels", [])],
        created_at=created_at,
        updated_at=_parse_dt(item["updated_at"]),
        comments_count=item.get("comments", 0),
        age_days=age_in_days(created_at, None),
    )


def _trackable(item: Optional[dict], dashboard: Dashboard) -> bool:
    """An open pull request, still in the board's org."""
    if not item or item.get("state") != "open" or "pull_request" not in item:
        return False
    return _repo_of(item).split("/")[0].lower() == dashboard.repo_owner.lower()


def _tracking_column(session: Session, dashboard: Dashboard, column_id: int) -> Column:
    column = _get_column_or_404(session, dashboard.id, column_id)
    if column.kind != "tracking":
        raise HTTPException(400, "Only tracking columns take dropped pull requests.")
    return column


async def _tracked(session: Session, dashboard: Dashboard, column: Column) -> list[dict]:
    """The column's PRs, newest first. Merged, closed or deleted ones are
    dropped from the column on the way."""
    rows = session.exec(
        select(TrackedPull)
        .where(TrackedPull.column_id == column.id)
        .order_by(TrackedPull.added_at.desc(), TrackedPull.id.desc())
    ).all()
    if not rows:
        return []
    client = GitHubClient(read_token(session, dashboard))
    gate = asyncio.Semaphore(8)

    async def fetch(row: TrackedPull) -> Optional[dict]:
        owner, name = row.repo.split("/")
        async with gate:
            try:
                return await client.get_issue(owner, name, row.number)
            except GitHubError as exc:
                if exc.status_code in (404, 410):
                    return None
                raise

    try:
        items = await asyncio.gather(*(fetch(row) for row in rows))
    except GitHubError as exc:
        raise HTTPException(exc.status_code, exc.message)
    finally:
        await client.aclose()

    kept = []
    for row, item in zip(rows, items):
        if _trackable(item, dashboard):
            kept.append(item)
        else:
            session.delete(row)
    session.commit()
    return kept


@router.get("/{dashboard_uuid}/columns/{column_id}/pulls", response_model=list[PullCardOut])
async def list_column_pulls(
    dashboard_uuid: str, column_id: int, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    dashboard = _pull_board(session, dashboard_uuid, user, VIEW)
    if column_id >= 0:
        column = _tracking_column(session, dashboard, column_id)
        return [_to_card(i) for i in await _tracked(session, dashboard, column)]

    # The automatic columns follow whoever is looking, not the board's owner.
    username = get_settings(session, user.id).github_username
    if not username:
        raise HTTPException(404, "Set your GitHub username in settings to see your PRs here.")
    # It goes into a search query, where a space would add terms of its own.
    if parse_org_ref(username) != username:
        raise HTTPException(422, "Your saved GitHub username isn't a valid GitHub login.")
    qualifier = {VIRTUAL_MY_PULLS_ID: "author", VIRTUAL_REVIEW_ID: "review-requested"}.get(column_id)
    if not qualifier:
        raise HTTPException(404, "Column not found")
    query = f"is:pr is:open archived:false org:{dashboard.repo_owner} {qualifier}:{username}"
    client = GitHubClient(read_token(session, dashboard))
    try:
        items = await client.search_all(query)
    except GitHubError as exc:
        raise HTTPException(exc.status_code, exc.message)
    finally:
        await client.aclose()
    return [_to_card(i) for i in items]


@router.post("/{dashboard_uuid}/columns/{column_id}/tracked-pulls", response_model=PullCardOut)
async def track_pull(
    dashboard_uuid: str,
    column_id: int,
    payload: TrackPullRequest,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    """Adds an open PR to a tracking column. From another tracking column on
    the board it moves; from an automatic column it's a copy."""
    dashboard = _pull_board(session, dashboard_uuid, user, MANAGE)
    column = _tracking_column(session, dashboard, column_id)
    if not _REPO.match(payload.repo):
        raise HTTPException(422, "repo must be 'owner/name'.")
    repo = payload.repo.lower()

    existing = session.exec(
        select(TrackedPull).where(
            TrackedPull.column_id == column.id, TrackedPull.repo == repo, TrackedPull.number == payload.number
        )
    ).first()
    if not existing:
        count = len(session.exec(select(TrackedPull.id).where(TrackedPull.column_id == column.id)).all())
        if count >= TRACKING_LIMIT:
            raise HTTPException(409, f"A tracking column holds up to {TRACKING_LIMIT} pull requests. Remove some first.")

    owner, name = payload.repo.split("/")
    client = GitHubClient(read_token(session, dashboard))
    try:
        item = await client.get_issue(owner, name, payload.number)
    except GitHubError as exc:
        raise HTTPException(exc.status_code, exc.message)
    finally:
        await client.aclose()
    if not _trackable(item, dashboard):
        raise HTTPException(422, f"{payload.repo}#{payload.number} isn't an open pull request in {dashboard.repo_owner}.")

    if not existing:
        session.add(TrackedPull(column_id=column.id, repo=repo, number=payload.number, added_by=user.id))
    source_id = payload.from_column_id
    if source_id is not None and source_id != column.id:
        source = session.get(Column, source_id)
        if source and source.dashboard_id == dashboard.id:
            for row in session.exec(
                select(TrackedPull).where(
                    TrackedPull.column_id == source.id, TrackedPull.repo == repo, TrackedPull.number == payload.number
                )
            ):
                session.delete(row)
    session.commit()
    return _to_card(item)


@router.delete("/{dashboard_uuid}/columns/{column_id}/tracked-pulls/{owner}/{name}/{number}", status_code=204)
def untrack_pull(
    dashboard_uuid: str,
    column_id: int,
    owner: str,
    name: str,
    number: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    dashboard = _pull_board(session, dashboard_uuid, user, MANAGE)
    column = _tracking_column(session, dashboard, column_id)
    repo = f"{owner}/{name}".lower()
    for row in session.exec(
        select(TrackedPull).where(TrackedPull.column_id == column.id, TrackedPull.repo == repo, TrackedPull.number == number)
    ):
        session.delete(row)
    session.commit()
