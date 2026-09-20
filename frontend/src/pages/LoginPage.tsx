import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { InvitationPreview, User } from "../types/api";
import { ShowcaseSlides } from "../components/ShowcaseSlides";
import { SSO_ERRORS, SsoButtons } from "../components/SsoButtons";

type Mode = "signin" | "register";

/** The token when this page was reached through an invitation link. The
 * sign-in page stands in front of every route while signed out, so it reads
 * the address itself rather than through the router. */
function invitationTokenFromPath(): string | null {
  const match = window.location.pathname.match(/^\/invite\/([^/]+)\/?$/);
  return match ? decodeURIComponent(match[1]) : null;
}

/** The slug when this page is an organisation's sign-in link, /o/<slug>. */
function orgSlugFromPath(): string | undefined {
  const match = window.location.pathname.match(/^\/o\/([^/]+)\/?$/);
  return match ? decodeURIComponent(match[1]) : undefined;
}

export function LoginPage({ onSignedIn }: { onSignedIn: (user: User) => void }) {
  const [invitationToken] = useState(invitationTokenFromPath);
  const [orgSlug] = useState(orgSlugFromPath);
  const [signingInTo, setSigningInTo] = useState<{ name: string; slug: string } | null>(null);
  const [invitation, setInvitation] = useState<InvitationPreview | null>(null);
  const [mode, setMode] = useState<Mode>(invitationToken ? "register" : "signin");
  // Offered when the instance takes new accounts -- or to anyone holding a
  // live invitation, which lets them in even when it doesn't.
  const [registrationOpen, setRegistrationOpen] = useState(false);
  const [identifier, setIdentifier] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  // A failed single sign-on comes back as ?sso_error=<code>.
  const [error, setError] = useState<string | null>(() => {
    const code = new URLSearchParams(window.location.search).get("sso_error");
    return code ? (SSO_ERRORS[code] ?? SSO_ERRORS.failed) : null;
  });

  const registering = mode === "register" && registrationOpen;

  useEffect(() => {
    // Shown once; a refresh shouldn't bring the error back.
    const url = new URL(window.location.href);
    if (url.searchParams.has("sso_error")) {
      url.searchParams.delete("sso_error");
      window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    }
  }, []);

  useEffect(() => {
    api
      .registrationStatus()
      .then((s) => setRegistrationOpen((open) => open || s.open))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!invitationToken) return;
    api
      .previewInvitation(invitationToken)
      .then((preview) => {
        setInvitation(preview);
        if (preview.status === "pending") setRegistrationOpen(true);
        else setMode("signin");
      })
      .catch(() => setMode("signin"));
  }, [invitationToken]);

  const liveInvitation = invitation?.status === "pending" ? invitationToken : null;

  useEffect(() => {
    document.title = `${registering ? "Create an account" : "Sign in"} · DevNotePad`;
  }, [registering]);

  function switchTo(next: Mode) {
    setMode(next);
    setError(null);
    setPassword("");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      onSignedIn(
        registering
          ? await api.register({ username, email, password, invitation_token: liveInvitation ?? undefined })
          : await api.login(identifier, password)
      );
    } catch (err) {
      setError((err as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <div className="login-page">
      <section className="login-panel">
        <div className="login-brand">
          <span className="login-mark">D</span>
          <span className="login-wordmark">DevNotePad</span>
        </div>

        {signingInTo && !invitation && (
          <div className="login-invite pending" role="status">
            Sign in to <strong>{signingInTo.name}</strong>.
          </div>
        )}

        {invitation && (
          <div className={`login-invite ${invitation.status}`} role="status">
            {invitation.status === "pending" ? (
              <>
                You’ve been invited to join <strong>{invitation.organization_name}</strong>
                {invitation.role === "admin" ? " as an admin" : ""}. Create an account, or sign in if you already have
                one, to accept.
              </>
            ) : (
              <>
                This invitation to <strong>{invitation.organization_name}</strong> is{" "}
                {invitation.status === "accepted" ? "already used" : invitation.status}. Ask an admin there for a new
                link.
              </>
            )}
          </div>
        )}

        <div className="login-lede">
          <h1>{registering ? "Make your own boards" : "Your issues, your board"}</h1>
          <p>
            {registering
              ? "Your account gets its own boards, notes and token. Nobody else on this instance can see them."
              : "Shape the issues you already track into the dashboard you actually work from."}
          </p>
        </div>

        <form className="login-card" onSubmit={handleSubmit} key={registering ? "register" : "signin"}>
          <SsoButtons orgSlug={orgSlug} onOrganization={setSigningInTo} />
          {registering ? (
            <>
              <div className="form-row">
                <label htmlFor="register-username">Username</label>
                <input
                  id="register-username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  autoFocus
                  required
                />
              </div>
              <div className="form-row">
                <label htmlFor="register-email">Email</label>
                <input
                  id="register-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                />
              </div>
              <div className="form-row">
                <label htmlFor="register-password">Password</label>
                <input
                  id="register-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                  minLength={8}
                  required
                />
                <p className="empty-hint" style={{ marginTop: 6 }}>
                  At least 8 characters.
                </p>
              </div>
            </>
          ) : (
            <>
              <div className="form-row">
                <label htmlFor="login-identifier">Username or email</label>
                <input
                  id="login-identifier"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  autoComplete="username"
                  autoFocus
                  required
                />
              </div>
              <div className="form-row">
                <label htmlFor="login-password">Password</label>
                <input
                  id="login-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
              </div>
            </>
          )}

          {error && (
            <p className="login-error" role="alert">
              {error}
            </p>
          )}

          <button className="btn primary login-submit" type="submit" disabled={submitting}>
            {registering
              ? submitting
                ? "Creating account…"
                : "Create account"
              : submitting
                ? "Signing in…"
                : "Sign in"}
          </button>
        </form>

        {registrationOpen && (
          <p className="login-switch">
            {registering ? "Already have an account?" : "New here?"}{" "}
            <button type="button" onClick={() => switchTo(registering ? "signin" : "register")}>
              {registering ? "Sign in" : "Create an account"}
            </button>
          </p>
        )}

        <p className="login-foot">Self-hosted. Your boards and tokens stay on this server.</p>
      </section>

      <ShowcaseSlides />
    </div>
  );
}
