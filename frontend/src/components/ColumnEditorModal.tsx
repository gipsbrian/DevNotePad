import { useState } from "react";
import type { Column, RepoMetadata, Settings } from "../types/api";

export interface ColumnFilterPayload {
  name: string;
  state: string | null;
  labels: string[];
  milestone: string | null;
  assignee: string | null;
  creator: string | null;
  issue_type: string | null;
}

export function ColumnEditorModal({
  metadata,
  settings,
  column,
  onCancel,
  onSubmit,
}: {
  metadata: RepoMetadata;
  settings: Settings | null;
  /** Existing column to edit; omit to create a new one. */
  column?: Column;
  onCancel: () => void;
  onSubmit: (payload: ColumnFilterPayload) => void;
}) {
  const editing = !!column;
  const [name, setName] = useState(column?.name ?? "");
  const [state, setState] = useState<string>(column?.state ?? "open");
  const [labels, setLabels] = useState<string[]>(column?.labels ?? []);
  const [milestone, setMilestone] = useState<string>(column?.milestone ?? "");
  const [assignee, setAssignee] = useState<string>(column?.assignee ?? "");
  const [creator, setCreator] = useState<string>(column?.creator ?? "");
  const [issueType, setIssueType] = useState<string>(column?.issue_type ?? "");

  const me = settings?.github_username ?? null;

  function toggleLabel(labelName: string) {
    setLabels((prev) => (prev.includes(labelName) ? prev.filter((l) => l !== labelName) : [...prev, labelName]));
  }

  // Assignee/creator dropdowns list the repo's assignable users, but the
  // saved username may not be among them (e.g. you can file issues on a
  // repo you're not assignable on), so make sure it's always offered.
  const people = [...new Set([...(me ? [me] : []), ...metadata.assignees.map((a) => a.login)])];

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal narrow" onClick={(e) => e.stopPropagation()}>
        <h2 className="modal-title">{editing ? "Edit column" : "New column"}</h2>
        <p className="empty-hint">
          Built from labels, milestones and people that already exist on this repo — this app never creates new ones.
        </p>

        <div className="form-row" style={{ marginTop: 18 }}>
          <label>Column name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Priority bugs" autoFocus />
        </div>

        <div className="form-row">
          <label>State</label>
          <select value={state} onChange={(e) => setState(e.target.value)}>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
            <option value="all">Any</option>
          </select>
        </div>

        <div className="form-row">
          <label>Labels {labels.length > 0 && <span className="count-pill">{labels.length}</span>}</label>
          <div className="label-picker">
            {metadata.labels.map((l) => (
              <button
                type="button"
                key={l.name}
                onClick={() => toggleLabel(l.name)}
                className={`label-pick${labels.includes(l.name) ? " on" : ""}`}
              >
                <i style={{ background: `#${l.color}` }} />
                {l.name}
              </button>
            ))}
            {metadata.labels.length === 0 && <span className="empty-hint">No labels on this repo yet.</span>}
          </div>
        </div>

        <div style={{ display: "flex", gap: 12 }}>
          <div className="form-row" style={{ flex: 1 }}>
            <label>Assignee</label>
            <select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
              <option value="">Anyone</option>
              {people.map((login) => (
                <option key={login} value={login}>
                  {login}
                  {login === me ? " (me)" : ""}
                </option>
              ))}
            </select>
          </div>
          <div className="form-row" style={{ flex: 1 }}>
            <label>Created by</label>
            <select value={creator} onChange={(e) => setCreator(e.target.value)}>
              <option value="">Anyone</option>
              {people.map((login) => (
                <option key={login} value={login}>
                  {login}
                  {login === me ? " (me)" : ""}
                </option>
              ))}
            </select>
          </div>
        </div>

        {metadata.issue_types.length > 0 && (
          <div className="form-row">
            <label>Issue type</label>
            <select value={issueType} onChange={(e) => setIssueType(e.target.value)}>
              <option value="">Any</option>
              {metadata.issue_types.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.name}
                </option>
              ))}
            </select>
            <p className="empty-hint" style={{ marginTop: 6 }}>
              {metadata.issue_types_source === "repo"
                ? "Types seen on this repo's issues."
                : metadata.issue_types_source === "repo+org"
                  ? "Types used on this repo, plus others defined for the org."
                  : "Types defined for the organization."}
            </p>
          </div>
        )}

        <div className="form-row">
          <label>Milestone</label>
          <select value={milestone} onChange={(e) => setMilestone(e.target.value)}>
            <option value="">Any</option>
            {metadata.milestones.map((m) => (
              <option key={m.number} value={String(m.number)}>
                {m.title} ({m.state})
              </option>
            ))}
          </select>
        </div>

        <div className="modal-foot">
          <button className="btn ghost" onClick={onCancel}>
            Cancel
          </button>
          <button
            className="btn primary"
            disabled={!name}
            onClick={() =>
              onSubmit({
                name,
                state: state === "all" ? null : state,
                labels,
                milestone: milestone || "",
                assignee: assignee || "",
                creator: creator || "",
                issue_type: issueType || "",
              })
            }
          >
            {editing ? "Save column" : "Create column"}
          </button>
        </div>
      </div>
    </div>
  );
}
