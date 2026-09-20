import { useLayoutEffect, useState } from "react";

export interface SidePosition {
  top: number;
  left: number;
  /** The panel sits to the anchor's left, because there was no room right. */
  flipped: boolean;
}

/** Places a fixed-position panel beside an anchor, level with its top:
 * to the right where there's room, otherwise to the left, and nudged up
 * when it would run off the bottom of the window.
 *
 * Fixed positioning (in a portal) is what lets it escape the column body's
 * `overflow-y: auto`, which clips anything drawn outside it. */
export function useSidePosition(
  anchor: HTMLElement | null,
  width: number,
  height: number,
  { gap = 12, margin = 8 } = {}
): SidePosition | null {
  const [pos, setPos] = useState<SidePosition | null>(null);

  useLayoutEffect(() => {
    if (!anchor) return;

    function place() {
      const rect = anchor!.getBoundingClientRect();
      const fits = rect.right + gap + width + margin <= window.innerWidth;
      const left = fits ? rect.right + gap : Math.max(margin, rect.left - gap - width);
      const top = Math.min(Math.max(margin, rect.top), Math.max(margin, window.innerHeight - height - margin));
      setPos({ top, left, flipped: !fits });
    }

    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [anchor, width, height, gap, margin]);

  return pos;
}
