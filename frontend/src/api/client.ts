import type {
  Column,
  Comment,
  Organization,
  OrganizationMember,
  Invitation,
  InvitationPreview,
  OrganizationLookup,
  JoinRequest,
  AppNotification,
  OrganizationSso,
  SsoProviderInput,
  AdminOverview,
  AdminUser,
  AdminOrganization,
  Dashboard,
  DashboardDetail,
  IssueCard,
  IssueDetail,
  Note,
  RepoMetadata,
  Insights,
  Member,
  Settings,
  StickyNote,
  SubIssue,
  User,
} from "../types/api";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** Fired when the server stops recognising our session, so the app can
 * drop back to the login screen wherever the call came from. */
export const UNAUTHORIZED_EVENT = "devnotepad:unauthorized";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    // The session lives in a cookie, which a cross-origin dev setup
    // (frontend and backend on different ports) drops without this.
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith("/api/auth/")) {
      window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
    }
    let message = res.statusText;
    try {
      const body = await res.json();
      message = body.detail ?? message;
    } catch {
      // ignore, keep statusText
    }
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  login: (identifier: string, password: string) =>
    request<User>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier, password }),
    }),
  register: (payload: { username: string; email: string; password: string; invitation_token?: string }) =>
    request<User>("/api/auth/register", { method: "POST", body: JSON.stringify(payload) }),
  registrationStatus: () => request<{ open: boolean }>("/api/auth/registration"),
  /** Main's providers, or the organisation's whose link this is. */
  ssoProviders: (orgSlug?: string) =>
    request<{ organization: { name: string; slug: string } | null; providers: { id: string; label: string }[] }>(
      `/api/auth/sso/providers${orgSlug ? `?org=${encodeURIComponent(orgSlug)}` : ""}`
    ),
  /** A full-page navigation target, not a fetch: the provider's sign-in page
   * has to take over the whole window. */
  ssoLoginUrl: (providerId: string, orgSlug?: string) =>
    `${API_BASE}/api/auth/sso/${encodeURIComponent(providerId)}/login${orgSlug ? `?org=${encodeURIComponent(orgSlug)}` : ""}`,
  getOrganizationSso: (orgId: string) => request<OrganizationSso>(`/api/organizations/${orgId}/sso`),
  saveOrganizationSso: (orgId: string, type: string, payload: SsoProviderInput) =>
    request<OrganizationSso>(`/api/organizations/${orgId}/sso/${type}`, { method: "PUT", body: JSON.stringify(payload) }),
  removeOrganizationSso: (orgId: string, type: string) =>
    request<void>(`/api/organizations/${orgId}/sso/${type}`, { method: "DELETE" }),

  adminOverview: () => request<AdminOverview>("/api/admin/overview"),
  adminUsers: () => request<AdminUser[]>("/api/admin/users"),
  adminOrganizations: () => request<AdminOrganization[]>("/api/admin/organizations"),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  me: () => request<User>("/api/auth/me"),
  markTourSeen: (name: string) => request<User>(`/api/auth/tours/${name}/seen`, { method: "POST" }),

  getSettings: () => request<Settings>("/api/settings"),
  detectUsername: () => request<{ login: string | null }>("/api/settings/detect-username"),
  updateSettings: (payload: {
    github_username?: string;
    default_org_url?: string;
    default_token?: string;
    show_my_columns?: boolean;
  }) => request<Settings>("/api/settings", { method: "PUT", body: JSON.stringify(payload) }),

  getInsights: (scope: "me" | "org", username?: string) =>
    request<Insights>(
      `/api/insights?scope=${scope}${username ? `&username=${encodeURIComponent(username)}` : ""}`
    ),
  listMembers: () => request<Member[]>("/api/insights/members"),

  listOrganizations: () => request<Organization[]>("/api/organizations"),
  createOrganization: (name: string) =>
    request<Organization>("/api/organizations", { method: "POST", body: JSON.stringify({ name }) }),
  switchOrganization: (id: string) =>
    request<Organization>(`/api/organizations/${id}/switch`, { method: "POST" }),
  renameOrganization: (id: string, name: string) =>
    request<Organization>(`/api/organizations/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  /** null goes back to landing wherever you were last. */
  setDefaultOrganization: (id: string | null) =>
    request<void>("/api/organizations/default", {
      method: "PUT",
      body: JSON.stringify({ organization_id: id }),
    }),
  /** An empty string removes it. */
  setOrganizationToken: (id: string, token: string) =>
    request<Organization>(`/api/organizations/${id}/token`, { method: "PUT", body: JSON.stringify({ token }) }),
  listMemberBoards: (orgId: string, userId: number) =>
    request<Dashboard[]>(`/api/organizations/${orgId}/members/${userId}/boards`),
  listOrganizationMembers: (id: string) =>
    request<OrganizationMember[]>(`/api/organizations/${id}/members`),
  setOrganizationMemberRole: (id: string, userId: number, role: OrganizationMember["role"]) =>
    request<OrganizationMember>(`/api/organizations/${id}/members/${userId}`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    }),
  /** Removing yourself is leaving. */
  removeOrganizationMember: (id: string, userId: number) =>
    request<void>(`/api/organizations/${id}/members/${userId}`, { method: "DELETE" }),

  createInvitation: (orgId: string, role: Invitation["role"], label: string) =>
    request<Invitation & { token: string }>(`/api/organizations/${orgId}/invitations`, {
      method: "POST",
      body: JSON.stringify({ role, label }),
    }),
  listInvitations: (orgId: string) => request<Invitation[]>(`/api/organizations/${orgId}/invitations`),
  revokeInvitation: (orgId: string, id: string) =>
    request<void>(`/api/organizations/${orgId}/invitations/${id}`, { method: "DELETE" }),
  previewInvitation: (token: string) => request<InvitationPreview>(`/api/invitations/${encodeURIComponent(token)}`),
  acceptInvitation: (token: string) =>
    request<{ organization_id: string; organization_name: string; already_member: boolean }>(
      `/api/invitations/${encodeURIComponent(token)}/accept`,
      { method: "POST" }
    ),

  lookupOrganization: (slug: string) =>
    request<OrganizationLookup>(`/api/organizations/by-slug/${encodeURIComponent(slug)}`),
  requestToJoin: (slug: string) =>
    request<JoinRequest>(`/api/organizations/by-slug/${encodeURIComponent(slug)}/join-requests`, { method: "POST" }),
  listJoinRequests: (orgId: string) => request<JoinRequest[]>(`/api/organizations/${orgId}/join-requests`),
  decideJoinRequest: (orgId: string, id: string, approve: boolean, role: "admin" | "member" = "member") =>
    request<JoinRequest>(`/api/organizations/${orgId}/join-requests/${id}/${approve ? "approve" : "decline"}`, {
      method: "POST",
      body: approve ? JSON.stringify({ role }) : undefined,
    }),

  listNotifications: () => request<{ unread: number; items: AppNotification[] }>("/api/notifications"),
  /** No ids marks everything read. */
  markNotificationsRead: (ids?: number[]) =>
    request<void>("/api/notifications/read", { method: "POST", body: JSON.stringify(ids ? { ids } : {}) }),

  listDashboards: () => request<Dashboard[]>("/api/dashboards"),
  getDashboard: (id: string) => request<DashboardDetail>(`/api/dashboards/${id}`),
  createDashboard: (payload: {
    name: string;
    repo_ref: string;
    token?: string;
    accent_color?: string;
    background_url?: string;
    kind?: Dashboard["kind"];
  }) => request<Dashboard>("/api/dashboards", { method: "POST", body: JSON.stringify(payload) }),
  getSharing: (id: string) =>
    request<{ shared_with_organization: boolean; user_ids: number[] }>(`/api/dashboards/${id}/sharing`),
  setSharing: (id: string, payload: { shared_with_organization: boolean; user_ids: number[] }) =>
    request<{ shared_with_organization: boolean; user_ids: number[] }>(`/api/dashboards/${id}/sharing`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  updateDashboard: (id: string, payload: { name?: string; repo_ref?: string; token?: string }) =>
    request<Dashboard>(`/api/dashboards/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteDashboard: (id: string) => request<void>(`/api/dashboards/${id}`, { method: "DELETE" }),
  updateAppearance: (id: string, payload: { accent_color?: string | null; background_url?: string | null }) =>
    request<Dashboard>(`/api/dashboards/${id}/appearance`, { method: "PATCH", body: JSON.stringify(payload) }),
  getRepoMetadata: (dashboardId: string) =>
    request<RepoMetadata>(`/api/dashboards/${dashboardId}/github-metadata`),

  listColumns: (dashboardId: string) => request<Column[]>(`/api/dashboards/${dashboardId}/columns`),
  createColumn: (
    dashboardId: string,
    payload: {
      name: string;
      state?: string | null;
      labels?: string[];
      milestone?: string | null;
      assignee?: string | null;
      creator?: string | null;
      issue_type?: string | null;
    }
  ) =>
    request<Column>(`/api/dashboards/${dashboardId}/columns`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateColumn: (dashboardId: string, columnId: number, payload: Partial<Column>) =>
    request<Column>(`/api/dashboards/${dashboardId}/columns/${columnId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  reorderColumns: (dashboardId: string, columnIds: number[]) =>
    request<Column[]>(`/api/dashboards/${dashboardId}/columns/reorder`, {
      method: "PUT",
      body: JSON.stringify({ column_ids: columnIds }),
    }),
  deleteColumn: (dashboardId: string, columnId: number) =>
    request<void>(`/api/dashboards/${dashboardId}/columns/${columnId}`, { method: "DELETE" }),

  listColumnIssues: (dashboardId: string, columnId: number) =>
    request<IssueCard[]>(`/api/dashboards/${dashboardId}/columns/${columnId}/issues`),
  /** `days` bounds the window; 0 means all time. */
  listClosedIssues: (dashboardId: string, days: number) =>
    request<IssueCard[]>(`/api/dashboards/${dashboardId}/closed?days=${days}`),
  getIssueDetail: (dashboardId: string, number: number) =>
    request<IssueDetail>(`/api/dashboards/${dashboardId}/issues/${number}`),
  listIssueComments: (dashboardId: string, number: number) =>
    request<Comment[]>(`/api/dashboards/${dashboardId}/issues/${number}/comments`),
  listSubIssues: (dashboardId: string, number: number) =>
    request<SubIssue[]>(`/api/dashboards/${dashboardId}/issues/${number}/sub-issues`),
  closeIssue: (dashboardId: string, number: number) =>
    request<IssueCard>(`/api/dashboards/${dashboardId}/issues/${number}/close`, { method: "POST" }),
  moveIssue: (dashboardId: string, number: number, targetColumnId: number) =>
    request<IssueCard>(`/api/dashboards/${dashboardId}/issues/${number}/move`, {
      method: "POST",
      body: JSON.stringify({ target_column_id: targetColumnId }),
    }),

  listStickyNotes: (dashboardId: string, archived = false) =>
    request<StickyNote[]>(`/api/dashboards/${dashboardId}/sticky-notes?archived=${archived}`),
  createStickyNote: (dashboardId: string, body: string) =>
    request<StickyNote>(`/api/dashboards/${dashboardId}/sticky-notes`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),
  updateStickyNote: (
    dashboardId: string,
    noteId: number,
    changes: { body?: string; pinned?: boolean; archived?: boolean }
  ) =>
    request<StickyNote>(`/api/dashboards/${dashboardId}/sticky-notes/${noteId}`, {
      method: "PUT",
      body: JSON.stringify(changes),
    }),
  deleteStickyNote: (dashboardId: string, noteId: number) =>
    request<void>(`/api/dashboards/${dashboardId}/sticky-notes/${noteId}`, { method: "DELETE" }),

  listNotes: (dashboardId: string, issueNumber?: number) =>
    request<Note[]>(
      `/api/dashboards/${dashboardId}/notes${issueNumber !== undefined ? `?issue_number=${issueNumber}` : ""}`
    ),
  createNote: (dashboardId: string, payload: { issue_number: number; body: string }) =>
    request<Note>(`/api/dashboards/${dashboardId}/notes`, { method: "POST", body: JSON.stringify(payload) }),
  updateNote: (noteId: number, body: string) =>
    request<Note>(`/api/notes/${noteId}`, { method: "PUT", body: JSON.stringify({ body }) }),
  deleteNote: (noteId: number) => request<void>(`/api/notes/${noteId}`, { method: "DELETE" }),
  pushNote: (noteId: number) => request<Note>(`/api/notes/${noteId}/push`, { method: "POST" }),
  /** Straight to GitHub as a comment -- no local note is kept. */
  commentOnIssue: (dashboardId: string, number: number, body: string) =>
    request<Comment>(`/api/dashboards/${dashboardId}/issues/${number}/comments`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),
};
