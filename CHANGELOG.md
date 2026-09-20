# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/) — see the
`VERSION` file for the current release.

## [Unreleased]

Nothing yet.

## [0.2.0] - 2026-09-20

### Added

- **An issue's comments beside its card.** The comment badge -- which only
  appears on issues that have comments -- opens the thread on hover, and
  you can reply from it without opening the issue. The panel stays put
  while there's a draft in it, and is read-only on a board shared with
  you. It costs one GitHub call, where opening the issue costs three.
- **Sharing boards.** Personal boards can be shared, view-only, with chosen
  members or the whole organisation, and appear under "Shared with you";
  a member's page shows what they've shared with you. Organisation boards,
  created by admins, are seen by every member. Reads use the board's token,
  its owner's, or the organisation's (set by admins, write-only); every
  change on GitHub uses the acting person's own token, and shared boards
  allow none. Issue notes and sticky notes are now private to their writer
  on every board; existing notes belong to their board's owner.
- **Single sign-on per organisation.** Google, Microsoft and Apple are
  configured by each organisation's admins in the app, or with
  `python -m app.cli sso`, with secrets write-only and encrypted at rest.
  Each organisation's link, `/o/<slug>`, offers its own providers. Members
  signing in land in the organisation; others land in main with a join
  request, unless a verified email is on the provider's auto-join domains.
  One callback URL per provider type serves every organisation, built from
  `PUBLIC_URL`. `.env` provider settings remain a fallback for the main
  organisation only.
- **Instance admin** page for the main organisation's admins: counts, every
  account and organisation, and promoting or demoting instance admins.
- **Command-line administration**: `python -m app.cli` for organisations,
  instance admins and SSO providers.

- **Invitations and join requests.** Organisation admins create
  single-use invitation links (member or admin, 7 days, shown once and
  stored only as a hash) and can withdraw them; an invitation also lets
  someone register while registration is closed. Every organisation has a
  join link where anyone signed in can ask to join; admins approve or
  decline, and a declined person waits a few days before asking again.
- **Notifications** in the rail for join requests, decisions and used
  invitations, checked every minute and on returning to the tab.
- **Organisations.** Every account belongs to a main organisation, and
  anyone can create more from the new organisation menu in the rail,
  becoming that organisation's admin. Boards belong to the organisation
  they were made in, and the organisation you're working in is remembered
  by the browser rather than the address, so it only changes through the
  menu -- or by opening a link to one of your boards elsewhere, which
  switches you there with a notice. Admins rename, promote and remove;
  members can leave; an organisation always keeps an admin; main is
  everyone's. Removal is soft, so boards come back when someone rejoins.
  Pick a default organisation to land in, otherwise you land in the last
  one used. Existing accounts and boards move into main on startup, and
  the first account becomes its admin.
- **Guided tours** for new accounts, built on driver.js: one for the
  boards page on first sign-in, one for a board the first time one opens.
  Steps whose element isn't on the page (no cards yet, say) are skipped
  rather than pointing at nothing. Finishing or dismissing a tour is saved
  to the account, so it shows once per person on any device; a **?** in
  the rail replays the one for the current page. Accounts that existed
  before tours start with both marked seen.
- **Comment on GitHub directly** from the issue modal, alongside **Save
  locally**, for replying on an issue without first saving a private note
  and then pushing it. The comment appears in the thread straight from
  GitHub's response rather than a reload, which can briefly miss it; a
  refused comment keeps its text.
- **Accounts for a team.** With `ALLOW_REGISTRATION=true`, the sign-in
  page offers to create an account (username, email, password), so
  several people can share one hosted instance. Each account's boards,
  columns, notes, sticky notes and settings -- including its GitHub
  token -- are private to it, and another account's board answers as if
  it doesn't exist. The `.env` token and org are only ever lent to the
  first account. Boards and settings from before this belong to that
  first account on startup. Registration is on unless
  `ALLOW_REGISTRATION=false`.
- **Up to three issues open side by side**, for comparing ones that look
  alike without a second tab. The floating **+** beside an open issue
  asks which column to take the next one from, then lists that column's
  issues. Panes scroll independently; **✕** closes one and Escape closes
  all.
