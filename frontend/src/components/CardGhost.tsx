import type { IssueCard } from "../types/api";

/** What follows the pointer while a card is dragged. A plain copy rather
 * than the card itself, so it can travel outside its column's scroll box. */
export function CardGhost({ issue }: { issue: IssueCard }) {
  return (
    <article className="card card-ghost" aria-hidden="true">
      <div className="card-number">#{issue.number}</div>
      <h4 className="card-title">{issue.title}</h4>
      {issue.labels.length > 0 && (
        <div className="card-labels">
          {issue.labels.slice(0, 3).map((l) => (
            <span key={l.name} className="label-chip">
              <i style={{ background: `#${l.color}` }} />
              {l.name}
            </span>
          ))}
        </div>
      )}
    </article>
  );
}
