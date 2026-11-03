import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { UsernamePrompt } from "./PullBoardPage";
import { api } from "../api/client";

vi.mock("../api/client", () => ({
  api: { detectUsername: vi.fn(), updateSettings: vi.fn() },
}));

describe("UsernamePrompt", () => {
  it("offers the token's account, saves it to settings and reloads the board", async () => {
    vi.mocked(api.detectUsername).mockResolvedValue({ login: "octocat" });
    vi.mocked(api.updateSettings).mockResolvedValue({} as never);
    const onSaved = vi.fn();
    const reloadSettings = vi.fn();
    render(
      <MemoryRouter>
        <Routes>
          <Route element={<Outlet context={{ reloadSettings }} />}>
            <Route index element={<UsernamePrompt onSaved={onSaved} />} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    const field = screen.getByLabelText(/Your GitHub username/);
    await waitFor(() => expect(field).toHaveValue("octocat"));
    fireEvent.change(field, { target: { value: "hubot" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(api.updateSettings).toHaveBeenCalledWith({ github_username: "hubot" });
    expect(reloadSettings).toHaveBeenCalled();
  });
});
