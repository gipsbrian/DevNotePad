# Security policy

DevNotePad stores GitHub tokens, so a flaw here can reach real
repositories. Please report privately rather than in a public issue.

## Reporting a vulnerability

Use GitHub's **Report a vulnerability** button on this repository's
Security tab, which opens a private advisory only the maintainers can see.
If that isn't available to you, open an issue saying only that you have a
security report and asking for a private channel. Never include the
details, a token, or a working exploit in a public issue.

Helpful to include: what an attacker can do, the steps to reproduce it,
and the version or commit you tested.

## What to expect

- An acknowledgement within a few days.
- A fix or an explanation of why the behaviour is intended.
- Credit in the release notes, unless you'd rather not be named.

## Supported versions

The latest release on the default branch. There are no long-term support
branches.

## Running an instance safely

- **Set `SECRET_KEY`** and keep it with the database backup. It encrypts
  stored tokens.
- **Scope GitHub tokens** to the repos you actually use, with
  `Issues: Read-only`, or `Read & write` only if you close issues or
  comment from the app.
- **Serve it over HTTPS** and set `SESSION_HTTPS_ONLY=true`, so session
  cookies aren't sent in the clear.
- **Close sign-up** with `ALLOW_REGISTRATION=false` once your team is in,
  if the instance is reachable from the internet.
- **Don't expose the development server.** Docker Compose runs Vite's dev
  server, which is for local work; put a production build behind your own
  server for a public deployment.

## Out of scope

There is no rate limiting on sign-in, registration or join requests yet,
and no password reset. These are known gaps rather than findings.
