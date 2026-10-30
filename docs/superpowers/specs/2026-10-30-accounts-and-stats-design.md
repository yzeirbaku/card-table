# Accounts and stats

Date: 2026-10-30. Status: approved in chat, being built.
Builds on: `2026-10-14-murlan-design.md`, `2026-10-16-mixed-tables-design.md`.

## Why

Friends want to keep track of who wins. Today nothing outlives a room: a player
is a name typed for one table, and a restart forgets everything. Accounts give a
player one identity across tables, so their finished games can be counted.

Kept simple on purpose: a username and a password, nothing else.

## Goals

- Sign up and sign in with a username and password (hashed).
- Every finished Murlan game is recorded for the signed-in people at the table.
- A **Profile** page with wins and losses, split into **vs people**, **vs
  computer** and **total**, built to take more later (coins).
- Comparing with friends: a **leaderboard** and **head-to-head** records.
- Accounts and stats survive restarts and redeploys.

## Non-goals

- Email, password reset by email, social login, avatars.
- Coins, a shop or anything else on the profile beyond stats (the page leaves
  room for them; they come later).
- Per-round stats. Only whole games (first to the target score) count.
- A hosted database. No Neon, nothing else to run.

## Anti-goals

- **Guests must keep working exactly as today.** Nobody has to sign up to play.
- Nothing about accounts may change the game itself or what `view_for` sends.
- A result must never be recorded wrongly: when in doubt, record nothing.

## Storage: SQLite on the VM

- One SQLite file, opened by the backend with Python's built-in `sqlite3`. No
  new service, no new dependency.
- Path from the env var `DB_PATH`. Dev default: `backend/data/cards.db`
  (gitignored). Tests use a temporary file.
- **Production:** the file lives at `~/apps/card-table/data/cards.db`, outside
  `repo/`, mounted into the container as a plain folder
  (`volumes: - ./data:/data`, `DB_PATH=/data/cards.db`). Not a named Docker
  volume: `docker compose down -v` or a prune can't delete a folder. A redeploy
  replaces the container; the file stays, so accounts, sign-ins and stats are
  kept. Games in progress still end on a redeploy, as today, and record nothing.
- **Schema changes:** at startup the backend reads `PRAGMA user_version` and
  applies any newer numbered migrations in order. Existing data is kept.
- **Backup:** a nightly cron job on the VM copies the file (with
  `sqlite3 .backup`, safe while the app is running) to a dated file and keeps
  the last 14. Set up during the deploy, written into the deploy skill.
- Single worker, small load: plain blocking `sqlite3` calls inside the async
  handlers are fine.

### Tables (builder may adjust columns)

- `users`: id, username, username_key (lowercase, unique), password_hash,
  created_at.
- `sessions`: token (random, unique), user_id, created_at.
- `games`: id, game ("murlan"), players (2/3/4), target, ended_at, how it ended
  (`target` or `leave`), had_computer (bool).
- `game_seats`: game_id, seat, user_id (null for guests and computers),
  computer (bool), side (team 0/1 in 4-player games, else the seat), score,
  won (bool).

Guests and computers get rows too (user_id null), so a game's record is
complete, but only rows with a user_id show up in anyone's stats.

## Accounts

- **Username:** 3-20 characters (20 is today's name limit), letters, digits,
  `.`, `_`, `-`. Unique ignoring case; shown as typed at sign-up. It is the
  player's name at the table.
- **Password:** at least 8 characters. Hashed with `hashlib.scrypt` and a random
  salt per user, stored with its parameters so they can be raised later.
- **Endpoints:** `POST /auth/register`, `POST /auth/login` (both return
  `{token, username}`, so registering also signs you in), `POST /auth/logout`,
  `GET /me`, `GET /stats/{username}`.
- **Session:** a random token, stored in the database, kept by the phone in
  localStorage (key `session` in the `card-table` store). Sent as
  `Authorization: Bearer <token>` (add `Authorization` to the CORS
  `allow_headers`) and, on the WebSocket, as its first message (never in the
  URL: URLs end up in the server's logs). Stored hashed (SHA-256). **Not a cookie:** the
  frontend and backend are on different sites, and Safari and the iOS home-screen
  app block cross-site cookies. Sessions don't expire; signing out deletes it.
- **Login rate limit:** in memory, 5 failed attempts per username in 10
  minutes, then "Too many tries, wait a few minutes" (HTTP 429). *My call:* per
  username only, not per IP. Behind Caddy in another container the backend sees
  Caddy's address for every request, so a per-IP limit would lock everyone out
  at once.
- **Forgotten password:** there's no email. A small script run on the VM sets a
  new password: `python -m app.accounts reset-password <username>`.

## Joining a table signed in

- A signed-in phone connects with `?signed_in=1` and sends
  `{"type": "session", "session": <token>}` first. A valid session makes the
  player that account: their name is the username, and the `name` parameter is
  ignored.
- A seat token only ever gets back its own player: never a seat that belongs to
  another account. A dead session with a valid seat token still gets its seat
  back (the token proves it).
- A guest can't play under a name that belongs to an account (closes with 4400,
  "<name> has an account. Sign in to play as <name>").
- An unknown or deleted session: the socket closes with a new code (4401,
  "Signed out"), and the phone forgets the session and shows the main screen
  signed out.
- One account sits in a room at most once. Joining again from a second phone
  without a seat token is rejected ("You're already at this table"). A seat-token
  reconnect works as today.
- `Player` gets `user_id: int | None`. `players_view` doesn't send it. Whether
  someone is signed in isn't shown to the table (builder's call; easy to add).

## What gets recorded

