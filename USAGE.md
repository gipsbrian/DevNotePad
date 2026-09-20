# Using DevNotePad

## Signing in

The app asks for a username (or the email on the account) and a password.
The first account comes from `ADMIN_USERNAME` / `ADMIN_EMAIL` /
`ADMIN_PASSWORD` in `.env` and is created the first time the backend
starts - see [README.md](README.md#setup). Editing those values
afterwards won't change the password of an account that already exists.

Unless the instance has turned it off (`ALLOW_REGISTRATION=false`), the
sign-in page also offers **Create an account**. Usernames are 3-32
letters, numbers, dots, dashes or underscores; passwords need at least 8
characters.

A new account starts with a short guided tour of the boards page, and
another the first time it opens a board. Finishing or dismissing one
(Escape, the close button, or clicking outside it) means it won't start
on its own again; the **?** button in the left rail replays the tour for
whichever page you're on, for any account.

A new account starts empty. Open settings (the person icon, with a dot on
it until it's done) and add a GitHub token and username, then create
boards as usual. What you make is yours alone: other accounts on the same
instance can't see or open your boards, notes or token, and you can't see
theirs.

Everything except the sign-in screen itself needs a session, and it lasts
two weeks or until you sign out from the bottom of the left rail.

## Organisations

The rounded chip under the logo shows which organisation you're working
in. Click it to switch, to open **Organisation settings**, or to **Create
organisation**.

- **Main** is everyone's: every account belongs to it and nobody leaves
  it.
- **Creating an organisation** makes you its admin and moves you into it.
  Your GitHub token stays personal; it isn't shared with the organisation.
- **Boards belong to the organisation you made them in**, and the boards
  page lists only the current organisation's. A link to one of your boards
  in another organisation you belong to switches you there, with a notice.
- **Where you land after signing in:** tick "Open this organisation when I
  sign in" in its settings to make it your default; otherwise you land in
  the one you used last.
- **Admins** can rename the organisation, make other members admins, and
  remove members. Anyone can leave an organisation other than main. An
  organisation always keeps at least one admin.
- **Removal is not deletion.** Someone removed from (or leaving) an
  organisation loses access to their boards there, but the boards are kept
  and come back if they're added again.

### Bringing people in

Two ways in, both from **Organisation settings** (admins only):

- **Invitation links.** Choose whether the person joins as a member or an
  admin, optionally note who it's for, and **Create link**. Copy it
  straight away -- it's only shown once -- and send it however you like;
  the app doesn't send email yet. Each link lets one person in and lasts
  7 days. Someone without an account can create one from the link, even
  when the instance has registration turned off. Opening a link while
  signed in asks before joining. **Withdraw** cancels a link that hasn't
  been used.
- **Join requests.** Every organisation has a join link,
  `/o/<its-name-in-links>`, shown under **Join requests**. Someone who
  opens it can **Ask to join**; every admin gets a notification, and
  **Approve** or **Decline** answers them (they're notified either way).
  After a decline, the same person can't ask again for a few days.

### Notifications

The bell in the rail shows how many are unread: join requests for
organisations you run, whether your own requests were approved, and when
someone uses an invitation you made. Clicking one takes you to the
organisation it's about. The bell checks for new ones every minute and
whenever you come back to the tab.

## Sharing boards

- **Your boards** are personal: nobody else sees them until you share them.
  On a board you own, **Share** offers everyone in the organisation, or
  chosen members.
- **Sharing is view-only.** People you share with see the columns and
  issues and keep their own private notes and sticky notes, but can't change
  the board, act on GitHub from it (close, move, comment, push a note), or
  see its token. Your boards page lists what's been shared with you under
  **Shared with you**, and a member's page (click their name in the
  organisation's member list) shows what they've shared with you.
- **Organisation boards** are created by admins -- choose "Everyone in
  <organisation>" when making a board -- and every member sees them. Admins
  manage them; any member can act on GitHub from them, always with their
  own token. Members without a token of their own can view but not act.
  They read GitHub with the board's own token, or the organisation's token,
  which admins set in **Organisation settings**.
- **Notes are always private.** On any board, shared or not, your issue
  notes and sticky notes are yours alone.

## Single sign-on for an organisation

Admins configure Google, Microsoft and Apple under **Organisation settings
> Single sign-on**: the client details from each provider (secrets are
write-only), which provider to switch on, and optionally auto-join domains.
Each provider shows the callback URL to register with it, and the page shows
the organisation's sign-in link to share. The main organisation's providers
are the ones on the normal sign-in page.

Signing in through an organisation's link takes members straight into it.
Anyone else is signed in to Main and their request to join goes to the
organisation's admins -- unless the provider verified an email on one of the
auto-join domains, which joins them at once.

## Instance admin

Admins of the main organisation see a shield in the left rail. The
**Instance admin** page counts accounts, organisations and boards, lists
every account (with how they sign in) and every organisation, and makes or
removes other instance admins.

## Concept

A **dashboard** tracks one GitHub repo. Inside it, you define **columns** —
each column is a saved filter (state, label(s), milestone, assignee)
built from labels/milestones/assignees that already exist on that repo.
DevNotePad never creates new GitHub labels, issue types, or milestones for
you — if a filter you want doesn't exist yet, create it in GitHub first.

## Settings (shared by every board)

Open settings from the person icon in the left rail:

- **Your GitHub username** — adds **Assigned to me** and **Created by me**
  as the last two columns on every board. It's detected from your token,
  so you normally just confirm it. Untick "Show those two columns" to
  hide them.
- **Default organization URL** — prefills the repo field when you create
  a board.
- **General token** — used by any board that doesn't carry its own. For
  the first account only, `GIT_TOKEN` from `.env` is used automatically
  if set; a token saved here takes precedence. Every other account saves
  its own.

## Analytics

The boards page carries an **Analytics** section covering the whole
organisation, not just one board:

- **Me** (the default) shows one person's issues — the token's own user,
  with a picker for anyone else on the team. Opened counts issues that
  person *authored*; closed counts issues *assigned* to them, which is the
  closest GitHub search gets to "work they finished".
- **Organisation** shows the same figures across every repo in the org.

Each view gives four headline numbers, an opened-vs-closed chart by week,
and which repos the open work sits in. The window is the last 6 weeks.

Analytics use GitHub's search API, which is limited to **30 requests per
minute** — much tighter than the rest of the API. One view spends most of
that, so results are cached for two minutes, and switching scope
immediately after a fresh load may briefly report the limit was reached.

## Creating a dashboard

1. From the dashboard list, click **New dashboard**.
2. Give it a name, and the repo it should track — `owner/repo`, a
   github.com URL, or an SSH remote all work. It's prefilled with your
   default org.
3. Choose whether it uses the **general token** or **a token just for
   this board**. If no general token exists, the board needs its own.
4. Pick an accent color and, optionally, a background wallpaper URL —
   purely cosmetic, doesn't touch GitHub.

To change a board later — rename it, point it at a different repo, or
switch which token it uses — open **Customize** on the board.

To remove a dashboard later, click the **✕** on its tile in the dashboard
list. This deletes the dashboard's columns and local notes from
DevNotePad only — it never touches GitHub itself.

## Adding columns

On a dashboard, click **+ Add column**. Pick from the repo's *existing*
labels, milestones, assignees, issue authors and issue types — nothing is typed freely
except the column's own name. Edit a column's filters later with the
**⋯** button in its header (the two automatic "…me" columns are marked
`auto` and aren't editable). A column with:

- a single label -> dragging/moving a card into it **adds** that label
  (never removes labels from other columns)
- `state: closed` and no other filters -> dragging/moving a card into it
  **closes the issue**

Columns with a more specific combination of filters (e.g. a label *and* a
milestone) are view-only for drag/move, since there's no single
unambiguous action to take — use the issue detail modal to change those
fields directly on GitHub instead.

## Working with cards

- **Card face**: title, a stripped-markdown summary, full labels, opened
  and last-updated dates, and an "open for Nd" age bubble.
- **Badges**: a sticky-note icon means you have a local note on this issue
  (hover to preview on desktop; tap the badge on mobile); a chat-bubble
  icon with a count means GitHub has comments on the issue -- hover it to
  read them beside the card, and reply from there without opening the
  issue (see [Comments beside a card](#comments-beside-a-card)); a
  `done/total` badge means the issue has sub-issues — hover it to list
  them, or open the issue to see them with links.
- **Click a card** to open the detail modal: full description, labels,
  assignees, milestone, the GitHub comment thread, your local notes, and a
  **Close issue** button. The description, comments, and notes are
  rendered as formatted markdown (bold/italic, lists, links, code blocks,
  tables) rather than shown as raw source.
- **Compare issues side by side** — with an issue open, the floating
  **+** to its right opens a second (and a third) alongside it. It asks
  which column to take one from, then lists that column's issues. Close
  one with the **✕** above its pane, or all of them with Escape.
- **The open issues are part of the address**, so a refresh reopens
  exactly what you were reading and the link can be sent to someone else.
- **Move a card** either by dragging it between compatible columns, or via
  the `⋯` menu on the card for a non-drag alternative — both use the exact
  same underlying action.
- **Close an issue** from that same `⋯` menu without opening it. It asks
  once (`Close issue` → `Really close #123?`) because it closes the issue
  on GitHub for real.

Each column fetches its own issues straight from GitHub using that
column's filter, so the **refresh icon** in a column header refetches only
that column — useful when one list is stale but you don't want to reload
the whole board.

Each column's own `⋯` menu (in its header) can edit the column's filters,
remove the column, or **copy its issues** as `title : link`, one per line —
handy for pasting into a standup note or ticket. Copy takes whatever the
column currently shows, so an active search narrows it.

## Comments beside a card

A card's chat-bubble badge appears only on issues that have comments.
Hover it and the thread opens beside the card: who wrote each comment,
when, and the text.

- **Move the pointer into the panel** to read it; it closes shortly after
  you leave, and Escape closes it at once. Clicking the badge pins it,
  which is how it works on a touchscreen.
- **Reply from the panel.** Type in the box at the bottom and press
  Comment, or Ctrl/Cmd+Enter. It posts on GitHub as a real comment, with
  your own token.
- **Your draft keeps the panel open**, so moving the pointer away doesn't
  discard what you were writing. A comment GitHub refuses keeps its text
  and shows the reason.
- On a board **shared with you**, the panel is read-only and says so.

## Notes and comments

The box under **Local notes** in the issue modal has two buttons:

- **Save locally** keeps it as a private note on the issue. When you're
  ready to share one, **Push to GitHub** posts it as a real comment;
  editing an already-pushed note and pushing again updates that same
  comment instead of posting a new one each time.
- **Comment on GitHub** posts it straight to the issue as a comment, for
  when you're joining a conversation rather than keeping something for
  yourself. No local note is kept. It's public to everyone who can see the
  issue, and needs a token with write access to issues; if GitHub refuses,
  the error shows and your text stays in the box.

## Sticky notes

A scratch pad for the board itself, separate from the per-issue notes.
It **floats above the board** — the columns scroll underneath, so it's
always reachable.

- **+** adds a note. Notes take markdown, and the toolbar inserts
  checklist items, bullets and bold. If your browser supports the Web
  Speech API (Chrome does, Firefox doesn't), a mic button dictates.
- **Checklists are tickable in place** — clicking a checkbox in a
  rendered note updates the note itself, and the header shows done/total.
- **Pin** keeps a note on top of the stack; **archive** files a finished
  one away without losing it (the archive button in the header switches
  between active and archived).
- **See all** (the grid button in the panel header) lays every note out
  at once over the board; click one to bring it to the front. The search
  box narrows both the stack and that view.
- The stack shows one note at a time with a `+N under` pill and arrows to
  page through it. Double-click a note to edit it.
- Use the corner button to move the panel between the four corners, or
  collapse it to a small tab. Both are remembered per board.

## Closed issues

Below the columns, the **Closed** section lists issues grouped by the date
they were closed (Today / Yesterday / older dates), most recent first.

Use the range buttons beside the heading to choose the window — 7 days
(the default), 1 month, 2 months, 6 months, or all time. Your choice is
remembered per board. The default is short on purpose: pulling a busy
repo's whole closed history takes many seconds and delays the board.

## Search

The search box filters cards already loaded on the dashboard (title,
issue number, summary text, and label names) — it doesn't query GitHub
again, so it's instant but only searches what's currently on the board.

## Theme and appearance

Use the theme toggle in the header to cycle System -> Light -> Dark; your
choice is remembered per browser. Use **Customize** on a dashboard to set
its accent color and background wallpaper.

## Token safety

DevNotePad shows you the detected token type and, where possible, an
inferred read/write capability — but it can never *guarantee* a
fine-grained token's permissions, since GitHub doesn't expose that. Always
scope tokens to the specific repos you use here, with the minimum
permission you need (`Issues: Read-only`, or `Read & write` only if you
want to close issues / post comments from the app).

Tokens are encrypted before they're written to the database, using
`SECRET_KEY` from `.env`. Replacing that key doesn't destroy anything,
but it does make existing tokens unreadable — the app then treats them as
absent, and you re-enter them. Back it up with the database, not
separately from it.

A board's URL carries a random id (`/dashboards/2b1e…`) rather than a
counter, so one board's link gives away nothing about any other. That
makes a link awkward to guess, which is not the same as private — the
sign-in is what actually keeps people out.
