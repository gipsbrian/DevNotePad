import { createPortal } from "react-dom";
import type { SubIssue } from "../types/api";
import { useAnchoredPosition } from "../utils/useAnchoredPosition";

const WIDTH = 300;

/** Hover preview of an issue's sub-issues. */
export function SubIssuesPopover({
  anchor,
  subIssues,
  loading,
}: {
  anchor: HTMLElement | null;
  subIssues: SubIssue[] | null;
  loading: boolean;
}) {
  const pos = useAnchoredPosition(anchor, WIDTH);
  if (!anchor || !pos) return null;

  const done = subIssues?.filter((s) => s.state === "closed").length ?? 0;

  return createPortal(
    <div
      className="note-popover-anchor"
      style={{
        top: pos.top,
        left: pos.left,
        width: WIDTH,
        transform: pos.below ? undefined : "translateY(-100%)",
      }}
    >
      <div className="sub-panel" role="tooltip">
        <div className="sub-panel-head">
          Sub-issues
          {subIssues && (
            <span className="count-pill">
              {done}/{subIssues.length}
            </span>
          )}
        </div>
        {loading && <div className="sub-panel-empty">Loading…</div>}
        {!loading && subIssues?.length === 0 && <div className="sub-panel-empty">None found.</div>}
        <ul className="sub-list">
          {subIssues?.map((s) => (
            <li key={s.number} className={s.state === "closed" ? "done" : ""}>
              <span className={`sub-dot ${s.state}`} />
              <span className="sub-num">#{s.number}</span>
              <span className="sub-title">{s.title}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>,
    document.body
  );
}
