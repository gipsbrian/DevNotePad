import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import type { DashboardDetail } from "../types/api";
import { useOrganizations } from "../org-context";
import { DashboardBoardPage } from "./DashboardBoardPage";
import { PullBoardPage } from "./PullBoardPage";

/** A board is an issue board or a PR board; which one decides the page. */
export function BoardRoute() {
  const { id } = useParams();
  const [board, setBoard] = useState<DashboardDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { reload: reloadOrganizations } = useOrganizations();

  useEffect(() => {
    let live = true;
    setBoard(null);
    setError(null);
    api
      .getDashboard(id!)
      .then((b) => {
        if (!live) return;
        setBoard(b);
        // Opening a board in another of your organisations moved you there.
        if (b.switched_organization) reloadOrganizations();
      })
      .catch((e) => live && setError((e as Error).message));
    return () => {
      live = false;
    };
  }, [id, reloadOrganizations]);

  if (error) return <main className="app-main"><p className="state-msg">Error: {error}</p></main>;
  if (!board) return <main className="app-main"><p className="state-msg">Loading board…</p></main>;
  const switchedTo = board.switched_organization ? board.organization_name : null;
  if (board.subject === "pulls") return <PullBoardPage key={board.id} initial={board} switchedTo={switchedTo} />;
  return <DashboardBoardPage key={board.id} switchedTo={switchedTo} />;
}
