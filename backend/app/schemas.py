from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


# ---- Auth ----

class LoginRequest(BaseModel):
    # Username or email — the form asks for "username or email".
    identifier: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    # Registering from an invitation link joins that organisation too, and
    # works even while registration is otherwise closed.
    invitation_token: Optional[str] = None


class RegistrationStatusOut(BaseModel):
    open: bool


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    tours_seen: list[str] = []
    # An admin of the main organisation, and so of the instance.
    is_instance_admin: bool = False


# ---- Insights ----

class WeeklyPointOut(BaseModel):
    week_start: str
    opened: int
    closed: int


class RepoCountOut(BaseModel):
    repo: str
    count: int


class MemberOut(BaseModel):
    login: str
    avatar_url: str = ""


class InsightsOut(BaseModel):
    scope: str
    org: str
    username: Optional[str] = None
    window_days: int
    totals: dict
    weekly: List[WeeklyPointOut]
    top_repos: List[RepoCountOut]


# ---- Settings (cut across every board) ----

class SettingsOut(BaseModel):
    github_username: Optional[str] = None
    default_org_url: Optional[str] = None
    show_my_columns: bool = True
    # Never returns the token itself — only whether one is available and
    # where it came from.
    has_default_token: bool = False
    default_token_source: str = "none"  # "settings" | "env" | "none"


class SettingsUpdate(BaseModel):
    github_username: Optional[str] = None
    default_org_url: Optional[str] = None
    default_token: Optional[str] = None
    show_my_columns: Optional[bool] = None


# ---- Dashboards ----

class DashboardCreate(BaseModel):
    name: str
    # Either repo_owner/repo_name, or repo_ref ("owner/repo" or a
    # github.com URL) which the API parses.
    repo_owner: Optional[str] = None
    repo_name: Optional[str] = None
    repo_ref: Optional[str] = None
    token: Optional[str] = None
    accent_color: Optional[str] = None
    background_url: Optional[str] = None
    # "personal" (yours) or "organization" (admins only; every member sees it)
    kind: str = "personal"


class DashboardUpdate(BaseModel):
    name: Optional[str] = None
    repo_ref: Optional[str] = None
    # "" clears the per-board token so it falls back to the general one.
    token: Optional[str] = None


class DashboardAppearanceUpdate(BaseModel):
    accent_color: Optional[str] = None
    background_url: Optional[str] = None


class TokenInfoOut(BaseModel):
    token_type: str
    type_label: str
    classic_scopes: Optional[List[str]] = None
    inferred_can_read: Optional[bool] = None
    inferred_can_write: Optional[bool] = None
    error: Optional[str] = None
    warning: str


class DashboardOut(BaseModel):
    id: str
    name: str
    repo_owner: str
    repo_name: str
    has_own_token: bool
    created_at: datetime
    accent_color: Optional[str] = None
    background_url: Optional[str] = None
    kind: str = "personal"
    # What the caller may do: "view" or "manage".
    access: str = "manage"
    owner: Optional[str] = None
    shared_with_organization: bool = False
    # Personal boards the caller manages: shared with anyone at all.
    is_shared: bool = False


class DashboardDetailOut(DashboardOut):
    # Only for those who manage the board: it describes the token the board
    # reads with, which may be someone else's.
    token_info: Optional[TokenInfoOut] = None
    # Whether the caller can make changes on GitHub from this board, and if
    # not, why.
    can_write: bool = False
    write_block_reason: Optional[str] = None
    organization_id: str
    organization_name: str
    # True when opening this board moved the session into its organisation.
    switched_organization: bool = False


class OrganizationOut(BaseModel):
    id: str
    slug: str
    name: str
    is_main: bool
    role: str
    is_active: bool
    is_default: bool
    # Admins only: whether the organisation has a token for its boards.
    has_token: Optional[bool] = None


class OrganizationCreate(BaseModel):
    name: str


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None


class OrganizationMemberOut(BaseModel):
    user_id: int
    username: str
    role: str
    joined_at: datetime


class OrganizationMemberUpdate(BaseModel):
    role: str


class DefaultOrganizationUpdate(BaseModel):
    # An organisation's id, or null to go back to "wherever I was last".
    organization_id: Optional[str] = None


# ---- Columns ----

class ColumnCreate(BaseModel):
    name: str
    state: Optional[str] = "open"
    labels: List[str] = []
    milestone: Optional[str] = None
    assignee: Optional[str] = None
    creator: Optional[str] = None
    issue_type: Optional[str] = None
    position: Optional[int] = None


class ColumnUpdate(BaseModel):
    name: Optional[str] = None
    state: Optional[str] = None
    labels: Optional[List[str]] = None
    # "" clears these back to "any".
    milestone: Optional[str] = None
    assignee: Optional[str] = None
    creator: Optional[str] = None
    issue_type: Optional[str] = None
    position: Optional[int] = None


class ColumnReorder(BaseModel):
    # Real column ids in their new left-to-right order. Virtual columns
    # are ignored — they always sit last.
    column_ids: List[int]


