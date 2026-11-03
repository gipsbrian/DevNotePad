import type { Label } from "../types/api";

/** The little a ghost shows; an issue card or a PR card both fit. */
export type GhostCard = { number: number; title: string; labels: Label[]; repo?: string };

/** What follows the pointer while a card is dragged. A plain copy rather
 * than the card itself, so it can travel outside its column's scroll box. */
export function CardGhost({ issue }: { issue: GhostCard }) {
  return (
    <article className="card card-ghost" aria-hidden="true">
      <div className="card-number">
        {issue.repo ? `${issue.repo.split("/")[1]} ` : ""}#{issue.number}
      </div>
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
