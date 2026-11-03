import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { DndContext } from "@dnd-kit/core";
import { PullCardView, pullKey } from "./PullCardView";
import type { Column, PullCard } from "../types/api";

const pull: PullCard = {
  repo: "acme/api",
  number: 12,
  title: "Add rate limits",
  html_url: "https://github.com/acme/api/pull/12",
  author: { login: "octocat", avatar_url: "https://avatars/octocat" },
  draft: true,
  labels: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
  comments_count: 0,
  age_days: 3,
  closed_at: null,
  merged: false,
};

const watching: Column = {
  id: 5,
  dashboard_id: "board",
  name: "Watching",
  position: 0,
  state: "open",
  labels: [],
  milestone: null,
  assignee: null,
  creator: null,
  issue_type: null,
  virtual: false,
  kind: "tracking",
  drag_compatible: false,
};

function renderCard(props: Partial<React.ComponentProps<typeof PullCardView>> = {}) {
  const onTrack = vi.fn();
  const onUntrack = vi.fn();
  render(
    <DndContext>
      <PullCardView
        pull={pull}
        columnId={-3}
        onTrack={onTrack}
        onUntrack={onUntrack}
        trackingColumns={[watching]}
        inTrackingColumn={false}
        canManage
        draggable
        {...props}
      />
    </DndContext>
  );
  return { onTrack, onUntrack };
}

describe("PullCardView", () => {
  it("shows the repo, number and draft state", () => {
    renderCard();
    expect(screen.getByText("api")).toBeInTheDocument();
    expect(screen.getByText(/#12/)).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
  });

  it("tracks from an automatic column as a copy, and moves between tracking columns", () => {
    const first = renderCard();
    fireEvent.click(screen.getByLabelText("Actions for acme/api#12"));
    fireEvent.click(screen.getByRole("menuitem", { name: "Watching" }));
    expect(first.onTrack).toHaveBeenCalledWith(pull, 5, undefined);
  });

  it("can stop tracking from a tracking column", () => {
    const { onUntrack, onTrack } = renderCard({ columnId: 9, inTrackingColumn: true });
    fireEvent.click(screen.getByLabelText("Actions for acme/api#12"));
    fireEvent.click(screen.getByRole("menuitem", { name: "Watching" }));
    expect(onTrack).toHaveBeenCalledWith(pull, 5, 9);
    fireEvent.click(screen.getByLabelText("Actions for acme/api#12"));
    fireEvent.click(screen.getByRole("menuitem", { name: "Stop tracking here" }));
    expect(onUntrack).toHaveBeenCalledWith(pull, 9);
  });

  it("has no menu for viewers with nowhere to track it", () => {
    renderCard({ canManage: false, trackingColumns: [] });
    expect(screen.queryByLabelText("Actions for acme/api#12")).toBeNull();
  });

  it("shows merged or closed instead of the age once a PR is closed", () => {
    renderCard({ pull: { ...pull, closed_at: "2026-01-05T00:00:00Z", merged: true } });
    expect(screen.getByText("Merged")).toBeInTheDocument();
    expect(screen.queryByText("3d")).toBeNull();
  });

  it("keys PRs by repo as well as number", () => {
    expect(pullKey(pull)).not.toBe(pullKey({ ...pull, repo: "acme/web" }));
    expect(pullKey(pull)).toBe(pullKey({ ...pull, repo: "Acme/API" }));
  });
});
