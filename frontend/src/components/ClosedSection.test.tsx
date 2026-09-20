import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ClosedSection } from "./ClosedSection";
import type { IssueCard, Note } from "../types/api";

function makeIssue(number: number, closedAt: string, title: string): IssueCard {
  return {
    number,
    title,
    summary: "",
    state: "closed",
    html_url: `https://github.com/acme/widgets/issues/${number}`,
    labels: [],
    assignees: [],
    milestone: null,
    created_at: closedAt,
    updated_at: closedAt,
    closed_at: closedAt,
    comments_count: 0,
    age_days: 0,
    has_local_note: false,
    sub_issues_total: 0,
    sub_issues_completed: 0,
  };
}

describe("ClosedSection", () => {
  it("shows an empty state when nothing is closed", () => {
    render(
      <ClosedSection
        issues={[]}
        dashboardId="board-uuid"
        notesByIssue={new Map<number, Note[]>()}
        days={0}
        loading={false}
        onChangeDays={vi.fn()}
        onOpenIssue={vi.fn()}
      />
    );
    expect(screen.getByText(/Nothing closed yet/)).toBeInTheDocument();
  });

  it("groups closed issues under Today / Yesterday headers", () => {
    const today = new Date();
    const yesterday = new Date();
    yesterday.setDate(today.getDate() - 1);

    render(
      <ClosedSection
        issues={[
          makeIssue(1, today.toISOString(), "Closed today"),
          makeIssue(2, yesterday.toISOString(), "Closed yesterday"),
        ]}
        dashboardId="board-uuid"
        notesByIssue={new Map<number, Note[]>()}
        days={7}
        loading={false}
        onChangeDays={vi.fn()}
        onOpenIssue={vi.fn()}
      />
    );

    expect(screen.getByText(/Today \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Yesterday \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Closed today/)).toBeInTheDocument();
    expect(screen.getByText(/Closed yesterday/)).toBeInTheDocument();
  });

  it("shows the total closed count in the section heading", () => {
    const today = new Date().toISOString();
    render(
      <ClosedSection
        issues={[makeIssue(1, today, "A"), makeIssue(2, today, "B")]}
        dashboardId="board-uuid"
        notesByIssue={new Map<number, Note[]>()}
        days={7}
        loading={false}
        onChangeDays={vi.fn()}
        onOpenIssue={vi.fn()}
      />
    );
    expect(screen.getByText(/Closed \(2\)/)).toBeInTheDocument();
  });
});
