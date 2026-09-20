import type { IssueCard, IssueDetail } from "../types/api";

/** One issue per line, as `title : link`. */
export function formatIssuesForCopy(issues: IssueCard[]): string {
  return issues.map((i) => `${i.title} : ${i.html_url}`).join("\n");
}

/** One issue in full, for pasting into a note or a chat: a heading line,
 * the link, then the description as written. */
export function formatIssueForCopy(issue: IssueDetail): string {
  const heading = `#${issue.number} ${issue.title}`;
  const body = issue.body?.trim();
  return body
    ? `${heading}\n${issue.html_url}\n\n${body}`
    : `${heading}\n${issue.html_url}`;
}

/** Writes to the clipboard, falling back to a hidden textarea when the
 * async Clipboard API isn't available (non-secure context, or denied). */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to the legacy path
  }

  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(area);
    return ok;
  } catch {
    return false;
  }
}