class ColumnOut(BaseModel):
    id: int
    dashboard_id: str
    name: str
    position: int
    state: Optional[str]
    labels: List[str]
    milestone: Optional[str]
    assignee: Optional[str]
    creator: Optional[str] = None
    issue_type: Optional[str] = None
    # Virtual columns ("Assigned to me" / "Created by me") are synthesized
    # from the saved username rather than stored, so they can't be edited
    # or deleted and always sit last.
    virtual: bool = False
    # Whether dragging/moving into this column maps to one unambiguous
    # mutation — the frontend uses this to enable/disable drop.
    drag_compatible: bool


# ---- GitHub metadata (for the column filter builder) ----

class LabelOut(BaseModel):
    name: str
    color: str
    description: Optional[str] = None


class MilestoneOut(BaseModel):
    number: int
    title: str
    state: str


class AssigneeOut(BaseModel):
    login: str
    avatar_url: str


class IssueTypeOut(BaseModel):
    name: str
    color: Optional[str] = None
    description: Optional[str] = None


class RepoMetadataOut(BaseModel):
    labels: List[LabelOut]
    milestones: List[MilestoneOut]
    assignees: List[AssigneeOut]
    issue_types: List[IssueTypeOut] = []
    # Where the types came from: types actually used on this repo's issues
    # ("repo"), the org-level registry ("org"), or both. Repo-observed
    # types are listed first, since those are the ones that will match.
    issue_types_source: str = "none"


# ---- Issue cards ----

class IssueCardOut(BaseModel):
    number: int
    title: str
    summary: str
    state: str
    html_url: str
    labels: List[LabelOut]
    assignees: List[AssigneeOut]
    milestone: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None
    comments_count: int
    age_days: int
    has_local_note: bool
    # From `sub_issues_summary` on the issue payload — free, no extra call.
    sub_issues_total: int = 0
    sub_issues_completed: int = 0


class IssueDetailOut(BaseModel):
    number: int
    title: str
    body: Optional[str]
    state: str
    html_url: str
    labels: List[LabelOut]
    assignees: List[AssigneeOut]
    milestone: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None
    comments: List["CommentOut"]
    notes: List["NoteOut"]
    sub_issues: List["SubIssueOut"] = []


class CommentCreate(BaseModel):
    body: str


class CommentOut(BaseModel):
    id: int
    author: str
    body: str
    created_at: datetime


class SubIssueOut(BaseModel):
    number: int
    title: str
    state: str
    html_url: str


class MoveIssueRequest(BaseModel):
    target_column_id: int


# ---- Sticky notes (board-level scratch pad) ----

class StickyNoteCreate(BaseModel):
    body: str = ""


class StickyNoteUpdate(BaseModel):
    body: Optional[str] = None
    pinned: Optional[bool] = None
    archived: Optional[bool] = None


class StickyNoteOut(BaseModel):
    id: int
    dashboard_id: str
    body: str
    pinned: bool
    archived: bool
    created_at: datetime
    updated_at: datetime


# ---- Notes ----

class NoteCreate(BaseModel):
    issue_number: int
    body: str


class NoteUpdate(BaseModel):
    body: str


class NoteOut(BaseModel):
    id: int
    dashboard_id: str
    issue_number: int
    body: str
    created_at: datetime
    updated_at: datetime
    synced: bool
    github_comment_id: Optional[int] = None


IssueDetailOut.model_rebuild()


# ---- Invitations, join requests, notifications ----

class InvitationCreate(BaseModel):
    role: str = "member"
    label: Optional[str] = None


class InvitationOut(BaseModel):
    id: str
    role: str
    label: Optional[str] = None
    status: str  # "pending" | "accepted" | "expired" | "revoked"
    created_at: datetime
    expires_at: datetime
    invited_by: Optional[str] = None
    accepted_by: Optional[str] = None


class InvitationCreatedOut(InvitationOut):
    # Shown once, at creation. Only its hash is stored.
    token: str


class InvitationPreviewOut(BaseModel):
    """What someone holding the link may see before signing in."""

    organization_name: str
    role: str
    status: str


class InvitationAcceptOut(BaseModel):
    organization_id: str
    organization_name: str
    already_member: bool


class OrganizationLookupOut(BaseModel):
    """An organisation found by its link, as the person holding the link
    sees it."""

    id: str
    slug: str
    name: str
    is_member: bool
    request_status: Optional[str] = None  # the latest request's status, if any


class JoinRequestOut(BaseModel):
    id: str
    username: str
    status: str
    via: str
    created_at: datetime


class JoinRequestDecision(BaseModel):
    role: str = "member"


class NotificationOut(BaseModel):
    id: int
    kind: str
    organization_id: Optional[str] = None
    organization_name: Optional[str] = None
    actor: Optional[str] = None
    created_at: datetime
    read: bool


class NotificationsOut(BaseModel):
    unread: int
    items: list[NotificationOut]


class NotificationsRead(BaseModel):
    # Specific notifications, or all of them when omitted.
    ids: Optional[list[int]] = None


# ---- Sharing ----

class BoardSharingOut(BaseModel):
    shared_with_organization: bool
    user_ids: list[int]


class BoardSharingUpdate(BaseModel):
    shared_with_organization: bool = False
    user_ids: list[int] = []


class OrganizationTokenUpdate(BaseModel):
    # An empty string removes it.
    token: str
