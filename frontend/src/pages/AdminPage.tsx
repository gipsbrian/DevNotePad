import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth-context";
import type { AdminOrganization, AdminOverview, AdminUser } from "../types/api";

function day(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** The instance at a glance, for its admins (the main organisation's admins). */
export function AdminPage() {
  const { user } = useAuth();
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [orgs, setOrgs] = useState<AdminOrganization[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    Promise.all([api.adminOverview(), api.adminUsers(), api.adminOrganizations()])
      .then(([o, u, g]) => {
        setOverview(o);
        setUsers(u);
        setOrgs(g);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  useEffect(() => {
    document.title = "Instance admin · DevNotePad";
    load();
  }, [load]);

  async function setAdmin(target: AdminUser, admin: boolean) {
    if (!overview) return;
    const verb = admin ? "Make" : "Remove";
    if (!confirm(`${verb} ${target.username} ${admin ? "an instance admin" : "as an instance admin"}?`)) return;
    setBusy(true);
    setError(null);
    try {
      await api.setOrganizationMemberRole(overview.main_organization_id, target.id, admin ? "admin" : "member");
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (error && !overview) return <main className="app-main"><p className="state-msg">{error}</p></main>;
  if (!overview || !users || !orgs) return <main className="app-main"><p className="state-msg">Loading…</p></main>;

  return (
    <main className="app-main">
      <header className="page-head">
        <div>
          <h1 className="page-title">Instance admin</h1>
          <p className="page-sub">
            Everyone here administers the main organisation, and through it the instance. Single sign-on for the main
            sign-in page is set in Main’s organisation settings.
          </p>
        </div>
      </header>

      <div className="stat-row admin-stats">
        {[
          ["Accounts", overview.users],
          ["Organisations", overview.organizations],
          ["Boards", overview.boards],
        ].map(([label, value]) => (
          <div className="stat-tile" key={label}>
            <div>
              <div className="stat-value">{value}</div>
              <div className="stat-label">{label}</div>
            </div>
          </div>
        ))}
        <div className="stat-tile">
          <div>
            <div className="stat-value small">{overview.registration_open ? "Open" : "Closed"}</div>
            <div className="stat-label">Registration (ALLOW_REGISTRATION)</div>
          </div>
        </div>
      </div>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      <section className="org-section wide">
        <h2>
          Accounts <span className="org-count">{users.length}</span>
        </h2>
        <div className="table-scroll">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Signs in with</th>
                <th>Organisations</th>
                <th>Boards</th>
                <th>Joined</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>
                    <strong>{u.username}</strong>
                    {u.is_instance_admin && <span className="admin-badge">Admin</span>}
                    <small>{u.email}</small>
                  </td>
                  <td>{[u.has_password ? "Password" : null, ...u.sso_providers.map((s) => s[0].toUpperCase() + s.slice(1))].filter(Boolean).join(", ")}</td>
                  <td>{u.organizations}</td>
                  <td>{u.boards}</td>
                  <td>{day(u.created_at)}</td>
                  <td className="admin-actions">
                    {u.id !== user.id &&
                      (u.is_instance_admin ? (
                        <button className="btn small ghost" disabled={busy} onClick={() => setAdmin(u, false)}>
                          Remove admin
                        </button>
                      ) : (
                        <button className="btn small" disabled={busy} onClick={() => setAdmin(u, true)}>
                          Make admin
                        </button>
                      ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="org-section wide">
        <h2>
          Organisations <span className="org-count">{orgs.length}</span>
        </h2>
        <div className="table-scroll">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Organisation</th>
                <th>Members</th>
                <th>Admins</th>
                <th>Boards</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {orgs.map((o) => (
                <tr key={o.id}>
                  <td>
                    <strong>{o.name}</strong>
                    {o.is_main && <span className="admin-badge">Main</span>}
                    <small>/o/{o.slug}{o.created_by ? ` · by ${o.created_by}` : ""}</small>
                  </td>
                  <td>{o.members}</td>
                  <td>{o.admins}</td>
                  <td>{o.boards}</td>
                  <td>{day(o.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