- Copy an issue's **link** from beside its number, or the **whole issue**
  — heading, link and description — from the footer.
- **Sign-in** — the API had no authentication of its own, and it holds a
  token that can write to real repositories. Every endpoint that touches
  board data or GitHub now sits behind a session; only the health check
  and the auth endpoints are open. Sign in with either the username or
  the email; a wrong password and an unknown account give the same
  answer. The first account is created from `ADMIN_USERNAME` /
  `ADMIN_EMAIL` / `ADMIN_PASSWORD` on startup, and only ever into an
  empty user table.
- The sign-in screen splits the form from a rotating look at what the app
  does. Those slides are drawn with CSS rather than screenshotted, so
  there are no images to keep in step with the UI and they follow the
  theme.

- **Sticky notes** — a board-level scratch pad that floats over the
  board rather than sitting in the column scroll, so it's never scrolled
  out of reach; the columns pass underneath it. Modelled on the reference
  stack: cream paper on an amber tray, the top sheet tilted with the
  others peeking out and a `+N under` pill.
  - Markdown editing with a small toolbar (checklist, bullet, bold) and
    **voice dictation** where the browser supports the Web Speech API.
  - Checklists are tickable in place — clicking a rendered checkbox
    rewrites the underlying markdown — with a done/total counter.
  - Pin to top, archive (revisitable later), delete, page through the
    stack, and each note shows when it was created.
  - **Search** across notes, and a **See all** button that lays every
    note out at once over the board -- click one to bring it to the top
    of the stack.
  - Collapses to a tab, and can be moved between all four corners; both
    the corner and collapsed state are remembered per board.
- **Per-column refresh** — a refresh icon in each column header refetches
  just that column. Columns already query GitHub independently with their
  own filter, so this costs one request rather than reloading the board.
- **Close an issue from its card menu**, without opening it. The action
  is two-step (`Close issue` → `Really close #123?`) since it mutates a
  real GitHub issue and the menu is easy to mis-click.
- **Analytics on the boards page** — personal and organisation issue
  metrics, defaulting to the token's own user with a picker for anyone
  else on the team. Four headline figures (open, closed in window, opened
  in window, and whether the backlog grew or shrank), a weekly
  opened-vs-closed chart, and a breakdown of which repos the open work
  sits in. Charts are hand-drawn SVG with a hover layer; the two series
  use a palette validated for colour-vision deficiency and contrast
  against both the light and dark surfaces.


- **Settings that cut across boards** (rail → person icon): your GitHub
  username, a general token, and a default org URL. The username is
  detected from the token so you don't have to look it up, and every
  form is prefilled with what's already known.
- **Two automatic columns on every board** — "Assigned to me" and
  "Created by me", always last. They're synthesized from the saved
  username rather than stored, so they follow a username change and
  can't be edited or deleted; toggle them off in settings.
- **Editable boards**: rename, repoint at another repo, and switch
  between the general token and a board-specific one. Repo fields accept
  `owner/repo`, a github.com URL, or an SSH remote.
- **Editable column filters**, plus a new "created by" filter alongside
  labels, state, milestone and assignee.

- **Sub-issue support.** Cards show a `done/total` badge when an issue has
  sub-issues (free — GitHub already sends `sub_issues_summary` on the
  issue payload), hovering it lists them with per-issue state, and the
  detail modal gains a Sub-issues section linking each one.
- **The note preview is now a sticky note** — tilted yellow paper with
  tape and a curled corner, rather than a dark tooltip.
- **Column actions menu** (⋯): edit the column's filters, remove it, or
  **copy its issues** to the clipboard as `title : link`, one per line.
  Copy respects the current search, and works on the automatic columns
  too.
- **Time window for the Closed section** — 7 days (default), 1 month,
  2 months, 6 months, or all time; remembered per board.
