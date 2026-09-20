import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api/client";
import type { Comment } from "../types/api";
import { Markdown } from "./Markdown";
import { useSidePosition } from "../utils/useSidePosition";
import { IconChat } from "./Icons";

const WIDTH = 330;
const MAX_HEIGHT = 420;

function when(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** An issue's GitHub comments, beside its card. Shown on hover, and only
 * for issues that have comments -- the badge it hangs off only exists then. */
export function CommentsPopover({
  anchor,
  dashboardId,
  issueNumber,
  comments,
  loading,
  error,
  expected,
  canWrite,
  writeBlockReason,
  onMouseEnter,
  onMouseLeave,
  onPosted,
  onHold,
  onClose,
}: {
  anchor: HTMLElement | null;
  dashboardId: string;
  issueNumber: number;
  comments: Comment[] | null;
  loading: boolean;
  error: string | null;
  /** The count from the card, so the header reads right before they load. */
  expected: number;
  canWrite: boolean;
  writeBlockReason?: string | null;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onPosted: (comment: Comment) => void;
  /** Keeps the panel open while there's a draft in it, so moving the pointer
   * away mid-sentence doesn't throw the words out. */
  onHold: (held: boolean) => void;
  onClose: () => void;
}) {
  const pos = useSidePosition(anchor, WIDTH, MAX_HEIGHT);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [postError, setPostError] = useState<string | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    onHold(draft.trim().length > 0 || busy);
  }, [draft, busy, onHold]);

  async function post() {
    const body = draft.trim();
    if (!body || busy) return;
    setBusy(true);
    setPostError(null);
    try {
      onPosted(await api.commentOnIssue(dashboardId, issueNumber, body));
      setDraft("");
      // Bring the new comment into view; it's added at the end.
      requestAnimationFrame(() => bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight }));
    } catch (e) {
      // The draft stays put: a refused comment mustn't cost the words.
      setPostError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!anchor || !pos) return null;

  return createPortal(
    <div
      className={`comments-panel${pos.flipped ? " flipped" : ""}`}
      style={{ top: pos.top, left: pos.left, width: WIDTH, maxHeight: MAX_HEIGHT }}
      role="dialog"
      aria-label={`Comments on issue ${issueNumber}`}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      // Portalled panels still bubble through React's tree, so without this a
      // click in here would open the issue behind it.
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          setDraft("");
          onClose();
        }
      }}
    >
      <div className="comments-panel-head">
        <IconChat />
        {comments?.length ?? expected} comment{(comments?.length ?? expected) === 1 ? "" : "s"}
      </div>
      <div className="comments-panel-body" ref={bodyRef}>
        {loading && <p className="comments-panel-empty">Loading comments…</p>}
        {error && <p className="comments-panel-empty">{error}</p>}
        {comments?.map((c) => (
          <div key={c.id} className="comments-panel-item">
            <div className="comments-panel-meta">
              <span className="author">{c.author}</span>
              <time dateTime={c.created_at} title={new Date(c.created_at).toLocaleString()}>
                {when(c.created_at)}
              </time>
            </div>
            <Markdown text={c.body} />
          </div>
        ))}
      </div>

      {canWrite ? (
        <div className="comments-panel-compose">
          <textarea
            rows={2}
            value={draft}
            placeholder="Write a comment…"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) post();
            }}
          />
          {postError && (
            <p className="comments-panel-error" role="alert">
              {postError}
            </p>
          )}
          <div className="comments-panel-actions">
            <span className="comments-panel-hint">Posts on GitHub</span>
            <button className="btn small primary" onClick={post} disabled={busy || !draft.trim()}>
              {busy ? "Posting…" : "Comment"}
            </button>
          </div>
        </div>
      ) : (
        writeBlockReason && <p className="comments-panel-empty compose-blocked">{writeBlockReason}</p>
      )}
    </div>,
    document.body
  );
}
