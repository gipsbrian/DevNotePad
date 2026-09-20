import re
from datetime import datetime, timezone

from .schemas import AssigneeOut, IssueCardOut, LabelOut

_MD_STRIP_RE = re.compile(r"[#*`_>\[\]()!~-]")


def strip_markdown_summary(body: str | None, length: int = 160) -> str:
    if not body:
        return ""
    text = _MD_STRIP_RE.sub(" ", body)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > length:
        text = text[:length].rsplit(" ", 1)[0] + "…"
    return text


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def age_in_days(created_at: datetime, closed_at: datetime | None) -> int:
    end = closed_at or datetime.now(timezone.utc)
    return max((end - created_at).days, 0)


def issue_to_card(issue: dict, has_local_note: bool) -> IssueCardOut:
    created_at = _parse_dt(issue["created_at"])
    closed_at = _parse_dt(issue["closed_at"]) if issue.get("closed_at") else None
    sub_summary = issue.get("sub_issues_summary") or {}
    return IssueCardOut(
        number=issue["number"],
        title=issue["title"],
        summary=strip_markdown_summary(issue.get("body")),
        state=issue["state"],
        html_url=issue["html_url"],
        labels=[
            LabelOut(name=l["name"], color=l["color"], description=l.get("description"))
            for l in issue.get("labels", [])
        ],
        assignees=[
            AssigneeOut(login=a["login"], avatar_url=a["avatar_url"])
            for a in issue.get("assignees", [])
        ],
        milestone=issue["milestone"]["title"] if issue.get("milestone") else None,
        created_at=created_at,
        updated_at=_parse_dt(issue["updated_at"]),
        closed_at=closed_at,
        comments_count=issue.get("comments", 0),
        age_days=age_in_days(created_at, closed_at),
        has_local_note=has_local_note,
        sub_issues_total=sub_summary.get("total", 0) or 0,
        sub_issues_completed=sub_summary.get("completed", 0) or 0,
    )
