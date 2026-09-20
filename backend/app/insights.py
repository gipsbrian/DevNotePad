"""Org and personal issue analytics, built on GitHub's search API.

Search is the only endpoint that answers "how many issues match X across a
whole org" without walking every repo, and `total_count` on a `per_page=1`
query makes each answer one cheap request. That budget matters: search is
rate limited to 30 requests/minute, far tighter than the 5,000/hour REST
limit, so the number of queries per view is deliberately bounded and the
result is cached briefly.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from .github_client import GitHubClient

WEEKS = 6
TOP_REPOS = 4  # each costs an exact-count query; keeps a view under the limit
CACHE_TTL_SECONDS = 120
# Search allows 30 requests/minute; a view costs ~21. Run them concurrently
# to keep the page responsive, but bounded — GitHub asks clients not to
# fire high-concurrency bursts, and that also risks secondary rate limits.
MAX_CONCURRENCY = 6


@dataclass
class WeeklyPoint:
    week_start: str
    opened: int
    closed: int


@dataclass
class RepoCount:
    repo: str
    count: int


@dataclass
class Insights:
    scope: str
    org: str
    username: Optional[str]
    window_days: int
    totals: dict = field(default_factory=dict)
    weekly: list = field(default_factory=list)
    top_repos: list = field(default_factory=list)
    error: Optional[str] = None


_cache: dict[tuple, tuple[float, Insights]] = {}


def clear_cache(user_id: Optional[int] = None) -> None:
    """Analytics are computed with whatever token/settings were current, so
    a settings change has to drop that account's results -- otherwise the
    view keeps showing ones from the previous token. No id drops all."""
    if user_id is None:
        _cache.clear()
        return
    for key in [k for k in _cache if k[0] == user_id]:
        del _cache[key]


def _week_starts(weeks: int) -> list[date]:
    """Monday-aligned week starts, oldest first, ending with this week."""
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    return [this_monday - timedelta(weeks=w) for w in range(weeks - 1, -1, -1)]


def _actor_qualifier(scope: str, username: Optional[str], kind: str) -> str:
    """`kind` is "opened" or "closed": an issue is opened by its author and
    closed by whoever it was assigned to — the closest proxy GitHub search
    offers for "work someone finished"."""
    if scope != "me" or not username:
        return ""
    return f" author:{username}" if kind == "opened" else f" assignee:{username}"


async def _count(client: GitHubClient, query: str, gate: asyncio.Semaphore) -> int:
    async with gate:
        data = await client.search_issues(query, per_page=1)
    return int(data.get("total_count", 0))


async def gather_insights(
    client: GitHubClient, org: str, scope: str, username: Optional[str], user_id: int
) -> Insights:
    # Per account: the result reflects what that account's token can see,
    # which another account's token may not.
    key = (user_id, org, scope, username)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL_SECONDS:
        return hit[1]

    starts = _week_starts(WEEKS)
    since = starts[0].isoformat()
    base = f"org:{org} type:issue"
    opened_by = _actor_qualifier(scope, username, "opened")
    closed_by = _actor_qualifier(scope, username, "closed")

    result = Insights(
        scope=scope,
        org=org,
        username=username if scope == "me" else None,
        window_days=WEEKS * 7,
    )
    gate = asyncio.Semaphore(MAX_CONCURRENCY)

    spans = [
        (start, f"{start.isoformat()}..{(start + timedelta(days=6)).isoformat()}")
        for start in starts
    ]

    # Headline counts and the weekly series are independent, so issue them
    # together rather than one after another — sequentially this took ~13s.
    headline_queries = [
        f"{base} state:open{closed_by or opened_by}",
        f"{base}{opened_by} created:>={since}",
        f"{base}{closed_by} closed:>={since}",
        f"{base} state:open{opened_by}",
    ] if scope == "me" else [
        f"{base} state:open",
        f"{base} created:>={since}",
        f"{base} closed:>={since}",
    ]
    weekly_queries = []
    for _, span in spans:
        weekly_queries.append(f"{base}{opened_by} created:{span}")
        weekly_queries.append(f"{base}{closed_by} closed:{span}")

    counts = await asyncio.gather(
        *[_count(client, q, gate) for q in headline_queries + weekly_queries]
    )
    headline = counts[: len(headline_queries)]
    weekly = counts[len(headline_queries) :]

    result.totals = {
        "open": headline[0],
        "opened_in_window": headline[1],
        "closed_in_window": headline[2],
    }
    if scope == "me":
        result.totals["open_authored"] = headline[3]
    for i, (start, _) in enumerate(spans):
        result.weekly.append(
            WeeklyPoint(
                week_start=start.isoformat(),
                opened=weekly[i * 2],
                closed=weekly[i * 2 + 1],
            )
        )

    # Where the open work sits. One sample page to find candidate repos,
    # then an exact count per repo — aggregating the sample alone would
    # under-report anything past the first 100 results.
    sample = await client.search_issues(
        f"{base} state:open{closed_by or opened_by}", per_page=100, sort="updated"
    )
    seen: dict[str, int] = {}
    for item in sample.get("items", []):
        repo = item.get("repository_url", "").rsplit("/", 1)[-1]
        if repo:
            seen[repo] = seen.get(repo, 0) + 1

    candidates = sorted(seen, key=seen.get, reverse=True)[:TOP_REPOS]
    exact_counts = await asyncio.gather(
        *[
            _count(client, f"repo:{org}/{repo} type:issue state:open{closed_by or opened_by}", gate)
            for repo in candidates
        ]
    )
    result.top_repos = [RepoCount(repo=r, count=c) for r, c in zip(candidates, exact_counts)]
    result.top_repos.sort(key=lambda r: r.count, reverse=True)

    _cache[key] = (time.time(), result)
    return result
