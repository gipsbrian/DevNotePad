import type { PullCard } from "../types/api";
import { CLOSED_RANGES, dateGroupLabel } from "./ClosedSection";
import { PullCardView, pullKey } from "./PullCardView";
import { IconCheckCircle } from "./Icons";

const noop = () => {};

/** A PR board's counterpart to the issue board's Closed section: the PRs
 * you wrote or reviewed that were merged or closed, grouped by day. */
export function PullClosedSection({
  pulls,
  days,
  loading,
  error,
  onChangeDays,
}: {
  pulls: PullCard[];
  days: number;
  loading: boolean;
  error: string | null;
  onChangeDays: (days: number) => void;
}) {
  const groups = new Map<string, PullCard[]>();
  for (const pull of pulls) {
    const label = dateGroupLabel(pull.closed_at ?? pull.updated_at);
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label)!.push(pull);
  }

  return (
    <section className="closed-section">
      <div className="section-head">
        <IconCheckCircle style={{ width: 18, height: 18, color: "currentColor" }} />
        <h2>Merged and closed ({pulls.length})</h2>
        <div className="range-picker" role="group" aria-label="Closed pull requests time range">
          {CLOSED_RANGES.map((r) => (
            <button
              key={r.days}
              className={`range-option${days === r.days ? " on" : ""}`}
              onClick={() => onChangeDays(r.days)}
              aria-pressed={days === r.days}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
      <p className="empty-hint">Pull requests you wrote or reviewed.</p>
      {loading && <p className="empty-hint">Loading closed pull requests…</p>}
      {error && <p className="empty-hint">{error}</p>}
      {!loading && !error && pulls.length === 0 && (
        <p className="empty-hint">{days === 0 ? "Nothing closed yet." : `Nothing closed in the last ${days} days.`}</p>
      )}
      {[...groups.entries()].map(([label, group]) => (
        <div key={label} className="closed-date-group">
          <div className="date-head">
            <h3>
              {label} ({group.length})
            </h3>
          </div>
          <div className="closed-card-grid">
            {group.map((pull) => (
              <PullCardView
                key={pullKey(pull)}
                pull={pull}
                columnId={0}
                onTrack={noop}
                onUntrack={noop}
                trackingColumns={[]}
                inTrackingColumn={false}
                canManage={false}
                draggable={false}
              />
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
