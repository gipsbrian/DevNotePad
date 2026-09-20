import { useEffect, useState } from "react";
import { api } from "../api/client";

type SsoProvider = { id: string; label: string };

/** Official marks, which each provider's brand rules ask sign-in buttons to
 * carry. Apple's follows the text colour so it holds up in dark mode. */
const MARKS: Record<string, React.ReactNode> = {
  google: (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path fill="#4285F4" d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5a5.6 5.6 0 0 1-2.4 3.6v3h3.9c2.3-2.1 3.5-5.2 3.5-8.8Z" />
      <path fill="#34A853" d="M12 24c3.2 0 6-1.1 8-2.9l-3.9-3c-1.1.7-2.5 1.2-4.1 1.2-3.1 0-5.8-2.1-6.7-5H1.3v3.1A12 12 0 0 0 12 24Z" />
      <path fill="#FBBC05" d="M5.3 14.3a7.2 7.2 0 0 1 0-4.6V6.6h-4a12 12 0 0 0 0 10.8l4-3.1Z" />
      <path fill="#EA4335" d="M12 4.8c1.8 0 3.3.6 4.6 1.8l3.4-3.4A12 12 0 0 0 1.3 6.6l4 3.1c.9-2.8 3.6-4.9 6.7-4.9Z" />
    </svg>
  ),
  microsoft: (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path fill="#F25022" d="M1 1h10.5v10.5H1z" />
      <path fill="#7FBA00" d="M12.5 1H23v10.5H12.5z" />
      <path fill="#00A4EF" d="M1 12.5h10.5V23H1z" />
      <path fill="#FFB900" d="M12.5 12.5H23V23H12.5z" />
    </svg>
  ),
  apple: (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path
        fill="currentColor"
        d="M16.4 12.7c0-2.5 2-3.7 2.1-3.7-1.2-1.7-3-1.9-3.6-2-1.5-.2-3 .9-3.8.9-.8 0-2-.9-3.3-.9A4.9 4.9 0 0 0 3.7 9.5c-1.8 3.1-.5 7.6 1.3 10.1.8 1.2 1.8 2.6 3.1 2.5 1.3 0 1.7-.8 3.3-.8 1.5 0 1.9.8 3.2.8 1.4 0 2.2-1.2 3-2.4a10 10 0 0 0 1.4-2.8 4.3 4.3 0 0 1-2.6-4.2ZM14 5.3c.7-.9 1.2-2 1-3.2-1 0-2.2.7-2.9 1.5-.6.7-1.2 1.9-1 3.1 1.1 0 2.2-.6 2.9-1.4Z"
      />
    </svg>
  ),
};

/** Buttons for whichever identity providers this instance has configured --
 * none at all until an operator sets one up. */
export function SsoButtons({
  orgSlug,
  onOrganization,
}: {
  /** Set on an organisation's sign-in link: offers that organisation's providers. */
  orgSlug?: string;
  onOrganization?: (organization: { name: string; slug: string } | null) => void;
}) {
  const [providers, setProviders] = useState<SsoProvider[]>([]);

  useEffect(() => {
    api
      .ssoProviders(orgSlug)
      .then((found) => {
        setProviders(found.providers);
        onOrganization?.(found.organization);
      })
      .catch(() => setProviders([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgSlug]);

  if (providers.length === 0) return null;

  return (
    <div className="sso">
      {providers.map((p) => (
        <a key={p.id} className={`btn sso-btn sso-${p.id}`} href={api.ssoLoginUrl(p.id, orgSlug)}>
          <span className="sso-mark">{MARKS[p.id]}</span>
          Continue with {p.label}
        </a>
      ))}
      <div className="sso-divider" role="separator">
        <span>or</span>
      </div>
    </div>
  );
}

/** What the backend's `sso_error` codes mean to a person. The page only ever
 * shows these fixed messages, never text taken from the address bar. */
export const SSO_ERRORS: Record<string, string> = {
  denied: "Sign-in was cancelled.",
  expired: "That sign-in expired or was started in another browser. Please try again.",
  provider: "The sign-in provider couldn’t confirm who you are. Please try again.",
  unverified:
    "An account already uses that email, and the provider didn’t verify it’s yours. Sign in with your password instead.",
  no_email: "That account didn’t share an email address, and DevNotePad needs one.",
  closed: "This instance isn’t taking new accounts for that email.",
  unavailable: "That sign-in option isn’t available.",
  failed: "Something went wrong signing you in. Please try again.",
};

/** Codes for things worth telling someone after a successful sign-in. */
export const SSO_NOTICES: Record<string, string> = {
  join_requested:
    "You’re signed in. You weren’t a member of that organisation yet, so its admins have been asked to let you in; you’ll get a notification when they decide.",
};
