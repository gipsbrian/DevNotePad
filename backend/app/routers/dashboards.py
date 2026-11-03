import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlmodel import Session, select

from ..access import MANAGE, VIEW, board_access, get_board, read_token, write_block_reason, write_token
from ..auth import require_user
from ..db import get_session
from ..github_client import GitHubClient, GitHubError
from ..models import BoardShare, Column, Dashboard, LocalNote, Organization, StickyNote, TrackedIssue, TrackedPull, User
from ..orgs import current_organization, membership, switch_to
from ..repo_ref import parse_org_ref, parse_repo_ref
from ..settings_store import get_settings
from ..schemas import (
    ColumnCreate,
    ColumnOut,
    ColumnReorder,
    ColumnUpdate,
    DashboardAppearanceUpdate,
    DashboardCreate,
    DashboardUpdate,
    DashboardDetailOut,
    DashboardOut,
    IssueCardOut,
    IssueDetailOut,
    BoardSharingOut,
    BoardSharingUpdate,
    CommentCreate,
    CommentOut,
    MoveIssueRequest,
    SubIssueOut,
    TrackIssueRequest,
    RepoMetadataOut,
    LabelOut,
    MilestoneOut,
    AssigneeOut,
    IssueTypeOut,
)
from ..serializers import issue_to_card, strip_markdown_summary
from ..token_utils import TokenInfo

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])

# Column filters that map to exactly one unambiguous mutation when a card
# is dropped/moved into them. Anything else is view-only for
# drag/move purposes.
def _drag_compatible(column: Column) -> bool:
    if column.kind == "tracking":
        return False
    no_people = (
        not column.milestone
        and not column.assignee
        and not column.creator
        and not column.issue_type
    )
    single_label = len(column.labels) == 1 and no_people
    single_state = column.state == "closed" and not column.labels and no_people
    return single_label or single_state


# Virtual column ids. Negative so they can never collide with a real
# (autoincrement) column row. PR boards: "My open PRs" / "Review requested".
VIRTUAL_MY_PULLS_ID = -3
VIRTUAL_REVIEW_ID = -4


def _dashboard_out(session: Session, d: Dashboard, user: User) -> DashboardOut:
    access = board_access(session, d, user) or VIEW
    owner = session.get(User, d.owner_id) if d.owner_id else None
    return DashboardOut(
        id=d.uuid,
        name=d.name,
        repo_owner=d.repo_owner,
        repo_name=d.repo_name,
        # Whether a token is set is the manager's business only.
        has_own_token=bool(d.token) if access == MANAGE else False,
        created_at=d.created_at,
        accent_color=d.accent_color,
        background_url=d.background_url,
        kind=d.kind,
        subject=d.subject,
        access=access,
        owner=owner.username if owner else None,
        shared_with_organization=d.shared_with_organization,
        is_shared=access == MANAGE
        and d.kind == "personal"
        and (d.shared_with_organization or session.exec(select(BoardShare).where(BoardShare.dashboard_id == d.id)).first() is not None),
    )


def _column_out(c: Column, dashboard_uuid: str) -> ColumnOut:
    return ColumnOut(
        id=c.id,
        dashboard_id=dashboard_uuid,
        name=c.name,
        position=c.position,
        state=c.state,
        labels=c.labels,
        milestone=c.milestone,
        assignee=c.assignee,
        creator=c.creator,
        issue_type=c.issue_type,
        virtual=False,
        kind=c.kind,
        drag_compatible=_drag_compatible(c),
    )


def _virtual_columns(session: Session, dashboard: Dashboard, user: User, start_position: int) -> list[ColumnOut]:
    """A PR board's "My open PRs" / "Review requested", after its own columns.

    Synthesized from the viewer's own saved username rather than stored, so
    on a shared board each person sees their own, they stay in sync when
    the username changes, and can't be edited or deleted. Issue boards have
    none."""
    username = get_settings(session, user.id).github_username
    if dashboard.subject != "pulls" or not username:
        return []
    dashboard_uuid = dashboard.uuid
    return [
        ColumnOut(id=VIRTUAL_MY_PULLS_ID, dashboard_id=dashboard_uuid, name="My open PRs", position=start_position,
                  state="open", labels=[], milestone=None, assignee=None, creator=username, virtual=True, drag_compatible=False),
        ColumnOut(id=VIRTUAL_REVIEW_ID, dashboard_id=dashboard_uuid, name="Review requested",
                  position=start_position + 1, state="open", labels=[], milestone=None, assignee=username, virtual=True, drag_compatible=False),
    ]


