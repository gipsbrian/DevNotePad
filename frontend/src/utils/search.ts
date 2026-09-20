import type { IssueCard } from "../types/api";

/** Client-side search over already-loaded cards — title, number, summary,
 * and label names. No extra GitHub calls; searches only what's already on
 * the board/closed section. */
export function matchesSearch(issue: IssueCard, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  if (`#${issue.number}`.includes(q)) return true;
  if (issue.title.toLowerCase().includes(q)) return true;
  if (issue.summary.toLowerCase().includes(q)) return true;
  return issue.labels.some((l) => l.name.toLowerCase().includes(q));
}
