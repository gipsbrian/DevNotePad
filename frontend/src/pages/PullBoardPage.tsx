import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createPortal } from "react-dom";
import { DndContext, PointerSensor, useDroppable, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { AnimatePresence } from "framer-motion";
import { api } from "../api/client";
import type { Column, DashboardDetail, PullCard, Settings } from "../types/api";
import { TokenBadge } from "../components/TokenBadge";
import { DragLayer, landsIn } from "../components/DragLayer";
import { PullCardView, pullKey } from "../components/PullCardView";
import { StickyColumn } from "../components/StickyColumn";
import { CustomizePanel } from "../components/CustomizePanel";
import { ShareModal } from "../components/ShareModal";
import { BoardSearch } from "./DashboardBoardPage";
import {
  IconAlert,
  IconChevronLeft,
  IconChevronRight,
  IconEye,
  IconPalette,
  IconPlus,
  IconRefresh,
  IconRepo,
  IconSearch,
  IconUsers,
  IconX,
} from "../components/Icons";

function matches(pull: PullCard, query: string): boolean {
  if (!query) return true;
  const q = query.toLowerCase();
  return [pull.title, pull.repo, `#${pull.number}`, pull.author?.login ?? "", ...pull.labels.map((l) => l.name)].some(
    (s) => s.toLowerCase().includes(q)
  );
}

/** A PR board: pull requests across one GitHub org. Two automatic columns
 * follow whoever is looking (their open PRs, and PRs waiting on their
 * review); the board's own columns are tracking columns PRs are dropped into. */
export function PullBoardPage({ initial, switchedTo: arrivedIn = null }: { initial: DashboardDetail; switchedTo?: string | null }) {
  const navigate = useNavigate();
  const dashboardId = initial.id;
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const [dashboard, setDashboard] = useState(initial);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [columns, setColumns] = useState<Column[]>([]);
  const [pullsByColumn, setPullsByColumn] = useState<Record<number, PullCard[]>>({});
  const [columnErrors, setColumnErrors] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState<Set<number>>(new Set());
  const [query, setQuery] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [showCustomize, setShowCustomize] = useState(false);
  const [showShare, setShowShare] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [switchedTo, setSwitchedTo] = useState(arrivedIn);
  const boardRef = useRef<HTMLDivElement>(null);

  const loadColumn = useCallback(
    async (columnId: number) => {
      setLoading((prev) => new Set(prev).add(columnId));
      try {
        const pulls = await api.listColumnPulls(dashboardId, columnId);
        setPullsByColumn((prev) => ({ ...prev, [columnId]: pulls }));
        setColumnErrors(({ [columnId]: _, ...rest }) => rest);
      } catch (e) {
        setColumnErrors((prev) => ({ ...prev, [columnId]: (e as Error).message }));
      } finally {
        setLoading((prev) => {
          const next = new Set(prev);
          next.delete(columnId);
          return next;
        });
      }
    },
    [dashboardId]
  );

  const loadAll = useCallback(async () => {
    try {
      const [dash, cols, s] = await Promise.all([api.getDashboard(dashboardId), api.listColumns(dashboardId), api.getSettings()]);
      setDashboard(dash);
      setSettings(s);
      // The automatic columns are the point of the board, so they lead.
      const ordered = [...cols.filter((c) => c.virtual), ...cols.filter((c) => !c.virtual)];
      setColumns(ordered);
      await Promise.all(ordered.map((c) => loadColumn(c.id)));
    } catch (e) {
      setActionError((e as Error).message);
    }
  }, [dashboardId, loadColumn]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // The automatic columns come from your username in settings.
  useEffect(() => {
    window.addEventListener("devnotepad:settings-changed", loadAll);
    return () => window.removeEventListener("devnotepad:settings-changed", loadAll);
  }, [loadAll]);

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await loadAll();
    } finally {
      setRefreshing(false);
    }
  }

  // useCallback keeps these stable, so the memoised cards don't all
  // re-render on every change to the board.

  /** Optimistic, like tracking an issue: the card lands at once and the
   * server's copy replaces it. From another tracking column it moves. */
  const handleTrack = useCallback(
    async (pull: PullCard, columnId: number, fromColumnId?: number) => {
      const key = pullKey(pull);
      const place = (list: PullCard[] | undefined, fresh: PullCard) =>
        list?.some((p) => pullKey(p) === key) ? list.map((p) => (pullKey(p) === key ? fresh : p)) : [fresh, ...(list ?? [])];
      setPullsByColumn((prev) => {
        const next = { ...prev, [columnId]: place(prev[columnId], pull) };
        if (fromColumnId !== undefined) next[fromColumnId] = (prev[fromColumnId] ?? []).filter((p) => pullKey(p) !== key);
        return next;
      });
      try {
        const fresh = await api.trackPull(dashboardId, columnId, pull.repo, pull.number, fromColumnId);
        setPullsByColumn((prev) => ({ ...prev, [columnId]: place(prev[columnId], fresh) }));
      } catch (e) {
        setActionError((e as Error).message);
        loadColumn(columnId);
        if (fromColumnId !== undefined) loadColumn(fromColumnId);
      }
    },
    [dashboardId, loadColumn]
  );

  const handleUntrack = useCallback(
    async (pull: PullCard, columnId: number) => {
      const key = pullKey(pull);
      setPullsByColumn((prev) => ({ ...prev, [columnId]: (prev[columnId] ?? []).filter((p) => pullKey(p) !== key) }));
      try {
        await api.untrackPull(dashboardId, columnId, pull.repo, pull.number);
      } catch (e) {
        setActionError((e as Error).message);
        loadColumn(columnId);
      }
    },
    [dashboardId, loadColumn]
  );

  function handleDragEnd(event: DragEndEvent) {
    const target = landsIn(event);
    const pull = event.active.data.current?.pull as PullCard | undefined;
    if (target === null || !pull) return;
    const source = columns.find((c) => c.id === event.active.data.current?.sourceColumnId);
    handleTrack(pull, target, source?.kind === "tracking" ? source.id : undefined);
  }

  async function handleAddColumn(name: string) {
    try {
      const column = await api.createColumn(dashboardId, { name, kind: "tracking" });
      setColumns((prev) => [...prev, column]);
      setPullsByColumn((prev) => ({ ...prev, [column.id]: [] }));
    } catch (e) {
      setActionError((e as Error).message);
    }
  }

  async function handleDeleteColumn(columnId: number) {
    try {
      await api.deleteColumn(dashboardId, columnId);
      setColumns((prev) => prev.filter((c) => c.id !== columnId));
    } catch (e) {
      setActionError((e as Error).message);
    }
  }

  async function handleMoveColumn(columnId: number, direction: -1 | 1) {
    const own = columns.filter((c) => !c.virtual);
    const from = own.findIndex((c) => c.id === columnId);
    const to = from + direction;
    if (from < 0 || to < 0 || to >= own.length) return;
    const reordered = [...own];
    [reordered[from], reordered[to]] = [reordered[to], reordered[from]];
    try {
      const saved = await api.reorderColumns(dashboardId, reordered.map((c) => c.id));
      setColumns((prev) => [...prev.filter((c) => c.virtual), ...saved]);
    } catch (e) {
      setActionError((e as Error).message);
      loadAll();
    }
  }

  const canManage = dashboard.access === "manage";
  const trackingColumns = useMemo(() => (canManage ? columns.filter((c) => c.kind === "tracking") : []), [columns, canManage]);
  const canDrag = trackingColumns.length > 0;
  const own = columns.filter((c) => !c.virtual);
  const accent = dashboard.accent_color ?? "#6d5efc";
  const canvasStyle: React.CSSProperties = {
    ["--accent" as string]: accent,
    ["--canvas-image" as string]: dashboard.background_url
      ? `url(${dashboard.background_url})`
      : `linear-gradient(150deg, color-mix(in srgb, ${accent} 80%, #ffffff) 0%, ${accent} 45%, color-mix(in srgb, ${accent} 58%, #10142b) 100%)`,
  };

  return (
    <main className="app-main board-main">
      <div className="board-canvas" style={canvasStyle}>
        <header className="board-topbar">
          <div>
            <h1 className="page-title">{dashboard.name}</h1>
            <p className="page-sub">
              <IconRepo />
              Pull requests in {dashboard.repo_owner}
            </p>
          </div>
          <div className="head-actions">
            <div className="search-pill">
              <IconSearch />
              <BoardSearch onQuery={setQuery} label="pull requests" />
            </div>
            {dashboard.token_info && <TokenBadge info={dashboard.token_info} />}
            <button className="icon-btn" onClick={handleRefresh} title="Refresh" aria-label="Refresh">
              <IconRefresh style={refreshing ? { opacity: 0.5 } : undefined} />
            </button>
            {canManage && dashboard.kind === "personal" && (
              <button className="btn" onClick={() => setShowShare(true)}>
                <IconUsers /> {dashboard.is_shared ? "Shared" : "Share"}
              </button>
            )}
            {canManage && (
              <button className="btn" onClick={() => setShowCustomize((v) => !v)}>
                <IconPalette /> Customize
              </button>
            )}
          </div>
        </header>

        <div className="board-inner">
          {actionError && (
            <div className="notice" role="alert">
              <IconAlert />
              <span>{actionError}</span>
              <button className="notice-dismiss" onClick={() => setActionError(null)} aria-label="Dismiss">
                <IconX />
              </button>
            </div>
          )}

          {switchedTo && (
            <div className="notice" role="status">
              <IconAlert />
              <span>
                This board belongs to <strong>{switchedTo}</strong>, so you’ve been switched to that organisation.
              </span>
              <button className="notice-dismiss" onClick={() => setSwitchedTo(null)} aria-label="Dismiss">
                <IconX />
              </button>
            </div>
          )}

          {settings && !settings.github_username && (
            <div className="notice" role="status">
              <IconAlert />
              <span>Set your GitHub username in settings to see your open PRs and the ones waiting on your review.</span>
            </div>
          )}

          {!canManage && (
            <div className="notice view-only" role="status">
              <IconEye />
              <span>
                {dashboard.kind === "organization"
                  ? "An organisation board, managed by its admins. The automatic columns show your own PRs."
                  : `Shared with you by ${dashboard.owner ?? "its owner"}, view only. The automatic columns show your own PRs.`}
              </span>
            </div>
          )}

          {showCustomize && (
            <CustomizePanel
              dashboard={dashboard}
              settings={settings}
              onChanged={(d) => {
                setDashboard({ ...dashboard, ...d });
                loadAll();
              }}
              onDeleted={() => navigate("/")}
              onClose={() => setShowCustomize(false)}
            />
          )}

          <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
            <div className="board" ref={boardRef}>
              {columns.map((column) => (
                <PullColumn
                  key={column.id}
                  column={column}
                  pulls={pullsByColumn[column.id]?.filter((p) => matches(p, query))}
                  error={columnErrors[column.id]}
                  loading={loading.has(column.id)}
                  accentColor={accent}
                  trackingColumns={trackingColumns}
                  canManage={canManage}
                  canDrag={canDrag}
                  canMoveLeft={!column.virtual && own.findIndex((c) => c.id === column.id) > 0}
                  canMoveRight={!column.virtual && own.findIndex((c) => c.id === column.id) < own.length - 1}
                  onRefresh={loadColumn}
                  onTrack={handleTrack}
                  onUntrack={handleUntrack}
                  onDelete={handleDeleteColumn}
                  onMove={handleMoveColumn}
                />
              ))}
              {canManage && <AddTrackingColumn onAdd={handleAddColumn} />}
            </div>
            <DragLayer boardRef={boardRef} />
          </DndContext>

          {createPortal(<StickyColumn dashboardId={dashboardId} issuesOpen={false} />, document.body)}
        </div>
      </div>

      {showShare && (
        <ShareModal
          dashboardId={dashboardId}
          onClose={() => setShowShare(false)}
          onSaved={async () => setDashboard({ ...dashboard, ...(await api.getDashboard(dashboardId)) })}
        />
      )}
    </main>
  );
}

