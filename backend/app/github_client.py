"""Thin GitHub REST client.

- The issue list endpoint also returns pull requests; we filter those out.
- We only ever read labels/milestones/assignees that already exist: this
  app never calls the create-label or create-milestone endpoints.
- Rate limits: REST allows 5,000 requests an hour per token. There's no
  ETag caching yet.
"""

from typing import Any, Optional

import httpx

from .token_utils import TokenInfo, detect_token_type, token_type_label

GITHUB_API = "https://api.github.com"


class GitHubError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class GitHubClient:
    def __init__(self, token: Optional[str]):
        self.token = token
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API, headers=headers, timeout=15.0
        )

    async def aclose(self):
        await self._client.aclose()

    async def _get(self, path: str, params: Optional[dict] = None) -> httpx.Response:
        resp = await self._client.get(path, params=params)
        return resp

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            detail = resp.json().get("message", resp.text) if resp.content else resp.text
            raise GitHubError(resp.status_code, detail)

    # ---- Token / permission introspection ----

    async def get_token_info(self, owner: str, repo: str) -> TokenInfo:
        token_type = detect_token_type(self.token)
        info = TokenInfo(token_type=token_type, type_label=token_type_label(token_type))

        if token_type == "none":
            info.error = "No token configured for this dashboard."
            return info

        try:
            resp = await self._get(f"/repos/{owner}/{repo}")
        except httpx.HTTPError as exc:
            info.error = f"Could not reach GitHub: {exc}"
            return info

        if resp.status_code == 401:
            info.error = "Token is invalid or revoked."
            return info
        if resp.status_code == 404:
            info.error = "Repo not found or token can't see it (private + no access)."
            return info
        if resp.status_code >= 400:
            info.error = resp.text
            return info

        if token_type == "classic-pat":
            scopes_header = resp.headers.get("X-OAuth-Scopes", "")
            info.classic_scopes = [s.strip() for s in scopes_header.split(",") if s.strip()]

        data = resp.json()
        perms = data.get("permissions") or {}
        if perms:
            info.inferred_can_read = bool(perms.get("pull"))
            info.inferred_can_write = bool(perms.get("push"))

        return info

    async def get_authenticated_login(self) -> Optional[str]:
        """The login the token belongs to, so settings can prefill it.
        None for tokens that aren't user-scoped (e.g. app installation)."""
        if not self.token:
            return None
        resp = await self._get("/user")
        if resp.status_code >= 400:
            return None
        return resp.json().get("login")

    # ---- Metadata: pull existing taxonomy only, never create it ----

    async def list_labels(self, owner: str, repo: str) -> list[dict]:
        resp = await self._get(f"/repos/{owner}/{repo}/labels", params={"per_page": 100})
        self._raise_for_status(resp)
        return resp.json()

    async def list_milestones(self, owner: str, repo: str) -> list[dict]:
        resp = await self._get(
            f"/repos/{owner}/{repo}/milestones",
            params={"state": "all", "per_page": 100},
        )
        self._raise_for_status(resp)
        return resp.json()

    async def list_assignees(self, owner: str, repo: str) -> list[dict]:
        resp = await self._get(f"/repos/{owner}/{repo}/assignees", params={"per_page": 100})
        self._raise_for_status(resp)
        return resp.json()

    # ---- Issues ----

    async def list_issues(
        self,
        owner: str,
        repo: str,
        state: Optional[str] = "open",
        labels: Optional[list[str]] = None,
        milestone: Optional[str] = None,
        assignee: Optional[str] = None,
        creator: Optional[str] = None,
        issue_type: Optional[str] = None,
        since: Optional[str] = None,
    ) -> list[dict]:
        params: dict[str, Any] = {"state": state or "all", "per_page": 100}
        if labels:
            params["labels"] = ",".join(labels)
        if milestone:
            params["milestone"] = milestone
        if assignee:
            params["assignee"] = assignee
        if creator:
            params["creator"] = creator
        if issue_type:
            params["type"] = issue_type
        if since:
            # GitHub filters `since` on updated_at, not closed_at — it's a
            # cheap way to bound the pages fetched; callers narrow further.
            params["since"] = since

        issues: list[dict] = []
        page = 1
        while True:
            params["page"] = page
            resp = await self._get(f"/repos/{owner}/{repo}/issues", params=params)
            self._raise_for_status(resp)
            batch = resp.json()
            if not batch:
                break
            # The issues endpoint also returns PRs — filter them out.
            issues.extend(i for i in batch if "pull_request" not in i)
            if len(batch) < 100:
                break
            page += 1
        return issues

    async def search_issues(
        self, query: str, per_page: int = 1, sort: Optional[str] = None
    ) -> dict:
        """Search is the only way to count issues across a whole org
        without walking every repo. Rate limited to 30/min, so callers
        budget their queries."""
        params: dict[str, Any] = {"q": query, "per_page": per_page}
        if sort:
            params["sort"] = sort
        resp = await self._get("/search/issues", params=params)
        # Deliberately raises rather than returning an empty result: a
        # swallowed error here renders as "0 issues", which reads as real
        # data instead of a failure.
        self._raise_for_status(resp)
        return resp.json()

    async def list_org_members(self, org: str) -> list[dict]:
        """Team members for the insights picker. Needs org read; returns
        [] rather than raising when the token can't see them."""
        resp = await self._get(f"/orgs/{org}/members", params={"per_page": 100})
        if resp.status_code >= 400:
            return []
        data = resp.json()
        return data if isinstance(data, list) else []

    async def list_org_issue_types(self, org: str) -> list[dict]:
        """Org-level issue types. Needs org read scope, which many tokens
        don't have — callers should fall back to sampling issues."""
        resp = await self._get(f"/orgs/{org}/issue-types")
        if resp.status_code >= 400:
            return []
        data = resp.json()
        return data if isinstance(data, list) else []

    async def sample_issue_types(self, owner: str, repo: str) -> list[dict]:
        """Distinct issue types seen on a page of the repo's own issues —
        so the filter still works without org read access."""
        resp = await self._get(
            f"/repos/{owner}/{repo}/issues",
            params={"state": "all", "per_page": 100},
        )
        if resp.status_code >= 400:
            return []
        seen: dict[str, dict] = {}
        for issue in resp.json():
            issue_type = issue.get("type")
            if issue_type and issue_type.get("name") not in seen:
                seen[issue_type["name"]] = issue_type
        return list(seen.values())

    async def get_issue(self, owner: str, repo: str, number: int) -> dict:
        resp = await self._get(f"/repos/{owner}/{repo}/issues/{number}")
        self._raise_for_status(resp)
        return resp.json()

    async def list_sub_issues(self, owner: str, repo: str, number: int) -> list[dict]:
        """An issue's sub-issues (GA April 2025). Returns [] rather than
        raising when unavailable, so a board still renders on an instance
        or token that can't see them."""
        resp = await self._get(
            f"/repos/{owner}/{repo}/issues/{number}/sub_issues", params={"per_page": 100}
        )
        if resp.status_code >= 400:
            return []
        data = resp.json()
        return data if isinstance(data, list) else []

    async def list_comments(self, owner: str, repo: str, number: int) -> list[dict]:
        resp = await self._get(
            f"/repos/{owner}/{repo}/issues/{number}/comments", params={"per_page": 100}
        )
        self._raise_for_status(resp)
        return resp.json()

    async def close_issue(self, owner: str, repo: str, number: int) -> dict:
        resp = await self._client.patch(
            f"/repos/{owner}/{repo}/issues/{number}", json={"state": "closed"}
        )
        self._raise_for_status(resp)
        return resp.json()

    async def add_label(self, owner: str, repo: str, number: int, label: str) -> dict:
        resp = await self._client.post(
            f"/repos/{owner}/{repo}/issues/{number}/labels", json={"labels": [label]}
        )
        self._raise_for_status(resp)
        return resp.json()

    async def create_comment(self, owner: str, repo: str, number: int, body: str) -> dict:
        resp = await self._client.post(
            f"/repos/{owner}/{repo}/issues/{number}/comments", json={"body": body}
        )
        self._raise_for_status(resp)
        return resp.json()

    async def update_comment(self, owner: str, repo: str, comment_id: int, body: str) -> dict:
        resp = await self._client.patch(
            f"/repos/{owner}/{repo}/issues/comments/{comment_id}", json={"body": body}
        )
        self._raise_for_status(resp)
        return resp.json()
