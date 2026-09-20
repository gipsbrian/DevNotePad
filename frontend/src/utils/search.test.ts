import { describe, expect, it } from "vitest";
import { matchesSearch } from "./search";
import type { IssueCard } from "../types/api";

function makeIssue(overrides: Partial<IssueCard> = {}): IssueCard {
  return {
    number: 42,
    title: "Fix login redirect loop",
    summary: "Users get stuck bouncing between pages",
    state: "open",
    html_url: "https://github.com/acme/widgets/issues/42",
    labels: [{ name: "bug", color: "ff0000", description: null }],
    assignees: [],
    milestone: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    closed_at: null,
    comments_count: 0,
    age_days: 1,
    has_local_note: false,
    sub_issues_total: 0,
    sub_issues_completed: 0,
    ...overrides,
  };
}

describe("matchesSearch", () => {
  it("matches on empty query", () => {
    expect(matchesSearch(makeIssue(), "")).toBe(true);
    expect(matchesSearch(makeIssue(), "   ")).toBe(true);
  });

  it("matches issue number with #", () => {
    expect(matchesSearch(makeIssue({ number: 42 }), "#42")).toBe(true);
    expect(matchesSearch(makeIssue({ number: 42 }), "#43")).toBe(false);
  });

  it("matches title case-insensitively", () => {
    expect(matchesSearch(makeIssue(), "LOGIN")).toBe(true);
    expect(matchesSearch(makeIssue(), "nonexistent")).toBe(false);
  });

  it("matches summary text", () => {
    expect(matchesSearch(makeIssue(), "bouncing")).toBe(true);
  });

  it("matches label names", () => {
    expect(matchesSearch(makeIssue(), "bug")).toBe(true);
    expect(matchesSearch(makeIssue({ labels: [] }), "bug")).toBe(false);
  });
});