def _get_column_or_404(session: Session, dashboard_pk: int, column_id: int) -> Column:
    column = session.get(Column, column_id)
    if not column or column.dashboard_id != dashboard_pk:
        raise HTTPException(404, "Column not found")
    return column


def _column_spec(session: Session, dashboard: Dashboard, column_id: int) -> ColumnOut:
    """The filter to query GitHub with for one of the board's columns."""
    return _column_out(_get_column_or_404(session, dashboard.id, column_id), dashboard.uuid)


def _resolve_repo(payload_ref: Optional[str], owner: Optional[str], name: Optional[str]) -> tuple[str, str]:
    """A board must point at exactly one repo. Accepts either an explicit
    owner/name pair or anything paste-able (owner/repo, a github.com URL,
    an SSH remote)."""
    if payload_ref:
        parsed = parse_repo_ref(payload_ref)
        if not parsed:
            raise HTTPException(422, f"Couldn't read a repo from {payload_ref!r}. Try 'owner/repo' or a github.com URL.")
        return parsed
    if owner and name:
        return owner, name
    raise HTTPException(422, "A repo is required — pass repo_ref, or repo_owner and repo_name.")


def _resolve_org(ref: Optional[str]) -> str:
    org = parse_org_ref(ref)
    if not org:
        raise HTTPException(422, "A PR board needs a GitHub organisation, e.g. 'my-org' or https://github.com/my-org.")
    return org


