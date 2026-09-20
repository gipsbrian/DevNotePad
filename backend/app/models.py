from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import Column as SAColumn
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from .crypto import EncryptedToken


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Dashboard(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # What the API and the URL identify a board by. The integer primary
    # key stays internal: it's guessable, so it never leaves the backend.
    uuid: str = Field(default_factory=lambda: str(uuid4()), index=True, unique=True)
    name: str
    repo_owner: str
    repo_name: str
    # Per-dashboard token override. Never returned verbatim over the API
    # once set — only a masked form and its detected type/permission.
    # Encrypted at rest by the column type.
    token: Optional[str] = Field(default=None, sa_column=SAColumn(EncryptedToken))
    # The account the board belongs to. Nobody else can see or reach it.
    owner_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    # The organisation the board lives in; only its active members reach it.
    organization_id: Optional[int] = Field(default=None, foreign_key="organization.id", index=True)
    # "personal": managed by its owner, private unless shared.
    # "organization": managed by the organisation's admins, seen by every member.
    kind: str = Field(default="personal", sa_column_kwargs={"server_default": "personal"})
    # Personal boards only: every member of the organisation may view it.
    shared_with_organization: bool = Field(default=False, sa_column_kwargs={"server_default": "0"})
    created_at: datetime = Field(default_factory=utcnow)

    # Appearance — purely cosmetic, app-side only (like a Trello board
    # background). Never affects GitHub data or filtering.
    accent_color: Optional[str] = None  # hex, e.g. "#0052cc"
    background_url: Optional[str] = None  # image URL used as board wallpaper


class User(SQLModel, table=True):
    """An account. Boards and settings belong to exactly one."""

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    # Guided tours this account has finished or dismissed, comma-separated.
    tours_seen: str = ""
    # Where to land after signing in: the chosen default, else the last
    # organisation used.
    default_organization_id: Optional[int] = None
    last_organization_id: Optional[int] = None
    created_at: datetime = Field(default_factory=utcnow)


class Organization(SQLModel, table=True):
    """A group of accounts working together. Exactly one is the main
    organisation, which every account belongs to."""

    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: str = Field(default_factory=lambda: str(uuid4()), index=True, unique=True)
    # Names the organisation in its sign-in link. Fixed once created.
    slug: str = Field(index=True, unique=True)
    name: str
    is_main: bool = False
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=utcnow)
    # Reads the organisation's boards when they carry no token of their own.
    # Set by an admin; never returned over the API.
    token: Optional[str] = Field(default=None, sa_column=SAColumn(EncryptedToken))


class BoardShare(SQLModel, table=True):
    """A personal board shared, view-only, with one member of its organisation."""

    id: Optional[int] = Field(default=None, primary_key=True)
    dashboard_id: int = Field(foreign_key="dashboard.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)

    __table_args__ = (UniqueConstraint("dashboard_id", "user_id"),)


class Membership(SQLModel, table=True):
    """An account's place in an organisation. Removal is soft: the row stays
    with `removed_at` set, so the person's boards there return if they're
    added again."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    role: str = "member"  # "admin" | "member"
    created_at: datetime = Field(default_factory=utcnow)
    removed_at: Optional[datetime] = None

    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)


class Invitation(SQLModel, table=True):
    """A single-use link that adds whoever opens it to an organisation.

    Only a hash of the link's token is stored, so the database alone can't
    be used to join anything. There's deliberately no email on it: this app
    doesn't verify the email on a password account, so tying an invitation
    to one would look like a safeguard without being one."""

    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: str = Field(default_factory=lambda: str(uuid4()), index=True, unique=True)
    organization_id: int = Field(foreign_key="organization.id", index=True)
    role: str = "member"
    # Who it's meant for, as the inviting admin describes them.
    label: Optional[str] = None
    token_hash: str = Field(index=True, unique=True)
    invited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    accepted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    accepted_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


class JoinRequest(SQLModel, table=True):
    """Someone asking to join an organisation, for its admins to decide."""

    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: str = Field(default_factory=lambda: str(uuid4()), index=True, unique=True)
    organization_id: int = Field(foreign_key="organization.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    via: str = "link"  # "link" | "sso"
    status: str = "pending"  # "pending" | "approved" | "declined"
    decided_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=utcnow)
    decided_at: Optional[datetime] = None


class Notification(SQLModel, table=True):
    """Something one account should hear about. Shown in the app; email
    delivery comes later."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    # "join_request" | "join_approved" | "join_declined" | "invitation_accepted"
    kind: str
    organization_id: Optional[int] = Field(default=None, foreign_key="organization.id")
    # The other person involved, when there is one.
    actor_id: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=utcnow)
    read_at: Optional[datetime] = None


