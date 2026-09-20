import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TokenBadge } from "./TokenBadge";
import type { TokenInfo } from "../types/api";

function makeInfo(overrides: Partial<TokenInfo> = {}): TokenInfo {
  return {
    token_type: "classic-pat",
    type_label: "Classic personal access token",
    classic_scopes: null,
    inferred_can_read: null,
    inferred_can_write: null,
    error: null,
    warning: "Use a scoped token.",
    ...overrides,
  };
}

describe("TokenBadge", () => {
  it("flags a broken token and keeps the detail available on hover", () => {
    render(<TokenBadge info={makeInfo({ error: "Token is invalid or revoked." })} />);
    const badge = screen.getByText(/token problem/i);
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAttribute("title", expect.stringContaining("Token is invalid or revoked."));
  });

  it("labels a write-capable token distinctly from read-only", () => {
    const { rerender } = render(
      <TokenBadge info={makeInfo({ inferred_can_read: true, inferred_can_write: true })} />
    );
    expect(screen.getByText(/read \+ write/i)).toBeInTheDocument();

    rerender(<TokenBadge info={makeInfo({ inferred_can_read: true, inferred_can_write: false })} />);
    expect(screen.getByText(/read-only/i)).toBeInTheDocument();
  });

  it("never presents inferred permissions as verified", () => {
    render(<TokenBadge info={makeInfo({ inferred_can_read: true, inferred_can_write: false })} />);
    expect(screen.getByText(/read-only/i)).toHaveAttribute("title", expect.stringContaining("not verified by GitHub"));
  });

  it("shows classic scopes verbatim when no permission was inferred", () => {
    render(<TokenBadge info={makeInfo({ classic_scopes: ["repo", "read:org"] })} />);
    expect(screen.getByText(/repo, read:org/)).toBeInTheDocument();
  });
});
