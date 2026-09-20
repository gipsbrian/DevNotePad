import { useState } from "react";
import type { Dashboard, Settings } from "../types/api";
import { api } from "../api/client";
import { IconTrash } from "./Icons";

export const PRESET_COLORS = [
  "#6d5efc",
  "#0b74de",
  "#12a37a",
  "#e0483d",
  "#f2621f",
  "#d63aa0",
  "#0f766e",
  "#232b3d",
];

export function CustomizePanel({
  dashboard,
  settings,
  onChanged,
  onDeleted,
  onClose,
}: {
  dashboard: Dashboard;
  settings: Settings | null;
  onChanged: (d: Dashboard) => void;
  onDeleted: () => void;
  onClose: () => void;
}) {
  const [name, setName] = useState(dashboard.name);
  const [repoRef, setRepoRef] = useState(`${dashboard.repo_owner}/${dashboard.repo_name}`);
  const [useOwnToken, setUseOwnToken] = useState(dashboard.has_own_token);
  const [token, setToken] = useState("");
  const [accentColor, setAccentColor] = useState(dashboard.accent_color ?? PRESET_COLORS[0]);
  const [backgroundUrl, setBackgroundUrl] = useState(dashboard.background_url ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const details: { name?: string; repo_ref?: string; token?: string } = {};
      if (name !== dashboard.name) details.name = name;
      if (repoRef !== `${dashboard.repo_owner}/${dashboard.repo_name}`) details.repo_ref = repoRef;
      if (!useOwnToken && dashboard.has_own_token) details.token = ""; // fall back to the general one
      if (useOwnToken && token) details.token = token;

      let updated: Dashboard = dashboard;
      if (Object.keys(details).length > 0) updated = await api.updateDashboard(dashboard.id, details);

      updated = await api.updateAppearance(dashboard.id, {
        accent_color: accentColor,
        background_url: backgroundUrl || null,
      });

      onChanged(updated);
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="panel customize-panel">
      <h4>Board settings</h4>

      <div className="form-row">
        <label>Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </div>

      <div className="form-row">
        <label>Repository</label>
        <input
          value={repoRef}
          onChange={(e) => setRepoRef(e.target.value)}
          placeholder="owner/repo or https://github.com/owner/repo"
        />
        <p className="empty-hint" style={{ marginTop: 6 }}>
          Changing this repoints the board — columns and local notes stay, but they’ll now match issues in the new repo.
        </p>
      </div>

      <div className="form-row">
        <label>Token</label>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 400, cursor: "pointer" }}>
            <input
              type="radio"
              name="boardtoken"
              checked={!useOwnToken}
              disabled={!settings?.has_default_token}
              onChange={() => setUseOwnToken(false)}
              style={{ width: "auto" }}
            />
            Use the general token
            {settings && !settings.has_default_token && " — none set yet"}
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 400, cursor: "pointer" }}>
            <input
              type="radio"
              name="boardtoken"
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
            placeholder={dashboard.has_own_token ? "Leave blank to keep this board’s token" : "ghp_… or github_pat_…"}
            autoComplete="off"
          />
        )}
      </div>

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
        <label>Background image URL (optional — replaces the gradient)</label>
        <input value={backgroundUrl} onChange={(e) => setBackgroundUrl(e.target.value)} placeholder="https://…/photo.jpg" />
      </div>

      {error && <p style={{ color: "var(--danger)", fontSize: 13 }}>{error}</p>}

      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn primary" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        <button className="btn ghost" onClick={onClose}>
          Cancel
        </button>
      </div>

      <div className="danger-zone">
        <span className="empty-hint" style={{ margin: 0 }}>
          Deleting removes this board’s columns and local notes. Your GitHub issues are untouched.
        </span>
        <button
          className="btn danger small"
          disabled={saving}
          onClick={async () => {
            if (!confirm(`Delete “${dashboard.name}”? Its columns and local notes go with it. GitHub is untouched.`)) return;
            setSaving(true);
            try {
              await api.deleteDashboard(dashboard.id);
              onDeleted();
            } catch (e) {
              setError((e as Error).message);
              setSaving(false);
            }
          }}
        >
          <IconTrash />
          Delete board
        </button>
      </div>
    </div>
  );
}
