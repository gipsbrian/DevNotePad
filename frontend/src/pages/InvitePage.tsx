import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useOrganizations } from "../org-context";
import type { InvitationPreview } from "../types/api";

/** An invitation link opened while signed in. Joining is a deliberate click
 * rather than automatic, so a link can't quietly move someone into an
 * organisation just by being opened. */
export function InvitePage() {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const { reload } = useOrganizations();
  const [preview, setPreview] = useState<InvitationPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    document.title = "Invitation · DevNotePad";
    api
      .previewInvitation(token)
      .then(setPreview)
      .catch((e) => setError((e as Error).message));
  }, [token]);

  async function accept() {
    setBusy(true);
    setError(null);
    try {
      await api.acceptInvitation(token);
      await reload();
      navigate("/", { replace: true });
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <main className="app-main">
      <section className="org-section join-card">
        {!preview && !error && <p className="empty-hint">Checking the invitation…</p>}
        {error && !preview && (
          <>
            <h1 className="page-title">This invitation link isn’t valid</h1>
            <p className="page-sub">Check you copied the whole link, or ask an admin for a new one.</p>
          </>
        )}
        {preview && (
          <>
            <p className="join-eyebrow">Invitation</p>
            <h1 className="page-title">{preview.organization_name}</h1>
            {preview.status === "pending" ? (
              <>
                <p className="page-sub">
                  You’ve been invited to join as {preview.role === "admin" ? "an admin" : "a member"}.
                </p>
                {error && (
                  <p className="form-error" role="alert">
                    {error}
                  </p>
                )}
                <div className="join-actions">
                  <button className="btn primary" onClick={accept} disabled={busy}>
                    {busy ? "Joining…" : `Join ${preview.organization_name}`}
                  </button>
                  <button className="btn ghost" onClick={() => navigate("/")} disabled={busy}>
                    Not now
                  </button>
                </div>
              </>
            ) : (
              <p className="page-sub">
                This invitation is {preview.status === "accepted" ? "already used" : preview.status}. Ask an admin
                there for a new link.
              </p>
            )}
          </>
        )}
      </section>
    </main>
  );
}
