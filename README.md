# DevNotePad

[![version](https://img.shields.io/badge/version-0.2.0-blue)](CHANGELOG.md)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A Trello-style board for organizing your GitHub issues into dashboards you
define — without going back to GitHub to re-filter. Columns filter on
labels, state, milestone, or assignee that already exist on the repo; the
app never creates new GitHub taxonomy on your behalf.

See [USAGE.md](USAGE.md) for how to actually use the app once it's
running, [CONTRIBUTING.md](CONTRIBUTING.md) if you're changing it, and
[CHANGELOG.md](CHANGELOG.md) for release history.

## Stack

- **Backend**: FastAPI + SQLite (`backend/`)
- **Frontend**: React + TypeScript, Vite (`frontend/`)
- Accounts: each has its own boards, notes, settings and GitHub token.

## Setup

The fastest path uses the `Makefile`:

```
make setup      # interactively writes .env — token and password input
                # hidden, never touches shell history
make install    # backend (Python 3.12 via uv, no sudo) + frontend deps
make dev        # runs both dev servers, prints the URLs
```

Run `make help` for the full list of tasks (tests, Docker, cleanup).

`make setup` also generates `SECRET_KEY`, which encrypts the GitHub
tokens the app stores — **the backend refuses to start without it** — and
asks for the account you'll sign in with (`ADMIN_*`). That account is
created on first startup, and only ever into an empty user table, so
editing those values later won't change an existing password.

### Accounts and organisations

The sign-in page offers **Create an account** (username, email and
password). Anyone who can reach that page can sign up, so to close it set
`ALLOW_REGISTRATION=false` in `.env` and restart the backend (with Docker,
`make docker-up`). Existing accounts keep working either way.

Every account belongs to the **main** organisation, and anyone can create
further organisations from the organisation menu at the top of the left
rail, becoming that organisation's admin. A new account joins main only,
never as an admin. The first account (the `ADMIN_*` one) is main's admin,
and main's admins run the instance.

Boards live in an organisation. A personal board is private to the account
that made it until shared, view-only, with chosen members or the whole
organisation; organisation boards are managed by its admins and seen by
every member. Tokens never cross between people: a board is read with its
own token, its owner's, or (for organisation boards) the organisation's,
and every change made on GitHub goes out with the acting person's own
token. `GIT_TOKEN` / `GIT_ORG_URL` from `.env` are only ever lent to the
first account. The full model is in
[docs/plans/organisations-and-sso.md](docs/plans/organisations-and-sso.md).

Admins bring people in with single-use invitation links or by approving
join requests from the organisation's link, `/o/<slug>`. The main
organisation's admins run the instance and get an **Instance admin** page
listing every account and organisation.

### Single sign-on

Google, Microsoft and Apple sign-in are configured per organisation, by its
admins, under **Organisation settings > Single sign-on**. The main
organisation's providers appear on the normal sign-in page; another
organisation's appear on its link, `/o/<slug>`. Someone signing in through an
organisation's link who isn't a member lands in main with a join request
filed, unless their provider-verified email is on that provider's auto-join
domains. New accounts are only ever created while `ALLOW_REGISTRATION` is on.

1. Set `PUBLIC_URL` in `.env` to where people reach the app (e.g.
   `https://devnotepad.example.com`) and restart the backend. Callback URLs
   are built from it, never from incoming requests.
2. Register these with each provider -- one per provider type, shared by
   every organisation:
   - Google (OAuth client, Web application): redirect URI
     `<PUBLIC_URL>/api/auth/sso/google/callback`, JavaScript origin
     `<PUBLIC_URL>`
   - Microsoft (Entra app registration, Web): redirect URI
     `<PUBLIC_URL>/api/auth/sso/microsoft/callback`
   - Apple (Services ID, Sign in with Apple): domain `<PUBLIC_URL host>`,
     return URL `<PUBLIC_URL>/api/auth/sso/apple/callback`. Needs an Apple
     Developer Program membership, a Team ID, and a Sign in with Apple key
     (`.p8`) with its Key ID.
3. Enter the client details in the organisation's settings, or from the
   command line:

   ```
   printf '%s' "$SECRET" | docker exec -i devnotepad-backend python -m app.cli \
       sso set --org main --type google --client-id <id> --client-secret-file - --enable
   docker exec devnotepad-backend python -m app.cli sso list --org main
   ```

   `python -m app.cli --help` also covers `sso import` (a JSON list on
   stdin), `sso remove`, `org list`, `org create`, and `admin promote` /
   `admin demote` for instance admins. Secrets are only read from files or
   stdin and are never printed.

While the main organisation has no providers saved, `GOOGLE_CLIENT_ID` /
`GOOGLE_CLIENT_SECRET`, `MICROSOFT_CLIENT_ID` / `MICROSOFT_CLIENT_SECRET` /
`MICROSOFT_TENANT` and `APPLE_CLIENT_ID` / `APPLE_TEAM_ID` / `APPLE_KEY_ID` /
`APPLE_PRIVATE_KEY` in `.env` are used for it instead. Once any provider is
saved in the app, `.env` is ignored for SSO.

### Docker Compose (alternative)

```
make setup       # or: cp .env.example .env and fill it in
make docker-up   # docker compose up --build
```

**This is a development setup.** The frontend container runs Vite's dev
server, which serves unminified code and the project's source files, and
its live-reload client tries to reach `localhost` on the visitor's own
machine -- browsers ask permission for that. It's fine on your own
machine; for anything others use, serve a production build (below).
Backend: http://localhost:8010 · Frontend: http://localhost:5180
(override with `BACKEND_PORT` / `FRONTEND_PORT` in `.env` or on the
command line).

Backend source is baked into its image, so backend changes need
`make docker-up` again to rebuild. The frontend is bind-mounted and
hot-reloads, but its `node_modules` lives in a named volume that is only
seeded once — **after adding or removing an npm dependency, run
`make docker-reset`**, which drops just that volume and rebuilds. It
leaves `devnotepad-data` (your boards and local notes) untouched.

Docker needs your user to be in the `docker` group:
`sudo usermod -aG docker $USER && newgrp docker`.

### Serving a production build

`make build-frontend` writes static files to `frontend/dist/`. Serve that
directory with any web server, and proxy `/api/` to the backend
container, which is production-ready as it stands. In `.env`, set
`VITE_API_BASE_URL=` (empty) so the app calls `/api` on its own address,
and set `PUBLIC_URL` to the address people use.

Rebuild after each frontend change; nothing here watches for you. There
is no packaged production image yet.

### Behind a reverse proxy

Both ports bind to `127.0.0.1`, so a proxy on the same host is the only
way in. Point it at the frontend port, give it a `/api` location onto the
backend port, and set these in `.env`:

```
VITE_API_BASE_URL=       # empty: the SPA calls /api on its own origin
SESSION_HTTPS_ONLY=true  # if the proxy serves HTTPS
```

Leave `VITE_API_BASE_URL` unset for a plain local run — the browser then
talks to the backend directly on `BACKEND_PORT`, which is what the
localhost URLs above assume. A Vite dev server also rejects a proxied
`Host` header unless the hostname is in `VITE_ALLOWED_HOSTS` (a
comma-separated list in `.env`). A production build has no such check.

### Manual, without Make or Docker

Backend (needs Python 3.12 specifically — SQLModel/pydantic aren't yet
compatible with 3.14's lazy-annotation change; grab 3.12 via
[uv](https://docs.astral.sh/uv/) if your system Python is newer:
`uv python install 3.12 && uv venv --python 3.12 backend/.venv`):
```
cd backend
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8010
```

Frontend:
```
cd frontend
npm install
VITE_API_BASE_URL=http://localhost:8010 npm run dev -- --port 5180
```

## Tests

```
make test
```
or individually: `make test-backend` / `make test-frontend`.

## What it does

**Boards**
- One repo per board; as many boards as you like.
- Columns are saved filters over labels, state, milestone, assignee,
  author and issue type that already exist on the repo.
- Cards carry labels, assignees, age, comment and sub-issue counts.
- Drag or use a card's menu to move an issue between compatible columns.
- Close an issue, comment on it, or read its comments without leaving the
  board.
- Private notes per issue, pushed to GitHub as a comment only when you ask.
- A sticky-note pad per board, searchable, with checklists and dictation.
- Closed issues grouped by day, and search across loaded cards.
- Per-board accent colour and wallpaper; light and dark themes.
- Organisation-wide issue analytics: opened against closed, by week and by
  repo.

**Accounts and teams**
- Sign in with a username or email and password, or through Google,
  Microsoft or Apple.
- Organisations: invite people, approve join requests, share boards
  view-only, and run organisation-wide boards.
- Every account's boards, notes and GitHub token are private to it, and
  tokens are encrypted at rest.
- An instance-admin view of every account and organisation.

Not built: a roadmap view over GitHub's Issue Dependencies API, email
delivery (invitations are links you share), and password reset.

## Contributing, bugs and security

- **Bugs:** open a [bug report](../../issues/new?template=bug_report.yml).
  Pull requests fixing an open bug are welcome from anyone -- say so on
  the issue first, add a test that fails without the fix, and link it with
  `Fixes #123`. See [CONTRIBUTING.md](CONTRIBUTING.md).
- **Security:** report privately, never in an issue. See
  [SECURITY.md](SECURITY.md).
- **Conduct:** [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## For Claude Code sessions

`.claude/skills/run/SKILL.md` in this repo documents exactly how to
launch and drive the app (ports, the Python-version gotcha, safe test
data, and how to avoid live-mutating a real repo during verification) —
load it before improvising a run/test setup from scratch.

## License

[MIT](LICENSE).