@router.post("", response_model=DashboardOut)
def create_dashboard(
    payload: DashboardCreate, request: Request, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    organization = current_organization(request, session, user)
    if payload.kind not in ("personal", "organization"):
        raise HTTPException(422, "A board is either 'personal' or 'organization'.")
    if payload.kind == "organization" and membership(session, organization.id, user.id).role != "admin":
        raise HTTPException(403, "Only this organization's admins can create organization boards.")
    if payload.subject == "pulls":
        repo_owner, repo_name = _resolve_org(payload.org_ref), ""
    else:
        repo_owner, repo_name = _resolve_repo(payload.repo_ref, payload.repo_owner, payload.repo_name)
    dashboard = Dashboard(
        name=payload.name,
        repo_owner=repo_owner,
        repo_name=repo_name,
        owner_id=user.id,
        organization_id=organization.id,
        kind=payload.kind,
        subject=payload.subject,
        token=payload.token,
        accent_color=payload.accent_color,
        background_url=payload.background_url,
    )
    session.add(dashboard)
    session.commit()
    session.refresh(dashboard)
    return _dashboard_out(session, dashboard, user)


@router.patch("/{dashboard_uuid}", response_model=DashboardOut)
def update_dashboard(
    dashboard_uuid: str, payload: DashboardUpdate, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    dashboard = get_board(session, dashboard_uuid, user, MANAGE)
    if payload.name is not None and payload.name.strip():
        dashboard.name = payload.name.strip()
    if payload.repo_ref is not None:
        if dashboard.subject == "pulls":
            dashboard.repo_owner = _resolve_org(payload.repo_ref)
        else:
            owner, name = _resolve_repo(payload.repo_ref, None, None)
            dashboard.repo_owner, dashboard.repo_name = owner, name
    if payload.token is not None:
        # Empty string means "fall back to the general token".
        dashboard.token = payload.token.strip() or None
    session.add(dashboard)
    session.commit()
    session.refresh(dashboard)
    return _dashboard_out(session, dashboard, user)


@router.patch("/{dashboard_uuid}/appearance", response_model=DashboardOut)
def update_appearance(
    dashboard_uuid: str, payload: DashboardAppearanceUpdate, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    dashboard = get_board(session, dashboard_uuid, user, MANAGE)
    if payload.accent_color is not None:
        dashboard.accent_color = payload.accent_color or None
    if payload.background_url is not None:
        dashboard.background_url = payload.background_url or None
    session.add(dashboard)
    session.commit()
    session.refresh(dashboard)
    return _dashboard_out(session, dashboard, user)


@router.get("", response_model=list[DashboardOut])
def list_dashboards(request: Request, session: Session = Depends(get_session), user: User = Depends(require_user)):
    """Every board you can reach in the organisation you're working in:
    organisation boards, your own, and ones shared with you. Each says which
    it is through `kind`, `access` and `owner`."""
    organization = current_organization(request, session, user)
    boards = session.exec(select(Dashboard).where(Dashboard.organization_id == organization.id)).all()
    return [_dashboard_out(session, d, user) for d in boards if board_access(session, d, user)]


@router.get("/{dashboard_uuid}", response_model=DashboardDetailOut)
async def get_dashboard(
    dashboard_uuid: str,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    dashboard = get_board(session, dashboard_uuid, user, VIEW)
    # A link to a board in another of your organisations takes you there.
    # Access was already checked above; this only moves the session.
    organization = session.get(Organization, dashboard.organization_id)
    switched = current_organization(request, session, user).id != organization.id
    if switched:
        switch_to(response, session, user, organization)
    token_info = None
    if board_access(session, dashboard, user) == MANAGE:
        client = GitHubClient(read_token(session, dashboard))
        try:
            info: TokenInfo = (
                await client.get_org_token_info(dashboard.repo_owner)
                if dashboard.subject == "pulls"
                else await client.get_token_info(dashboard.repo_owner, dashboard.repo_name)
            )
        finally:
            await client.aclose()
        token_info = info.__dict__ | {"warning": info.warning}
    reason = write_block_reason(session, dashboard, user)
    return DashboardDetailOut(
        **_dashboard_out(session, dashboard, user).model_dump(),
        token_info=token_info,
        can_write=reason is None,
        write_block_reason=reason,
        organization_id=organization.uuid,
        organization_name=organization.name,
        switched_organization=switched,
    )


@router.delete("/{dashboard_uuid}", status_code=204)
def delete_dashboard(dashboard_uuid: str, session: Session = Depends(get_session), user: User = Depends(require_user)):
    dashboard = get_board(session, dashboard_uuid, user, MANAGE)
    for column in session.exec(select(Column).where(Column.dashboard_id == dashboard.id)):
        _forget_tracked(session, column)
        session.delete(column)
    for note in session.exec(select(LocalNote).where(LocalNote.dashboard_id == dashboard.id)):
        session.delete(note)
    # SQLite can reuse the id of the newest deleted row, so a leftover note
    # would surface on the next board created -- possibly someone else's.
    for sticky in session.exec(select(StickyNote).where(StickyNote.dashboard_id == dashboard.id)):
        session.delete(sticky)
    for share in session.exec(select(BoardShare).where(BoardShare.dashboard_id == dashboard.id)):
        session.delete(share)
    session.delete(dashboard)
    session.commit()


# ---- Sharing ----

def _sharing(session: Session, dashboard: Dashboard) -> BoardSharingOut:
    shares = session.exec(select(BoardShare).where(BoardShare.dashboard_id == dashboard.id)).all()
    return BoardSharingOut(
        shared_with_organization=dashboard.shared_with_organization,
        user_ids=sorted(s.user_id for s in shares),
    )


def _personal_board_to_share(session: Session, dashboard_uuid: str, user: User) -> Dashboard:
    dashboard = get_board(session, dashboard_uuid, user, MANAGE)
    if dashboard.kind != "personal":
        raise HTTPException(409, "Organization boards are already visible to every member.")
    return dashboard


@router.get("/{dashboard_uuid}/sharing", response_model=BoardSharingOut)
def get_sharing(dashboard_uuid: str, session: Session = Depends(get_session), user: User = Depends(require_user)):
    return _sharing(session, _personal_board_to_share(session, dashboard_uuid, user))


@router.put("/{dashboard_uuid}/sharing", response_model=BoardSharingOut)
def set_sharing(
    dashboard_uuid: str, payload: BoardSharingUpdate, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    """Replaces who the board is shared with. Sharing only ever grants
    viewing, and only to members of the board's own organisation."""
    dashboard = _personal_board_to_share(session, dashboard_uuid, user)
    wanted = set(payload.user_ids) - {user.id}
    outsiders = [uid for uid in wanted if membership(session, dashboard.organization_id, uid) is None]
    if outsiders:
        raise HTTPException(422, "You can only share with members of this board's organization.")

    current = {s.user_id: s for s in session.exec(select(BoardShare).where(BoardShare.dashboard_id == dashboard.id)).all()}
    for uid, share in current.items():
        if uid not in wanted:
            session.delete(share)
    for uid in wanted - current.keys():
        session.add(BoardShare(dashboard_id=dashboard.id, user_id=uid))
    dashboard.shared_with_organization = payload.shared_with_organization
    session.add(dashboard)
    session.commit()
    session.refresh(dashboard)
    return _sharing(session, dashboard)


@router.get("/{dashboard_uuid}/github-metadata", response_model=RepoMetadataOut)
async def get_github_metadata(dashboard_uuid: str, session: Session = Depends(get_session), user: User = Depends(require_user)):
    dashboard = get_board(session, dashboard_uuid, user, VIEW)
    client = GitHubClient(read_token(session, dashboard))
    try:
        labels = await client.list_labels(dashboard.repo_owner, dashboard.repo_name)
        milestones = await client.list_milestones(dashboard.repo_owner, dashboard.repo_name)
        assignees = await client.list_assignees(dashboard.repo_owner, dashboard.repo_name)
        # GitHub defines issue types per *organization*, not per repo, but
        # what's useful on a board is what this repo actually uses — an org
        # may define types this repo never applies. So: the repo's own
        # issues first, then any extra org-defined types we're allowed to
        # see (that endpoint needs org read scope, which many tokens lack).
        from_repo = await client.sample_issue_types(dashboard.repo_owner, dashboard.repo_name)
        from_org = await client.list_org_issue_types(dashboard.repo_owner)

        seen = {t["name"] for t in from_repo}
        extra = [t for t in from_org if t["name"] not in seen]
        issue_types = from_repo + extra
        if from_repo and extra:
            source = "repo+org"
        elif from_repo:
            source = "repo"
        elif extra:
            source = "org"
        else:
            source = "none"
    except GitHubError as exc:
        raise HTTPException(exc.status_code, exc.message)
    finally:
        await client.aclose()
    return RepoMetadataOut(
        labels=[LabelOut(name=l["name"], color=l["color"], description=l.get("description")) for l in labels],
        milestones=[MilestoneOut(number=m["number"], title=m["title"], state=m["state"]) for m in milestones],
        assignees=[AssigneeOut(login=a["login"], avatar_url=a["avatar_url"]) for a in assignees],
        issue_types=[
            IssueTypeOut(name=t["name"], color=t.get("color"), description=t.get("description"))
            for t in issue_types
        ],
        issue_types_source=source,
    )


# ---- Columns ----

@router.post("/{dashboard_uuid}/columns", response_model=ColumnOut)
def create_column(dashboard_uuid: str, payload: ColumnCreate, session: Session = Depends(get_session), user: User = Depends(require_user)):
    dashboard = get_board(session, dashboard_uuid, user, MANAGE)
    if payload.position is None:
        existing = session.exec(select(Column).where(Column.dashboard_id == dashboard.id)).all()
        position = max((c.position for c in existing), default=-1) + 1
    else:
        position = payload.position
    if dashboard.subject == "pulls" and payload.kind != "tracking":
        raise HTTPException(422, "A PR board's own columns are tracking columns.")
    if payload.kind == "tracking":
        # Holds whatever is dropped into it, so there's nothing to filter on.
        column = Column(dashboard_id=dashboard.id, name=payload.name, kind="tracking", state="open", position=position)
    else:
        column = Column(
            dashboard_id=dashboard.id,
            name=payload.name,
            state=payload.state,
            # Normalize "" (the UI's "any") to NULL rather than storing blanks.
            milestone=payload.milestone or None,
            assignee=payload.assignee or None,
            creator=payload.creator or None,
            issue_type=payload.issue_type or None,
            position=position,
        )
        column.labels = payload.labels
    session.add(column)
    session.commit()
    session.refresh(column)
    return _column_out(column, dashboard_uuid)


@router.get("/{dashboard_uuid}/columns", response_model=list[ColumnOut])
def list_columns(dashboard_uuid: str, session: Session = Depends(get_session), user: User = Depends(require_user)):
    dashboard = get_board(session, dashboard_uuid, user, VIEW)
    columns = session.exec(
        select(Column).where(Column.dashboard_id == dashboard.id).order_by(Column.position)
    ).all()
    out = [_column_out(c, dashboard_uuid) for c in columns]
    return out + _virtual_columns(session, dashboard, user, start_position=len(out))


@router.put("/{dashboard_uuid}/columns/reorder", response_model=list[ColumnOut])
def reorder_columns(
    dashboard_uuid: str, payload: ColumnReorder, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    """Rewrites column positions from the given left-to-right order."""
    dashboard = get_board(session, dashboard_uuid, user, MANAGE)
    owned = {
        c.id: c
        for c in session.exec(select(Column).where(Column.dashboard_id == dashboard.id)).all()
    }

    unknown = [cid for cid in payload.column_ids if cid not in owned]
    if unknown:
        raise HTTPException(404, f"Columns not on this board: {unknown}")

    for position, column_id in enumerate(payload.column_ids):
        owned[column_id].position = position
        session.add(owned[column_id])
    # Anything the client didn't mention keeps a stable spot after the
    # reordered ones rather than silently jumping to the front.
    for offset, column in enumerate(
        c for c in sorted(owned.values(), key=lambda c: c.position) if c.id not in payload.column_ids
    ):
        column.position = len(payload.column_ids) + offset
        session.add(column)

    session.commit()

    columns = session.exec(
        select(Column).where(Column.dashboard_id == dashboard.id).order_by(Column.position)
    ).all()
    return [_column_out(c, dashboard_uuid) for c in columns]


@router.put("/{dashboard_uuid}/columns/{column_id}", response_model=ColumnOut)
def update_column(
    dashboard_uuid: str, column_id: int, payload: ColumnUpdate, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    dashboard = get_board(session, dashboard_uuid, user, MANAGE)
    column = _get_column_or_404(session, dashboard.id, column_id)
    if dashboard.subject == "pulls" and payload.kind == "filter":
        raise HTTPException(422, "A PR board's own columns are tracking columns.")
    if payload.name is not None:
        column.name = payload.name
    if payload.position is not None:
        column.position = payload.position
    if payload.kind == "tracking" and column.kind != "tracking":
        column.kind = "tracking"
        column.state = "open"
        column.labels = []
        column.milestone = column.assignee = column.creator = column.issue_type = None
    elif payload.kind == "filter" and column.kind == "tracking":
        _forget_tracked(session, column)
        column.kind = "filter"
    if column.kind == "tracking":
        # Only the name and place change; filters would mean nothing here.
        session.add(column)
        session.commit()
        session.refresh(column)
        return _column_out(column, dashboard_uuid)
    if payload.state is not None:
        column.state = payload.state
    if payload.labels is not None:
        column.labels = payload.labels
    # Empty strings clear these back to "any".
    if payload.milestone is not None:
        column.milestone = payload.milestone or None
    if payload.assignee is not None:
        column.assignee = payload.assignee or None
    if payload.creator is not None:
        column.creator = payload.creator or None
    if payload.issue_type is not None:
        column.issue_type = payload.issue_type or None
    session.add(column)
    session.commit()
    session.refresh(column)
    return _column_out(column, dashboard_uuid)


@router.delete("/{dashboard_uuid}/columns/{column_id}", status_code=204)
def delete_column(dashboard_uuid: str, column_id: int, session: Session = Depends(get_session), user: User = Depends(require_user)):
    dashboard = get_board(session, dashboard_uuid, user, MANAGE)
    column = _get_column_or_404(session, dashboard.id, column_id)
    _forget_tracked(session, column)
    session.delete(column)
    session.commit()


# ---- Tracking columns ----

# Each tracked issue is one GitHub request when the column loads, so a
# column holds a bounded number.
TRACKING_LIMIT = 100


def _forget_tracked(session: Session, column: Column) -> None:
    # SQLite can reuse a deleted column's id, which would hand its tracked
    # issues to the next column created.
    for row in session.exec(select(TrackedIssue).where(TrackedIssue.column_id == column.id)):
        session.delete(row)
    for row in session.exec(select(TrackedPull).where(TrackedPull.column_id == column.id)):
        session.delete(row)


def _trackable(issue: Optional[dict], dashboard: Dashboard) -> bool:
    """Open, an issue rather than a pull request, and still in this repo. A
    transferred issue answers 301 with no issue in the body."""
    if not issue or issue.get("state") != "open" or "pull_request" in issue:
        return False
    repo_url = (issue.get("repository_url") or "").lower()
    return repo_url.endswith(f"/repos/{dashboard.repo_owner}/{dashboard.repo_name}".lower())


def _tracking_column_or_400(session: Session, dashboard: Dashboard, column_id: int) -> Column:
    column = _get_column_or_404(session, dashboard.id, column_id)
    if column.kind != "tracking":
        raise HTTPException(400, "Only tracking columns take dropped issues; this one is filled by its filter.")
    return column


async def _tracked_issues(session: Session, dashboard: Dashboard, column: Column) -> list[dict]:
    """The column's issues, newest first. Any that are closed, deleted or
    transferred are dropped from the column on the way."""
    rows = session.exec(
        select(TrackedIssue)
        .where(TrackedIssue.column_id == column.id)
        .order_by(TrackedIssue.added_at.desc(), TrackedIssue.id.desc())
    ).all()
    if not rows:
        return []

    client = GitHubClient(read_token(session, dashboard))
    gate = asyncio.Semaphore(8)

    async def fetch(number: int) -> Optional[dict]:
        async with gate:
            try:
                return await client.get_issue(dashboard.repo_owner, dashboard.repo_name, number)
            except GitHubError as exc:
                if exc.status_code in (404, 410):
                    return None
                raise

    try:
        issues = await asyncio.gather(*(fetch(row.issue_number) for row in rows))
    except GitHubError as exc:
        raise HTTPException(exc.status_code, exc.message)
    finally:
        await client.aclose()

    kept = []
    for row, issue in zip(rows, issues):
        if _trackable(issue, dashboard):
            kept.append(issue)
        else:
            session.delete(row)
    session.commit()
    return kept


@router.post("/{dashboard_uuid}/columns/{column_id}/tracked", response_model=IssueCardOut)
async def track_issue(
    dashboard_uuid: str,
    column_id: int,
    payload: TrackIssueRequest,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    """Adds an open issue to a tracking column. Coming from another tracking
    column on the board, it moves; from a filter column, it's a copy, since
    the filter still matches it."""
    dashboard = get_board(session, dashboard_uuid, user, MANAGE)
    column = _tracking_column_or_400(session, dashboard, column_id)

    existing = session.exec(
        select(TrackedIssue).where(TrackedIssue.column_id == column.id, TrackedIssue.issue_number == payload.issue_number)
    ).first()
    if not existing:
        count = len(session.exec(select(TrackedIssue.id).where(TrackedIssue.column_id == column.id)).all())
        if count >= TRACKING_LIMIT:
            raise HTTPException(409, f"A tracking column holds up to {TRACKING_LIMIT} issues. Remove some first.")

    client = GitHubClient(read_token(session, dashboard))
    try:
        issue = await client.get_issue(dashboard.repo_owner, dashboard.repo_name, payload.issue_number)
    except GitHubError as exc:
        raise HTTPException(exc.status_code, exc.message)
    finally:
        await client.aclose()
    if not _trackable(issue, dashboard):
        raise HTTPException(422, f"#{payload.issue_number} isn't an open issue in this repo.")

    if not existing:
        session.add(TrackedIssue(column_id=column.id, issue_number=payload.issue_number, added_by=user.id))
    source_id = payload.from_column_id
    if source_id is not None and source_id != column.id:
        source = session.get(Column, source_id)
        # Only ever this board's column; a filter column has nothing to remove.
        if source and source.dashboard_id == dashboard.id:
            for row in session.exec(
                select(TrackedIssue).where(
                    TrackedIssue.column_id == source.id, TrackedIssue.issue_number == payload.issue_number
                )
            ):
                session.delete(row)
    session.commit()

    noted = session.exec(
        select(LocalNote).where(
            LocalNote.dashboard_id == dashboard.id,
            LocalNote.user_id == user.id,
            LocalNote.issue_number == payload.issue_number,
        )
    ).first()
    return issue_to_card(issue, noted is not None)


@router.delete("/{dashboard_uuid}/columns/{column_id}/tracked/{number}", status_code=204)
def untrack_issue(
    dashboard_uuid: str, column_id: int, number: int, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    dashboard = get_board(session, dashboard_uuid, user, MANAGE)
    column = _tracking_column_or_400(session, dashboard, column_id)
    for row in session.exec(
        select(TrackedIssue).where(TrackedIssue.column_id == column.id, TrackedIssue.issue_number == number)
    ):
        session.delete(row)
    session.commit()


# ---- Issues ----

@router.get("/{dashboard_uuid}/columns/{column_id}/issues", response_model=list[IssueCardOut])
async def list_column_issues(
    dashboard_uuid: str, column_id: int, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    dashboard = get_board(session, dashboard_uuid, user, VIEW)
    spec = _column_spec(session, dashboard, column_id)
    if spec.kind == "tracking":
        issues = await _tracked_issues(session, dashboard, _get_column_or_404(session, dashboard.id, column_id))
        noted = {
            n.issue_number
            for n in session.exec(
                select(LocalNote).where(LocalNote.dashboard_id == dashboard.id, LocalNote.user_id == user.id)
            ).all()
        }
        return [issue_to_card(issue, issue["number"] in noted) for issue in issues]
    client = GitHubClient(read_token(session, dashboard))
    try:
        issues = await client.list_issues(
            dashboard.repo_owner,
            dashboard.repo_name,
            state=spec.state,
            labels=spec.labels or None,
            milestone=spec.milestone,
            assignee=spec.assignee,
            creator=spec.creator,
            issue_type=spec.issue_type,
        )
    except GitHubError as exc:
        raise HTTPException(exc.status_code, exc.message)
    finally:
        await client.aclose()

    noted_issue_numbers = {
        n.issue_number
        for n in session.exec(
            select(LocalNote).where(LocalNote.dashboard_id == dashboard.id, LocalNote.user_id == user.id)
        ).all()
    }
    return [issue_to_card(issue, issue["number"] in noted_issue_numbers) for issue in issues]


@router.get("/{dashboard_uuid}/closed", response_model=list[IssueCardOut])
async def list_closed_issues(
    dashboard_uuid: str, days: int = 7, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    """Closed issues for the date-grouped Closed section.

    Bounded by `days` (0 = all time). Fetching a busy repo's entire closed
    history is slow enough to dominate board load, so the default is a
    short window. GitHub's `since` filters on updated_at, which is a cheap
    way to cut the pages fetched; we then narrow to actual closed_at.
    """
    dashboard = get_board(session, dashboard_uuid, user, VIEW)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days > 0 else None
    client = GitHubClient(read_token(session, dashboard))
    try:
        issues = await client.list_issues(
            dashboard.repo_owner,
            dashboard.repo_name,
            state="closed",
            since=cutoff.isoformat().replace("+00:00", "Z") if cutoff else None,
        )
    except GitHubError as exc:
        raise HTTPException(exc.status_code, exc.message)
    finally:
        await client.aclose()

    if cutoff:
        # `since` matches anything *updated* in the window, including issues
        # closed long ago and touched recently — keep only real closures.
        issues = [
            i
            for i in issues
            if i.get("closed_at")
            and datetime.fromisoformat(i["closed_at"].replace("Z", "+00:00")) >= cutoff
        ]

    noted_issue_numbers = {
        n.issue_number
        for n in session.exec(
            select(LocalNote).where(LocalNote.dashboard_id == dashboard.id, LocalNote.user_id == user.id)
        ).all()
    }
    return [issue_to_card(issue, issue["number"] in noted_issue_numbers) for issue in issues]


@router.get("/{dashboard_uuid}/issues/{number}", response_model=IssueDetailOut)
async def get_issue_detail(dashboard_uuid: str, number: int, session: Session = Depends(get_session), user: User = Depends(require_user)):
    dashboard = get_board(session, dashboard_uuid, user, VIEW)
    client = GitHubClient(read_token(session, dashboard))
    try:
        issue = await client.get_issue(dashboard.repo_owner, dashboard.repo_name, number)
        comments = await client.list_comments(dashboard.repo_owner, dashboard.repo_name, number)
        sub_issues = (
            await client.list_sub_issues(dashboard.repo_owner, dashboard.repo_name, number)
            if (issue.get("sub_issues_summary") or {}).get("total")
            else []
        )
    except GitHubError as exc:
        raise HTTPException(exc.status_code, exc.message)
    finally:
        await client.aclose()

    notes = session.exec(
        select(LocalNote).where(
            LocalNote.dashboard_id == dashboard.id,
            LocalNote.issue_number == number,
            LocalNote.user_id == user.id,
        )
    ).all()

    return IssueDetailOut(
        number=issue["number"],
        title=issue["title"],
        body=issue.get("body"),
        state=issue["state"],
        html_url=issue["html_url"],
        labels=[LabelOut(name=l["name"], color=l["color"], description=l.get("description")) for l in issue.get("labels", [])],
        assignees=[AssigneeOut(login=a["login"], avatar_url=a["avatar_url"]) for a in issue.get("assignees", [])],
        milestone=issue["milestone"]["title"] if issue.get("milestone") else None,
        created_at=issue["created_at"],
        updated_at=issue["updated_at"],
        closed_at=issue.get("closed_at"),
        comments=[
            CommentOut(id=c["id"], author=c["user"]["login"], body=c["body"], created_at=c["created_at"])
            for c in comments
        ],
        sub_issues=[
            SubIssueOut(
                number=si["number"], title=si["title"], state=si["state"], html_url=si["html_url"]
            )
            for si in sub_issues
        ],
        notes=[
            {
                "id": n.id,
                "dashboard_id": dashboard.uuid,
                "issue_number": n.issue_number,
                "body": n.body,
                "created_at": n.created_at,
                "updated_at": n.updated_at,
                "synced": n.synced,
                "github_comment_id": n.github_comment_id,
            }
            for n in notes
        ],
    )


@router.get("/{dashboard_uuid}/issues/{number}/sub-issues", response_model=list[SubIssueOut])
async def list_issue_sub_issues(
    dashboard_uuid: str, number: int, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    """Just the sub-issues, for the card's hover preview — the full issue
    detail is a heavier call than a hover should make."""
    dashboard = get_board(session, dashboard_uuid, user, VIEW)
    client = GitHubClient(read_token(session, dashboard))
    try:
        sub_issues = await client.list_sub_issues(
            dashboard.repo_owner, dashboard.repo_name, number
        )
    finally:
        await client.aclose()
    return [
        SubIssueOut(number=si["number"], title=si["title"], state=si["state"], html_url=si["html_url"])
        for si in sub_issues
    ]


@router.post("/{dashboard_uuid}/issues/{number}/close", response_model=IssueCardOut)
async def close_issue(dashboard_uuid: str, number: int, session: Session = Depends(get_session), user: User = Depends(require_user)):
    dashboard = get_board(session, dashboard_uuid, user, VIEW)
    client = GitHubClient(write_token(session, dashboard, user))
    try:
        issue = await client.close_issue(dashboard.repo_owner, dashboard.repo_name, number)
    except GitHubError as exc:
        raise HTTPException(exc.status_code, exc.message)
    finally:
        await client.aclose()
    return issue_to_card(issue, has_local_note=False)


@router.get("/{dashboard_uuid}/issues/{number}/comments", response_model=list[CommentOut])
async def list_issue_comments(
    dashboard_uuid: str, number: int, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    """Just the comment thread, for the hover panel on a card -- one GitHub
    call, where the issue detail costs three."""
    dashboard = get_board(session, dashboard_uuid, user, VIEW)
    client = GitHubClient(read_token(session, dashboard))
    try:
        comments = await client.list_comments(dashboard.repo_owner, dashboard.repo_name, number)
    except GitHubError as exc:
        raise HTTPException(exc.status_code, exc.message)
    finally:
        await client.aclose()
    return [
        CommentOut(id=c["id"], author=c["user"]["login"], body=c["body"], created_at=c["created_at"])
        for c in comments
    ]


@router.post("/{dashboard_uuid}/issues/{number}/comments", response_model=CommentOut)
async def comment_on_issue(
    dashboard_uuid: str, number: int, payload: CommentCreate, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    """Posts straight to GitHub, with no local note behind it -- for joining
    a conversation on the issue rather than keeping something private."""
    dashboard = get_board(session, dashboard_uuid, user, VIEW)
    body = payload.body.strip()
    if not body:
        raise HTTPException(422, "A comment needs some text.")
    client = GitHubClient(write_token(session, dashboard, user))
    try:
        comment = await client.create_comment(dashboard.repo_owner, dashboard.repo_name, number, body)
    except GitHubError as exc:
        raise HTTPException(exc.status_code, exc.message)
    finally:
        await client.aclose()
    return CommentOut(
        id=comment["id"], author=comment["user"]["login"], body=comment["body"], created_at=comment["created_at"]
    )


@router.post("/{dashboard_uuid}/issues/{number}/move", response_model=IssueCardOut)
async def move_issue(
    dashboard_uuid: str, number: int, payload: MoveIssueRequest, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    """Move-without-drag -- same filter->mutation mapping a
    drag-drop would use. Only drag-compatible columns are valid targets."""
    dashboard = get_board(session, dashboard_uuid, user, VIEW)
    target = _get_column_or_404(session, dashboard.id, payload.target_column_id)
    if not _drag_compatible(target):
        raise HTTPException(400, "This column's filter doesn't map to a single unambiguous action.")

    client = GitHubClient(write_token(session, dashboard, user))
    try:
        if target.state == "closed":
            issue = await client.close_issue(dashboard.repo_owner, dashboard.repo_name, number)
        else:
            label = target.labels[0]
            await client.add_label(dashboard.repo_owner, dashboard.repo_name, number, label)
            issue = await client.get_issue(dashboard.repo_owner, dashboard.repo_name, number)
    except GitHubError as exc:
        raise HTTPException(exc.status_code, exc.message)
    finally:
        await client.aclose()
    return issue_to_card(issue, has_local_note=False)