const PullColumn = memo(function PullColumn({
  column,
  pulls,
  error,
  loading,
  accentColor,
  trackingColumns,
  canManage,
  canDrag,
  canMoveLeft,
  canMoveRight,
  onRefresh,
  onTrack,
  onUntrack,
  onDelete,
  onMove,
}: {
  column: Column;
  pulls: PullCard[] | undefined;
  error?: string;
  loading: boolean;
  accentColor: string;
  trackingColumns: Column[];
  canManage: boolean;
  canDrag: boolean;
  canMoveLeft: boolean;
  canMoveRight: boolean;
  onRefresh: (columnId: number) => void;
  onTrack: (pull: PullCard, columnId: number, fromColumnId?: number) => void;
  onUntrack: (pull: PullCard, columnId: number) => void;
  onDelete: (columnId: number) => void;
  onMove: (columnId: number, direction: -1 | 1) => void;
}) {
  const tracking = column.kind === "tracking";
  const droppable = tracking && canManage;
  const { setNodeRef, isOver } = useDroppable({
    id: `column-${column.id}`,
    data: { type: "pulls", columnId: column.id, tracking },
    disabled: !droppable,
  });
  const others = useMemo(() => trackingColumns.filter((c) => c.id !== column.id), [trackingColumns, column.id]);
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <section
      className={`column${tracking ? " tracking" : ""}${droppable ? " droppable" : ""}${isOver && droppable ? " is-over" : ""}`}
      data-column-id={column.id}
    >
      <header className="column-header">
        <div className="column-title">
          <span className="column-dot" style={{ background: accentColor }} />
          <span>{column.name}</span>
          {pulls && <span className="count-pill">{pulls.length}</span>}
        </div>
        <span className="column-actions">
          <button
            className={`card-menu-btn${loading ? " spinning" : ""}`}
            style={{ position: "static" }}
            disabled={loading}
            onClick={() => onRefresh(column.id)}
            title="Refresh this column"
            aria-label={`Refresh column ${column.name}`}
          >
            <IconRefresh />
          </button>
          {column.virtual && (
            <span className="filter-chip" title="Automatic column, from your GitHub username in settings">
              auto
            </span>
          )}
          {!column.virtual && canManage && (
            <>
              <button
                className="card-menu-btn"
                style={{ position: "static" }}
                disabled={!canMoveLeft}
                onClick={() => onMove(column.id, -1)}
                aria-label={`Move column ${column.name} left`}
              >
                <IconChevronLeft />
              </button>
              <button
                className="card-menu-btn"
                style={{ position: "static" }}
                disabled={!canMoveRight}
                onClick={() => onMove(column.id, 1)}
                aria-label={`Move column ${column.name} right`}
              >
                <IconChevronRight />
              </button>
              <button
                className="card-menu-btn"
                style={{ position: "static" }}
                onClick={() => (confirmDelete ? onDelete(column.id) : setConfirmDelete(true))}
                onBlur={() => setConfirmDelete(false)}
                title={confirmDelete ? "Click again to remove" : "Remove column"}
                aria-label={confirmDelete ? `Really remove ${column.name}?` : `Remove column ${column.name}`}
              >
                <IconX />
              </button>
            </>
          )}
        </span>
      </header>
      {tracking && (
        <div className="column-filters">
          <span className="filter-chip">tracking</span>
        </div>
      )}

      <div className="column-body" ref={setNodeRef}>
        {loading && !pulls && [0, 1].map((i) => <div key={i} className="skeleton card-skeleton" />)}
        {error && <div className="column-empty">{error}</div>}
        <AnimatePresence initial={false}>
          {pulls?.map((pull) => (
            <PullCardView
              key={pullKey(pull)}
              pull={pull}
              columnId={column.id}
              onTrack={onTrack}
              onUntrack={onUntrack}
              trackingColumns={others}
              inTrackingColumn={tracking}
              canManage={canManage}
              draggable={canDrag}
            />
          ))}
        </AnimatePresence>
        {!loading && !error && pulls?.length === 0 && (
          <div className="column-empty">
            {tracking
              ? canManage
                ? "Drag pull requests here to keep track of them."
                : "Nothing tracked here yet."
              : column.id === -4
                ? "No reviews waiting on you."
                : "No open pull requests."}
          </div>
        )}
      </div>
    </section>
  );
});

function AddTrackingColumn({ onAdd }: { onAdd: (name: string) => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  if (!open)
    return (
      <button className="add-column-btn" onClick={() => setOpen(true)}>
        <IconPlus />
        Add tracking column
      </button>
    );
  return (
    <form
      className="add-column-btn add-column-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (!name.trim()) return;
        onAdd(name.trim());
        setName("");
        setOpen(false);
      }}
    >
      <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Column name" aria-label="New column name" />
      <div style={{ display: "flex", gap: 6 }}>
        <button className="btn primary" type="submit">
          Add
        </button>
        <button className="btn" type="button" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </form>
  );
}
