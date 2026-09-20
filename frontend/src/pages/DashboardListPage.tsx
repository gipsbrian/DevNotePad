import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Dashboard } from "../types/api";
import { InsightsPanel } from "../components/InsightsPanel";
import { IconBoard, IconPlus, IconRepo, IconSearch, IconX } from "../components/Icons";
import { useFirstVisitTour } from "../tour/useTour";
import { useOrganizations } from "../org-context";
import { SSO_ERRORS, SSO_NOTICES } from "../components/SsoButtons";

export function DashboardListPage() {
  const [dashboards, setDashboards] = useState<Dashboard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  useFirstVisitTour("home", dashboards !== null);

  const { active } = useOrganizations();
  // Single sign-on sends people back here with a code worth telling them.
  const [ssoMessage, setSsoMessage] = useState<{ text: string; error: boolean } | null>(() => {
    const params = new URLSearchParams(window.location.search);
    const notice = params.get("sso_notice");
    const error = params.get("sso_error");
    if (notice) return { text: SSO_NOTICES[notice] ?? "Signed in.", error: false };
    if (error) return { text: SSO_ERRORS[error] ?? SSO_ERRORS.failed, error: true };
    return null;
  });
  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.searchParams.has("sso_notice") || url.searchParams.has("sso_error")) {
      url.searchParams.delete("sso_notice");
      url.searchParams.delete("sso_error");
      window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    }
  }, []);
  const activeId = active?.id;

  // Boards live in an organisation: switching organisations means a
  // different list.
  useEffect(() => {
    if (!activeId) return;
    setDashboards(null);
    api.listDashboards().then(setDashboards).catch((e) => setError(e.message));
  }, [activeId]);

  const visible = useMemo(() => {
    if (!dashboards) return [];
    const q = query.trim().toLowerCase();
    if (!q) return dashboards;
    return dashboards.filter(
      (d) =>
        d.name.toLowerCase().includes(q) ||
        `${d.repo_owner}/${d.repo_name}`.toLowerCase().includes(q)
    );
  }, [dashboards, query]);

  const organizationBoards = visible.filter((d) => d.kind === "organization");
  const ownBoards = visible.filter((d) => d.kind === "personal" && d.access === "manage");
  const sharedBoards = visible.filter((d) => d.kind === "personal" && d.access === "view");

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm("Remove this board? Its columns and local notes go with it. GitHub itself is never touched.")) return;
    await api.deleteDashboard(id);
    setDashboards((prev) => prev?.filter((d) => d.id !== id) ?? null);
  }

  if (error) return <main className="app-main"><p className="state-msg">Couldn’t load boards: {error}</p></main>;

  return (
    <main className="app-main">
      <header className="page-head">
        <div>
          <h1 className="page-title">Your boards</h1>
          <p className="page-sub">
            {active && !active.is_main ? (
              <>
                In <strong>{active.name}</strong>. Each board tracks one repo, arranged by filters that already exist on
                GitHub.
              </>
            ) : (
              "Each board tracks one repo, arranged by filters that already exist on GitHub."
            )}
          </p>
        </div>
        <div className="head-actions">
          <div className="search-pill">
            <IconSearch />
            <input
              type="search"
              placeholder="Search boards…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search boards"
            />
          </div>
          <Link to="/new" className="btn primary">
            <IconPlus /> New board
          </Link>
        </div>
      </header>

      {ssoMessage && (
        <div className={`notice${ssoMessage.error ? " error" : ""}`} role="status">
          <span>{ssoMessage.text}</span>
          <button className="notice-dismiss" onClick={() => setSsoMessage(null)} aria-label="Dismiss">
            <IconX />
          </button>
        </div>
      )}

      {!dashboards ? (
        <div className="dashboard-grid">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton" style={{ height: 168 }} />
          ))}
        </div>
      ) : (
        <>
          {organizationBoards.length > 0 && (
            <BoardSection title="Organisation boards" hint={`Everyone in ${active?.name ?? "this organisation"} sees these.`}>
              {organizationBoards.map((d) => (
                <BoardTile key={d.id} board={d} onDelete={handleDelete} />
              ))}
            </BoardSection>
          )}

          <BoardSection title={organizationBoards.length || sharedBoards.length ? "Your boards" : null}>
            {ownBoards.map((d) => (
              <BoardTile key={d.id} board={d} onDelete={handleDelete} />
            ))}
            <Link to="/new" className="dashboard-tile new-dashboard-tile">
              <div>
                <span className="plus">
                  <IconPlus />
                </span>
                Create a board
              </div>
            </Link>
          </BoardSection>

          {sharedBoards.length > 0 && (
            <BoardSection title="Shared with you" hint="View only. Notes you keep on them are private to you.">
              {sharedBoards.map((d) => (
                <BoardTile key={d.id} board={d} onDelete={handleDelete} />
              ))}
            </BoardSection>
          )}
        </>
      )}

      <InsightsPanel />

      {dashboards && dashboards.length > 0 && visible.length === 0 && (
        <p className="state-msg">
          <IconBoard /> No boards match “{query}”.
        </p>
      )}
    </main>
  );
}

function BoardSection({ title, hint, children }: { title: string | null; hint?: string; children: React.ReactNode }) {
  return (
    <section className="board-section">
      {title && (
        <div className="board-section-head">
          <h2>{title}</h2>
          {hint && <p>{hint}</p>}
        </div>
      )}
      <div className="dashboard-grid">{children}</div>
    </section>
  );
}

function BoardTile({ board: d, onDelete }: { board: Dashboard; onDelete: (e: React.MouseEvent, id: string) => void }) {
  return (
    <Link
      to={`/dashboards/${d.id}`}
      className="dashboard-tile"
      style={{ ["--tile-accent" as string]: d.accent_color ?? undefined }}
    >
      <div className="tile-cover">
        {d.background_url && <div className="tile-cover-img" style={{ backgroundImage: `url(${d.background_url})` }} />}
        {d.access === "manage" && (
          <button className="tile-remove" onClick={(e) => onDelete(e, d.id)} title="Remove board" aria-label={`Remove ${d.name}`}>
            <IconX />
          </button>
        )}
        {d.access === "view" && d.kind === "personal" && <span className="tile-badge">View only</span>}
        {d.is_shared && <span className="tile-badge">Shared</span>}
      </div>
      <div className="tile-body">
        <h3>{d.name}</h3>
        <div className="tile-repo">
          <IconRepo />
          {d.repo_owner}/{d.repo_name}
        </div>
        {d.access === "view" && d.kind === "personal" && d.owner && <div className="tile-owner">by {d.owner}</div>}
      </div>
    </Link>
  );
}
