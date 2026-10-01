import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ColumnEditorModal } from "./ColumnEditorModal";
import type { Column, RepoMetadata } from "../types/api";

const metadata: RepoMetadata = {
  labels: [{ name: "bug", color: "ff0000", description: null }],
  milestones: [],
  assignees: [],
  issue_types: [],
  issue_types_source: "repo",
};

function column(overrides: Partial<Column> = {}): Column {
  return {
    id: 7,
    dashboard_id: "board",
    name: "Look out",
    position: 0,
    state: "open",
    labels: [],
    milestone: null,
    assignee: null,
    creator: null,
    issue_type: null,
    virtual: false,
    kind: "filter",
    drag_compatible: false,
    ...overrides,
  };
}

function open(col?: Column) {
  const onSubmit = vi.fn();
  render(<ColumnEditorModal metadata={metadata} settings={null} column={col} onCancel={() => {}} onSubmit={onSubmit} />);
  return onSubmit;
}

describe("ColumnEditorModal", () => {
  it("warns that a filter column with nothing picked shows every open issue, and offers tracking", () => {
    const onSubmit = open(column());
    expect(screen.getByText(/shows every open issue/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /make it a tracking column instead/i }));
    expect(screen.getByRole("radio", { name: /tracking/i })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText(/starts empty/i)).toBeInTheDocument();
    expect(screen.queryByText("State")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /save column/i }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ kind: "tracking", name: "Look out" }));
  });

  it("drops the hint once a filter is picked", () => {
    open(column({ labels: ["bug"] }));
    expect(screen.queryByText(/shows every open issue/i)).not.toBeInTheDocument();
  });

  it("says what switching a tracking column back to a filter does", () => {
    open(column({ kind: "tracking" }));
    fireEvent.click(screen.getByRole("radio", { name: /filter/i }));
    expect(screen.getByText(/tracked in it are let go/i)).toBeInTheDocument();
  });
});
