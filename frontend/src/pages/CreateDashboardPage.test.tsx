import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { CreateDashboardPage } from "./CreateDashboardPage";
import { OrgContext } from "../org-context";
import { api } from "../api/client";
import type { Settings } from "../types/api";

vi.mock("../api/client", () => ({
  api: {
    getSettings: vi.fn(),
    detectUsername: vi.fn(),
    updateSettings: vi.fn(),
    createDashboard: vi.fn(),
  },
}));

const settings = (overrides: Partial<Settings> = {}): Settings => ({
  github_username: null,
  default_org_url: "https://github.com/acme",
  show_my_columns: true,
  has_default_token: true,
  default_token_source: "settings",
  ...overrides,
});

const reloadSettings = vi.fn();

function renderPage() {
  render(
    <OrgContext.Provider value={{ organizations: [], active: null, reload: async () => {}, switchTo: async () => {} }}>
      <MemoryRouter initialEntries={["/new"]}>
        <Routes>
          <Route element={<Outlet context={{ reloadSettings }} />}>
            <Route path="new" element={<CreateDashboardPage />} />
            <Route path="dashboards/:id" element={<p>board page</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </OrgContext.Provider>
  );
}

describe("CreateDashboardPage, PR boards", () => {
  beforeEach(() => {
    vi.mocked(api.detectUsername).mockResolvedValue({ login: "octocat" });
    vi.mocked(api.updateSettings).mockResolvedValue(settings({ github_username: "octocat" }));
    vi.mocked(api.createDashboard).mockResolvedValue({ id: "new-board" } as never);
    reloadSettings.mockReset();
  });

  it("asks for a missing username, prefilled from the token, and saves it before creating", async () => {
    vi.mocked(api.getSettings).mockResolvedValue(settings());
    renderPage();
    fireEvent.click(await screen.findByText("Pull requests"));

    const field = await screen.findByLabelText("Your GitHub username");
    await waitFor(() => expect(field).toHaveValue("octocat"));
    expect(screen.getByPlaceholderText("my-org or https://github.com/my-org")).toHaveValue("acme");

    fireEvent.change(screen.getByPlaceholderText("e.g. Backend priorities"), { target: { value: "PRs" } });
    fireEvent.click(screen.getByRole("button", { name: /create board/i }));

    await screen.findByText("board page");
    expect(api.updateSettings).toHaveBeenCalledWith({ github_username: "octocat" });
    expect(vi.mocked(api.updateSettings).mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(api.createDashboard).mock.invocationCallOrder[0]
    );
    expect(api.createDashboard).toHaveBeenCalledWith(expect.objectContaining({ subject: "pulls", org_ref: "acme" }));
    expect(reloadSettings).toHaveBeenCalled();
  });

  it("doesn't ask when the username is already set, or for an issue board", async () => {
    vi.mocked(api.getSettings).mockResolvedValue(settings({ github_username: "octocat" }));
    renderPage();
    fireEvent.click(await screen.findByText("Pull requests"));
    await screen.findByPlaceholderText("my-org or https://github.com/my-org");
    expect(screen.queryByLabelText("Your GitHub username")).toBeNull();

    fireEvent.click(screen.getByText("Issues"));
    expect(screen.queryByLabelText("Your GitHub username")).toBeNull();
  });
});
