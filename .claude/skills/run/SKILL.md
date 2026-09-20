---
name: run
description: Launch and drive DevNotePad (FastAPI backend + React/Vite frontend) for manual testing or a screenshot-verified change.
---

# Running DevNotePad

Two processes: a FastAPI backend (SQLite-backed) and a Vite/React
frontend. Use the `Makefile` — it already encodes the port choices and
env vars below; don't reinvent them.

## Prerequisites

- A repo-root `.env` — run `make setup` if it doesn't exist yet (prompts
  interactively, secret input hidden, never touches shell history). It
  needs, beyond `GIT_TOKEN` / `GIT_ORG_URL`:
  - `SECRET_KEY` — encrypts stored GitHub tokens. **The backend raises on
    startup without it**, so a hand-written `.env` that omits it looks
    like a broken app. `make setup` generates one.
  - `ADMIN_USERNAME` / `ADMIN_EMAIL` / `ADMIN_PASSWORD` — the account to
    sign in with, created on first startup into an empty user table.
    Without all three the app boots and logs a warning, but nobody can
    get in.
  - `ALLOW_REGISTRATION` defaults to on (`false` closes sign-up). Every
    account's boards/notes/settings are private to it, boards belong to an
    organisation (the active one lives in the session), and `GIT_TOKEN`
    only ever applies to the first account -- so to verify as a second
    account, register one and give it its own token. The test suite pins
    registration off regardless of `.env`.
- **Every endpoint but `/api/health` and `/api/auth/*` needs a session.**
  Driving the UI means signing in first; hitting the API with curl means
  posting to `/api/auth/login` and keeping the cookie
  (`curl -c jar -b jar`).
- Backend needs **Python 3.12**, not whatever `python3` resolves to on
  the host. SQLModel/pydantic aren't compatible with Python 3.14's
  lazy-annotation change (`PydanticUserError: Field 'id' requires a type
  annotation` if you try). `make install-backend` handles this via `uv`
  (`uv python install 3.12 && uv venv --python 3.12 backend/.venv`) —
  no sudo, no system package needed.

## Launch

```bash
make install   # first time only (or after dependency changes)
make dev       # backend :8010 + frontend :5180, prints both URLs
```

`make dev` runs both under one `trap ... wait`, so Ctrl+C stops both. To
run them separately (e.g. to watch one's logs): `make dev-backend` /
`make dev-frontend` in separate terminals.

**Ports default to 8010/5180, not 8000/5173** — a sibling project on this
machine (`Nestedboard-app`) already listens on 8000. Check before
assuming a clash: `ss -ltnp | grep 8000`. Override if needed:
`make dev BACKEND_PORT=8000 FRONTEND_PORT=5173`.

Confirm the backend is actually up before driving the frontend:
```bash
timeout 20 bash -c 'until curl -sf http://localhost:8010/api/health >/dev/null; do sleep 1; done'
```

To stop a stray background instance, kill by **port**, not by a broad
`pkill -f "uvicorn app.main:app"` — that pattern also matches
`Nestedboard-app`'s own backend if it's running:
```bash
lsof -ti:8010 -sTCP:LISTEN | xargs -r kill
```

## Drive it

No `chromium-cli` or Claude-in-Chrome extension has been available in
this environment so far — the working fallback is a scratch Playwright
script (per `run` skill's `examples/playwright.md`):

```bash
mkdir -p /tmp/pw-check && cd /tmp/pw-check
npm init -y -q && npm install -q playwright
npx playwright install chromium   # NOT --with-deps, that needs sudo
```

Then a small Node script with `chromium.launch({ args: ['--no-sandbox'] })`,
`page.goto('http://localhost:5180')`, etc. One representative path: open
the dashboard list -> create a dashboard against a real small repo (see
"Test data" below) -> add a column -> wait for `.column .card` -> screenshot.

**Gotcha**: `waitForSelector('.card')` can resolve against the *Closed*
section's cards, which are intentionally non-draggable
(`aria-disabled="true"` from dnd-kit) and fail Playwright's strict
actionability check on `.click()`. Scope the selector to `.column .card`
to get an open-column (draggable) card instead.

## Test data

Never invent a repo — list real ones the configured token can see and
pick a small public one:
```bash
source .env
curl -s -H "Authorization: Bearer $GIT_TOKEN" -H "Accept: application/vnd.github+json" \
  "https://api.github.com/orgs/<org-from-GIT_ORG_URL>/repos?per_page=100&sort=updated" \
  | python3 -c "import json,sys; [print(r['name'], r['open_issues_count'], r['private']) for r in json.load(sys.stdin)]"
```
Pick a small public repo for verification passes: a huge issue list makes
GitHub refuse to page through it, and the board then fails to load.
`pallets/markupsafe` works well.

**Never click "Close issue" or "Push to GitHub" against a real repo**
during a verification pass unless the user explicitly asks for a live
write test — those mutate the actual GitHub issue. Read-only exploration
(create dashboard, add columns, open cards, search, toggle theme) is safe
and suffices to prove the app works.

## Typechecking and tests

`npx tsc --noEmit` **checks nothing here** and exits 0 whatever the state
of the code — the root `tsconfig.json` is `"files": []` with project
references. Use `npx tsc -b` (what `npm run build` runs).

The backend suite needs no local venv:
```bash
docker run --rm -v "$PWD/backend:/w" -w /w python:3.12-slim \
  bash -c "pip install -q -r requirements-dev.txt && python -m pytest -q"
```
The frontend suite needs **Node 22** — on 20, undici calls
`webidl.util.markAsUncloneable`, which doesn't exist, and vitest dies
before collecting a single test:
```bash
docker run --rm -v "$PWD/frontend:/app" \
  -v devnotepad-frontend-node-modules:/app/node_modules \
  -w /app node:22-slim npx vitest run
```

## Full-stack (Docker) alternative

`make docker-up` (`docker compose up --build`) runs the containerized
version on 8010/5180, both bound to `127.0.0.1`. Requires the invoking
user to be in the `docker` group or `sudo docker compose ...`.

If `VITE_API_BASE_URL=` (empty) is set in `.env`, the SPA calls `/api` on
its own origin and only works through a reverse proxy that serves both —
hitting the frontend port directly then fails every API call. When an
instance is deployed that way (`PUBLIC_URL` names its address), drive it
through that address rather than the container port.
