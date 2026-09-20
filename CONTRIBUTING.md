# Contributing

Thanks for looking at DevNotePad. It started as a personal tool, so the
process below is intentionally lightweight.

## Design background

A few constraints aren't obvious from the code and shouldn't be undone
without discussion:

- **The app never creates GitHub taxonomy.** Columns filter on labels,
  milestones, issue types and assignees that already exist on the repo.
  Nothing here calls GitHub's create-label or create-milestone endpoints.
- **Nothing is written to GitHub without an explicit action.** Notes stay
  local until someone pushes them; closing, moving and commenting are all
  deliberate clicks.
- **A GitHub write always uses the acting person's own token**, never the
  board owner's or the organisation's, so GitHub records who did it.
- **Stored tokens are encrypted at rest** and never returned by the API,
  not even masked.

## Local setup

```
make setup      # interactively writes .env (token input hidden)
make install    # backend (Python 3.12 via uv) + frontend deps
make dev        # runs both dev servers; prints the URLs
```

See `README.md` for the manual (non-Makefile) equivalent and Docker
Compose instructions.

## Before opening a PR

```
make test              # backend pytest + frontend vitest
cd frontend && npm run build   # confirm the production build still compiles
```

Both suites must pass. If you touch GitHub-facing backend code, add or
update a `respx`-mocked test in `backend/tests/` — never make live GitHub
calls in tests (see `backend/tests/conftest.py`, which deliberately blanks
out any real token from a developer's `.env` before tests run).

## Code conventions

- Backend: FastAPI + SQLModel. Keep GitHub API calls inside
  `app/github_client.py`; routers should stay thin.
- Frontend: React + TypeScript function components, no class components.
  Keep business logic (filtering, drag→mutation mapping) out of
  presentation-only components where practical — this project intends to
  reuse that layer if it's ever ported to React Native.
- No new GitHub-taxonomy-creation code paths (labels, issue types,
  milestones) — this is a firm product constraint, not a style
  preference.
- Don't add a dependency for something a few lines of code already cover.

## Commit messages

Explain *why*, not just *what* — especially for anything that touches the
token-safety logic or the drag/move-compatibility rules, since those
encode constraints that aren't visible from the diff alone.

## Reporting a bug

Open a [bug report](../../issues/new?template=bug_report.yml). The
template asks for the steps to reproduce, the version or commit, and how
you're running it. Those three answers are usually the difference between
a bug that gets fixed and one that stalls.

Two things to check first:

- **Is it GitHub refusing, rather than the app failing?** The board shows
  GitHub's own message for rate limits, token permissions and repos with
  more issues than GitHub will page through. Those say so.
- **Is your token scoped for it?** Closing an issue or commenting needs
  `Issues: Read & write`.

**A security flaw goes to [SECURITY.md](SECURITY.md) instead**, never a
public issue: this app holds GitHub tokens.

## Fixing a reported bug

Pull requests against an open bug are welcome, including from people who
didn't report it.

1. **Say so on the issue** before you start, so two people don't write the
   same fix. If there's no issue yet, open one first; it's where the
   behaviour gets agreed.
2. **Branch from `main`.**
3. **Write a failing test first.** For a bug this matters more than
   anything else in the change: it should fail before your fix and pass
   after. Backend tests live in `backend/tests/`, frontend ones beside the
   code as `*.test.tsx`.
4. **Keep the fix to that bug.** Unrelated tidying makes a review slower
   and is easier to accept as its own pull request.
5. **Run `make test`** (backend and frontend), and click through the
   change if it touches the UI.
6. **Open the pull request** with `Fixes #123` in the description, so the
   issue closes when it merges. The template asks what you ran to verify
   it.

CI runs the same tests on every pull request. A review looks at whether
the test really fails without the fix, whether the behaviour matches the
docs, and whether anything now writes to GitHub without an explicit
action.

Maintainers: the same applies, minus the permission to start.
