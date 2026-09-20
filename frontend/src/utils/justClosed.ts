import type { IssueCard } from "../types/api";

/** Which of the issues we just closed a refetch still reports as open.
 *
 * Closing writes to GitHub, but its issue list can lag a moment behind
 * that write, so the refetch fired right after a close may hand the card
 * back. Those numbers stay hidden; the rest are dropped, because the
 * server has caught up and its own data is now right -- including if the
 * issue is later reopened outside the app. */
export function stillReportedOpen(
  issuesByColumn: Record<number, IssueCard[]>,
  justClosed: Set<number>
): Set<number> {
  const open = new Set<number>();
  for (const list of Object.values(issuesByColumn))
    for (const issue of list) if (issue.state === "open") open.add(issue.number);
  return new Set([...justClosed].filter((n) => open.has(n)));
}
