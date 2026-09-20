import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Insights, Member } from "../types/api";
import { IconCheckCircle, IconIssue, IconRefresh, IconTimer, IconUser } from "./Icons";

/* Charts are hand-drawn SVG rather than a charting library: two simple
 * forms, full control over the marks, and no extra bundle weight.
 * Series colours live in CSS (`.viz`) so light/dark swap in one place;
 * they're slots 1 and 2 of a palette validated for colour-vision
 * deficiency and contrast against both surfaces. */

function fmtWeek(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

type Hover = { x: number; y: number; label: string; rows: string[] } | null;

function WeeklyChart({ data }: { data: Insights["weekly"] }) {
  const [hover, setHover] = useState<Hover>(null);

  const W = 560;
  const H = 190;
  const PAD = { top: 14, right: 8, bottom: 26, left: 34 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const max = Math.max(1, ...data.flatMap((d) => [d.opened, d.closed]));
  const ticks = [0, Math.round(max / 2), max];
  const groupW = plotW / Math.max(1, data.length);
  const barW = Math.min(16, (groupW - 10) / 2);

  const y = (v: number) => PAD.top + plotH - (v / max) * plotH;

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Issues opened and closed per week">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} className="grid" />
            <text x={PAD.left - 7} y={y(t) + 3.5} className="axis" textAnchor="end">
              {t}
            </text>
          </g>
        ))}

        {data.map((d, i) => {
          const gx = PAD.left + i * groupW;
          const pairs: [number, string, string][] = [
            [d.opened, "series-1", "Opened"],
            [d.closed, "series-2", "Closed"],
          ];
          return (
            <g key={d.week_start}>
              {pairs.map(([v, cls], j) => {
                const bx = gx + groupW / 2 - barW - 1 + j * (barW + 2);
                const bh = Math.max(v > 0 ? 2 : 0, PAD.top + plotH - y(v));
                return (
                  <rect
                    key={cls}
                    x={bx}
                    y={PAD.top + plotH - bh}
                    width={barW}
                    height={bh}
                    rx={3}
                    className={`bar ${cls}`}
                    onMouseEnter={(e) =>
                      setHover({
                        x: e.currentTarget.getBoundingClientRect().left,
                        y: e.currentTarget.getBoundingClientRect().top,
                        label: `Week of ${fmtWeek(d.week_start)}`,
                        rows: [`Opened ${d.opened}`, `Closed ${d.closed}`],
                      })
                    }
                    onMouseLeave={() => setHover(null)}
                  />
                );
              })}
              <text x={gx + groupW / 2} y={H - 8} className="axis" textAnchor="middle">
                {fmtWeek(d.week_start)}
              </text>
            </g>
          );
        })}
      </svg>

      {hover && (
        <div className="chart-tip" style={{ left: hover.x, top: hover.y }}>
          <strong>{hover.label}</strong>
          {hover.rows.map((r) => (
            <span key={r}>{r}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function TopReposChart({ data }: { data: Insights["top_repos"] }) {
  if (data.length === 0) return <p className="empty-hint">No open issues to place.</p>;
  const max = Math.max(...data.map((d) => d.count), 1);

  return (
    <ul className="hbars">
      {data.map((d) => (
        <li key={d.repo}>
          <span className="hbar-label" title={d.repo}>
            {d.repo}
          </span>
          <span className="hbar-track">
            <span className="hbar-fill" style={{ width: `${Math.max(2, (d.count / max) * 100)}%` }} />
          </span>
          <span className="hbar-value">{d.count}</span>
        </li>
      ))}
    </ul>
  );
}

export function InsightsPanel() {
  const [scope, setScope] = useState<"me" | "org">("me");
  const [username, setUsername] = useState<string | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [data, setData] = useState<Insights | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listMembers().then(setMembers).catch(() => setMembers([]));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.getInsights(scope, username ?? undefined));
    } catch (e) {
      setError((e as Error).message);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [scope, username]);

  useEffect(() => {
    load();
  }, [load]);

  const totals = data?.totals ?? {};
  const net = (totals.opened_in_window ?? 0) - (totals.closed_in_window ?? 0);

  return (
    <section className="insights viz">
      <div className="insights-head">
        <h2>Analytics</h2>
        <div className="insights-controls">
          <div className="range-picker light">
            <button className={`range-option${scope === "me" ? " on" : ""}`} onClick={() => setScope("me")}>
              <IconUser /> Me
            </button>
            <button className={`range-option${scope === "org" ? " on" : ""}`} onClick={() => setScope("org")}>
              Organisation
            </button>
          </div>
          {scope === "me" && members.length > 0 && (
            <select
              className="member-select"
              value={username ?? data?.username ?? ""}
              onChange={(e) => setUsername(e.target.value)}
              aria-label="Team member"
            >
              {members.map((m) => (
                <option key={m.login} value={m.login}>
                  {m.login}
                </option>
              ))}
            </select>
          )}
          <button className="icon-btn" onClick={load} title="Refresh analytics" aria-label="Refresh analytics">
            <IconRefresh />
          </button>
        </div>
      </div>

      {error && <p className="insights-error">{error}</p>}
      {loading && !data && <div className="skeleton" style={{ height: 260 }} />}

      {data && (
        <>
          <p className="insights-sub">
            {data.scope === "me" ? (
              <>
                <strong>{data.username}</strong> across <strong>{data.org}</strong> · last {data.window_days} days
              </>
            ) : (
              <>
                All of <strong>{data.org}</strong> · last {data.window_days} days
              </>
            )}
          </p>

          <div className="stat-row">
            <div className="stat-tile">
              <span className="stat-icon">
                <IconIssue />
              </span>
              <div>
                <div className="stat-value">{totals.open ?? 0}</div>
                <div className="stat-label">{data.scope === "me" ? "Open, assigned" : "Open issues"}</div>
              </div>
            </div>
            <div className="stat-tile">
              <span className="stat-icon muted">
                <IconCheckCircle />
              </span>
              <div>
                <div className="stat-value">{totals.closed_in_window ?? 0}</div>
                <div className="stat-label">Closed in window</div>
              </div>
            </div>
            <div className="stat-tile">
              <span className="stat-icon muted">
                <IconTimer />
              </span>
              <div>
                <div className="stat-value">{totals.opened_in_window ?? 0}</div>
                <div className="stat-label">Opened in window</div>
              </div>
            </div>
            <div className="stat-tile">
              <span className={`stat-icon ${net > 0 ? "" : "muted"}`}>
                <IconIssue />
              </span>
              <div>
                <div className="stat-value">
                  {net > 0 ? "+" : ""}
                  {net}
                </div>
                <div className="stat-label">{net > 0 ? "Backlog grew" : net < 0 ? "Backlog shrank" : "Backlog flat"}</div>
              </div>
            </div>
          </div>

          <div className="chart-grid">
            <div className="panel chart-card">
              <div className="chart-head">
                <h3>Opened vs closed, by week</h3>
                <div className="legend">
                  <span>
                    <i className="swatch series-1" /> Opened
                  </span>
                  <span>
                    <i className="swatch series-2" /> Closed
                  </span>
                </div>
              </div>
              <WeeklyChart data={data.weekly} />
            </div>

            <div className="panel chart-card">
              <div className="chart-head">
                <h3>Where the open work sits</h3>
              </div>
              <TopReposChart data={data.top_repos} />
            </div>
          </div>
        </>
      )}
    </section>
  );
}
