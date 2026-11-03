import { useState } from "react";
import type { RepoMetadata } from "../types/api";

export interface NewIssuePayload {
  title: string;
  body?: string;
  labels: string[];
  assignees: string[];
  milestone?: number;
  issue_type?: string;
}

/** A new issue in the board's repo. Everything but the title is optional,
 * and labels, people, milestones and types come from what the repo already
 * has, as in the column editor. */
export function NewIssueModal({
  repo,
  metadata,
  me,
  onCancel,
  onSubmit,
}: {
  repo: string;
  metadata: RepoMetadata;
  me: string | null;
  onCancel: () => void;
  /** Resolves once GitHub has it; rejects with its error. */
  onSubmit: (payload: NewIssuePayload) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [labels, setLabels] = useState<string[]>([]);
  const [assignees, setAssignees] = useState<string[]>([]);
  const [milestone, setMilestone] = useState("");
  const [issueType, setIssueType] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (list: string[], value: string) => (list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  const people = [...new Set([...(me ? [me] : []), ...metadata.assignees.map((a) => a.login)])];
  const openMilestones = metadata.milestones.filter((m) => m.state === "open");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await onSubmit({
        title: title.trim(),
        body: body.trim() ? body : undefined,
        labels,
        assignees,
        milestone: milestone ? Number(milestone) : undefined,
        issue_type: issueType || undefined,
      });
    } catch (err) {
      setError((err as Error).message);
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2 className="modal-title">New issue</h2>
        <p className="empty-hint">
          Opened on GitHub in <strong>{repo}</strong>, as you.
        </p>

        <div className="form-row" style={{ marginTop: 14 }}>
          <label htmlFor="new-issue-title">Title</label>
          <input id="new-issue-title" value={title} onChange={(e) => setTitle(e.target.value)} required autoFocus />
        </div>

        <div className="form-row">
          <label htmlFor="new-issue-body">Description</label>
          <textarea
            id="new-issue-body"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={7}
            placeholder="Markdown works, as on GitHub."
          />
        </div>

        {metadata.labels.length > 0 && (
          <div className="form-row">
            <label>Labels {labels.length > 0 && <span className="count-pill">{labels.length}</span>}</label>
            <div className="label-picker">
              {metadata.labels.map((l) => (
                <button
                  type="button"
                  key={l.name}
                  onClick={() => setLabels((prev) => toggle(prev, l.name))}
                  className={`label-pick${labels.includes(l.name) ? " on" : ""}`}
                  aria-pressed={labels.includes(l.name)}
                >
                  <i style={{ background: `#${l.color}` }} />
                  {l.name}
                </button>
              ))}
            </div>
          </div>
        )}

        {people.length > 0 && (
          <div className="form-row">
            <label>Assignees {assignees.length > 0 && <span className="count-pill">{assignees.length}</span>}</label>
            <div className="label-picker">
              {people.map((login) => (
                <button
                  type="button"
                  key={login}
                  onClick={() => setAssignees((prev) => toggle(prev, login))}
                  className={`label-pick${assignees.includes(login) ? " on" : ""}`}
                  aria-pressed={assignees.includes(login)}
                >
                  {login}
                  {login === me ? " (me)" : ""}
                </button>
              ))}
            </div>
          </div>
        )}

        <div style={{ display: "flex", gap: 12 }}>
          {openMilestones.length > 0 && (
            <div className="form-row" style={{ flex: 1 }}>
              <label htmlFor="new-issue-milestone">Milestone</label>
              <select id="new-issue-milestone" value={milestone} onChange={(e) => setMilestone(e.target.value)}>
                <option value="">None</option>
                {openMilestones.map((m) => (
                  <option key={m.number} value={String(m.number)}>
                    {m.title}
                  </option>
                ))}
              </select>
            </div>
          )}
          {metadata.issue_types.length > 0 && (
            <div className="form-row" style={{ flex: 1 }}>
              <label htmlFor="new-issue-type">Type</label>
              <select id="new-issue-type" value={issueType} onChange={(e) => setIssueType(e.target.value)}>
                <option value="">None</option>
                {metadata.issue_types.map((t) => (
                  <option key={t.name} value={t.name}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {error && <p style={{ color: "var(--danger)", fontSize: 13 }}>{error}</p>}

        <div className="modal-foot">
          <button type="button" className="btn ghost" onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" className="btn primary" disabled={!title.trim() || saving}>
            {saving ? "Creating…" : "Create issue"}
          </button>
        </div>
      </form>
    </div>
  );
}
