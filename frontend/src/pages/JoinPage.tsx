import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useOrganizations } from "../org-context";
import type { OrganizationLookup } from "../types/api";

/** An organisation's shareable link. Members go straight in; anyone else
 * can ask its admins to let them join. */
export function JoinPage() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const { switchTo } = useOrganizations();
  const [org, setOrg] = useState<OrganizationLookup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    document.title = "Join an organisation · DevNotePad";
    api
      .lookupOrganization(slug)
      .then(setOrg)
      .catch(() => setNotFound(true));
  }, [slug]);

  async function ask() {
    if (!org) return;
    setBusy(true);
    setError(null);
    try {
      await api.requestToJoin(org.slug);
      setOrg({ ...org, request_status: "pending" });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function open() {
    if (!org) return;
    await switchTo(org.id);
    navigate("/", { replace: true });
  }

  return (
    <main className="app-main">
      <section className="org-section join-card">
        {notFound && (
          <>
            <h1 className="page-title">No organisation here</h1>
            <p className="page-sub">This link doesn’t match any organisation. Check you have the whole link.</p>
          </>
        )}
        {!org && !notFound && <p className="empty-hint">Looking the organisation up…</p>}
        {org && (
          <>
            <p className="join-eyebrow">Organisation</p>
            <h1 className="page-title">{org.name}</h1>
            {org.is_member ? (
              <>
                <p className="page-sub">You’re a member.</p>
                <div className="join-actions">
                  <button className="btn primary" onClick={open}>
                    Open {org.name}
                  </button>
                </div>
              </>
            ) : org.request_status === "pending" ? (
              <p className="page-sub">
                You’ve asked to join. Its admins have been told, and you’ll get a notification when they decide.
              </p>
            ) : (
              <>
                <p className="page-sub">
                  {org.request_status === "declined"
                    ? "Your last request to join was declined. You can ask again after a few days."
                    : "Ask to join, and its admins will be notified to approve you."}
                </p>
                {error && (
                  <p className="form-error" role="alert">
                    {error}
                  </p>
                )}
                <div className="join-actions">
                  <button className="btn primary" onClick={ask} disabled={busy}>
                    {busy ? "Asking…" : "Ask to join"}
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </section>
    </main>
  );
}
