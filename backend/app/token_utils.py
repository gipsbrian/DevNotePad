"""Token type detection.

GitHub token prefixes are stable and documented; this lets us label a
token's type before making any API call. We can never *guarantee* a
fine-grained PAT is read-only (GitHub exposes no introspection endpoint
for them) — only classic PATs expose their scopes, via the
X-OAuth-Scopes response header. Everything else is inferred from the
`permissions` object GitHub returns on a repo call, or from a failed
write attempt.
"""

from dataclasses import dataclass
from typing import Optional

TOKEN_TYPE_LABELS = {
    "classic-pat": "Classic personal access token",
    "fine-grained-pat": "Fine-grained personal access token",
    "oauth-token": "OAuth app user token",
    "github-app-user-token": "GitHub App user-to-server token",
    "github-app-installation-token": "GitHub App installation token",
    "github-app-refresh-token": "GitHub App refresh token",
    "unrecognized": "Unrecognized token format",
    "none": "No token configured",
}


def detect_token_type(token: Optional[str]) -> str:
    if not token:
        return "none"
    if token.startswith("github_pat_"):
        return "fine-grained-pat"
    if token.startswith("ghp_"):
        return "classic-pat"
    if token.startswith("gho_"):
        return "oauth-token"
    if token.startswith("ghu_"):
        return "github-app-user-token"
    if token.startswith("ghs_"):
        return "github-app-installation-token"
    if token.startswith("ghr_"):
        return "github-app-refresh-token"
    return "unrecognized"


def token_type_label(token_type: str) -> str:
    return TOKEN_TYPE_LABELS.get(token_type, "Unrecognized token format")


@dataclass
class TokenInfo:
    token_type: str
    type_label: str
    # Only populated for classic PATs, straight from X-OAuth-Scopes.
    classic_scopes: Optional[list[str]] = None
    # Inferred from GET /repos/{owner}/{repo} `permissions`, works for any
    # token type but is a *permission on this repo*, not a certified scope.
    inferred_can_read: Optional[bool] = None
    inferred_can_write: Optional[bool] = None
    error: Optional[str] = None

    @property
    def warning(self) -> str:
        return (
            "For your safety, use a token scoped only to the repos you list "
            "here, with Issues: Read-only (or Read & write only if you want "
            "to close issues / post comments from this dashboard). Avoid "
            "granting full `repo` access or organization-wide permissions — "
            "GitHub cannot tell us what a fine-grained token can actually "
            "do, so this app can't fully verify that for you."
        )
