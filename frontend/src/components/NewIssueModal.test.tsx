import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NewIssueModal } from "./NewIssueModal";
import type { RepoMetadata } from "../types/api";

const metadata: RepoMetadata = {
  labels: [
    { name: "bug", color: "ff0000", description: null },
    { name: "docs", color: "00ff00", description: null },
  ],
  milestones: [
    { number: 3, title: "v1", state: "open" },
    { number: 1, title: "v0", state: "closed" },
  ],
  assignees: [{ login: "octocat", avatar_url: "" }],
  issue_types: [{ name: "Bug", color: null, description: null }],
  issue_types_source: "org",
};

function renderModal(onSubmit = vi.fn().mockResolvedValue(undefined)) {
  render(<NewIssueModal repo="acme/widgets" metadata={metadata} me="me-gh" onCancel={vi.fn()} onSubmit={onSubmit} />);
  return onSubmit;
}

describe("NewIssueModal", () => {
  it("sends the title and whatever was picked", async () => {
    const onSubmit = renderModal();
    expect(screen.getByText("acme/widgets")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: " Login fails " } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Steps" } });
    fireEvent.click(screen.getByRole("button", { name: "bug" }));
    fireEvent.click(screen.getByRole("button", { name: "me-gh (me)" }));
    fireEvent.change(screen.getByLabelText("Milestone"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "Bug" } });
    fireEvent.click(screen.getByRole("button", { name: "Create issue" }));

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({
        title: "Login fails",
        body: "Steps",
        labels: ["bug"],
        assignees: ["me-gh"],
        milestone: 3,
        issue_type: "Bug",
      })
    );
  });

  it("offers only open milestones and needs a title", () => {
    renderModal();
    expect(screen.queryByRole("option", { name: "v0" })).toBeNull();
    expect(screen.getByRole("button", { name: "Create issue" })).toBeDisabled();
  });

  it("shows GitHub's refusal and stays open", async () => {
    renderModal(vi.fn().mockRejectedValue(new Error("Validation Failed")));
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Create issue" }));
    expect(await screen.findByText("Validation Failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create issue" })).not.toBeDisabled();
  });
});
