import type { IssueCard, Note } from "../types/api";
import { IssueCardView } from "./IssueCardView";
import { IconCheckCircle } from "./Icons";

function dateGroupLabel(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);

  const sameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

  if (sameDay(date, today)) return "Today";
  if (sameDay(date, yesterday)) return "Yesterday";
  return date.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
}

export const CLOSED_RANGES: { label: string; days: number }[] = [
  { label: "7 days", days: 7 },
  { label: "1 month", days: 30 },
  { label: "2 months", days: 60 },
  { label: "6 months", days: 182 },
  { label: "All time", days: 0 },
];

export function ClosedSection({
  issues,
  dashboardId,
  notesByIssue,
  days,
  loading,
  onChangeDays,
  onOpenIssue,
  canWrite = true,
  writeBlockReason = null,
}: {
  issues: IssueCard[];
  dashboardId: string;
  notesByIssue: Map<number, Note[]>;
  days: number;
  loading: boolean;
  onChangeDays: (days: number) => void;
  onOpenIssue: (issueNumber: number) => void;
  canWrite?: boolean;
  writeBlockReason?: string | null;
}) {
  const sorted = [...issues].sort(
    (a, b) => new Date(b.closed_at ?? b.updated_at).getTime() - new Date(a.closed_at ?? a.updated_at).getTime()
  );

  const groups = new Map<string, IssueCard[]>();
  for (const issue of sorted) {
    const label = dateGroupLabel(issue.closed_at ?? issue.updated_at);
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label)!.push(issue);
  }

  return (
    <section className="closed-section">
      <div className="section-head">
        <IconCheckCircle style={{ width: 18, height: 18, color: "currentColor" }} />
        <h2>Closed ({issues.length})</h2>
        <div className="range-picker" role="group" aria-label="Closed issues time range">
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
      {loading && <p className="empty-hint">Loading closed issues…</p>}
      {!loading && issues.length === 0 && (
        <p className="empty-hint">
          {days === 0 ? "Nothing closed yet." : `Nothing closed in the last ${days} days.`}
        </p>
      )}
      {[...groups.entries()].map(([label, group]) => (
        <div key={label} className="closed-date-group">
          <div className="date-head">
            <h3>
              {label} ({group.length})
            </h3>
          </div>
          <div className="closed-card-grid">
            {group.map((issue) => (
              <IssueCardView
                key={issue.number}
                issue={issue}
                dashboardId={dashboardId}
                columnId="closed"
                otherColumns={[]}
                notesByIssue={notesByIssue}
                onOpen={onOpenIssue}
                onMove={() => {}}
                onCloseIssue={() => {}}
                draggable={false}
                canWrite={canWrite}
                writeBlockReason={writeBlockReason}
              />
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
