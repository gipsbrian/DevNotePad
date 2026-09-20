import { useEffect, useRef, useState } from "react";
import { useDraggable } from "@dnd-kit/core";
import { motion } from "framer-motion";
import type { Column, Comment, IssueCard, Note, SubIssue } from "../types/api";
import { api } from "../api/client";
import { NotePopover } from "./NotePopover";
import { SubIssuesPopover } from "./SubIssuesPopover";
import { IconChat, IconClock, IconDots, IconNote, IconSubIssues } from "./Icons";
import { CommentsPopover } from "./CommentsPopover";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function IssueCardView({
  issue,
  dashboardId,
  columnId,
  otherColumns,
  notesByIssue,
  onOpen,
  onMove,
  onCloseIssue,
  draggable = true,
  canWrite = true,
  writeBlockReason = null,
}: {
  issue: IssueCard;
  dashboardId: string;
  columnId: number | "closed";
  otherColumns: Column[];
  notesByIssue: Map<number, Note[]>;
  onOpen: (issueNumber: number) => void;
  onMove: (issueNumber: number, targetColumnId: number) => void;
  onCloseIssue: (issueNumber: number) => void;
  draggable?: boolean;
  /** Moving and closing change GitHub; hidden where you can't. */
  canWrite?: boolean;
  writeBlockReason?: string | null;
}) {
  const [hovered, setHovered] = useState(false);
  const [noteTapped, setNoteTapped] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const notes = notesByIssue.get(issue.number) ?? [];
  const latestNote = notes[notes.length - 1];
  const cardRef = useRef<HTMLElement | null>(null);
  const canClose = canWrite && issue.state === "open";
  const movableTo = canWrite ? otherColumns : [];
  const subRef = useRef<HTMLButtonElement | null>(null);
  // The comments panel hangs off the card, not the badge, so it sits beside
  // the whole issue.
  const [commentsOpen, setCommentsOpen] = useState(false);
  const [comments, setComments] = useState<Comment[] | null>(null);
  const [commentsLoading, setCommentsLoading] = useState(false);
  const [commentsError, setCommentsError] = useState<string | null>(null);
  // Leaving the badge shouldn't snatch the panel away while the pointer is
  // travelling to it.
  const closeTimer = useRef<number | undefined>(undefined);
  // True while the panel holds a draft, so a stray pointer move can't close it.
  const [commentsHeld, setCommentsHeld] = useState(false);
  // Comments added from the panel, on top of the count the board loaded with.
  const [postedHere, setPostedHere] = useState(0);
  const [subOpen, setSubOpen] = useState(false);
  const [subIssues, setSubIssues] = useState<SubIssue[] | null>(null);
  const [subLoading, setSubLoading] = useState(false);

  function openComments() {
    window.clearTimeout(closeTimer.current);
    setCommentsOpen(true);
    if (comments || commentsLoading) return;
    setCommentsLoading(true);
    setCommentsError(null);
    api
      .listIssueComments(dashboardId, issue.number)
      .then(setComments)
      .catch((e) => setCommentsError((e as Error).message))
      .finally(() => setCommentsLoading(false));
  }

  function closeCommentsSoon() {
    window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => {
      if (!commentsHeld) setCommentsOpen(false);
    }, 160);
  }

  useEffect(() => () => window.clearTimeout(closeTimer.current), []);

  // A held panel ignores the pointer leaving, so give it another way out.
  useEffect(() => {
    if (!commentsOpen || !commentsHeld) return;
    function onDocument(e: MouseEvent) {
      const target = e.target as HTMLElement;
      if (!target.closest(".comments-panel") && !cardRef.current?.contains(target)) {
        setCommentsHeld(false);
        setCommentsOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocument);
    return () => document.removeEventListener("mousedown", onDocument);
  }, [commentsOpen, commentsHeld]);

  // Fetched only when the badge is actually hovered, and kept afterwards —
  // the card already knows the counts, so the list is the only thing worth
  // a request.
  async function loadSubIssues() {
    setSubOpen(true);
    if (subIssues || subLoading) return;
    setSubLoading(true);
    try {
      setSubIssues(await api.listSubIssues(dashboardId, issue.number));
    } catch {
      setSubIssues([]);
    } finally {
      setSubLoading(false);
    }
  }

  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `issue-${issue.number}`,
    data: { type: "issue", issueNumber: issue.number, sourceColumnId: columnId },
    disabled: !draggable || !canWrite,
  });

  const style = transform
    ? {
        transform: `translate(${transform.x}px, ${transform.y}px) rotate(2deg)`,
        zIndex: isDragging ? 30 : undefined,
        boxShadow: isDragging ? "var(--shadow-lg)" : undefined,
      }
    : undefined;

  return (
    <motion.article
      layout
      initial={false}
      // Scoped to the column: the same issue legitimately appears in
      // several columns at once (e.g. "All open" and "Assigned to me"),
      // and framer-motion collapses duplicate layoutIds into one element,
      // which made every copy after the first render blank.
      layoutId={`card-${columnId}-${issue.number}`}
      ref={(node) => {
        setNodeRef(node);
        cardRef.current = node;
      }}
      style={style}
      // Only apply dnd-kit's ARIA/listener bundle when the card really is
      // draggable. Otherwise a non-draggable card (the Closed section)
      // gets aria-disabled="true" and is announced as disabled, even
      // though clicking it to open the issue works fine.
      {...(draggable && canWrite ? attributes : {})}
      {...(draggable && canWrite ? listeners : {})}
      className="card"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => !isDragging && onOpen(issue.number)}
    >
      {(hovered || noteTapped) && latestNote && !subOpen && (
        <NotePopover anchor={cardRef.current} text={latestNote.body} moreCount={notes.length - 1} />
      )}

      {subOpen && (
        <SubIssuesPopover anchor={subRef.current} subIssues={subIssues} loading={subLoading} />
      )}

      {commentsOpen && (
        <CommentsPopover
          anchor={cardRef.current}
          comments={comments}
          loading={commentsLoading}
          error={commentsError}
          expected={issue.comments_count + postedHere}
          canWrite={canWrite}
          writeBlockReason={writeBlockReason}
          dashboardId={dashboardId}
          issueNumber={issue.number}
          onMouseEnter={openComments}
          onMouseLeave={closeCommentsSoon}
          onPosted={(comment) => {
            setComments((list) => [...(list ?? []), comment]);
            setPostedHere((n) => n + 1);
          }}
          onHold={setCommentsHeld}
          onClose={() => {
            setCommentsHeld(false);
            setCommentsOpen(false);
          }}
        />
      )}

      {issue.labels.length > 0 && (
        <div className="card-stripes">
          {issue.labels.slice(0, 4).map((l) => (
            <span key={l.name} className="card-stripe" style={{ background: `#${l.color}` }} title={l.name} />
          ))}
        </div>
      )}

      {(movableTo.length > 0 || canClose) && (
        <>
          <button
            className="card-menu-btn"
            onClick={(e) => {
              e.stopPropagation();
              setConfirmClose(false);
              setMenuOpen((v) => !v);
            }}
            title="Card actions"
            aria-label={`Actions for issue ${issue.number}`}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
          >
            <IconDots />
          </button>
          {menuOpen && (
            <div className="move-menu" role="menu" onClick={(e) => e.stopPropagation()}>
              {movableTo.length > 0 && (
                <>
                  <div className="move-menu-label">Move to</div>
                  {movableTo.map((c) => (
                    <button
                      key={c.id}
                      role="menuitem"
                      disabled={!c.drag_compatible}
                      onClick={() => {
                        onMove(issue.number, c.id);
                        setMenuOpen(false);
                      }}
                      title={c.drag_compatible ? undefined : "This column's filter can't be reached by a single action"}
                    >
                      {c.name}
                    </button>
                  ))}
                </>
              )}

              {canClose && (
                <>
                  {movableTo.length > 0 && <div className="menu-divider" />}
                  {/* Two-step rather than a native dialog: this closes a real
                      issue on GitHub, and the menu is easy to mis-click. */}
                  {confirmClose ? (
                    <button
                      role="menuitem"
                      className="menu-danger"
                      onClick={() => {
                        onCloseIssue(issue.number);
                        setMenuOpen(false);
                        setConfirmClose(false);
                      }}
                    >
                      Really close #{issue.number}?
                    </button>
                  ) : (
                    <button role="menuitem" className="menu-danger" onClick={() => setConfirmClose(true)}>
                      Close issue
                    </button>
                  )}
                </>
              )}
            </div>
          )}
        </>
      )}

      <div className="card-number">#{issue.number}</div>
      <h4 className="card-title">{issue.title}</h4>
      {issue.summary && <p className="card-summary">{issue.summary}</p>}

      {issue.labels.length > 0 && (
        <div className="card-labels">
          {issue.labels.slice(0, 3).map((l) => (
            <span key={l.name} className="label-chip" title={l.description ?? l.name}>
              <i style={{ background: `#${l.color}` }} />
              {l.name}
            </span>
          ))}
          {issue.labels.length > 3 && <span className="label-chip">+{issue.labels.length - 3}</span>}
        </div>
      )}

      <div className="card-foot">
        <div className="card-meta">
          <span
            className={`age-bubble${issue.age_days >= 30 ? " long-open" : ""}`}
            title={
              issue.closed_at
                ? `Open ${issue.age_days}d before closing`
                : `Open for ${issue.age_days} day${issue.age_days === 1 ? "" : "s"}`
            }
          >
            <IconClock />
            {issue.age_days}d
          </span>
          <span className="meta-item" title={`Opened ${new Date(issue.created_at).toLocaleString()}`}>
            {formatDate(issue.created_at)}
          </span>
        </div>

        <div className="card-badges">
          {issue.has_local_note && (
            <button
              type="button"
              className="badge-icon note"
              title="Has a local sticky note — tap to preview"
              onClick={(e) => {
                e.stopPropagation();
                setNoteTapped((v) => !v);
              }}
            >
              <IconNote />
            </button>
          )}
          {issue.sub_issues_total > 0 && (
            <button
              type="button"
              ref={subRef}
              className="badge-icon sub"
              title={`${issue.sub_issues_completed} of ${issue.sub_issues_total} sub-issues done`}
              onMouseEnter={loadSubIssues}
              onMouseLeave={() => setSubOpen(false)}
              onClick={(e) => {
                e.stopPropagation();
                subOpen ? setSubOpen(false) : loadSubIssues();
              }}
            >
              <IconSubIssues />
              {issue.sub_issues_completed}/{issue.sub_issues_total}
            </button>
          )}
          {issue.comments_count > 0 && (
            <button
              type="button"
              className="badge-icon chat"
              aria-label={`${issue.comments_count + postedHere} GitHub comment${issue.comments_count + postedHere === 1 ? "" : "s"}`}
              onMouseEnter={openComments}
              onMouseLeave={closeCommentsSoon}
              onClick={(e) => {
                e.stopPropagation();
                commentsOpen ? setCommentsOpen(false) : openComments();
              }}
            >
              <IconChat />
              {issue.comments_count + postedHere}
            </button>
          )}
          {issue.assignees.length > 0 && (
            <span className="avatar-stack">
              {issue.assignees.slice(0, 3).map((a) => (
                <img key={a.login} className="avatar" src={a.avatar_url} alt={a.login} title={a.login} />
              ))}
            </span>
          )}
        </div>
      </div>
    </motion.article>
  );
}
