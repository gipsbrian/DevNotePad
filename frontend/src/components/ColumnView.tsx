import { useEffect, useRef, useState } from "react";
import { useDndContext, useDroppable } from "@dnd-kit/core";
import { AnimatePresence } from "framer-motion";
import type { Column, IssueCard, Note } from "../types/api";
import { IssueCardView } from "./IssueCardView";
import { copyText, formatIssuesForCopy } from "../utils/clipboard";
import { IconChevronLeft, IconChevronRight, IconDots, IconRefresh } from "./Icons";

/** More cards than this arriving or leaving at once aren't animated. */
const MAX_ANIMATED = 12;

/** Cards drawn at a time; scrolling near the end draws the next batch. A
 * column matching a thousand issues would otherwise draw a thousand cards
 * on every re-render, freezing the page. */
const BATCH = 60;

function filterChips(column: Column): string[] {
  const chips: string[] = [];
  if (column.state && column.state !== "open") chips.push(column.state);
  column.labels.forEach((l) => chips.push(l));
  if (column.milestone) chips.push(`milestone #${column.milestone}`);
  if (column.assignee) chips.push(`assignee: ${column.assignee}`);
  if (column.creator) chips.push(`by: ${column.creator}`);
  if (column.issue_type) chips.push(`type: ${column.issue_type}`);
  return chips;
}