- **Issue type filter** on columns, alongside labels/state/milestone/
  assignee/creator. GitHub defines issue types per organization, but the
  picker is sourced from the types actually used on the board's own repo
  (so it doesn't offer filters that match nothing), then supplemented
  with any org-defined types the token can see — the org registry
  endpoint needs `read:org`, which many tokens lack.
- **Reorderable columns** — move a column left or right from its header;
  the order is saved per board. The two automatic columns always stay
  last.
- **Delete a board from the board itself**, in Board settings, rather
  than only from the boards list.

### Fixed

- A card's comment badge no longer shows a browser tooltip repeating the
  count over the comments panel it opens; screen readers still announce it.
- Pushing a note to GitHub ignored the general token saved in settings and
  only tried `GIT_TOKEN` from `.env`, so it failed on any board relying on
  the saved one. It now uses the same token as the rest of the board.
- Deleting a board left its sticky notes behind in the database.
- Closing an issue left its card sitting in the column until you refreshed
  by hand. The board did refetch on close -- but GitHub's issue list can
  still report an issue as open for a moment after the write that closed
  it, so the refetch handed the card straight back. A card you just closed
  is now held out of the columns and the open count until a refetch stops
  listing it, which also covers the issue being reopened later outside the
  app.
- Refreshing with an issue open dropped you back on the board. Which
  issues are open now lives in the address, so a refresh reopens them and
  the link can be handed to someone else.
- Every board load fetched each column twice in development: StrictMode
  double-invokes effects, and nothing coalesced the duplicate loads.
  Identical in-flight loads are now shared, halving the GitHub calls a
  dev-mode board load costs. (Production always issued one per column.)
- Sticky note text was invisible in dark mode: the sheet carries
  `.markdown-body`, whose `color: var(--text)` is declared later in the
  stylesheet and so won the cascade — near-white ink on cream paper. The
  paper now sets its own ink for itself and its descendants, measured at
  14.3:1 contrast in both themes.
- `NotePopover` and the sticky column both used `.sticky-body`, so the
  popover's 7-line clamp was silently truncating full notes. The popover's
  text has its own class now.


- Sticky notes: pressing **+** created an empty note on the server
  immediately, so abandoning the editor (navigating away, reloading) left
  a blank behind — and since notes sort newest-first, that blank sat on
  top hiding the real ones. A new note is now a local draft and is only
  persisted once it has content, so nothing is created if you change your
  mind. Any blank left by the old behaviour is also kept out of the
  stack, so the panel always opens on real content.


- Analytics search failures rendered as `0` rather than as errors, so
  hitting GitHub's 30/minute search limit looked like "this org has no
  issues". Failed searches now surface as a 429 with a plain explanation.
- The analytics cache is process-global, so changing the token, org or
  username left stale results in place; settings changes now clear it.
- The hover preview of a local note never appeared on a card in a column.
  Two causes: the popover was absolutely positioned inside `.column-body`,
  which scrolls (`overflow-y: auto`) and so clipped anything reaching
  outside it; and the board never refetched notes after one was added, so
  the card's note badge appeared with no note body behind it. The popover
  now renders in a portal with fixed positioning (flipping below the card
  when there's no room above) and animates in.
- Cards in the Closed section carried `aria-disabled="true"` from dnd-kit
  because they aren't draggable — they were announced as disabled despite
  being clickable. dnd-kit's ARIA bundle is now only applied to cards that
  really are draggable.
- The Closed section fetched a repo's entire closed history on every board
  load, which dominated load time — 15.3s for 1,403 issues on a real repo.
  It now defaults to the last 7 days (1.3s), bounded with GitHub's `since`
  and narrowed to actual `closed_at`, since `since` matches on updated_at
  and would otherwise leak in old issues that were merely touched.
- A failed action (a rejected move, a reorder that didn't save) replaced
  the whole board with an error page and never recovered. Load failures
  and action failures are now distinct: the latter shows a dismissible
  notice and leaves the board usable.
- Panels opening over the board no longer have cards animate across them.
- Destructive buttons kept their red on the board canvas instead of being
  flattened into ordinary-looking buttons by the glass styling.
- The delete affordance on a board tile is visible instead of appearing
  only on hover.
- The same issue appearing in more than one column (e.g. "All open" and
  "Assigned to me") rendered blank in all but one of them —
  framer-motion collapses duplicate `layoutId`s into a single element,
  so the ids are now scoped per column.

### Changed

- **Stored GitHub tokens are encrypted at rest**, keyed by a new required
  `SECRET_KEY`. It sits in a database column type rather than at the call
  sites, so no read or write can forget it. Tokens written before this
  are rewritten once on startup; a key that no longer decrypts a value
  leaves it reading as absent rather than failing the request. `make
  setup` generates the key, and the backend refuses to start without one.
- **A board is identified by a uuid, not its row id.** `/dashboards/1`
  invited anyone to try `2`. The integer key stays internal and no longer
  resolves anything through the API. Existing boards are backfilled one
  uuid each.
- The sticky note panel is larger, and long lines no longer get cut off.
  A flex item wouldn't shrink below its content, so one long URL stretched
  the sheet past the panel and the overflow was cropped; the editor had
  the opposite problem and collapsed to roughly two visible lines whatever
  the note's length.
- Both container ports bind to `127.0.0.1`. Set `VITE_API_BASE_URL=`
  (empty) to serve the app behind a reverse proxy on one origin.
- The frontend image moved to Node 22 — its test suite could not start on
  20 at all.

- Docker Compose now defaults to ports 8010/5180 (overridable via
  `BACKEND_PORT`/`FRONTEND_PORT`) instead of 8000/5173, which commonly
  clash with other local services, and its `CORS_ORIGINS` /
  `VITE_API_BASE_URL` follow those ports. Added `make docker-reset` for
  dependency changes — the frontend `node_modules` named volume is only
  seeded once, so a plain rebuild otherwise keeps stale modules. It drops
  only that volume, never the one holding boards and notes.
- Redesigned the UI around Trello's board model: each board now renders on
  a vivid rounded canvas (its wallpaper, or a gradient derived from its
  accent color) with translucent lists floating on top and a glassy board
  header. Cards gained label color stripes, label chips, assignee avatars,
  an age pill, and monochrome note/comment badges.
- New app shell: a dark icon rail (boards / new board / theme), which
  becomes a bottom bar on phones.
- Added at-a-glance stat tiles per board (open, closed, columns, oldest
  open), a pill search field, skeleton loading states, and an inline icon
  set replacing the emoji badges.
- The token warning is now a compact dismissible notice, and the dismissal
  is remembered per board.

### Added

- Markdown rendering (GitHub-flavored: tables, task lists, strikethrough)
  for issue descriptions, GitHub comments, and local notes, via
  `react-markdown` + `remark-gfm`. Previously these showed raw markdown
  source (literal `**bold**`, `- list`, `[text](url)`). Raw HTML embedded
  in markdown is intentionally left un-rendered rather than executed.

## [0.1.0] - 2026-09-03

Initial release.

### Added

- Dashboards, each tracking one GitHub repo, with an optional per-dashboard
  token override (falls back to a default `GIT_TOKEN`).
- Columns as saved filters over labels, state, milestone, and assignee that
  already exist on the repo — the app never creates new labels, issue
  types, or milestones.
- Token type detection (classic PAT / fine-grained PAT / OAuth / GitHub
  App) with a best-effort read/write inference and a standing warning,
  since GitHub gives no way to fully verify a fine-grained token's scope.
- Issue cards showing full labels, opened/updated dates, an "open for Nd"
  age bubble, a comment-count badge, and a local-note badge.
- Local notes per issue, kept private by default, with an explicit
  push-to-GitHub action that edits the same comment on later pushes
  instead of reposting.
- Closing issues from the app; a Closed section grouped by date.
- Move-without-drag (a per-card menu) alongside drag-and-drop, restricted
  to columns whose filter maps to one unambiguous mutation.
- Client-side search across loaded cards.
- App-wide light/dark theme (system-aware, manual override persisted) and
  per-dashboard accent color + background wallpaper.
- Responsive layout down to phone width.
- `Makefile` + `scripts/setup-env.sh` for local setup without a token ever
  touching shell history.

### Deferred

- A roadmap / "what's next" view built on GitHub's Issue Dependencies API.
