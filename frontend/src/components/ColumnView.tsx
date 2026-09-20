import { useEffect, useRef, useState } from "react";
import { useDroppable } from "@dnd-kit/core";
import type { Column, IssueCard, Note } from "../types/api";
import { IssueCardView } from "./IssueCardView";
import { copyText, formatIssuesForCopy } from "../utils/clipboard";
import { IconChevronLeft, IconChevronRight, IconDots, IconRefresh } from "./Icons";

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
  onEditColumn,
  onDeleteColumn,
  onMoveColumn,
  onRefreshColumn,
  canMoveLeft,
  canMoveRight,
  canManage = true,
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
  onEditColumn: (column: Column) => void;
  onDeleteColumn: (columnId: number) => void;
  onMoveColumn: (columnId: number, direction: -1 | 1) => void;
  onRefreshColumn: (columnId: number) => void;
  canMoveLeft: boolean;
  canMoveRight: boolean;
  /** Editing, moving and removing the column. */
  canManage?: boolean;
  /** Moving and closing its cards on GitHub. */
  canWrite?: boolean;
  writeBlockReason?: string | null;
}) {
  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: `column-${column.id}`,
    data: { type: "cards", columnId: column.id },
    disabled: !column.drag_compatible || !canWrite,
  });

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

  const chips = filterChips(column);

  return (
    <section className={`column${isOver && column.drag_compatible ? " is-over" : ""}`}>
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

      <div className="column-body" ref={setDropRef}>
        {loading && [0, 1].map((i) => <div key={i} className="skeleton card-skeleton" />)}
        {issues?.map((issue) => (
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
            canWrite={canWrite}
            writeBlockReason={writeBlockReason}
          />
        ))}
        {!loading && issues?.length === 0 && <div className="column-empty">Nothing here right now.</div>}
      </div>
    </section>
  );
}
