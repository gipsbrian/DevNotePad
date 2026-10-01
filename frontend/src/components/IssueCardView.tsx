import { useEffect, useRef, useState } from "react";
import { useDraggable } from "@dnd-kit/core";
import { motion } from "framer-motion";
import { rememberCardOrigin } from "../utils/cardOrigin";
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
  onTrack,
  onUntrack,
  trackingColumns = [],
  inTrackingColumn = false,
  canManage = false,
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
  onTrack?: (issueNumber: number, columnId: number, fromColumnId?: number) => void;
  onUntrack?: (issueNumber: number, columnId: number) => void;
  /** Tracking columns it could be added to, besides its own. */
  trackingColumns?: Column[];
  /** Sitting in a tracking column, so it can be taken out of it. */
  inTrackingColumn?: boolean;
  canManage?: boolean;
  /** Draggable into tracking columns. */
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
  // "Move to" changes the issue on GitHub, which only filter columns mean.
  const movableTo = canWrite ? otherColumns.filter((c) => c.kind !== "tracking") : [];
  const canUntrack = inTrackingColumn && canManage && typeof columnId === "number";
  const hasMenu = movableTo.length > 0 || canClose || trackingColumns.length > 0 || canUntrack;
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

  // Per column: the same issue can sit in several at once, and dnd-kit
  // needs every draggable's id to be unique. What moves on screen is a copy
  // in the board's drag layer, which can leave the column's scroll box;
  // this card stays put, faded, until the drop.
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `issue-${columnId}-${issue.number}`,
    data: { type: "issue", issueNumber: issue.number, sourceColumnId: columnId, issue },
    disabled: !draggable,
  });

  return (
    <motion.article
      layout
      // Cards arriving (moved in, newly matching) scale up into place;
      // leaving ones (closed, moved out) fade while the gap closes, so the
      // cards below slide up instead of jumping. Already-present cards
      // don't animate on load: the column's AnimatePresence skips them.
      initial={{ opacity: 0, scale: 0.96 }}
      // Faded while its copy is being dragged; through motion, since an
      // inline opacity from here would beat any stylesheet rule.
      animate={{ opacity: isDragging ? 0.35 : 1, scale: 1 }}
      exit={{
        opacity: 0,
        scale: 0.96,
        height: 0,
        paddingTop: 0,
        paddingBottom: 0,
        marginBottom: -9, // the column's gap
        transition: { duration: 0.26, ease: [0.2, 0.8, 0.2, 1], opacity: { duration: 0.14 } },
      }}
      transition={{ type: "spring", stiffness: 420, damping: 34 }}
      // Scoped to the column: the same issue legitimately appears in
      // several columns at once (e.g. "All open" and "Assigned to me"),
      // and framer-motion collapses duplicate layoutIds into one element,
      // which made every copy after the first render blank.
      layoutId={`card-${columnId}-${issue.number}`}
      ref={(node) => {
        setNodeRef(node);
        cardRef.current = node;
      }}
      // Only apply dnd-kit's ARIA/listener bundle when the card really is
      // draggable. Otherwise a non-draggable card (the Closed section)
      // gets aria-disabled="true" and is announced as disabled, even
      // though clicking it to open the issue works fine.
      {...(draggable ? attributes : {})}
      {...(draggable ? listeners : {})}
      className="card"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => {
        if (isDragging) return;
        rememberCardOrigin(issue.number, cardRef.current);
        onOpen(issue.number);
      }}
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

      {hasMenu && (
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

              {(trackingColumns.length > 0 || canUntrack) && (
                <>
                  {movableTo.length > 0 && <div className="menu-divider" />}
                  {trackingColumns.length > 0 && (
                    <div className="move-menu-label">{inTrackingColumn ? "Move into" : "Track in"}</div>
                  )}
                  {trackingColumns.map((c) => (
                    <button
                      key={c.id}
                      role="menuitem"
                      onClick={() => {
                        onTrack?.(issue.number, c.id, inTrackingColumn ? (columnId as number) : undefined);
                        setMenuOpen(false);
                      }}
                    >
                      {c.name}
                    </button>
                  ))}
                  {canUntrack && (
                    <button
                      role="menuitem"
                      onClick={() => {
                        onUntrack?.(issue.number, columnId as number);
                        setMenuOpen(false);
                      }}
                    >
                      Stop tracking here
                    </button>
                  )}
                </>
              )}

              {canClose && (
                <>
                  {(movableTo.length > 0 || trackingColumns.length > 0 || canUntrack) && <div className="menu-divider" />}
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
