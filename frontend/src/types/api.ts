export interface User {
  id: number;
  username: string;
  email: string;
  /** Guided tours this account has finished or dismissed. */
  tours_seen: string[];
  /** An admin of the main organisation, and so of the instance. */
  is_instance_admin: boolean;
}

export interface Settings {
  github_username: string | null;
  default_org_url: string | null;
  show_my_columns: boolean;
  has_default_token: boolean;
  default_token_source: "settings" | "env" | "none";
}

export interface Member {
  login: string;
  avatar_url: string;
}

export interface Insights {
  scope: "me" | "org";
  org: string;
  username: string | null;
  window_days: number;
  totals: Partial<Record<"open" | "opened_in_window" | "closed_in_window" | "open_authored", number>>;
  weekly: { week_start: string; opened: number; closed: number }[];
  top_repos: { repo: string; count: number }[];
}

export interface Dashboard {
  /** The board's uuid. The backend's row id is never exposed. */
  id: string;
  name: string;
  repo_owner: string;
  repo_name: string;
  has_own_token: boolean;
  created_at: string;
  accent_color: string | null;
  background_url: string | null;
  /** "personal" is one person's; "organization" is managed by admins and seen by every member. */
  kind: "personal" | "organization";
  /** What you may do with it: "view" (read only) or "manage". */
  access: "view" | "manage";
  owner: string | null;
  shared_with_organization: boolean;
  /** Your own personal board, shared with anyone. */
  is_shared: boolean;
}

export interface TokenInfo {
  token_type: string;
  type_label: string;
  classic_scopes: string[] | null;
  inferred_can_read: boolean | null;
  inferred_can_write: boolean | null;
  error: string | null;
  warning: string;
}

export interface DashboardDetail extends Dashboard {
  /** Only for those who manage the board. */
  token_info: TokenInfo | null;
  /** Whether you can make changes on GitHub from this board, and if not, why. */
  can_write: boolean;
  write_block_reason: string | null;
  organization_id: string;
  organization_name: string;
  /** Opening this board moved the session into its organisation. */
  switched_organization: boolean;
}

export interface Organization {
  id: string;
  slug: string;
  name: string;
  is_main: boolean;
  role: "admin" | "member";
  /** The one this session is working in. */
  is_active: boolean;
  is_default: boolean;
  /** Admins only: whether organisation boards have a token to read with. */
  has_token: boolean | null;
}

export interface OrganizationMember {
  user_id: number;
  username: string;
  role: "admin" | "member";
  joined_at: string;
}

export interface Column {
  id: number;
  dashboard_id: string;
  name: string;
  position: number;
  state: string | null;
  labels: string[];
  milestone: string | null;
  assignee: string | null;
  creator: string | null;
  issue_type: string | null;
  virtual: boolean;
  drag_compatible: boolean;
}

export interface Label {
  name: string;
  color: string;
  description: string | null;
}

export interface Milestone {
  number: number;
  title: string;
  state: string;
}

export interface Assignee {
  login: string;
  avatar_url: string;
}

export interface IssueType {
  name: string;
  color: string | null;
  description: string | null;
}

export interface RepoMetadata {
  labels: Label[];
  milestones: Milestone[];
  assignees: Assignee[];
  issue_types: IssueType[];
  issue_types_source: "repo" | "org" | "repo+org" | "none";
}

export interface IssueCard {
  number: number;
  title: string;
  summary: string;
  state: string;
  html_url: string;
  labels: Label[];
  assignees: Assignee[];
  milestone: string | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  comments_count: number;
  age_days: number;
  has_local_note: boolean;
  sub_issues_total: number;
  sub_issues_completed: number;
}

export interface SubIssue {
  number: number;
  title: string;
  state: string;
  html_url: string;
}

export interface StickyNote {
  id: number;
  dashboard_id: string;
  body: string;
  pinned: boolean;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface Comment {
  id: number;
  author: string;
  body: string;
  created_at: string;
}

export interface Note {
  id: number;
  dashboard_id: string;
  issue_number: number;
  body: string;
  created_at: string;
  updated_at: string;
  synced: boolean;
  github_comment_id: number | null;
}

export interface IssueDetail {
  number: number;
  title: string;
  body: string | null;
  state: string;
  html_url: string;
  labels: Label[];
  assignees: Assignee[];
  milestone: string | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  comments: Comment[];
  notes: Note[];
  sub_issues: SubIssue[];
}

export interface Invitation {
  id: string;
  role: "admin" | "member";
  label: string | null;
  status: "pending" | "accepted" | "expired" | "revoked";
  created_at: string;
  expires_at: string;
  invited_by: string | null;
  accepted_by: string | null;
}

export interface InvitationPreview {
  organization_name: string;
  role: "admin" | "member";
  status: Invitation["status"];
}

export interface OrganizationLookup {
  id: string;
  slug: string;
  name: string;
  is_member: boolean;
  request_status: "pending" | "approved" | "declined" | null;
}

export interface JoinRequest {
  id: string;
  username: string;
  status: "pending" | "approved" | "declined";
  via: string;
  created_at: string;
}

export interface AppNotification {
  id: number;
  kind: "join_request" | "join_approved" | "join_declined" | "invitation_accepted";
  organization_id: string | null;
  organization_name: string | null;
  actor: string | null;
  created_at: string;
  read: boolean;
}

export interface SsoProviderSettings {
  type: "google" | "microsoft" | "apple";
  label: string;
  configured: boolean;
  enabled: boolean;
  client_id: string;
  has_secret: boolean;
  tenant: string | null;
  team_id: string | null;
  key_id: string | null;
  auto_join_domains: string[];
  ready: boolean;
  callback_url: string | null;
}

export interface OrganizationSso {
  public_url_set: boolean;
  login_url: string | null;
  providers: SsoProviderSettings[];
}

export interface SsoProviderInput {
  enabled: boolean;
  client_id: string;
  /** Omit to keep the saved secret. For Apple, the .p8 key. */
  client_secret?: string;
  tenant?: string | null;
  team_id?: string | null;
  key_id?: string | null;
  auto_join_domains: string[];
}

export interface AdminOverview {
  main_organization_id: string;
  registration_open: boolean;
  public_url: string | null;
  users: number;
  organizations: number;
  boards: number;
}

export interface AdminUser {
  id: number;
  username: string;
  email: string;
  created_at: string;
  is_instance_admin: boolean;
  organizations: number;
  boards: number;
  has_password: boolean;
  sso_providers: string[];
}

export interface AdminOrganization {
  id: string;
  slug: string;
  name: string;
  is_main: boolean;
  created_at: string;
  created_by: string | null;
  members: number;
  admins: number;
  boards: number;
}
