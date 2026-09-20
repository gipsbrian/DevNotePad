import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Dashboard, Settings } from "../types/api";
import { useOrganizations } from "../org-context";
import { PRESET_COLORS } from "../components/CustomizePanel";
import { IconAlert, IconPlus } from "../components/Icons";

/** Turns "https://github.com/my-org" into "my-org/" so the repo field is
 * already half-filled with what we know. */
function orgPrefix(orgUrl: string | null): string {
  if (!orgUrl) return "";
  const login = orgUrl.replace(/^https?:\/\/(www\.)?github\.com\//i, "").replace(/\/+$/, "");
  return login && !login.includes("/") ? `${login}/` : "";
}

export function CreateDashboardPage() {
  const navigate = useNavigate();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [name, setName] = useState("");
  const [repoRef, setRepoRef] = useState("");
  const { active } = useOrganizations();
  const isAdmin = active?.role === "admin";
  const [kind, setKind] = useState<Dashboard["kind"]>("personal");
  const forOrganization = kind === "organization";
  const [useOwnToken, setUseOwnToken] = useState(false);
  useEffect(() => {
    if (forOrganization && !active?.has_token) setUseOwnToken(true);
  }, [forOrganization, active?.has_token]);
  const [token, setToken] = useState("");
  const [accentColor, setAccentColor] = useState<string>(PRESET_COLORS[0]);
  const [backgroundUrl, setBackgroundUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getSettings().then((s) => {
      setSettings(s);
      setRepoRef((current) => current || orgPrefix(s.default_org_url));
      // Without a general token there's nothing to fall back on, so the
      // board has to carry its own.
      if (!s.has_default_token) setUseOwnToken(true);
    });
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const dashboard = await api.createDashboard({
        name,
        repo_ref: repoRef,
        token: useOwnToken && token ? token : undefined,
        kind,
        accent_color: accentColor,
        background_url: backgroundUrl || undefined,
      });
      navigate(`/dashboards/${dashboard.id}`);
    } catch (err) {
      setError((err as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <main className="app-main">
      <header className="page-head">
        <div>
          <h1 className="page-title">New board</h1>
          <p className="page-sub">Point it at one repo — columns come next, built from that repo’s own labels.</p>
        </div>
      </header>

      <div className="panel" style={{ maxWidth: 560 }}>
        <form onSubmit={handleSubmit}>
          <div className="form-row">
            <label>Board name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} required placeholder="e.g. Backend priorities" />
          </div>

          <div className="form-row">
            <label>Repository</label>
            <input
              value={repoRef}
              onChange={(e) => setRepoRef(e.target.value)}
              required
              placeholder="owner/repo or https://github.com/owner/repo"
            />
            <p className="empty-hint" style={{ marginTop: 6 }}>
              {settings?.default_org_url
                ? `Prefilled from your default org (${settings.default_org_url}). Paste a full URL to use a different one.`
                : "Paste a GitHub URL or type owner/repo."}
            </p>
          </div>

          {isAdmin && (
            <div className="form-row">
              <label>Who it’s for</label>
              <div className="kind-choice">
                <label className={kind === "personal" ? "on" : ""}>
                  <input type="radio" name="kind" checked={kind === "personal"} onChange={() => setKind("personal")} />
                  <span>
                    <strong>Just me</strong>
                    <small>A personal board. You can share it later.</small>
                  </span>
                </label>
                <label className={forOrganization ? "on" : ""}>
                  <input type="radio" name="kind" checked={forOrganization} onChange={() => setKind("organization")} />
                  <span>
                    <strong>Everyone in {active?.name}</strong>
                    <small>An organisation board every member sees; admins manage it.</small>
                  </span>
                </label>
              </div>
            </div>
          )}

          <div className="form-row">
            <label>Token</label>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 400, cursor: "pointer" }}>
                <input
                  type="radio"
                  name="tokenchoice"
                  checked={!useOwnToken}
                  disabled={forOrganization ? !active?.has_token : !settings?.has_default_token}
                  onChange={() => setUseOwnToken(false)}
                  style={{ width: "auto" }}
                />
                {forOrganization ? "Use the organisation’s token" : "Use the general token"}
                {forOrganization
                  ? !active?.has_token && " — none set yet (Organisation settings)"
                  : settings && !settings.has_default_token && " — none set yet"}
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 400, cursor: "pointer" }}>
                <input
                  type="radio"
                  name="tokenchoice"
                  checked={useOwnToken}
                  onChange={() => setUseOwnToken(true)}
                  style={{ width: "auto" }}
                />
                Use a token just for this board
              </label>
            </div>
            {useOwnToken && (
              <input
                style={{ marginTop: 8 }}
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="ghp_… or github_pat_…"
                autoComplete="off"
                required={forOrganization ? !active?.has_token : !settings?.has_default_token}
              />
            )}
          </div>

          {forOrganization && (
            <p className="empty-hint">
              Members read this board with the token chosen here. Changes on GitHub — closing, moving, commenting — are
              always made with each member’s own token.
            </p>
          )}

          {!forOrganization && settings && !settings.has_default_token && (
            <div className="notice">
              <IconAlert />
              <span>
                No general token is configured, so this board needs its own. Scope it to just this repo with{" "}
                <strong>Issues: Read-only</strong> (or Read &amp; write to close issues and post comments). You can set a
                general token once in <Link to="/">Settings</Link> instead.
              </span>
            </div>
          )}

          <div className="form-row">
            <label>Accent color</label>
            <div className="color-swatch-row">
              {PRESET_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  className={`color-swatch${accentColor === c ? " selected" : ""}`}
                  style={{ background: c }}
                  onClick={() => setAccentColor(c)}
                  aria-label={c}
                />
              ))}
            </div>
          </div>

          <div className="form-row">
            <label>Background image URL (optional)</label>
            <input value={backgroundUrl} onChange={(e) => setBackgroundUrl(e.target.value)} placeholder="https://…/photo.jpg" />
          </div>

          {error && <p style={{ color: "var(--danger)", fontSize: 13 }}>{error}</p>}

          <button className="btn primary" type="submit" disabled={submitting}>
            <IconPlus />
            {submitting ? "Creating…" : "Create board"}
          </button>
        </form>
      </div>
    </main>
  );
}
