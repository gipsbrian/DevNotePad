import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth-context";
import { useOrganizations } from "../org-context";
import type { OrganizationMember } from "../types/api";

/** Share a personal board, view-only, with the whole organisation or with
 * chosen members. Nobody it's shared with sees its token or can change it. */
export function ShareModal({ dashboardId, onClose, onSaved }: { dashboardId: string; onClose: () => void; onSaved: () => void }) {
  const { user } = useAuth();
  const { active } = useOrganizations();
  const [members, setMembers] = useState<OrganizationMember[] | null>(null);
  const [everyone, setEveryone] = useState(false);
  const [chosen, setChosen] = useState<Set<number>>(new Set());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!active) return;
    Promise.all([api.getSharing(dashboardId), api.listOrganizationMembers(active.id)])
      .then(([sharing, list]) => {
        setEveryone(sharing.shared_with_organization);
        setChosen(new Set(sharing.user_ids));
        setMembers(list.filter((m) => m.user_id !== user.id));
      })
      .catch((e) => setError((e as Error).message));
  }, [dashboardId, active, user.id]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function toggle(id: number) {
    setChosen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api.setSharing(dashboardId, { shared_with_organization: everyone, user_ids: [...chosen] });
      onSaved();
      onClose();
    } catch (e) {
      setError((e as Error).message);
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal narrow" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Share board">
        <h2 className="modal-title">Share this board</h2>
        <p className="empty-hint">
          People you share with can see the columns and issues and keep their own private notes. They can’t change the
          board, act on GitHub from it, or see its token.
        </p>

        <label className="share-everyone">
          <input type="checkbox" checked={everyone} onChange={(e) => setEveryone(e.target.checked)} />
          <span>
            Everyone in <strong>{active?.name}</strong>
            <small>Including people who join later.</small>
          </span>
        </label>

        <h3 className="org-subhead">Or chosen members</h3>
        {!members && !error && <p className="empty-hint">Loading members…</p>}
        {members?.length === 0 && <p className="empty-hint">Nobody else is in this organisation yet.</p>}
        {members && members.length > 0 && (
          <ul className="share-members">
            {members.map((m) => (
              <li key={m.user_id}>
                <label className={everyone ? "covered" : ""}>
                  <input
                    type="checkbox"
                    checked={everyone || chosen.has(m.user_id)}
                    disabled={everyone}
                    onChange={() => toggle(m.user_id)}
                  />
                  <span className="org-member-avatar">{m.username.slice(0, 2).toUpperCase()}</span>
                  {m.username}
                </label>
              </li>
            ))}
          </ul>
        )}

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="modal-foot">
          <button className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" onClick={save} disabled={saving || !members}>
            {saving ? "Saving…" : "Save sharing"}
          </button>
        </div>
      </div>
    </div>
  );
}
