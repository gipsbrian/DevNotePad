import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Settings } from "../types/api";
import { IconAlert, IconUser } from "./Icons";

const TOKEN_SOURCE_LABEL: Record<Settings["default_token_source"], string> = {
  settings: "saved here",
  env: "from your .env file",
  none: "not set",
};

export function SettingsModal({
  settings,
  onSaved,
  onClose,
}: {
  settings: Settings;
  onSaved: (s: Settings) => void;
  onClose: () => void;
}) {
  const [username, setUsername] = useState(settings.github_username ?? "");
  const [orgUrl, setOrgUrl] = useState(settings.default_org_url ?? "");
  const [token, setToken] = useState("");
  const [showMyColumns, setShowMyColumns] = useState(settings.show_my_columns);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detected, setDetected] = useState<string | null>(null);

  // If we already have a token, we can tell them who it belongs to
  // rather than making them go look their username up.
  useEffect(() => {
    if (settings.github_username || !settings.has_default_token) return;
    api
      .detectUsername()
      .then(({ login }) => {
        if (!login) return;
        setDetected(login);
        setUsername((current) => current || login);
      })
      .catch(() => setDetected(null));
  }, [settings.github_username, settings.has_default_token]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const payload: Parameters<typeof api.updateSettings>[0] = {
        github_username: username,
        default_org_url: orgUrl,
        show_my_columns: showMyColumns,
      };
      // Only send the token when the user actually typed one, so saving
      // other fields never wipes an existing token.
      if (token) payload.default_token = token;
      onSaved(await api.updateSettings(payload));
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal narrow" onClick={(e) => e.stopPropagation()}>
        <h2 className="modal-title">Settings</h2>
        <p className="empty-hint">These apply to every board unless a board overrides them.</p>

        <div className="form-row" style={{ marginTop: 18 }}>
          <label>
            <IconUser style={{ width: 12, height: 12, verticalAlign: "-2px", marginRight: 5 }} />
            Your GitHub username
          </label>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="e.g. octocat"
            autoFocus
          />
          <p className="empty-hint" style={{ marginTop: 6 }}>
            {detected
              ? `Detected from your token — change it if that isn’t you. `
              : ""}
            Adds “Assigned to me” and “Created by me” as the last two columns on every board.
          </p>
        </div>

        {username && (
          <div className="form-row">
            <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={showMyColumns}
                onChange={(e) => setShowMyColumns(e.target.checked)}
                style={{ width: "auto" }}
              />
              Show those two columns
            </label>
          </div>
        )}

        <div className="form-row">
          <label>Default organization URL</label>
          <input
            value={orgUrl}
            onChange={(e) => setOrgUrl(e.target.value)}
            placeholder="https://github.com/my-org"
          />
          <p className="empty-hint" style={{ marginTop: 6 }}>
            Used to prefill the repo field when you create a board.
          </p>
        </div>

        <div className="form-row">
          <label>
            General token —{" "}
            <strong>{settings.has_default_token ? `set (${TOKEN_SOURCE_LABEL[settings.default_token_source]})` : "not set"}</strong>
          </label>
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder={settings.has_default_token ? "Leave blank to keep the current token" : "ghp_… or github_pat_…"}
            autoComplete="off"
          />
        </div>

        <div className="notice">
          <IconAlert />
          <span>
            Scope this token to just the repos you use here, with <strong>Issues: Read-only</strong> (or Read &amp; write
            to close issues and post comments). GitHub gives no way to verify a fine-grained token’s permissions, so
            this app can’t confirm it for you.
          </span>
        </div>

        {error && <p style={{ color: "var(--danger)", fontSize: 13 }}>{error}</p>}

        <div className="modal-foot">
          <button className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save settings"}
          </button>
        </div>
      </div>
    </div>
  );
}