class SsoProvider(SQLModel, table=True):
    """One organisation's settings for one identity provider. Secrets are
    encrypted at rest and never returned over the API."""

    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: str = Field(default_factory=lambda: str(uuid4()), index=True, unique=True)
    organization_id: int = Field(foreign_key="organization.id", index=True)
    type: str  # "google" | "microsoft" | "apple"
    enabled: bool = False
    client_id: str = ""
    # For Apple, the contents of the .p8 Sign in with Apple key.
    client_secret: Optional[str] = Field(default=None, sa_column=SAColumn(EncryptedToken))
    tenant: Optional[str] = None  # Microsoft
    team_id: Optional[str] = None  # Apple
    key_id: Optional[str] = None  # Apple
    # Verified emails on these domains (comma-separated) join the
    # organisation straight away instead of asking.
    auto_join_domains: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    __table_args__ = (UniqueConstraint("organization_id", "type"),)


class SsoIdentity(SQLModel, table=True):
    """An account at an identity provider, tied to one DevNotePad account.

    Matched on the provider's own stable id for the person (`subject`, the
    token's `sub`), never on email: emails change, and some providers only
    send one the first time, or let it be set to anything."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    provider: str = Field(index=True)
    subject: str
    # As last reported, for display only -- never used to find the account.
    email: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)

    __table_args__ = (UniqueConstraint("provider", "subject"),)


class SsoLoginAttempt(SQLModel, table=True):
    """One sign-in in flight, from leaving for the provider to arriving back.

    Kept server-side rather than in the session cookie because Apple returns
    people with a cross-site POST, which a SameSite=Lax session cookie
    doesn't ride along on."""

    # The OAuth `state` value: random, single-use, and short-lived.
    state: str = Field(primary_key=True)
    provider: str
    nonce: str
    code_verifier: Optional[str] = None
    # Hash of a random value held in a cookie on the browser that started
    # the attempt, so a sign-in can't be finished in somebody else's browser.
    binding_hash: str
    # Which organisation's sign-in page this started from, and which of its
    # provider rows (none: the .env fallback).
    organization_id: Optional[int] = None
    sso_provider_id: Optional[int] = None
    # Decided at the callback, applied at finish: the organisation to land in
    # (none: the usual default), and a notice code for the app to show.
    land_organization_id: Optional[int] = None
    notice: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    # Set once the provider has vouched for someone: the account to sign
    # in, and the one-time ticket that hands the session over.
    user_id: Optional[int] = None
    ticket: Optional[str] = Field(default=None, index=True)


class AppSettings(SQLModel, table=True):
    """One row per account, for things that cut across all of its boards."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True, unique=True)
    # Drives the automatic "Assigned to me" / "Created by me" columns.
    github_username: Optional[str] = None
    # General token/org used by any board that doesn't override them.
    # For the instance owner only, falls back to GIT_TOKEN / GIT_ORG_URL
    # from .env when unset.
    default_token: Optional[str] = Field(default=None, sa_column=SAColumn(EncryptedToken))
    default_org_url: Optional[str] = None
    show_my_columns: bool = True


class Column(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    dashboard_id: int = Field(foreign_key="dashboard.id", index=True)
    name: str
    position: int = 0
    # Filter — every value here must come from GitHub's existing data
    # (labels/state/milestone/assignee already on the repo), never
    # something the app lets you invent.
    state: Optional[str] = "open"  # "open" | "closed" | None (any)
    labels_csv: Optional[str] = None  # comma-separated label names
    milestone: Optional[str] = None  # milestone number as string, or "none"
    assignee: Optional[str] = None
    creator: Optional[str] = None
    # GitHub's org-level issue type (e.g. "Bug", "Feature"), distinct from
    # labels. Stored by name, which is what the REST filter takes.
    issue_type: Optional[str] = None

    @property
    def labels(self) -> List[str]:
        if not self.labels_csv:
            return []
        return [l for l in self.labels_csv.split(",") if l]

    @labels.setter
    def labels(self, value: List[str]) -> None:
        self.labels_csv = ",".join(value) if value else None


class StickyNote(SQLModel, table=True):
    """A board-level scratch note, unattached to any issue — distinct from
    LocalNote, which annotates one specific issue."""

    id: Optional[int] = Field(default=None, primary_key=True)
    dashboard_id: int = Field(foreign_key="dashboard.id", index=True)
    # Whose note it is. Private to them, on every board, shared or not.
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    body: str = ""
    pinned: bool = False
    archived: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class LocalNote(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    dashboard_id: int = Field(foreign_key="dashboard.id", index=True)
    # Whose note it is. Private to them, on every board, shared or not.
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    issue_number: int = Field(index=True)
    body: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    synced: bool = False
    github_comment_id: Optional[int] = None
