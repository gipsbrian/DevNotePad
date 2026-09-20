"""Parsing whatever shape of repo reference a user pastes in."""

import re
from typing import Optional, Tuple

_CLEAN = re.compile(r"^(https?://)?(www\.)?github\.com/", re.IGNORECASE)


def parse_repo_ref(value: str) -> Optional[Tuple[str, str]]:
    """Accepts 'owner/repo', a github.com URL, or an SSH remote.

    Returns (owner, repo), or None if it isn't a recognizable repo
    reference. Trailing '.git', query strings and deep paths
    (…/issues, /tree/main) are tolerated.
    """
    if not value:
        return None

    ref = value.strip()
    ref = ref.split("?", 1)[0].split("#", 1)[0]
    ref = re.sub(r"^git@github\.com:", "", ref, flags=re.IGNORECASE)
    ref = _CLEAN.sub("", ref)
    ref = ref.strip("/")

    if ref.endswith(".git"):
        ref = ref[: -len(".git")]

    parts = [p for p in ref.split("/") if p]
    if len(parts) < 2:
        return None

    owner, repo = parts[0], parts[1]
    if not owner or not repo:
        return None
    return owner, repo


def parse_org_url(value: Optional[str]) -> Optional[str]:
    """Pulls the org/user login out of a github.com org URL."""
    if not value:
        return None
    ref = _CLEAN.sub("", value.strip()).strip("/")
    parts = [p for p in ref.split("/") if p]
    return parts[0] if parts else None
