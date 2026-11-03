import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DndContext } from "@dnd-kit/core";
import { IssueCardView } from "./IssueCardView";
import type { Column, IssueCard, Note } from "../types/api";

function makeIssue(overrides: Partial<IssueCard> = {}): IssueCard {
  return {
    number: 7,
    title: "Crash on startup",
    summary: "App crashes immediately",
    state: "open",
    html_url: "https://github.com/acme/widgets/issues/7",
    labels: [{ name: "bug", color: "ff0000", description: null }],
    assignees: [],
    milestone: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    closed_at: null,
    comments_count: 2,
    age_days: 10,
    has_local_note: true,
    sub_issues_total: 0,
    sub_issues_completed: 0,
    ...overrides,
  };
}

function makeColumn(overrides: Partial<Column> = {}): Column {
  return {
    id: 1,
    dashboard_id: "board-uuid",
    name: "Bugs",
    position: 0,
    state: "open",
    labels: ["bug"],
    milestone: null,
    assignee: null,
    creator: null,
    issue_type: null,
    virtual: false,
    kind: "filter",
    drag_compatible: true,
    ...overrides,
  };
}

function renderCard(props: Partial<React.ComponentProps<typeof IssueCardView>> = {}) {
  const onOpen = vi.fn();
  const onMove = vi.fn();
  const onCloseIssue = vi.fn();
  const notesByIssue = new Map<number, Note[]>([
    [7, [{ id: 1, dashboard_id: "board-uuid", issue_number: 7, body: "remember to test edge cases", created_at: "", updated_at: "", synced: false, github_comment_id: null }]],
  ]);

  render(
    <DndContext>
      <IssueCardView
        issue={makeIssue()}
        dashboardId="board-uuid"
        columnId={1}
        otherColumns={[makeColumn({ id: 2, name: "Done", drag_compatible: false })]}
        notesByIssue={notesByIssue}
        onOpen={onOpen}
        onMove={onMove}
        onCloseIssue={onCloseIssue}
        {...props}
      />
    </DndContext>
  );
  return { onOpen, onMove, onCloseIssue };
}

describe("IssueCardView", () => {
  it("renders title, age bubble, and badges", () => {
    renderCard();
    expect(screen.getByText(/Crash on startup/)).toBeInTheDocument();
    expect(screen.getByTitle(/open for 10 days/i)).toHaveTextContent("10d");
    expect(screen.getByTitle(/local sticky note/i)).toBeInTheDocument();
    // No tooltip on this one: hovering it opens the comments themselves,
    // so the count is only announced to screen readers.
    expect(screen.getByRole("button", { name: /2 GitHub comments/i })).toHaveTextContent("2");
  });

  it("opens the issue when the card body is clicked", () => {
    const { onOpen } = renderCard();
    fireEvent.click(screen.getByText(/Crash on startup/));
    expect(onOpen).toHaveBeenCalledWith(7);
  });

  it("shows the note popover on tap without needing hover (mobile fallback)", () => {
    renderCard();
    expect(screen.queryByText(/remember to test edge cases/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByTitle(/tap to preview/));
    expect(screen.getByText(/remember to test edge cases/)).toBeInTheDocument();
  });

  it("disables moving into a column that isn't drag-compatible", () => {
    const { onMove } = renderCard();
    fireEvent.click(screen.getByTitle("Card actions"));
    const doneOption = screen.getByRole("menuitem", { name: "Done" });
    expect(doneOption).toBeDisabled();
    fireEvent.click(doneOption);
    expect(onMove).not.toHaveBeenCalled();
  });

  it("closes an issue from the card menu, but only after confirming", () => {
    const { onCloseIssue } = renderCard();
    fireEvent.click(screen.getByTitle("Card actions"));

    // First click arms the action rather than firing it — this closes a
    // real issue on GitHub and the menu is easy to mis-click.
    fireEvent.click(screen.getByRole("menuitem", { name: /close issue/i }));
    expect(onCloseIssue).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("menuitem", { name: /really close #7/i }));
    expect(onCloseIssue).toHaveBeenCalledWith(7);
  });

  it("offers no close action for an already-closed issue", () => {
    renderCard({ issue: makeIssue({ state: "closed" }) });
    fireEvent.click(screen.getByTitle("Card actions"));
    expect(screen.queryByRole("menuitem", { name: /close issue/i })).not.toBeInTheDocument();
  });

  it("lists tracking columns under Track in, never under Move to", () => {
    const onTrack = vi.fn();
    const watching = makeColumn({ id: 5, name: "Watching", kind: "tracking", drag_compatible: false });
    renderCard({
      otherColumns: [makeColumn({ id: 2, name: "Done" }), watching],
      trackingColumns: [watching],
      canManage: true,
      onTrack,
    });
    fireEvent.click(screen.getByTitle("Card actions"));
    // "Done" is the relabel move; "Watching" appears once, as a track target.
    expect(screen.getAllByRole("menuitem", { name: "Watching" })).toHaveLength(1);
    fireEvent.click(screen.getByRole("menuitem", { name: "Watching" }));
    expect(onTrack).toHaveBeenCalledWith(7, 5, undefined);
  });

  it("moves between tracking columns and can stop tracking", () => {
    const onTrack = vi.fn();
    const onUntrack = vi.fn();
    const later = makeColumn({ id: 6, name: "Later", kind: "tracking" });
    renderCard({ columnId: 5, inTrackingColumn: true, trackingColumns: [later], canManage: true, onTrack, onUntrack });
    fireEvent.click(screen.getByTitle("Card actions"));
    expect(screen.getByText("Move into")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("menuitem", { name: "Later" }));
    expect(onTrack).toHaveBeenCalledWith(7, 6, 5);

    fireEvent.click(screen.getByTitle("Card actions"));
    fireEvent.click(screen.getByRole("menuitem", { name: /stop tracking here/i }));
    expect(onUntrack).toHaveBeenCalledWith(7, 5);
  });

  it("offers no tracking actions to someone who can't manage the board", () => {
    renderCard({ columnId: 5, inTrackingColumn: true, trackingColumns: [], canManage: false });
    fireEvent.click(screen.getByTitle("Card actions"));
    expect(screen.queryByRole("menuitem", { name: /stop tracking/i })).not.toBeInTheDocument();
  });

  it("marks long-open issues distinctly", () => {
    renderCard({ issue: makeIssue({ age_days: 45 }) });
    const bubble = screen.getByTitle(/open for 45 days/i);
    expect(bubble.className).toContain("long-open");
  });
});
