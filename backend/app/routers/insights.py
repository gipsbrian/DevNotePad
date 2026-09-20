from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..auth import require_user
from ..db import get_session
from ..github_client import GitHubClient, GitHubError
from ..insights import gather_insights
from ..models import User
from ..repo_ref import parse_org_url
from ..schemas import InsightsOut, MemberOut
from ..settings_store import general_org_url, general_token, get_settings

router = APIRouter(prefix="/api/insights", tags=["insights"])


def _org_or_400(session: Session, user: User) -> str:
    org = parse_org_url(general_org_url(session, user.id))
    if not org:
        raise HTTPException(
            400, "Set a default organization URL in settings to see analytics."
        )
    return org


@router.get("/members", response_model=list[MemberOut])
async def list_members(session: Session = Depends(get_session), user: User = Depends(require_user)):
    org = _org_or_400(session, user)
    client = GitHubClient(general_token(session, user.id))
    try:
        members = await client.list_org_members(org)
    finally:
        await client.aclose()

    me = get_settings(session, user.id).github_username
    out = [MemberOut(login=m["login"], avatar_url=m.get("avatar_url", "")) for m in members]
    # The token's own user may not appear (or the list may be empty when
    # the token can't read org membership) — always offer them.
    if me and not any(m.login == me for m in out):
        out.insert(0, MemberOut(login=me, avatar_url=""))
    return out


@router.get("", response_model=InsightsOut)
async def read_insights(
    scope: str = "me", username: str | None = None, session: Session = Depends(get_session), user: User = Depends(require_user)
):
    if scope not in ("me", "org"):
        raise HTTPException(422, "scope must be 'me' or 'org'")

    org = _org_or_400(session, user)
    token = general_token(session, user.id)
    if not token:
        raise HTTPException(400, "A token is required to read analytics.")

    who = username or get_settings(session, user.id).github_username
    if scope == "me" and not who:
        raise HTTPException(400, "Set your GitHub username in settings to see personal analytics.")

    client = GitHubClient(token)
    try:
        data = await gather_insights(client, org, scope, who, user_id=user.id)
    except GitHubError as exc:
        # Search is limited to 30 requests/minute and one view spends most
        # of that, so switching scope quickly can trip it. Say so plainly
        # rather than rendering zeros.
        if exc.status_code in (403, 429):
            raise HTTPException(
                429,
                "GitHub's search rate limit (30/minute) was reached. Analytics refresh in about a minute.",
            )
        raise HTTPException(exc.status_code, exc.message)
    finally:
        await client.aclose()

    return InsightsOut(
        scope=data.scope,
        org=data.org,
        username=data.username,
        window_days=data.window_days,
        totals=data.totals,
        weekly=[w.__dict__ for w in data.weekly],
        top_repos=[r.__dict__ for r in data.top_repos],
    )
