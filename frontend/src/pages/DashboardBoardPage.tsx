import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { DndContext, PointerSensor, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { api } from "../api/client";
import type { Column, DashboardDetail, IssueCard, Note, RepoMetadata, Settings } from "../types/api";
import { TokenBadge } from "../components/TokenBadge";
import { ColumnView } from "../components/ColumnView";
import { ColumnEditorModal, type ColumnFilterPayload } from "../components/ColumnEditorModal";
import { IssueStack, MAX_OPEN_ISSUES } from "../components/IssueStack";
import { ClosedSection, CLOSED_RANGES } from "../components/ClosedSection";
import { StickyColumn } from "../components/StickyColumn";
import { CustomizePanel } from "../components/CustomizePanel";
import { ShareModal } from "../components/ShareModal";
import { matchesSearch } from "../utils/search";
import { useFirstVisitTour } from "../tour/useTour";
import { useOrganizations } from "../org-context";
import { stillReportedOpen } from "../utils/justClosed";
import {
  IconAlert,
  IconCheckCircle,
  IconIssue,
  IconLayers,
  IconPalette,
  IconPlus,
  IconRefresh,
  IconRepo,
  IconSearch,
  IconTimer,
  IconX,
  IconUsers,
  IconEye,
} from "../components/Icons";

export function DashboardBoardPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const dashboardId = id!;
  // Require a few pixels of movement before a drag starts, so a plain
  // click (open card, move-menu button, delete column) still fires —
  // without this dnd-kit's PointerSensor treats any pointerdown as the
  // start of a drag.
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  // Which issues are open lives in the URL rather than in state, so a
  // refresh reopens them instead of dropping you back on the board.
  const [searchParams, setSearchParams] = useSearchParams();
  const openIssues = useMemo(() => {
    const raw = searchParams.get("issues");
    if (!raw) return [];
    const seen = new Set<number>();
    for (const part of raw.split(",")) {
      const n = Number(part);
      if (Number.isInteger(n) && n > 0) seen.add(n);
    }
    return [...seen].slice(0, MAX_OPEN_ISSUES);
  }, [searchParams]);

  const setOpenIssues = useCallback(
    (numbers: number[]) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (numbers.length === 0) next.delete("issues");
          else next.set("issues", numbers.join(","));
          return next;
        },
        // Opening and closing issues shouldn't stack up history entries
        // between the board and itself.
        { replace: true }
      );
    },
    [setSearchParams]
  );

  const openIssue = useCallback((n: number) => setOpenIssues([n]), [setOpenIssues]);

  const [dashboard, setDashboard] = useState<DashboardDetail | null>(null);
  const { reload: reloadOrganizations } = useOrganizations();
  // Set when opening this board moved you into its organisation.
  const [switchedTo, setSwitchedTo] = useState<string | null>(null);
  const [columns, setColumns] = useState<Column[]>([]);
  const [issuesByColumn, setIssuesByColumn] = useState<Record<number, IssueCard[]>>({});
  const [closedIssues, setClosedIssues] = useState<IssueCard[]>([]);
  const [notesByIssue, setNotesByIssue] = useState<Map<number, Note[]>>(new Map());
  const [loadingColumns, setLoadingColumns] = useState<Set<number>>(new Set());
  const [refreshingColumns, setRefreshingColumns] = useState<Set<number>>(new Set());
  // StrictMode double-invokes effects in development, which doubled every
  // board load's GitHub calls. Coalescing identical in-flight loads keeps
  // dev honest without giving up StrictMode's checks. (Production already
  // issues exactly one request per column.)
  const inFlight = useRef<{ key: string; promise: Promise<void> } | null>(null);
  const [showColumnEditor, setShowColumnEditor] = useState(false);
  const [editingColumn, setEditingColumn] = useState<Column | null>(null);
  const [repoMetadata, setRepoMetadata] = useState<RepoMetadata | null>(null);
  const [appSettings, setAppSettings] = useState<Settings | null>(null);
  const [showCustomize, setShowCustomize] = useState(false);
  const [showShare, setShowShare] = useState(false);
  // `error` is fatal (the board couldn't load at all); `actionError` is a
  // transient failure from one action, which must not blow away a board
  // that is otherwise working.
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  // Dismissal sticks per board — the warning matters, but not every visit.
  const noticeKey = `devnotepad-notice-dismissed-${dashboardId}`;
  const [noticeOpen, setNoticeOpen] = useState(() => {
    try {
      return localStorage.getItem(noticeKey) !== "1";
    } catch {
      return true;
    }
  });

  function dismissNotice() {
    setNoticeOpen(false);
    try {
      localStorage.setItem(noticeKey, "1");
    } catch {
      // non-critical
    }
  }
  const [refreshing, setRefreshing] = useState(false);
  // Fetching a busy repo's whole closed history dominates load time, so
  // default to a short window and remember the choice per board.
  const closedDaysKey = `devnotepad-closed-days-${dashboardId}`;
  const [closedDays, setClosedDays] = useState<number>(() => {
    try {
      const saved = localStorage.getItem(closedDaysKey);
      return saved === null ? 7 : Number(saved);
    } catch {
      return 7;
    }
  });
  const [closedLoading, setClosedLoading] = useState(false);
  // Closing an issue is a write to GitHub, and its list endpoint can still
  // report that issue as open for a moment afterwards -- so the refetch we
  // fire right after closing would put the card straight back. Hide it
  // until a refetch stops listing it as open.
  const [justClosed, setJustClosed] = useState<Set<number>>(new Set());

  const loadAll = useCallback(async () => {
    const key = `${dashboardId}:${closedDays}`;
    if (inFlight.current?.key === key) return inFlight.current.promise;

    const run = (async () => {
    try {
      const [dash, cols, notes, closed, appSettingsResult] = await Promise.all([
        api.getDashboard(dashboardId),
        api.listColumns(dashboardId),
        api.listNotes(dashboardId),
        api.listClosedIssues(dashboardId, closedDays),
        api.getSettings(),
      ]);
      setDashboard(dash);
      if (dash.switched_organization) {
        setSwitchedTo(dash.organization_name);
        reloadOrganizations();
      }
      setAppSettings(appSettingsResult);
      setColumns(cols);
      setClosedIssues(closed);
      const map = new Map<number, Note[]>();
      for (const n of notes) {
        if (!map.has(n.issue_number)) map.set(n.issue_number, []);
        map.get(n.issue_number)!.push(n);
      }
      setNotesByIssue(map);

      setLoadingColumns(new Set(cols.map((c) => c.id)));
      const results = await Promise.all(cols.map((c) => api.listColumnIssues(dashboardId, c.id)));
      const byColumn: Record<number, IssueCard[]> = {};
      cols.forEach((c, i) => (byColumn[c.id] = results[i]));
      setIssuesByColumn(byColumn);
      setLoadingColumns(new Set());
    } catch (e) {
      setError((e as Error).message);
    }
    })();

    inFlight.current = { key, promise: run };
    try {
      await run;
    } finally {
      if (inFlight.current?.key === key) inFlight.current = null;
    }
  }, [dashboardId, closedDays, reloadOrganizations]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (justClosed.size === 0) return;
    const next = stillReportedOpen(issuesByColumn, justClosed);
    if (next.size !== justClosed.size) setJustClosed(next);
  }, [issuesByColumn, justClosed]);

  // The automatic "Assigned to me" / "Created by me" columns come from
  // global settings, so reload when those change.
  useEffect(() => {
    window.addEventListener("devnotepad:settings-changed", loadAll);
    return () => window.removeEventListener("devnotepad:settings-changed", loadAll);
  }, [loadAll]);

  async function refreshColumnIssues(columnId: number) {
    const issues = await api.listColumnIssues(dashboardId, columnId);
    setIssuesByColumn((prev) => ({ ...prev, [columnId]: issues }));
  }

  /** The hover preview reads from this map, so it has to be refetched
   * whenever a note is added, edited or deleted — otherwise the card's
   * note badge appears (that comes from the issue payload) with nothing
   * behind it to show. */
  async function refreshNotes() {
    const notes = await api.listNotes(dashboardId);
    const map = new Map<number, Note[]>();
    for (const n of notes) {
      if (!map.has(n.issue_number)) map.set(n.issue_number, []);
      map.get(n.issue_number)!.push(n);
    }
    setNotesByIssue(map);
  }

  /** Refetch one column. Each column already queries GitHub with its own
   * filter, so refreshing one costs exactly one request rather than
   * reloading the whole board. */
  async function handleRefreshColumn(columnId: number) {
    setRefreshingColumns((prev) => new Set(prev).add(columnId));
    try {
      await refreshColumnIssues(columnId);
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setRefreshingColumns((prev) => {
        const next = new Set(prev);
        next.delete(columnId);
        return next;
      });
    }
  }

  async function refreshClosed() {
    setClosedIssues(await api.listClosedIssues(dashboardId, closedDays));
  }

  async function handleChangeClosedDays(days: number) {
    setClosedDays(days);
    try {
      localStorage.setItem(closedDaysKey, String(days));
    } catch {
      // non-critical
    }
    setClosedLoading(true);
    try {
      setClosedIssues(await api.listClosedIssues(dashboardId, days));
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setClosedLoading(false);
    }
  }

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await loadAll();
    } finally {
      setRefreshing(false);
    }
  }

  async function handleMoveIssue(issueNumber: number, targetColumnId: number) {
    try {
      await api.moveIssue(dashboardId, issueNumber, targetColumnId);
      await Promise.all(columns.map((c) => refreshColumnIssues(c.id)));
      await refreshClosed();
    } catch (e) {
      setActionError((e as Error).message);
    }
  }

  /** Moves a column one slot left (-1) or right (+1). The server returns
   * the resulting order, which is what we render — no optimistic guess to
   * drift out of sync with. */
  async function handleMoveColumn(columnId: number, direction: -1 | 1) {
    const real = columns.filter((c) => !c.virtual);
    const from = real.findIndex((c) => c.id === columnId);
    const to = from + direction;
    if (from < 0 || to < 0 || to >= real.length) return;

    const reordered = [...real];
    [reordered[from], reordered[to]] = [reordered[to], reordered[from]];

    try {
      const saved = await api.reorderColumns(dashboardId, reordered.map((c) => c.id));
      setColumns([...saved, ...columns.filter((c) => c.virtual)]);
    } catch (e) {
      setActionError((e as Error).message);
      loadAll();
    }
  }

  /** Close straight from a card's menu, without opening the issue. */
  async function handleCloseIssue(issueNumber: number) {
    try {
      await api.closeIssue(dashboardId, issueNumber);
      setJustClosed((prev) => new Set(prev).add(issueNumber));
      await Promise.all(columns.map((c) => refreshColumnIssues(c.id)));
      await refreshClosed();
    } catch (e) {
      setActionError((e as Error).message);
    }
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over) return;

    const issueNumber = active.data.current?.issueNumber as number | undefined;
    const targetColumnId = over.data.current?.columnId as number | undefined;
    const sourceColumnId = active.data.current?.sourceColumnId;
    if (!issueNumber || !targetColumnId || targetColumnId === sourceColumnId) return;
    handleMoveIssue(issueNumber, targetColumnId);
  }

  async function openColumnEditor(column: Column | null = null) {
    if (!repoMetadata) {
      try {
        setRepoMetadata(await api.getRepoMetadata(dashboardId));
      } catch (e) {
        setActionError((e as Error).message);
        return;
      }
    }
    setEditingColumn(column);
    setShowColumnEditor(true);
  }

  async function handleSubmitColumn(payload: ColumnFilterPayload) {
    try {
      if (editingColumn) {
        const updated = await api.updateColumn(dashboardId, editingColumn.id, payload);
        setColumns((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
        refreshColumnIssues(updated.id);
      } else {
        const column = await api.createColumn(dashboardId, payload);
        // Keep the automatic "…me" columns last.
        setColumns((prev) => [...prev.filter((c) => !c.virtual), column, ...prev.filter((c) => c.virtual)]);
        refreshColumnIssues(column.id);
      }
      setShowColumnEditor(false);
      setEditingColumn(null);
    } catch (e) {
      setActionError((e as Error).message);
    }
  }

  async function handleDeleteColumn(columnId: number) {
    await api.deleteColumn(dashboardId, columnId);
    setColumns((prev) => prev.filter((c) => c.id !== columnId));
    setIssuesByColumn((prev) => {
      const next = { ...prev };
      delete next[columnId];
      return next;
    });
  }

  /** `closedIssueNumber` is set only when the change was closing that
   * issue on GitHub; note edits pass nothing. */
  function handleIssueChanged(closedIssueNumber?: number) {
    if (closedIssueNumber) setJustClosed((prev) => new Set(prev).add(closedIssueNumber));
    Promise.all(columns.map((c) => refreshColumnIssues(c.id)));
    refreshClosed();
    refreshNotes();
  }

  const stats = useMemo(() => {
    const open = new Map<number, IssueCard>();
    Object.values(issuesByColumn).forEach((list) =>
      list.forEach((i) => {
        if (i.state === "open" && !justClosed.has(i.number)) open.set(i.number, i);
      })
    );
    const openList = [...open.values()];
    const oldest = openList.reduce((max, i) => Math.max(max, i.age_days), 0);
    return { open: openList.length, closed: closedIssues.length, columns: columns.length, oldest };
  }, [issuesByColumn, closedIssues, columns, justClosed]);

  // Only once the cards are in, and never over an open issue or panel.
  useFirstVisitTour(
    "board",
    dashboard !== null && loadingColumns.size === 0 && openIssues.length === 0 && !showCustomize && !showColumnEditor
  );

  if (error) return <main className="app-main"><p className="state-msg">Error: {error}</p></main>;
  if (!dashboard) return <main className="app-main"><p className="state-msg">Loading board…</p></main>;

  const canManage = dashboard.access === "manage";
  const canWrite = dashboard.can_write;
  const accent = dashboard.accent_color ?? "#6d5efc";
  // The board canvas is either the dashboard's wallpaper or a rich
  // monochromatic gradient derived from its accent — light top-left,
  // deep bottom-right, so it reads well behind translucent lists.
  const canvasImage = dashboard.background_url
    ? `url(${dashboard.background_url})`
    : `linear-gradient(150deg, color-mix(in srgb, ${accent} 80%, #ffffff) 0%, ${accent} 45%, color-mix(in srgb, ${accent} 58%, #10142b) 100%)`;

  const canvasStyle: React.CSSProperties = {
    ["--accent" as string]: accent,
    ["--canvas-image" as string]: canvasImage,
  };

  return (
    <main className="app-main board-main">
      <div className="board-canvas" style={canvasStyle}>
        <header className="board-topbar">
          <div>
            <h1 className="page-title">{dashboard.name}</h1>
            <p className="page-sub">
              <IconRepo />
              {dashboard.repo_owner}/{dashboard.repo_name}
            </p>
          </div>
          <div className="head-actions">
            <div className="search-pill">
              <IconSearch />
              <input
                type="search"
                placeholder="Search issues…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                aria-label="Search issues on this board"
              />
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
              <button className="btn" data-tour="customize" onClick={() => setShowCustomize((v) => !v)}>
                <IconPalette /> Customize
              </button>
            )}
          </div>
        </header>

        <div className="board-inner">
        <div className="stat-row">
          <div className="stat-tile">
            <span className="stat-icon">
              <IconIssue />
            </span>
            <div>
              <div className="stat-value">{stats.open}</div>
              <div className="stat-label">Open on board</div>
            </div>
          </div>
          <div className="stat-tile">
            <span className="stat-icon muted">
              <IconCheckCircle />
            </span>
            <div>
              <div className="stat-value">{stats.closed}</div>
              <div className="stat-label">
                Closed · {CLOSED_RANGES.find((r) => r.days === closedDays)?.label ?? `${closedDays} days`}
              </div>
            </div>
          </div>
          <div className="stat-tile">
            <span className="stat-icon muted">
              <IconLayers />
            </span>
            <div>
              <div className="stat-value">{stats.columns}</div>
              <div className="stat-label">Columns</div>
            </div>
          </div>
          <div className="stat-tile">
            <span className="stat-icon muted">
              <IconTimer />
            </span>
            <div>
              <div className="stat-value">{stats.oldest}d</div>
              <div className="stat-label">Oldest open</div>
            </div>
          </div>
        </div>

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

        {!canManage && (
          <div className="notice view-only" role="status">
            <IconEye />
            <span>
              {dashboard.kind === "organization"
                ? `An organisation board, managed by its admins.${!canWrite && dashboard.write_block_reason ? ` ${dashboard.write_block_reason}` : ""}`
                : `Shared with you by ${dashboard.owner ?? "its owner"}, view only. Notes you keep here are private to you.`}
            </span>
          </div>
        )}

        {noticeOpen && dashboard.token_info && (
          <div className="notice">
            <IconAlert />
            <span>{dashboard.token_info.warning}</span>
            <button className="notice-dismiss" onClick={dismissNotice} aria-label="Dismiss">
              <IconX />
            </button>
          </div>
        )}

        {showCustomize && (
          <CustomizePanel
            dashboard={dashboard}
            settings={appSettings}
            onChanged={(d) => {
              setDashboard({ ...dashboard, ...d });
              loadAll();
            }}
            onDeleted={() => navigate("/")}
            onClose={() => setShowCustomize(false)}
          />
        )}

        <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
          <div className="board">
            {columns.map((column) => (
              <ColumnView
                key={column.id}
                column={column}
                dashboardId={dashboardId}
                issues={issuesByColumn[column.id]?.filter(
                  (i) => matchesSearch(i, search) && !justClosed.has(i.number)
                )}
                allColumns={columns}
                notesByIssue={notesByIssue}
                loading={loadingColumns.has(column.id)}
                refreshing={refreshingColumns.has(column.id)}
                onRefreshColumn={handleRefreshColumn}
                accentColor={accent}
                onOpenIssue={openIssue}
                onMoveIssue={handleMoveIssue}
                onCloseIssue={handleCloseIssue}
                onEditColumn={openColumnEditor}
                onDeleteColumn={handleDeleteColumn}
                onMoveColumn={handleMoveColumn}
                canManage={canManage}
                canWrite={canWrite}
                writeBlockReason={dashboard.write_block_reason}
                canMoveLeft={!column.virtual && columns.filter((c) => !c.virtual).findIndex((c) => c.id === column.id) > 0}
                canMoveRight={
                  !column.virtual &&
                  columns.filter((c) => !c.virtual).findIndex((c) => c.id === column.id) <
                    columns.filter((c) => !c.virtual).length - 1
                }
              />
            ))}
            {canManage && (
              <button className="add-column-btn" onClick={() => openColumnEditor()}>
                <IconPlus />
                Add column
              </button>
            )}

          </div>
        </DndContext>

        {/* Floats above the board rather than living in the column
            scroll, so it's never scrolled out of reach. */}
        <StickyColumn dashboardId={dashboardId} />

        <ClosedSection
          issues={closedIssues.filter((i) => matchesSearch(i, search))}
          dashboardId={dashboardId}
          notesByIssue={notesByIssue}
          days={closedDays}
          loading={closedLoading}
          onChangeDays={handleChangeClosedDays}
          onOpenIssue={openIssue}
          canWrite={canWrite}
          writeBlockReason={dashboard.write_block_reason}
        />
        </div>
      </div>

      {showColumnEditor && repoMetadata && (
        <ColumnEditorModal
          metadata={repoMetadata}
          settings={appSettings}
          column={editingColumn ?? undefined}
          onCancel={() => {
            setShowColumnEditor(false);
            setEditingColumn(null);
          }}
          onSubmit={handleSubmitColumn}
        />
      )}

      {openIssues.length > 0 && (
        <IssueStack
          dashboardId={dashboardId}
          issueNumbers={openIssues}
          columns={columns}
          issuesByColumn={issuesByColumn}
          onCloseOne={(n) => setOpenIssues(openIssues.filter((x) => x !== n))}
          onCloseAll={() => setOpenIssues([])}
          onAdd={(n) => setOpenIssues([...openIssues, n])}
          onChanged={handleIssueChanged}
          canWrite={canWrite}
          writeBlockReason={dashboard.write_block_reason}
        />
      )}

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
