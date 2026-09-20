import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth-context";
import { useOrganizations } from "../org-context";
import type { OrganizationMember } from "../types/api";
import { initials } from "../components/OrgSwitcher";
import { OrganizationAccess } from "../components/OrganizationAccess";
import { OrganizationSsoSettings } from "../components/OrganizationSso";

/** Settings for the organisation you're working in. Everyone sees the
 * members and can make it their default; admins can rename it and manage
 * roles and membership. */
export function OrganizationPage() {
  const { user } = useAuth();
  const { active, reload } = useOrganizations();
  const navigate = useNavigate();
  const [members, setMembers] = useState<OrganizationMember[] | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [orgToken, setOrgToken] = useState("");
  // Ticks the moment it's clicked; the saved value catches up after.
  const [isDefault, setIsDefault] = useState(false);

  const isAdmin = active?.role === "admin";

  const loadMembers = useCallback(() => {
    if (!active) return;
    api
      .listOrganizationMembers(active.id)
      .then(setMembers)
      .catch((e) => setError((e as Error).message));
  }, [active]);

  useEffect(() => {
    document.title = "Organisation · DevNotePad";
    setName(active?.name ?? "");
    setIsDefault(active?.is_default ?? false);
    loadMembers();
  }, [active, loadMembers]);

  useEffect(() => {
    if (!saved) return;
    const timer = setTimeout(() => setSaved(null), 2200);
    return () => clearTimeout(timer);
  }, [saved]);

  if (!active) return <main className="app-main"><p className="state-msg">Loading…</p></main>;
  const org = active;

  async function run(action: () => Promise<unknown>, message?: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      if (message) setSaved(message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="app-main">
      <header className="page-head">
        <div className="org-page-title">
          <span className="org-page-badge">{initials(org.name)}</span>
          <div>
            <h1 className="page-title">{org.name}</h1>
            <p className="page-sub">
              {org.is_main ? "The main organisation. Every account belongs to it." : "An organisation on this instance."}{" "}
              You’re {isAdmin ? "an admin" : "a member"}.
            </p>
          </div>
        </div>
      </header>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {saved && <p className="org-saved" role="status">{saved}</p>}

      <section className="org-section">
        <h2>General</h2>
        {isAdmin && (
          <form
            className="org-rename"
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                await api.renameOrganization(org.id, name);
                await reload();
              }, "Name saved");
            }}
          >
            <div className="form-row">
              <label htmlFor="org-rename">Name</label>
              <input id="org-rename" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} required />
            </div>
            <button className="btn" type="submit" disabled={busy || !name.trim() || name.trim() === org.name}>
              Save name
            </button>
          </form>
        )}

        <label className="org-default">
          <input
            type="checkbox"
            checked={isDefault}
            disabled={busy}
            onChange={(e) => {
              const next = e.target.checked;
              setIsDefault(next);
              run(async () => {
                try {
                  await api.setDefaultOrganization(next ? org.id : null);
                } catch (err) {
                  setIsDefault(!next);
                  throw err;
                }
                await reload();
              });
            }}
          />
          <span>
            Open this organisation when I sign in
            <small>Otherwise you land in whichever organisation you used last.</small>
          </span>
        </label>
      </section>

      <section className="org-section">
        <h2>Members {members && <span className="org-count">{members.length}</span>}</h2>
        {!members && <p className="empty-hint">Loading members…</p>}
        {members && (
          <ul className="org-members">
            {members.map((m) => {
              const self = m.user_id === user.id;
              return (
                <li key={m.user_id}>
                  <span className="org-member-avatar">{m.username.slice(0, 2).toUpperCase()}</span>
                  <span className="org-member-name">
                    {self ? m.username : <Link to={`/members/${m.user_id}`}>{m.username}</Link>}
                    {self && <small>You</small>}
                  </span>
                  {isAdmin ? (
                    <select
                      aria-label={`Role for ${m.username}`}
                      value={m.role}
                      disabled={busy}
                      onChange={(e) =>
                        run(async () => {
                          await api.setOrganizationMemberRole(org.id, m.user_id, e.target.value as OrganizationMember["role"]);
                          loadMembers();
                          if (self) await reload();
                        }, "Role updated")
                      }
                    >
                      <option value="admin">Admin</option>
                      <option value="member">Member</option>
                    </select>
                  ) : (
                    <span className={`org-role ${m.role}`}>{m.role === "admin" ? "Admin" : "Member"}</span>
                  )}
                  {!org.is_main && (isAdmin || self) && (
                    <button
                      className="btn small ghost danger"
                      disabled={busy}
                      onClick={() => {
                        const prompt = self
                          ? `Leave ${org.name}? Your boards here stay put and come back if you’re added again.`
                          : `Remove ${m.username} from ${org.name}? Their boards here are kept and come back if they’re added again.`;
                        if (!confirm(prompt)) return;
                        run(async () => {
                          await api.removeOrganizationMember(org.id, m.user_id);
                          if (self) {
                            await reload();
                            navigate("/");
                          } else {
                            loadMembers();
                          }
                        }, self ? undefined : "Member removed");
                      }}
                    >
                      {self ? "Leave" : "Remove"}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {isAdmin && (
        <section className="org-section">
          <h2>GitHub token for organisation boards</h2>
          <p className="empty-hint">
            Organisation boards read issues with this token unless a board has its own. It’s never shown again once
            saved. Changes on GitHub are always made with each member’s own token, never this one.
          </p>
          <p className="org-token-status">
            {org.has_token ? "A token is set." : "No token set: organisation boards need one of their own until you add it."}
          </p>
          <form
            className="org-rename"
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                await api.setOrganizationToken(org.id, orgToken);
                setOrgToken("");
                await reload();
              }, "Organisation token saved");
            }}
          >
            <div className="form-row">
              <label htmlFor="org-token">{org.has_token ? "Replace token" : "Token"}</label>
              <input
                id="org-token"
                type="password"
                autoComplete="off"
                placeholder="ghp_… or github_pat_…"
                value={orgToken}
                onChange={(e) => setOrgToken(e.target.value)}
              />
            </div>
            <button className="btn" type="submit" disabled={busy || !orgToken.trim()}>
              Save token
            </button>
            {org.has_token && (
              <button
                className="btn ghost danger"
                type="button"
                disabled={busy}
                onClick={() => {
                  if (!confirm("Remove the organisation token? Organisation boards without their own token will stop loading.")) return;
                  run(async () => {
                    await api.setOrganizationToken(org.id, "");
                    await reload();
                  }, "Organisation token removed");
                }}
              >
                Remove
              </button>
            )}
          </form>
        </section>
      )}

      {isAdmin && <OrganizationAccess organization={org} onMembersChanged={loadMembers} />}

      {isAdmin && <OrganizationSsoSettings organization={org} />}
    </main>
  );
}
