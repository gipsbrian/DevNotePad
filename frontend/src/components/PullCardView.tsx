import { memo, useState } from "react";
import { useDraggable } from "@dnd-kit/core";
import { motion } from "framer-motion";
import type { Column, PullCard } from "../types/api";
import { IconChat, IconClock, IconDots } from "./Icons";

/** Numbers repeat across an org's repos; this doesn't. */
export const pullKey = (p: Pick<PullCard, "repo" | "number">) => `${p.repo.toLowerCase()}#${p.number}`;

type PullCardProps = {
  pull: PullCard;
  columnId: number;
  onTrack: (pull: PullCard, columnId: number, fromColumnId?: number) => void;
  onUntrack: (pull: PullCard, columnId: number) => void;
  /** Tracking columns it could be added to, besides its own. */
  trackingColumns: Column[];
  inTrackingColumn: boolean;
  canManage: boolean;
  draggable: boolean;
};

/** Draggable shell around a memoised body, as for issue cards: dnd-kit
 * re-renders every draggable during a drag, and the memo stops that here. */
export function PullCardView(props: PullCardProps) {
  const { pull, columnId, draggable } = props;
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `pull-${columnId}-${pullKey(pull)}`,
    data: { type: "pull", pull, issue: pull, sourceColumnId: columnId },
    disabled: !draggable,
  });
  return (
    <PullCardBody
      {...props}
      dragAttributes={draggable ? attributes : undefined}
      dragListeners={draggable ? listeners : undefined}
      setDragNode={setNodeRef}
      isDragging={isDragging}
    />
  );
}

type DragBits = {
  dragAttributes?: ReturnType<typeof useDraggable>["attributes"];
  dragListeners?: ReturnType<typeof useDraggable>["listeners"];
  setDragNode: (node: HTMLElement | null) => void;
  isDragging: boolean;
};

const PullCardBody = memo(function PullCardBody({
  pull,
  columnId,
  onTrack,
  onUntrack,
  trackingColumns,
  inTrackingColumn,
  canManage,
  dragAttributes,
  dragListeners,
  setDragNode,
  isDragging,
}: PullCardProps & DragBits) {
  const [menuOpen, setMenuOpen] = useState(false);
  const canUntrack = inTrackingColumn && canManage;
  const hasMenu = trackingColumns.length > 0 || canUntrack;
  const [owner, name] = pull.repo.split("/");

  return (
    <motion.article
      layout
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: isDragging ? 0.35 : 1, scale: 1 }}
      exit={{
        opacity: 0,
        scale: 0.96,
        height: 0,
        paddingTop: 0,
        paddingBottom: 0,
        marginBottom: -9,
        transition: { duration: 0.26, ease: [0.2, 0.8, 0.2, 1], opacity: { duration: 0.14 } },
      }}
      transition={{ type: "spring", stiffness: 420, damping: 34 }}
      layoutId={`pull-${columnId}-${pullKey(pull)}`}
      ref={setDragNode}
      {...dragAttributes}
      {...dragListeners}
      className={`card pull-card${pull.draft ? " draft" : ""}`}
      onClick={() => {
        if (!isDragging) window.open(pull.html_url, "_blank", "noopener,noreferrer");
      }}
      title="Open on GitHub"
    >
      {pull.labels.length > 0 && (
        <div className="card-stripes">
          {pull.labels.slice(0, 4).map((l) => (
            <span key={l.name} className="card-stripe" style={{ background: `#${l.color}` }} title={l.name} />
          ))}
        </div>
      )}

      {hasMenu && (
        <>
          <button
            className="card-menu-btn"
            onClick={(e) => {
              e.stopPropagation();
              setMenuOpen((v) => !v);
            }}
            title="Card actions"
            aria-label={`Actions for ${pull.repo}#${pull.number}`}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
          >
            <IconDots />
          </button>
          {menuOpen && (
            <div className="move-menu" role="menu" onClick={(e) => e.stopPropagation()}>
              {trackingColumns.length > 0 && (
                <div className="move-menu-label">{inTrackingColumn ? "Move into" : "Track in"}</div>
              )}
              {trackingColumns.map((c) => (
                <button
                  key={c.id}
                  role="menuitem"
                  onClick={() => {
                    onTrack(pull, c.id, inTrackingColumn ? columnId : undefined);
                    setMenuOpen(false);
                  }}
                >
                  {c.name}
                </button>
              ))}
              {canUntrack && (
                <button
                  role="menuitem"
                  onClick={() => {
                    onUntrack(pull, columnId);
                    setMenuOpen(false);
                  }}
                >
                  Stop tracking here
                </button>
              )}
            </div>
          )}
        </>
      )}

      <div className="card-number" title={pull.repo}>
        <span className="pull-repo">{name}</span> #{pull.number}
        {pull.draft && <span className="pull-draft">Draft</span>}
      </div>
      <h4 className="card-title">{pull.title}</h4>

      {pull.labels.length > 0 && (
        <div className="card-labels">
          {pull.labels.slice(0, 3).map((l) => (
            <span key={l.name} className="label-chip" title={l.description ?? l.name}>
              <i style={{ background: `#${l.color}` }} />
              {l.name}
            </span>
          ))}
          {pull.labels.length > 3 && <span className="label-chip">+{pull.labels.length - 3}</span>}
        </div>
      )}

      <div className="card-foot">
        <div className="card-meta">
          <span
            className={`age-bubble${pull.age_days >= 14 ? " long-open" : ""}`}
            title={`Open for ${pull.age_days} day${pull.age_days === 1 ? "" : "s"}`}
          >
            <IconClock />
            {pull.age_days}d
          </span>
          <span className="meta-item" title={`Updated ${new Date(pull.updated_at).toLocaleString()} in ${owner}/${name}`}>
            updated {new Date(pull.updated_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
          </span>
        </div>
        <div className="card-badges">
          {pull.comments_count > 0 && (
            <span className="badge-icon chat" title={`${pull.comments_count} comments`}>
              <IconChat />
              {pull.comments_count}
            </span>
          )}
          {pull.author && (
            <img className="avatar" src={pull.author.avatar_url} alt={pull.author.login} title={`by ${pull.author.login}`} />
          )}
        </div>
      </div>
    </motion.article>
  );
});
