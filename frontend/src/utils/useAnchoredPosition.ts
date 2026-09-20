import { useLayoutEffect, useState } from "react";

export interface AnchoredPosition {
  top: number;
  left: number;
  below: boolean;
}

/** Places a fixed-position floating panel against an anchor element,
 * preferring above it and flipping below when there isn't room, clamped to
 * the viewport. Fixed positioning (in a portal) is what lets these panels
 * escape the column body's `overflow-y: auto`, which clips anything drawn
 * outside it. */
export function useAnchoredPosition(
  anchor: HTMLElement | null,
  width: number,
  { gap = 12, margin = 8, minSpaceAbove = 210 } = {}
): AnchoredPosition | null {
  const [pos, setPos] = useState<AnchoredPosition | null>(null);

  useLayoutEffect(() => {
    if (!anchor) return;

    function place() {
      const rect = anchor!.getBoundingClientRect();
      const left = Math.min(
        Math.max(margin, rect.left + 10),
        Math.max(margin, window.innerWidth - width - margin)
      );
      const below = rect.top < minSpaceAbove;
      setPos({ top: below ? rect.bottom + gap : rect.top - gap, left, below });
    }

    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [anchor, width, gap, margin, minSpaceAbove]);

  return pos;
}
