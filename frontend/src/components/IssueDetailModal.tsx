import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { IssueDetail } from "../types/api";
import { Markdown } from "./Markdown";
import { copyText, formatIssueForCopy } from "../utils/clipboard";
import {
  IconCalendar,
  IconChat,
  IconCopy,
  IconExternal,
  IconLink,
  IconMilestone,
  IconNote,
  IconSubIssues,
  IconUser,
} from "./Icons";

export function IssueDetailModal({
  dashboardId,
  issueNumber,
  onClose,
  onChanged,
  canWrite = true,
  writeBlockReason = null,
}: {
  dashboardId: string;
  issueNumber: number;
  onClose: () => void;
  onChanged: (closedIssueNumber?: number) => void;
  /** Closing, commenting and pushing notes change GitHub; hidden where you can't. */
  canWrite?: boolean;
  writeBlockReason?: string | null;
}) {
  const [detail, setDetail] = useState<IssueDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [editingNoteId, setEditingNoteId] = useState<number | null>(null);
  const [editingBody, setEditingBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [noteError, setNoteError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(null), 2200);
    return () => clearTimeout(timer);
  }, [copied]);

  async function handleCopy(what: "link" | "content") {
    if (!detail) return;
    const text = what === "link" ? detail.html_url : formatIssueForCopy(detail);
    const ok = await copyText(text);
    setCopied(ok ? (what === "link" ? "Link copied" : "Issue copied") : "Couldn’t copy");
  }

  function load() {
    api.getIssueDetail(dashboardId, issueNumber).then(setDetail).catch((e) => setError(e.message));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboardId, issueNumber]);


  async function handleSaveNote() {
    if (!draft.trim()) return;
    setBusy(true);
    try {
      await api.createNote(dashboardId, { issue_number: issueNumber, body: draft });
      setDraft("");
      load();
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  /** Posts the draft as a GitHub comment, skipping the local note. The new
   * comment is added from GitHub's response rather than by reloading:
   * GitHub's comment list can lag a moment behind the write, and a reload
   * straight away could come back without it. */
  async function handleComment() {
    const body = draft.trim();
    if (!body || !detail) return;
    setBusy(true);
    setNoteError(null);
    try {
      const comment = await api.commentOnIssue(dashboardId, issueNumber, body);
      setDetail({ ...detail, comments: [...detail.comments, comment] });
      setDraft("");
      onChanged();
    } catch (e) {
      // Keep the draft: a refused comment (a read-only token, say) mustn't
      // cost the words.
      setNoteError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handlePush(noteId: number) {
    setBusy(true);
    try {
      await api.pushNote(noteId);
      load();
    } finally {
      setBusy(false);
    }
  }

  async function handleUpdateNote(noteId: number) {
    setBusy(true);
    try {
      await api.updateNote(noteId, editingBody);
      setEditingNoteId(null);
      load();
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteNote(noteId: number) {
    setBusy(true);
    try {
      await api.deleteNote(noteId);
      load();
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function handleCloseIssue() {
    setBusy(true);
    try {
      await api.closeIssue(dashboardId, issueNumber);
      onChanged(issueNumber);
      onClose();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal issue-pane" onClick={(e) => e.stopPropagation()}>
        {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
        {!detail && !error && <p className="state-msg">Loading…</p>}
        {detail && (
          <>
            <div className="modal-topline">
              <span className="card-number">#{detail.number}</span>
              <button
                className="btn small ghost copy-link-btn"
                onClick={() => handleCopy("link")}
                title="Copy this issue's link"
              >
                <IconLink /> Copy link
              </button>
            </div>
            <h2 className="modal-title">{detail.title}</h2>

            {detail.labels.length > 0 && (
              <div className="card-labels" style={{ marginTop: 10 }}>
                {detail.labels.map((l) => (
                  <span key={l.name} className="label-chip">
                    <i style={{ background: `#${l.color}` }} />
                    {l.name}
                  </span>
                ))}
              </div>
            )}

            <div className="modal-meta">
              <span className="meta-item">
                <IconCalendar />
                Opened {new Date(detail.created_at).toLocaleDateString()}
              </span>
              {detail.assignees.length > 0 && (
                <span className="meta-item">
                  <IconUser />
                  {detail.assignees.map((a) => a.login).join(", ")}
                </span>
              )}
              {detail.milestone && (
                <span className="meta-item">
                  <IconMilestone />
                  {detail.milestone}
                </span>
              )}
              <a className="meta-item" href={detail.html_url} target="_blank" rel="noreferrer">
                <IconExternal />
                Open on GitHub
              </a>
            </div>

            <div className="modal-section">
              <h4>Description</h4>
              {detail.body ? <Markdown text={detail.body} /> : <p className="empty-hint">No description.</p>}
            </div>

            {detail.sub_issues.length > 0 && (
              <div className="modal-section">
                <h4>
                  <IconSubIssues style={{ width: 12, height: 12, verticalAlign: "-2px", marginRight: 5 }} />
                  Sub-issues ({detail.sub_issues.filter((s) => s.state === "closed").length}/
                  {detail.sub_issues.length})
                </h4>
                <ul className="sub-list modal-sub-list">
                  {detail.sub_issues.map((s) => (
                    <li key={s.number} className={s.state === "closed" ? "done" : ""}>
                      <span className={`sub-dot ${s.state}`} />
                      <span className="sub-num">#{s.number}</span>
                      <a className="sub-title" href={s.html_url} target="_blank" rel="noreferrer">
                        {s.title}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="modal-section">
              <h4>
                <IconNote style={{ width: 12, height: 12, verticalAlign: "-2px", marginRight: 5 }} />
                Local notes
              </h4>
              {detail.notes.length === 0 && <p className="empty-hint">Private to you until you push one.</p>}
              {detail.notes.map((n) => (
                <div key={n.id} className="note-item">
                  {editingNoteId === n.id ? (
                    <>
                      <textarea value={editingBody} onChange={(e) => setEditingBody(e.target.value)} rows={3} />
                      <div className="note-actions">
                        <button className="btn small primary" onClick={() => handleUpdateNote(n.id)} disabled={busy}>
                          Save
                        </button>
                        <button className="btn small ghost" onClick={() => setEditingNoteId(null)}>
                          Cancel
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <Markdown text={n.body} />
                      <div className="note-actions">
                        <button
                          className="btn small"
                          onClick={() => {
                            setEditingNoteId(n.id);
                            setEditingBody(n.body);
                          }}
                        >
                          Edit
                        </button>
                        <button className="btn small ghost" onClick={() => handleDeleteNote(n.id)} disabled={busy}>
                          Delete
                        </button>
                        {canWrite && (
                          <button className="btn small primary" onClick={() => handlePush(n.id)} disabled={busy}>
                            {n.synced ? "Update pushed comment" : "Push to GitHub"}
                          </button>
                        )}
                        {n.synced && <span className="synced-tag">synced ✓</span>}
                      </div>
                    </>
                  )}
                </div>
              ))}
              <textarea
                placeholder="Write something… keep it as a private note, or post it on the issue"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={2}
              />
              {noteError && (
                <p className="form-error" role="alert" style={{ margin: "8px 0 0" }}>
                  {noteError}
                </p>
              )}
              <div className="note-actions">
                <button className="btn small" onClick={handleSaveNote} disabled={busy || !draft.trim()}>
                  <IconNote /> Save locally
                </button>
                {canWrite && (
                  <button
                    className="btn small primary"
                    onClick={handleComment}
                    disabled={busy || !draft.trim()}
                    title="Posts publicly on the GitHub issue, where everyone watching it sees it"
                  >
                    <IconChat /> Comment on GitHub
                  </button>
                )}
              </div>
              {!canWrite && writeBlockReason && (
                <p className="empty-hint" style={{ marginTop: 8 }}>
                  Notes you save here are private to you. {writeBlockReason}
                </p>
              )}
            </div>

            <div className="modal-section">
              <h4>
                <IconChat style={{ width: 12, height: 12, verticalAlign: "-2px", marginRight: 5 }} />
                GitHub comments ({detail.comments.length})
              </h4>
              {detail.comments.length === 0 && <p className="empty-hint">No comments on GitHub yet.</p>}
              {detail.comments.map((c) => (
                <div key={c.id} className="comment">
                  <div className="comment-head">
                    <span className="author">{c.author}</span>
                    <time>{new Date(c.created_at).toLocaleString()}</time>
                  </div>
                  <Markdown text={c.body} />
                </div>
              ))}
            </div>

            <div className="modal-foot">
              <button
                className="btn small"
                onClick={() => handleCopy("content")}
                title="Copy the number, title, link and description"
              >
                <IconCopy /> Copy issue
              </button>
              {copied && <span className="copied-toast inline">{copied}</span>}
              <span className="modal-foot-spacer" />
              {detail.state === "open" ? (
                canWrite && (
                  <button className="btn danger" onClick={handleCloseIssue} disabled={busy}>
                    Close issue
                  </button>
                )
              ) : (
                <span className="empty-hint" style={{ margin: 0 }}>
                  This issue is closed.
                </span>
              )}
              <button className="btn" onClick={onClose}>
                Done
              </button>
            </div>
          </>
        )}
    </div>
  );
}
