import { describe, expect, it } from "vitest";
import type { IssueCard } from "../types/api";
import { stillReportedOpen } from "./justClosed";

function card(number: number, state: string): IssueCard {
  return {
    number,
    title: `Issue ${number}`,
    summary: "",
    state,
    html_url: "",
    labels: [],
    assignees: [],
    milestone: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    closed_at: null,
    comments_count: 0,
    age_days: 1,
    has_local_note: false,
    sub_issues_total: 0,
    sub_issues_completed: 0,
  };
}

describe("stillReportedOpen", () => {
  it("keeps hiding an issue GitHub has not caught up on yet", () => {
    const columns = { 1: [card(10, "open"), card(11, "open")] };
    expect([...stillReportedOpen(columns, new Set([10]))]).toEqual([10]);
  });

  it("drops the entry once the refetch stops listing it", () => {
    const columns = { 1: [card(11, "open")] };
    expect(stillReportedOpen(columns, new Set([10])).size).toBe(0);
  });

  it("drops the entry once the refetch reports it closed", () => {
    const columns = { 1: [card(10, "closed")] };
    expect(stillReportedOpen(columns, new Set([10])).size).toBe(0);
  });

  it("hides an issue that sits in more than one column", () => {
    const columns = { 1: [card(10, "open")], 2: [card(10, "open"), card(12, "open")] };
    expect([...stillReportedOpen(columns, new Set([10]))]).toEqual([10]);
  });

  it("is a no-op when nothing was just closed", () => {
    expect(stillReportedOpen({ 1: [card(10, "open")] }, new Set()).size).toBe(0);
  });
});
