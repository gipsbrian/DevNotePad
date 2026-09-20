import { describe, expect, it } from "vitest";
import { taskProgress, toggleTask } from "./markdownTasks";

const NOTE = `Shipping list

- [ ] write the thing
- [x] test the thing
- [ ] ship the thing`;

describe("toggleTask", () => {
  it("ticks an unchecked task by render order", () => {
    expect(toggleTask(NOTE, 0)).toContain("- [x] write the thing");
  });

  it("unticks a checked task", () => {
    expect(toggleTask(NOTE, 1)).toContain("- [ ] test the thing");
  });

  it("leaves every other line alone", () => {
    const out = toggleTask(NOTE, 2).split("\n");
    expect(out[0]).toBe("Shipping list");
    expect(out[2]).toBe("- [ ] write the thing");
    expect(out[3]).toBe("- [x] test the thing");
    expect(out[4]).toBe("- [x] ship the thing");
  });

  it("handles indented and numbered task lines", () => {
    const nested = "- [ ] top\n  - [ ] nested\n1. [ ] numbered";
    expect(toggleTask(nested, 1)).toContain("  - [x] nested");
    expect(toggleTask(nested, 2)).toContain("1. [x] numbered");
  });

  it("ignores an out-of-range index", () => {
    expect(toggleTask(NOTE, 99)).toBe(NOTE);
  });

  it("doesn't treat a bracket in prose as a task", () => {
    const prose = "see [ ] nothing here";
    expect(toggleTask(prose, 0)).toBe(prose);
  });
});

describe("taskProgress", () => {
  it("counts done and total", () => {
    expect(taskProgress(NOTE)).toEqual({ done: 1, total: 3 });
  });

  it("reports nothing for a note with no tasks", () => {
    expect(taskProgress("just words")).toEqual({ done: 0, total: 0 });
  });
});
