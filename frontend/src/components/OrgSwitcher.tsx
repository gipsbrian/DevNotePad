import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useOrganizations } from "../org-context";
import { IconCheck, IconPlus, IconSettings } from "./Icons";

export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? words[0][0] + words[1][0] : (words[0] ?? "?").slice(0, 2);
  return letters.toUpperCase();
}

/** The organisation chip at the top of the rail, and the menu it opens:
 * every organisation you're in, plus creating one and its settings. */
export function OrgSwitcher() {
  const { organizations, active, switchTo, reload } = useOrganizations();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocument(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocument);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocument);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!active) return <div className="org-chip placeholder" aria-hidden />;

  async function choose(id: string) {
    setOpen(false);
    if (id !== active!.id) {
      await switchTo(id);
      // Boards belong to an organisation, so the page you were on may not
      // exist in the one you've switched to.
      navigate("/");
    }
  }

  return (
    <div className="org-switcher" ref={ref}>
      <button
        className={`org-chip${open ? " open" : ""}`}
        data-tour="organization"
        onClick={() => setOpen((v) => !v)}
        title={`Organisation: ${active.name}`}
        aria-label={`Organisation: ${active.name}. Switch organisation`}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        {initials(active.name)}
      </button>

      {open && (
        <div className="org-menu" role="menu">
          <div className="org-menu-head">Organisations</div>
          <div className="org-menu-list">
            {organizations.map((o) => (
              <button key={o.id} role="menuitemradio" aria-checked={o.is_active} className="org-menu-item" onClick={() => choose(o.id)}>
                <span className="org-menu-badge">{initials(o.name)}</span>
                <span className="org-menu-name">
                  {o.name}
                  <small>
                    {o.role === "admin" ? "Admin" : "Member"}
                    {o.is_default ? " · Default" : ""}
                  </small>
                </span>
                {o.is_active && <IconCheck className="org-menu-check" />}
              </button>
            ))}
          </div>
          <div className="org-menu-foot">
            <button
              className="org-menu-action"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                navigate("/organization");
              }}
            >
              <IconSettings /> Organisation settings
            </button>
            <button
              className="org-menu-action"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                setCreating(true);
              }}
            >
              <IconPlus /> Create organisation
            </button>
          </div>
        </div>
      )}

      {creating && (
        <CreateOrganizationModal
          onClose={() => setCreating(false)}
          onCreated={async () => {
            setCreating(false);
            // Creating one moves you into it on the server already.
            await reload();
            navigate("/");
          }}
        />
      )}
    </div>
  );
}

function CreateOrganizationModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.createOrganization(name);
      onCreated();
    } catch (err) {
      setError((err as Error).message);
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <form className="modal narrow" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2 className="modal-title">Create an organisation</h2>
        <p className="empty-hint">
          You’ll be its admin, and you’ll move into it straight away. Your GitHub token stays personal; an admin can
          set a separate token for the organisation’s boards later.
        </p>
        <div className="form-row" style={{ marginTop: 18 }}>
          <label htmlFor="org-name">Name</label>
          <input
            id="org-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={80}
            autoFocus
            required
          />
        </div>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="modal-foot">
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn primary" disabled={saving || !name.trim()}>
            {saving ? "Creating…" : "Create organisation"}
          </button>
        </div>
      </form>
    </div>
  );
}