A result is written at the moment a game ends, from `rooms.py` (the game stays
pure Python, with no I/O). It's written for the whole table, guests and
computers included, if and only if a winner is clear:

| How the game ends | Result |
|---|---|
| A side reaches the target (or clinches it early) | That side wins, everyone else loses |
| A person taps **Leave game** | **The leaver's side always loses.** Of the other sides, the one with the highest score wins; the rest lose |
| Leave with the top score among the other sides tied, or before anyone has scored (0-0, or still choosing the target) | Nothing recorded |
| A drop's pause runs out and the table picks **End game** | Nothing recorded |
| The game ends any other way while someone is disconnected (room expires, a redeploy, a restart) | Nothing recorded |

- "Leave" means the player's own `leave` message during a game (`Room.leave`
  with a game on and the player seated). A guest leaving counts the same as a
  signed-in player leaving.
- *My call:* a Leave is recorded only while everyone at the table is connected
  and the game isn't over. Leaving while someone is disconnected (in the pause,
  or after its countdown ran out) records nothing, so the person whose phone
  died never gets a loss. Leaving after the game is over records nothing more:
  the game was already recorded when it ended (or deliberately not, after End
  game).
- The leaver never gets the win, even when ahead, so quitting while in front
  never pays off. In a 4-player game that is the leaver's whole team: they and
  their partner lose, the other team wins. In 2- and 3-player games the leaver
  loses and the highest of the others wins (a 2-player leave is always a win
  for the one who stayed, once anyone has scored).
- A game is recorded once. **Play again** starts a new game with its own record.

## Stats

Individual and team results are kept apart:

- **Solo** (2- and 3-player games): your own wins and losses.
- **Teams** (4-player games): a win counts for both partners. Your record as half
  of a team, whoever your partner was.

Each has three columns, decided by your **opponents** (your partner in a
4-player game is not an opponent):

- **vs people:** at least one opponent was a person (guests count). Mixed tables
  land here: you beat real people.
- **vs computer:** every opponent was a computer (alone against computers, or you
  and a partner against two).
- **Total:** both.

So you + a computer partner against Arben and Sebi is vs people; you and Arben
against two computers is vs computer; you, Arben and a computer at a 3-player
table is vs people.

```
YOUR STATS                     vs people   vs computer   total
Solo (2 & 3 players)  W–L        12–9        20–4       32–13
Teams (4 players)     W–L         8–6        11–2       19–8

PARTNERS (4 players)            W–L    win %
  with Sebi                    6–2     75%
  with Arben                   2–4     33%
  with a computer              11–2    85%
  with a guest                 1–0    100%
```

- **Partners:** your 4-player record broken down by who sat across. Accounts by
  username, most games first; computer partners in one row, guest partners in
  one row.
- `GET /stats/{username}` returns these numbers; the screen draws them. Counted
  from `game_seats` on each request (small data, no caching). Anyone's stats can
  be viewed (that's how you look at a friend).

### Leaderboard

- Two lists, **Solo** and **Teams**, of every account with at least one game
  against people (an account with only computer games isn't on them).
- Counts **vs people games only** (by the opponents rule above): it's about how
  you do against your friends, and beating computers on easy shouldn't climb it.
- Ranked by **win %**, among players with **at least 5** such games; ties by more
  wins, then name. Players with fewer games are listed after, unranked, by games
  played.
- `GET /leaderboard` → `{"solo": [...], "teams": [...]}`, each entry
  `{username, won, lost, ranked}`.

### Head-to-head

Tapping a player (on the leaderboard or among your partners) shows them:

- **You vs them:** games you both played on opposite sides that one of your
  sides won. Your side won: a win for you; theirs: a loss. Games someone else
  won don't count here.
- **Together:** 4-player games as partners, wins and losses.
- **Their record:** the same table as your own stats.
- `GET /head-to-head/{username}?with={other}` → `{against: {won, lost},
  together: {won, lost}}`, from `username`'s side.

## Frontend

Picked from mockups (option A, 2026-10-30):

- **Main screen:** as today plus a chip in the top-right corner. Signed out it
  says **Sign in**; signed in it shows your initial and username. The name field
  becomes "Playing as <username>" (not editable).
- **Sign in / New account:** one sheet with a two-way switch, username and
  password fields, a note that guests can always play. Errors from the server
  shown as text.
- **Profile:** tapping the signed-in chip opens a full page (a view, like the
  lobby), with a back arrow. Header: initial and username, room for coins later.
  Tabs: **Stats** (your table and partners, Sign out at the bottom) and
  **Players** (Solo / Teams switch, the leaderboard, you highlighted). Tapping a
  player opens their page: head-to-head, together, their record.
- The Profile page's exact look is picked from browser mockups. Nothing visual
  gets committed until the user has tried it.
- Everything from the server goes in with `textContent`.

## Delivery

One PR: backend, frontend, tests, and the deploy notes (`docker-compose.yml`
volume, `DB_PATH`, the backup cron, the reset-password command) in the deploy
skill. The VM compose change is applied by hand at deploy time.

## Tests

- Register, login, logout, wrong password, duplicate username in any case, rate
  limit, bad session on the WebSocket.
- Recording: each row of the "What gets recorded" table, 2/3/4 players, guests
  and computers present, the leaver's side on top, a tie on leave.
- Stats: solo/teams split, the three columns, partners.
- Migrations run on an empty database and on one at the previous version.
- `test_no_view_ever_leaks_hidden_cards` and the rest pass unchanged.

## Left to the builder

Module layout (e.g. `app/db.py`, `app/accounts.py`, `app/stats.py`), exact
column names, error messages, the migration helper's shape.
