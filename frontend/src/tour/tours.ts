import { driver, type DriveStep, type Driver } from "driver.js";
import "driver.js/dist/driver.css";

export type TourName = "home" | "board";

/** Steps point at elements by selector. One whose element isn't on the page
 * right now (no boards yet, no cards in a column) is left out rather than
 * shown pointing at nothing. */
const STEPS: Record<TourName, DriveStep[]> = {
  home: [
    {
      popover: {
        title: "Welcome to DevNotePad",
        description:
          "Boards built from the issues you already track. This takes about a minute, and the ? button in the left rail replays it whenever you like.",
      },
    },
    {
      element: '[data-tour="organization"]',
      popover: {
        title: "Your organisation",
        description:
          "Boards live in an organisation. Switch between the ones you belong to here, or create your own.",
        side: "right",
      },
    },
    {
      element: '[data-tour="notifications"]',
      popover: {
        title: "Notifications",
        description: "Join requests for organisations you run, and answers to the ones you’ve made, land here.",
        side: "right",
      },
    },
    {
      element: '[data-tour="settings"]',
      popover: {
        title: "Start here",
        description:
          "Add a GitHub token and your GitHub username. Boards read issues with that token, and your username adds “Assigned to me” and “Created by me” columns to every board.",
        side: "right",
      },
    },
    {
      element: ".page-head .btn.primary",
      popover: {
        title: "Make a board",
        description:
          "A board follows one repository. Paste owner/repo or a GitHub URL, then add columns for the issues you care about.",
        side: "bottom",
      },
    },
    {
      element: ".dashboard-grid",
      popover: {
        title: "Your boards",
        description: "Everything you create lives here. Other people on this instance can’t see your boards, notes or token.",
        side: "top",
      },
    },
    {
      element: ".insights",
      popover: {
        title: "Analytics",
        description:
          "Opened versus closed over the last six weeks, for you or your whole organisation. Set a default organization URL in settings to switch it on.",
        side: "top",
      },
    },
    {
      element: '[data-tour="theme"]',
      popover: { title: "Light or dark", description: "Follows your system until you pick one.", side: "right" },
    },
    {
      element: '[data-tour="help"]',
      popover: {
        title: "Lost? Come back here",
        description: "Replays the tour for whichever page you’re on. Open a board for the first time and it shows you around that too.",
        side: "right",
      },
    },
  ],
  board: [
    {
      element: ".board .column",
      popover: {
        title: "Columns are saved filters",
        description:
          "Each column is a query over the repo’s issues: labels, state, milestone, assignee, author or type. It always shows what GitHub says right now.",
        side: "right",
      },
    },
    {
      element: ".board .column .column-actions",
      popover: {
        title: "Column controls",
        description: "Refresh just this column, reorder it, or open ⋯ to edit its filters or copy its issues as a list.",
        side: "bottom",
      },
    },
    {
      element: ".board .column .card",
      popover: {
        title: "Open an issue",
        description:
          "Click a card for the full issue. Keep a private note on it, or comment on GitHub directly. Drag a card to another column to label or close it.",
        side: "right",
      },
    },
    {
      element: ".add-column-btn",
      popover: { title: "Add a column", description: "Built from labels and milestones that already exist on the repo.", side: "left" },
    },
    {
      element: ".board-topbar .search-pill",
      popover: { title: "Search the board", description: "Filters the cards already loaded, instantly.", side: "bottom" },
    },
    {
      element: '[data-tour="customize"]',
      popover: {
        title: "Make it yours",
        description: "Accent colour, wallpaper, the board’s name and repo, and whether it uses its own token.",
        side: "bottom",
      },
    },
    {
      element: ".sticky-column, .sticky-tab",
      popover: {
        title: "Sticky notes",
        description: "A scratch pad for the board itself, with checklists and dictation. It floats, so it’s always in reach.",
        side: "left",
      },
    },
    {
      element: ".closed-section",
      popover: { title: "Recently closed", description: "What got closed, grouped by day. Pick how far back to look.", side: "top" },
    },
  ],
};

let current: Driver | null = null;

/** Returns false when a tour is already running or nothing on the page
 * matches any step. `onFinished` runs whether the tour was completed or
 * dismissed. */
export function startTour(name: TourName, onFinished?: () => void): boolean {
  if (current) return false;
  const steps = STEPS[name].filter((s) => !s.element || document.querySelector(s.element as string));
  if (steps.length === 0) return false;

  const tour = driver({
    steps,
    popoverClass: "dnp-tour",
    showProgress: true,
    progressText: "{{current}} of {{total}}",
    nextBtnText: "Next",
    prevBtnText: "Back",
    doneBtnText: "Done",
    animate: true,
    smoothScroll: true,
    allowClose: true,
    overlayOpacity: 0.5,
    stagePadding: 6,
    stageRadius: 12,
    // Every way out -- Done, the close button, Escape, a click on the
    // backdrop -- comes through here. `onDestroyed` isn't dependable for
    // this: driver.js only calls it while it still holds an active step,
    // and dismissing with Escape ended a tour without it, leaving the tour
    // unrecorded and this module believing one was still running. Having
    // this hook means the tour has to be destroyed by hand.
    onDestroyStarted: () => {
      current = null;
      tour.destroy();
      onFinished?.();
    },
  });
  current = tour;
  tour.drive();
  return true;
}

/** Ends a running tour without recording it, e.g. when its page goes away. */
export function stopTour(): void {
  const tour = current;
  current = null;
  // The public destroy() bypasses onDestroyStarted, so nothing is marked seen.
  tour?.destroy();
}
