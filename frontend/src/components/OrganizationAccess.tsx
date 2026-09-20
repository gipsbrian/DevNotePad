import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Invitation, JoinRequest, Organization } from "../types/api";
import { copyText } from "../utils/clipboard";
import { IconCopy, IconLink } from "./Icons";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** How people get into an organisation, for its admins: invitation links,
 * requests waiting on a decision, and the link people can ask to join from. */
export function OrganizationAccess({ organization, onMembersChanged }: { organization: Organization; onMembersChanged: () => void }) {
  const [requests, setRequests] = useState<JoinRequest[] | null>(null);
  const [invitations, setInvitations] = useState<Invitation[] | null>(null);
  const [role, setRole] = useState<Invitation["role"]>("member");
  const [label, setLabel] = useState("");
  // The newest link, shown in full once: only its hash is kept on the server.
  const [freshLink, setFreshLink] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.listJoinRequests(organization.id).then(setRequests).catch((e) => setError((e as Error).message));
    api.listInvitations(organization.id).then(setInvitations).catch((e) => setError((e as Error).message));
  }, [organization.id]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(null), 2000);
    return () => clearTimeout(timer);
  }, [copied]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function copy(text: string, what: string) {
    setCopied((await copyText(text)) ? what : "Couldn’t copy");
  }

  const joinLink = `${window.location.origin}/o/${organization.slug}`;
  const pending = invitations?.filter((i) => i.status === "pending") ?? [];
  const used = invitations?.filter((i) => i.status !== "pending").slice(0, 5) ?? [];

  return (
    <>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      <section className="org-section">
        <h2>
          Join requests {requests && requests.length > 0 && <span className="org-count attention">{requests.length}</span>}
        </h2>
        {requests?.length === 0 && <p className="empty-hint">Nobody is waiting to join.</p>}
        {requests && requests.length > 0 && (
          <ul className="org-members">
            {requests.map((r) => (
              <li key={r.id}>
                <span className="org-member-avatar">{r.username.slice(0, 2).toUpperCase()}</span>
                <span className="org-member-name">
                  {r.username}
                  <small className="org-sub">asked {formatDate(r.created_at)}</small>
                </span>
                <button
                  className="btn small primary"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      await api.decideJoinRequest(organization.id, r.id, true);
                      load();
                      onMembersChanged();
                    })
                  }
                >
                  Approve
                </button>
                <button
                  className="btn small ghost"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      await api.decideJoinRequest(organization.id, r.id, false);
                      load();
                    })
                  }
                >
                  Decline
                </button>
              </li>
            ))}
          </ul>
        )}
        {!organization.is_main && (
          <div className="org-share">
            <span>
              <IconLink /> People can ask to join at
            </span>
            <code>{joinLink}</code>
            <button className="btn small" onClick={() => copy(joinLink, "Join link copied")}>
              <IconCopy /> Copy
            </button>
          </div>
        )}
      </section>

      <section className="org-section">
        <h2>Invite people</h2>
        <p className="empty-hint">
          Each link lets one person in and lasts 7 days. Send it to them yourself; this app doesn’t send email yet.
        </p>
        <form
          className="org-invite"
          onSubmit={(e) => {
            e.preventDefault();
            run(async () => {
              const created = await api.createInvitation(organization.id, role, label);
              setFreshLink(`${window.location.origin}/invite/${created.token}`);
              setLabel("");
              load();
            });
          }}
        >
          <div className="form-row">
            <label htmlFor="invite-label">Who it’s for (optional)</label>
            <input
              id="invite-label"
              value={label}
              maxLength={80}
              placeholder="e.g. Sam from design"
              onChange={(e) => setLabel(e.target.value)}
            />
          </div>
          <div className="form-row">
            <label htmlFor="invite-role">Joins as</label>
            <select id="invite-role" value={role} onChange={(e) => setRole(e.target.value as Invitation["role"])}>
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <button className="btn primary" type="submit" disabled={busy}>
            Create link
          </button>
        </form>

        {freshLink && (
          <div className="org-fresh-link" role="status">
            <p>Copy this now. For safety it isn’t shown again; make a new one if it’s lost.</p>
            <div className="org-share">
              <code>{freshLink}</code>
              <button className="btn small primary" onClick={() => copy(freshLink, "Invitation copied")}>
                <IconCopy /> Copy
              </button>
            </div>
          </div>
        )}
        {copied && <p className="org-saved">{copied}</p>}

        {pending.length > 0 && (
          <>
            <h3 className="org-subhead">Waiting to be used</h3>
            <ul className="org-invitations">
              {pending.map((i) => (
                <li key={i.id}>
                  <span className="org-member-name">
                    {i.label || "Unlabelled link"}
                    <small className="org-sub">
                      {i.role === "admin" ? "Admin" : "Member"} · expires {formatDate(i.expires_at)}
                      {i.invited_by ? ` · by ${i.invited_by}` : ""}
                    </small>
                  </span>
                  <button
                    className="btn small ghost danger"
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        await api.revokeInvitation(organization.id, i.id);
                        load();
                      })
                    }
                  >
                    Withdraw
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
        {used.length > 0 && (
          <>
            <h3 className="org-subhead">Recently closed</h3>
            <ul className="org-invitations muted">
              {used.map((i) => (
                <li key={i.id}>
                  <span className="org-member-name">
                    {i.label || "Unlabelled link"}
                    <small className="org-sub">
                      {i.status === "accepted" ? `Used by ${i.accepted_by ?? "someone"}` : i.status === "revoked" ? "Withdrawn" : "Expired"}
                    </small>
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </>
  );
}
