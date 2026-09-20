import { useCallback, useEffect } from "react";
import { useAuth } from "../auth-context";
import { startTour, stopTour, type TourName } from "./tours";

/** Replays a tour on request, and records it as seen when it ends. */
export function useStartTour() {
  const { markTourSeen } = useAuth();
  return useCallback((name: TourName) => startTour(name, () => markTourSeen(name)), [markTourSeen]);
}

/** Starts a tour by itself the first time this account reaches the page,
 * once `ready` says the things it points at have rendered. */
export function useFirstVisitTour(name: TourName, ready: boolean) {
  const { user } = useAuth();
  const start = useStartTour();
  const seen = user.tours_seen.includes(name);

  useEffect(() => {
    if (!ready || seen) return;
    // A beat after render, so the page settles (and cards finish animating
    // in) before anything gets highlighted.
    const timer = setTimeout(() => start(name), 700);
    return () => clearTimeout(timer);
  }, [ready, seen, name, start]);

  // Leaving the page mid-tour mustn't leave its overlay behind.
  useEffect(() => stopTour, []);
}
