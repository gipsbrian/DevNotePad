import { beforeEach, describe, expect, it } from "vitest";
import { applyTheme, getStoredTheme, nextTheme } from "./theme";

describe("theme", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("defaults to system when nothing stored", () => {
    expect(getStoredTheme()).toBe("system");
  });

  it("round-trips a stored choice", () => {
    applyTheme("dark");
    expect(getStoredTheme()).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("system choice removes the explicit attribute so prefers-color-scheme applies", () => {
    applyTheme("dark");
    applyTheme("system");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("cycles system -> light -> dark -> system", () => {
    expect(nextTheme("system")).toBe("light");
    expect(nextTheme("light")).toBe("dark");
    expect(nextTheme("dark")).toBe("system");
  });
});