export function ColumnView({
  column,
  dashboardId,
  issues,
  allColumns,
  notesByIssue,
  loading,
  refreshing,
  accentColor,
  onOpenIssue,
  onMoveIssue,
  onCloseIssue,
  onTrackIssue,
  onUntrackIssue,
  onEditColumn,
  onDeleteColumn,
  onMoveColumn,
  onRefreshColumn,
  canMoveLeft,
  canMoveRight,
  canManage = true,
  canDrag = false,
  canWrite = true,
  writeBlockReason = null,
}: {
  column: Column;
  dashboardId: string;
  issues: IssueCard[] | undefined;
  allColumns: Column[];
  notesByIssue: Map<number, Note[]>;
  loading: boolean;
  refreshing: boolean;
  accentColor?: string;
  onOpenIssue: (issueNumber: number) => void;
  onMoveIssue: (issueNumber: number, targetColumnId: number) => void;
  onCloseIssue: (issueNumber: number) => void;
  /** Into a tracking column; `fromColumnId` set when leaving one. */
  onTrackIssue: (issueNumber: number, columnId: number, fromColumnId?: number) => void;
  onUntrackIssue: (issueNumber: number, columnId: number) => void;
  onEditColumn: (column: Column) => void;
  onDeleteColumn: (columnId: number) => void;
  onMoveColumn: (columnId: number, direction: -1 | 1) => void;
  onRefreshColumn: (columnId: number) => void;
  canMoveLeft: boolean;
  canMoveRight: boolean;
  /** Editing, moving and removing the column. */
  canManage?: boolean;
  /** Whether its cards can be dragged into tracking columns. */
  canDrag?: boolean;
  /** Moving and closing its cards on GitHub. */
  canWrite?: boolean;
  writeBlockReason?: string | null;
}) {
  const tracking = column.kind === "tracking";
  // Only tracking columns take drops: a filter column shows whatever
  // matches its filter, so dropping into one would mean nothing.
  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: `column-${column.id}`,
    data: { type: "cards", columnId: column.id, tracking },
    disabled: !tracking || !canManage,
  });
  const { active } = useDndContext();
  const dragFrom = active?.data.current?.sourceColumnId as number | undefined;
  const dropState = !active
    ? ""
    : tracking && canManage && dragFrom !== column.id
      ? isOver
        ? " drop-target is-over"
        : " drop-target"
      : dragFrom === column.id
        ? ""
        : " no-drop";

  const [menuOpen, setMenuOpen] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const menuRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function onDocument(e: MouseEvent) {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("mousedown", onDocument);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocument);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(null), 2200);
    return () => clearTimeout(timer);
  }, [copied]);

  async function handleCopy() {
    setMenuOpen(false);
    const list = issues ?? [];
    if (list.length === 0) {
      setCopied("Nothing to copy");
      return;
    }
    const ok = await copyText(formatIssuesForCopy(list));
    setCopied(ok ? `Copied ${list.length} issue${list.length === 1 ? "" : "s"}` : "Couldn’t copy");
  }

  const chips = tracking ? ["tracking"] : filterChips(column);

  // Cards animate in and out one or a few at a time. A wholesale change
  // (first load, a new filter, a big refresh) swaps the list instantly:
  // animating hundreds of cards at once only stalls the page. A new key
  // remounts the presence group, and `initial={false}` then skips entrances.
  const [limit, setLimit] = useState(BATCH);
  const drawn = issues?.slice(0, limit);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const moreRef = useRef<HTMLButtonElement | null>(null);
  const hasMore = (issues?.length ?? 0) > limit;

  useEffect(() => {
    const more = moreRef.current;
    if (!hasMore || !more || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => entries[0].isIntersecting && setLimit((l) => l + BATCH),
      { root: bodyRef.current, rootMargin: "300px" }
    );
    observer.observe(more);
    return () => observer.disconnect();
  }, [hasMore, limit]);

  const shown = useRef<number[]>([]);
  const generation = useRef(0);
  const numbers = drawn?.map((i) => i.number) ?? [];
  const before = new Set(shown.current);
  const after = new Set(numbers);
  const arriving = numbers.filter((n) => !before.has(n)).length;
  const leaving = shown.current.filter((n) => !after.has(n)).length;
  if (arriving > MAX_ANIMATED || leaving > MAX_ANIMATED) generation.current += 1;
  shown.current = numbers;

  return (
    <section className={`column${tracking ? " tracking" : ""}${dropState}`}>
      <header className="column-header">
        <div className="column-title">
          <span className="column-dot" style={{ background: accentColor }} />
          <span>{column.name}</span>
          {issues && <span className="count-pill">{issues.length}</span>}
        </div>
        <span className="column-actions" ref={menuRef}>
          <button
            className={`card-menu-btn${refreshing ? " spinning" : ""}`}
            style={{ position: "static" }}
            disabled={refreshing}
            onClick={() => onRefreshColumn(column.id)}
            title="Refresh this column"
            aria-label={`Refresh column ${column.name}`}
          >
            <IconRefresh />
          </button>
          {column.virtual && (
            <span className="filter-chip" title="Automatic column, from your username in settings">
              auto
            </span>
          )}

          {!column.virtual && canManage && (
            <>
              <button
                className="card-menu-btn"
                style={{ position: "static" }}
                disabled={!canMoveLeft}
                onClick={() => onMoveColumn(column.id, -1)}
                title="Move column left"
                aria-label={`Move column ${column.name} left`}
              >
                <IconChevronLeft />
              </button>
              <button
                className="card-menu-btn"
                style={{ position: "static" }}
                disabled={!canMoveRight}
                onClick={() => onMoveColumn(column.id, 1)}
                title="Move column right"
                aria-label={`Move column ${column.name} right`}
              >
                <IconChevronRight />
              </button>
            </>
          )}

          <button
            className="card-menu-btn"
            style={{ position: "static" }}
            onClick={() => setMenuOpen((v) => !v)}
            title="Column actions"
            aria-label={`Actions for column ${column.name}`}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
          >
            <IconDots />
          </button>

          {menuOpen && (
            <div className="move-menu column-menu" role="menu">
              {!column.virtual && canManage && (
                <button role="menuitem" onClick={() => { setMenuOpen(false); onEditColumn(column); }}>
                  Edit filters…
                </button>
              )}
              <button role="menuitem" onClick={handleCopy}>
                Copy issues{issues ? ` (${issues.length})` : ""}
              </button>
              {!column.virtual && canManage && (
                <button role="menuitem" onClick={() => { setMenuOpen(false); onDeleteColumn(column.id); }}>
                  Remove column
                </button>
              )}
            </div>
          )}

          {copied && <span className="copied-toast">{copied}</span>}
        </span>
      </header>

      {chips.length > 0 && (
        <div className="column-filters">
          {chips.map((c) => (
            <span key={c} className="filter-chip">
              {c}
            </span>
          ))}
        </div>
      )}

      <div
        className="column-body"
        ref={(node) => {
          setDropRef(node);
          bodyRef.current = node;
        }}
      >
        {loading && [0, 1].map((i) => <div key={i} className="skeleton card-skeleton" />)}
        <AnimatePresence initial={false} key={generation.current}>
          {drawn?.map((issue) => (
            <IssueCardView
              key={issue.number}
              issue={issue}
              dashboardId={dashboardId}
              columnId={column.id}
              otherColumns={allColumns.filter((c) => c.id !== column.id)}
              notesByIssue={notesByIssue}
              onOpen={onOpenIssue}
              onMove={onMoveIssue}
              onCloseIssue={onCloseIssue}
              onTrack={onTrackIssue}
              onUntrack={onUntrackIssue}
              trackingColumns={canManage ? allColumns.filter((c) => c.kind === "tracking" && c.id !== column.id) : []}
              inTrackingColumn={tracking}
              canManage={canManage}
              draggable={canDrag}
              canWrite={canWrite}
              writeBlockReason={writeBlockReason}
            />
          ))}
        </AnimatePresence>
        {hasMore && (
          // Drawn on reaching it; a button too, for keyboards and for a
          // browser without IntersectionObserver.
          <button ref={moreRef} className="column-more" onClick={() => setLimit((l) => l + BATCH)}>
            Showing {limit} of {issues?.length} · more as you scroll
          </button>
        )}
        {!loading && issues?.length === 0 && (
          <div className="column-empty">
            {tracking
              ? canManage
                ? "Drag issues here to keep track of them."
                : "Nothing tracked here yet."
              : "Nothing here right now."}
          </div>
        )}
      </div>
    </section>
  );
}
