// Which card each open issue was opened from, so its pane can grow out of
// that card and shrink back into it when closed.

const origins = new Map<number, HTMLElement>();

const EASE = "cubic-bezier(0.2, 0.8, 0.2, 1)";
const CARD_RADIUS = 12; // --r-md
const PANE_RADIUS = 22; // --r-xl

export function rememberCardOrigin(issueNumber: number, el: HTMLElement | null) {
  if (el) origins.set(issueNumber, el);
}

/** Where the card is now, or null when it's gone or scrolled off screen
 * (a refetch can replace it, and a pane opened from the URL has none). */
function originRect(issueNumber: number): DOMRect | null {
  const el = origins.get(issueNumber);
  if (!el?.isConnected) return null;
  const r = el.getBoundingClientRect();
  if (r.width === 0 || r.bottom < 0 || r.top > window.innerHeight) return null;
  return r;
}

export function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

/** The pane scaled evenly down onto the card and clipped to its height, so
 * the content is revealed rather than squashed. */
function atCard(from: DOMRect, to: DOMRect): Keyframe {
  const s = from.width / to.width;
  const hidden = Math.max(0, to.height - from.height / s);
  return {
    transform: `translate(${from.left - to.left}px, ${from.top - to.top}px) scale(${s})`,
    clipPath: `inset(0px 0px ${hidden}px 0px round ${CARD_RADIUS / s}px)`,
    opacity: 0.6,
  };
}

const AT_REST: Keyframe = {
  transform: "none",
  clipPath: `inset(0px 0px 0px 0px round ${PANE_RADIUS}px)`,
  opacity: 1,
};

/** Without a card to come from, rise gently into place. */
const RISEN: Keyframe = { transform: "translateY(16px) scale(0.98)", clipPath: AT_REST.clipPath, opacity: 0 };

export function growFromCard(pane: HTMLElement, issueNumber: number) {
  if (prefersReducedMotion() || !pane.animate) return;
  // Measured at rest: a running animation would skew the pane's rect (and
  // StrictMode mounts twice in development).
  pane.getAnimations().forEach((a) => a.cancel());
  const from = originRect(issueNumber);
  const to = pane.getBoundingClientRect();
  pane.style.transformOrigin = "top left";
  pane.animate([from ? atCard(from, to) : RISEN, AT_REST], {
    duration: from ? 420 : 240,
    easing: EASE,
  });
}

export function shrinkIntoCard(pane: HTMLElement, issueNumber: number): Promise<unknown> {
  if (prefersReducedMotion() || !pane.animate) return Promise.resolve();
  // Measured at rest: a running animation would skew the pane's rect (and
  // StrictMode mounts twice in development).
  pane.getAnimations().forEach((a) => a.cancel());
  const from = originRect(issueNumber);
  const to = pane.getBoundingClientRect();
  pane.style.transformOrigin = "top left";
  const end = from ? { ...atCard(from, to), opacity: 0 } : RISEN;
  return pane
    .animate([AT_REST, end], { duration: from ? 340 : 180, easing: EASE, fill: "forwards" })
    .finished.catch(() => undefined);
}

/** Fades the dimmed, blurred backdrop without fading what sits on it. */
export function clearBackdrop(el: HTMLElement, duration: number): Promise<unknown> {
  if (prefersReducedMotion() || !el.animate) return Promise.resolve();
  return el
    .animate([{ backgroundColor: "rgba(12, 15, 20, 0)", backdropFilter: "blur(0px)" }], {
      duration,
      easing: "ease",
      fill: "forwards",
    })
    .finished.catch(() => undefined);
}
