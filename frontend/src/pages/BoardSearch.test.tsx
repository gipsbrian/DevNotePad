import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { BoardSearch } from "./DashboardBoardPage";

afterEach(() => vi.useRealTimers());

describe("BoardSearch", () => {
  it("hands the board the query once typing pauses, not on every keystroke", () => {
    vi.useFakeTimers();
    const onQuery = vi.fn();
    render(<BoardSearch onQuery={onQuery} />);
    const box = screen.getByLabelText("Search issues on this board");
    onQuery.mockClear();

    for (const value of ["d", "de", "deb"]) {
      fireEvent.change(box, { target: { value } });
      act(() => vi.advanceTimersByTime(100));
    }
    expect(onQuery).not.toHaveBeenCalled();
    expect(box).toHaveValue("deb"); // the box itself keeps up

    act(() => vi.advanceTimersByTime(200));
    expect(onQuery).toHaveBeenCalledTimes(1);
    expect(onQuery).toHaveBeenCalledWith("deb");
  });

  it("clears at once", () => {
    vi.useFakeTimers();
    const onQuery = vi.fn();
    render(<BoardSearch onQuery={onQuery} />);
    const box = screen.getByLabelText("Search issues on this board");
    fireEvent.change(box, { target: { value: "x" } });
    act(() => vi.advanceTimersByTime(250));
    onQuery.mockClear();
    fireEvent.change(box, { target: { value: "" } });
    expect(onQuery).toHaveBeenCalledWith("");
  });
});
