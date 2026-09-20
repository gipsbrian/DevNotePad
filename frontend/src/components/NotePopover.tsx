import { createPortal } from "react-dom";
import { useAnchoredPosition } from "../utils/useAnchoredPosition";

const WIDTH = 250;

/** Floating sticky-note preview of an issue's latest local note.
 *
 * Rendered in a portal with fixed positioning rather than inside the card:
 * the column body scrolls (`overflow-y: auto`), which clips any absolutely
 * positioned child that reaches outside it — so an in-card popover was
 * invisible for every card in a column.
 *
 * Positioning lives on the outer element and the paper's tilt/animation on
 * the inner one, so the two never fight over `transform`.
 */
export function NotePopover({
  anchor,
  text,
  moreCount = 0,
}: {
  anchor: HTMLElement | null;
  text: string;
  moreCount?: number;
}) {
  const pos = useAnchoredPosition(anchor, WIDTH);

  if (!anchor || !pos) return null;

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
      <div className={`sticky-note${pos.below ? " below" : ""}`} role="tooltip">
        <span className="sticky-tape" aria-hidden />
        <p className="sticky-note-preview">{text}</p>
        {moreCount > 0 && (
          <span className="sticky-more">
            +{moreCount} more note{moreCount === 1 ? "" : "s"}
          </span>
        )}
      </div>
    </div>,
    document.body
  );
}
