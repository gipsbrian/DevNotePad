import { describe, expect, it } from "vitest";
import { formatIssueForCopy, formatIssuesForCopy } from "./clipboard";
import type { IssueCard, IssueDetail } from "../types/api";

function makeIssue(number: number, title: string): IssueCard {
  return {
    number,
    title,
    summary: "",
    state: "open",
    html_url: `https://github.com/acme/widgets/issues/${number}`,
    labels: [],
    assignees: [],
    milestone: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    closed_at: null,
    comments_count: 0,
    age_days: 0,
    has_local_note: false,
    sub_issues_total: 0,
    sub_issues_completed: 0,
  };
}

describe("formatIssuesForCopy", () => {
  it("writes one 'title : link' line per issue", () => {
    const text = formatIssuesForCopy([makeIssue(7, "Crash on startup"), makeIssue(9, "Slow search")]);
    expect(text).toBe(
      "Crash on startup : https://github.com/acme/widgets/issues/7\n" +
        "Slow search : https://github.com/acme/widgets/issues/9"
    );
  });

  it("has no trailing newline, so pasting doesn't add a blank line", () => {
    expect(formatIssuesForCopy([makeIssue(1, "One")])).toBe(
      "One : https://github.com/acme/widgets/issues/1"
    );
  });

  it("returns an empty string for no issues", () => {
    expect(formatIssuesForCopy([])).toBe("");
  });

  it("keeps titles verbatim, including colons", () => {
    const text = formatIssuesForCopy([makeIssue(3, "Auth: token expiry")]);
    expect(text).toBe("Auth: token expiry : https://github.com/acme/widgets/issues/3");
  });
});

function makeDetail(body: string | null): IssueDetail {
  return {
    number: 42,
    title: "Crash on startup",
    body,
    state: "open",
    html_url: "https://github.com/acme/widgets/issues/42",
    labels: [],
    assignees: [],
    milestone: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    closed_at: null,
    comments: [],
    notes: [],
    sub_issues: [],
  };
}

describe("formatIssueForCopy", () => {
  it("leads with the number, title and link, then the body", () => {
    expect(formatIssueForCopy(makeDetail("Steps:\n1. Launch"))).toBe(
      "#42 Crash on startup\n" +
        "https://github.com/acme/widgets/issues/42\n\n" +
        "Steps:\n1. Launch"
    );
  });

  it("stops after the link when there is no description", () => {
    expect(formatIssueForCopy(makeDetail(null))).toBe(
      "#42 Crash on startup\nhttps://github.com/acme/widgets/issues/42"
    );
  });

  it("treats a whitespace-only description as none", () => {
    expect(formatIssueForCopy(makeDetail("   \n  "))).toBe(
      "#42 Crash on startup\nhttps://github.com/acme/widgets/issues/42"
    );
  });
});
