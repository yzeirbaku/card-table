# Accounts and Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Username/password accounts and per-account Murlan win/loss stats, stored in a SQLite file that survives redeploys, with guests still playing as today.

**Architecture:** A SQLite file opened by the backend (`app/db.py`) holds users, sessions and finished games. `rooms.py` stays free of I/O: a finished game becomes a `GameRecord` handed to a callback the app wires to the database. The frontend keeps a session token in localStorage and sends it as a bearer header and as `?session=` on the room WebSocket.

**Tech Stack:** Python 3.12 stdlib `sqlite3` + `hashlib.scrypt`, FastAPI, vanilla JS (no npm deps), `pytest`, `node --test`.

**Spec:** `docs/superpowers/specs/2026-10-30-accounts-and-stats-design.md`

## Global Constraints

- No new Python or npm dependencies. SQLite via stdlib `sqlite3`, hashing via `hashlib.scrypt`.
- DB path from env `DB_PATH`; dev default `backend/data/cards.db` (gitignored); prod `/data/cards.db`.
- Username: `^[A-Za-z0-9._-]{3,20}$`, unique ignoring case, shown as typed at sign-up. Password: 8-128 characters.
- Login limit: 5 failed attempts per username (lowercased) in 600 seconds → HTTP 429 "Too many tries, wait a few minutes". Per username only, never per IP.
- Session: random token, no expiry, deleted on logout. Not a cookie. `Authorization: Bearer <token>` on HTTP, `?session=` on the WebSocket.
- WebSocket with an unknown session closes with code 4401, reason "Signed out".
- `game.py` stays pure (no I/O). `rooms.py` does no I/O: it calls an injected callback.
- `view_for` and `players_view` output unchanged; `user_id` is never sent to clients.
- Everything from the server goes into the DOM via `textContent`.
- Visual changes (sheets, CSS) are chosen from browser mockups with the user and stay uncommitted until the user has tried and approved them.
- LF line endings; check `git diff --stat` before each commit. `node --check` every `frontend/js/*.js` before pushing.

## Review Focus

1. **Recording must never take a table down:** if the database write raises, the game and broadcast carry on; the error is logged. (Task 3 test.)
2. **Username case:** registering "sebi" when "Sebi" exists is rejected; logging in as "SEBI" works and returns "Sebi". (Task 2 test.)
3. **Same account twice in one room:** a second phone joining without a seat token is rejected; the first phone's seat-token reconnect still works. (Task 4 test.)
4. **A stale session must not loop:** a 4401 close is final on the phone, clears the stored session, and doesn't retry. (Task 6 test.)
5. **Play again records twice, lobby records nothing more:** two games in one room are two records; going back to the lobby after a recorded game adds none. (Task 3 test.)

---

### Task 1: Database file and migrations

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/tests/test_db.py`
- Modify: `backend/tests/conftest.py` (autouse fixture setting `DB_PATH` to a tmp file)
- Modify: `.gitignore` (add `backend/data/`)

**Interfaces:**
- Produces: `open_db(path: str | os.PathLike) -> sqlite3.Connection`: creates parent dir, `check_same_thread=False`, `row_factory = sqlite3.Row`, `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=WAL`, runs `migrate(conn)`.
- Produces: `migrate(conn) -> None`: applies `MIGRATIONS[user_version:]` in order, each in a transaction, setting `PRAGMA user_version` after each.
- Produces: `MIGRATIONS: list[str]`; migration 1 creates:
  - `users(id INTEGER PRIMARY KEY, username TEXT NOT NULL, username_key TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at REAL NOT NULL)`
  - `sessions(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, created_at REAL NOT NULL)`
  - `games(id INTEGER PRIMARY KEY, game TEXT NOT NULL, players INTEGER NOT NULL, target INTEGER, ended_at REAL NOT NULL, how TEXT NOT NULL CHECK (how IN ('target','leave')), had_computer INTEGER NOT NULL)`
  - `game_seats(game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE, seat INTEGER NOT NULL, user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, computer INTEGER NOT NULL, side INTEGER NOT NULL, score INTEGER NOT NULL, won INTEGER NOT NULL, PRIMARY KEY (game_id, seat))`, index on `user_id`.
- Produces: `default_db_path() -> str`: `os.environ.get("DB_PATH")` or `backend/data/cards.db` resolved from this file.

- [ ] **Step 1: Write the failing tests** in `test_db.py`:
  - `test_a_new_database_gets_every_table`: `open_db(tmp_path / "x.db")`; `PRAGMA user_version` == `len(MIGRATIONS)`; the four tables exist in `sqlite_master`.
  - `test_migrate_only_applies_newer_migrations`: open, insert a user row, monkeypatch `MIGRATIONS` with an extra `"CREATE TABLE extra(x)"`, call `migrate`; the user row is still there, `extra` exists, `user_version` went up by 1.
  - `test_reopening_keeps_the_data`: open, insert a user, close, open again → the row is there.
  - `test_the_parent_folder_is_created`: `open_db(tmp_path / "a" / "b" / "x.db")` works.
- [ ] **Step 2:** Run `cd backend && py -3.12 -m pytest tests/test_db.py -v`. Expected: FAIL (no module `app.db`).
- [ ] **Step 3:** Implement `app/db.py` per Interfaces. Add the conftest autouse fixture `db_path(tmp_path, monkeypatch)` that sets `DB_PATH` to `tmp_path / "cards.db"`, so no test ever touches `backend/data/`.
- [ ] **Step 4:** Run `py -3.12 -m pytest -q`. Expected: all pass.
- [ ] **Step 5:** Commit `feat(db): SQLite file with numbered migrations`.

### Task 2: Accounts (hashing, register, login, sessions, limit, reset CLI)

**Files:**
- Create: `backend/app/accounts.py`
- Create: `backend/tests/test_accounts.py`

**Interfaces:**
- Consumes: `open_db`, the `users`/`sessions` tables (Task 1).
- Produces: `class AccountError(Exception)` with `.status: int` and a message; `class User(NamedTuple): id: int; username: str`.
- Produces: `hash_password(password: str) -> str` → `"scrypt$16384$8$1$<salt hex>$<hash hex>"` (16-byte salt, dklen 32); `check_password(password: str, stored: str) -> bool` reads the parameters from the string, compares with `hmac.compare_digest`.
- Produces: `class Accounts`, constructed `Accounts(conn, clock: Callable[[], float] = time.time)`:
  - `register(username: str, password: str) -> tuple[User, str]` (user, session token). Errors: bad username → 400 "Usernames are 3-20 letters, digits, . _ or -"; bad password → 400 "Passwords are 8-128 characters"; taken (any case) → 409 "That username is taken".
  - `login(username: str, password: str) -> tuple[User, str]`. Wrong user or password → 401 "Wrong username or password" (same message for both); 6th try after 5 failures within 600 s → 429 "Too many tries, wait a few minutes" (checked before the password). A success clears that username's failures.
  - `logout(token: str) -> None` (unknown token: no-op).
  - `user_for(token: str | None) -> User | None`.
  - `reset_password(username: str, password: str) -> None`: sets the hash, deletes all that user's sessions; unknown user → 404 "No such user".
- Produces: CLI `python -m app.accounts reset-password <username>`: asks for the new password twice with `getpass`, opens `default_db_path()`.
- Session tokens: `secrets.token_urlsafe(32)`.

- [ ] **Step 1: Write the failing tests** (`Accounts(open_db(tmp_path/"a.db"), clock=FakeClock())`; `FakeClock` from `tests.murlan_helpers` has `.now`):
  - `test_register_signs_you_in`: `user, token = register("Sebi", "hunter2!!")`; `user_for(token) == user`; `user.username == "Sebi"`.
  - `test_the_password_is_stored_hashed`: the `password_hash` column doesn't contain the password and starts with `"scrypt$"`; `check_password` is True for it, False for `"hunter2!?"`.
  - `test_usernames_are_unique_ignoring_case`: after "Sebi", `register("sebi", ...)` raises `AccountError` with status 409.
  - `test_login_ignores_case_and_returns_the_name_as_registered`: `login("SEBI", pw)[0].username == "Sebi"`.
  - `test_bad_usernames_and_passwords_are_rejected` (parametrized): `"ab"`, `"a"*21`, `"sp ace"`, `"émile"` → 400; passwords `"short"`, `"x"*129` → 400.
  - `test_wrong_password_and_unknown_user_say_the_same`: both 401 with equal messages.
  - `test_five_failures_lock_the_username_for_ten_minutes`: 5 wrong logins → 401 each; the 6th, even with the right password → 429; advance the clock 601 s → right password works.
  - `test_a_success_clears_the_failures`: 4 wrong, 1 right, 4 wrong → still 401 not 429.
  - `test_the_limit_is_per_username`: 5 failures for "Sebi" don't block "Arben".
  - `test_logout_ends_the_session`: after `logout(token)`, `user_for(token) is None`; logging out an unknown token doesn't raise.
  - `test_reset_password_signs_out_everywhere`: two sessions, reset → both `None`; the new password logs in, the old one doesn't.
- [ ] **Step 2:** Run `py -3.12 -m pytest tests/test_accounts.py -v`. Expected: FAIL (no module).
- [ ] **Step 3:** Implement `app/accounts.py` per Interfaces. Failures: `dict[str, deque[float]]` keyed by lowercased username, pruned to the last 600 s on each check.
- [ ] **Step 4:** Run `py -3.12 -m pytest -q`. Expected: all pass.
- [ ] **Step 5:** Commit `feat(accounts): register, login, sessions, login limit, password reset`.

### Task 3: Rooms record finished games

**Files:**
- Modify: `backend/app/murlan/game.py` (add `ended_by`)
- Modify: `backend/app/rooms.py` (`Player.user_id`, `Room.record`, recording in `act` and `leave`)
- Create: `backend/app/results.py` (the record types)
- Create: `backend/tests/test_room_results.py`

**Interfaces:**
- Produces in `game.py`: `Game.ended_by: Literal["target", "table"] | None = None`; set to `"target"` where `_finish_round` sets `game_over`, `"table"` in `decide(..., "end_game")`. No other change to the game.
- Produces in `results.py`:
  ```python
  @dataclass(frozen=True)
  class SeatResult:
      seat: int; user_id: int | None; computer: bool; side: int; score: int; won: bool

  @dataclass(frozen=True)
  class GameRecord:
      game: str; players: int; target: int | None; how: Literal["target", "leave"]; seats: tuple[SeatResult, ...]
  ```
  `score` is the seat's side score (team score in 4-player games).
- Produces in `rooms.py`: `Player.user_id: int | None = None`; `Room.record: Callable[[GameRecord], None] | None = None`; `RoomManager.__init__(..., record: Callable[[GameRecord], None] | None = None)` passes it to every room it creates.
- Rules (from the spec; "everyone connected" = `not game.disconnected and game.pause is None`):
  - In `Room.act`: if the phase was not `game_over` before `apply_action` and is after, and `game.ended_by == "target"` → record with `how="target"`, winners = `game.winner_side`. (`run_bot` goes through `act`, so computer moves are covered.)
  - In `Room.leave`, before the game is dropped: if a game is on, the leaver is seated and not a computer, `game.phase != "game_over"`, everyone is connected, and `max(game.scores) > 0` → leaver's side loses; among the other sides, a unique highest score wins and all others lose; a tie for that highest → nothing. `how="leave"`.
  - Everything else records nothing (End game after a pause, room expiry, restarts, lobby).
  - A `record` call that raises is caught and logged (`log.exception`); the room carries on.

- [ ] **Step 1: Write the failing tests** (rooms built with `RoomManager(clock=FakeClock(), record=records.append)`; drive the end of a game by rigging: `rig(room.game, hands, turn, target)` with `game.scores` one short of the target and the leader holding one card on their turn, then `room.act(leader, {"type": "play", "cards": [card]})`):
  - `test_reaching_the_target_records_the_game_once` (2 players): one record, `how == "target"`, `players == 2`, the leader `won`, the other not; acting again (e.g. a rejected move) records nothing more.
  - `test_a_four_player_win_counts_for_both_partners`: seats 0 and 2 `won`, `side` 0/1 as `game.side_of`, `score` is the team score.
  - `test_user_ids_and_computers_are_carried`: a signed-in player (set `player.user_id = 7`), a guest (`None`), a computer (`computer=True`, `user_id None`).
  - `test_a_computer_move_that_wins_is_recorded`: a game the computer wins through `run_bot` is recorded.
  - `test_leaving_hands_the_win_to_the_top_of_the_others` (3 players, scores `[5, 3, 1]`, p0 leaves): p1 wins; p0 and p2 lose; `how == "leave"`.
  - `test_the_leaver_loses_even_when_ahead` (2 players, scores `[4, 1]`, p0 leaves): p1 wins.
  - `test_a_four_player_leave_loses_for_the_leavers_team`: leaver's team scores higher, the other team still wins.
  - `test_leave_records_nothing` (parametrized): scores all 0; still choosing the target; top of the others tied (3 players `[5, 3, 3]`, p0 leaves); someone else disconnected (`room.mark_disconnected`); after `game_over`.
  - `test_end_game_after_a_pause_records_nothing`: disconnect, run out the pause on the clock, `game.tick()`, decider sends `decide end_game` through `room.act` → no record.
  - `test_play_again_records_each_game_and_the_lobby_none`: finish, `after_game play_again`, finish again → 2 records; then `after_game lobby` → still 2.
  - `test_a_failing_recorder_does_not_break_the_room`: `record` raises `RuntimeError`; the winning `act` doesn't raise and `room.game.phase == "game_over"`.
- [ ] **Step 2:** Run `py -3.12 -m pytest tests/test_room_results.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement per Interfaces. One private `Room._record(how: str, winners: set[int])` builds the `GameRecord` from `game.seats`, `self.players` and `game.scores`.
- [ ] **Step 4:** Run `py -3.12 -m pytest -q` (whole suite, including `test_no_view_ever_leaks_hidden_cards`). Expected: all pass.
- [ ] **Step 5:** Commit `feat(rooms): record finished games for stats`.

### Task 4: Stats, and the HTTP and WebSocket wiring

**Files:**
- Create: `backend/app/stats.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/rooms.py` (`Room.join` takes the signed-in user)
- Create: `backend/tests/test_stats.py`, `backend/tests/test_api_accounts.py`

**Interfaces:**
- Consumes: `Accounts`, `User`, `AccountError` (Task 2); `GameRecord` (Task 3); `open_db`, `default_db_path` (Task 1).
- Produces in `stats.py`:
  - `save_game(conn, record: GameRecord, ended_at: float) -> None`: one `games` row (`had_computer` = any seat computer) + one `game_seats` row per seat, in one transaction.
  - `stats_for(conn, username: str) -> dict | None` (`None` for an unknown user), shape:
    ```json
    {"username": "Sebi",
     "solo":  {"people": {"won": 0, "lost": 0}, "computer": {...}, "total": {...}},
     "teams": {"people": {...}, "computer": {...}, "total": {...}},
     "partners": [{"kind": "user", "name": "Arben", "won": 2, "lost": 4},
                  {"kind": "computer", "won": 11, "lost": 2},
                  {"kind": "guest", "won": 1, "lost": 0}]}
    ```
    Solo = 2- and 3-player games, teams = 4-player. "computer" = any seat other than the user's is a computer. Partner = seat `(seat + 2) % 4`. Partner rows: users by most games then name, then computer, then guest; rows with 0 games left out.
- Produces in `rooms.py`: `Room.join(name: str, token: str | None, user: User | None = None) -> Player`: a token match still returns the player first; else with `user`, the name is `user.username`, and if any player in the room has `user_id == user.id` → `JoinRejected(4409, "You're already at this table")`; the new player gets `user_id = user.id`.
- Produces in `main.py`: `create_app(manager=None, *, use_timers=True, db: sqlite3.Connection | None = None)`; default `open_db(default_db_path())`. Sets the manager's `record` to `lambda r: save_game(db, r, time.time())` (on the manager and on rooms it creates). CORS `allow_headers=["Content-Type", "Authorization"]`. Routes:
  - `POST /auth/register`, `POST /auth/login`: body `{username, password}` → `{"token", "username"}`; `AccountError` → `HTTPException(e.status, str(e))`.
  - `POST /auth/logout`: bearer token → `{}` (always 200).
  - `GET /me`: bearer → `{"username"}`, else 401 "Signed out".
  - `GET /stats/{username}` → `stats_for` or 404 "No such player".
  - WebSocket `?session=`: present and `user_for` is `None` → `await ws.close(4401, "Signed out")` before joining; else pass the user to `room.join`.

- [ ] **Step 1: Write the failing tests.**
  - `test_stats.py` (save records built by hand, then `stats_for`): `test_unknown_user_has_no_stats`; `test_solo_and_teams_are_kept_apart`; `test_a_computer_anywhere_else_counts_as_vs_computer` (incl. only the partner a computer); `test_guests_count_as_people`; `test_total_is_people_plus_computer`; `test_partners_by_account_then_computer_then_guest`; `test_saving_writes_one_row_per_seat` (guests and computers with `user_id NULL`).
  - `test_api_accounts.py` (`TestClient(create_app(RoomManager(), use_timers=False, db=open_db(tmp_path/"t.db")))`): `test_register_then_me`; `test_login_errors_come_back_as_detail` (409, 401, 429 with the spec's messages in `detail`); `test_logout_then_me_is_401`; `test_stats_endpoint_404_for_unknown`; `test_cors_allows_the_authorization_header` (preflight like `test_api.py::preflight`); `test_a_bad_session_closes_the_socket_with_4401`; `test_signed_in_players_sit_under_their_username` (`?name=whatever&session=<t>` → the player's name in `players` is the username); `test_one_account_once_per_room` (second socket with the same session, no token → close 4409; the first reconnects with its seat token fine); `test_a_finished_game_shows_in_stats` (two signed-in players over WebSocket, rig the game through `client.app` state or a manager passed in, win → `GET /stats/<winner>` shows `solo.people.won == 1`).
- [ ] **Step 2:** Run `py -3.12 -m pytest tests/test_stats.py tests/test_api_accounts.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement per Interfaces. The stats queries can be one SQL per user, folded in Python.
- [ ] **Step 4:** Run `py -3.12 -m pytest -q`. Expected: all pass, existing `test_api.py` / `test_websocket.py` unchanged.
- [ ] **Step 5:** Commit `feat(api): accounts, stats and signed-in seats`.

### Task 5: Mockups of the sign-in and stats sheets (user picks)

No code committed. Uses the brainstorming visual companion (`superpowers:brainstorming` → `visual-companion.md`).

- [ ] **Step 1:** Make 2-3 browser mockups each of: the main screen signed out (Sign in button) and signed in (username + Stats), the Sign in / Sign up sheet, and the Stats sheet (the spec's table + partners), in the existing sheet style and the current themes.
- [ ] **Step 2:** Show them to the user; note which they pick and any changes. Stop here until they've picked.

### Task 6: Frontend: session, sign-in sheet, stats sheet

**Files:**
- Modify: `frontend/js/storage.js`, `frontend/js/api.js`, `frontend/js/connection.js`, `frontend/js/main-view.js`, `frontend/js/app.js` (startup `/me` check, `onClosed` for 4401), `frontend/index.html`, `frontend/styles.css`
- Create: `frontend/js/account.js` (sign-in/up sheet and stats sheet)
- Test: `frontend/tests/storage.test.js`, `frontend/tests/connection.test.js`

**Interfaces:**
- Consumes: the HTTP routes and 4401 close from Task 4; the mockup the user picked in Task 5.
- Produces in `storage.js`: `getSession() -> {token, username} | null`, `setSession({token, username})`, `clearSession()`.
- Produces in `api.js`: `register(username, password)`, `login(username, password)` → `{token, username}`; `logout(token)`; `me(token)` → `{username}` (throws an error with `.status === 401` when signed out); `fetchStats(username)`; `socketUrl(code, name, token, session)` adds `session` when given.
- Produces in `connection.js`: `urlFor(code, name, token, session)` called with `this.store.getSession()?.token`; `FINAL[4401] = { message: 'You were signed out. Sign in again', forget: false, signedOut: true }`; on a `signedOut` close it calls `this.store.clearSession()` before `finish`.
- Behaviour: at startup a stored session is checked with `me`; 401 clears it, a network error keeps it. Signed in: the name field shows the username, read-only, and `hasName` passes; the Stats button opens the stats sheet for the user. Sign out lives in the Settings sheet (`logout` then `clearSession`, even if the request fails).

- [ ] **Step 1: Write the failing tests:** `storage.test.js`: `test('the session round-trips and clears')`, `test('a corrupted session reads as signed out')`. `connection.test.js`: `test('the session token goes into the socket URL')`; `test('4401 signs out and does not retry')` (store's session cleared, `onClosed` called once with the message, no second socket created).
- [ ] **Step 2:** Run `cd frontend && node --test`. Expected: the new tests FAIL.
- [ ] **Step 3:** Implement per Interfaces and the picked mockup. Every server string via `textContent`.
- [ ] **Step 4:** Run `node --test` and `for f in js/*.js; do node --check "$f"; done`. Expected: all pass, no syntax errors.
- [ ] **Step 5:** Commit the logic only (`storage.js`, `api.js`, `connection.js`, tests): `feat(frontend): sessions on the phone and the socket`. Leave the sheets, `index.html` and CSS uncommitted.
- [ ] **Step 6:** Restart the dev stack (`dev-stack-launch` memory: kill old pids, uvicorn without reload + `serve_frontend` in the background). Walk through sign up → play a game vs computer to the target → stats show 1 win in "vs computer"; sign out; stale session → signed out. Then hand it to the user to try on their phone; commit the visual part (`feat(frontend): sign in and stats sheets`) only after they approve.

### Task 7: Deploy notes and project docs

**Files:**
- Modify: `.claude/skills/deploy/SKILL.md`, `CLAUDE.md`

- [ ] **Step 1:** In the deploy skill: the VM layout gains `data/cards.db`; `docker-compose.yml` gets `volumes: - ./data:/data` and `environment: DB_PATH=/data/cards.db` (one-time, by hand, before the first deploy of this branch: `mkdir -p ~/apps/card-table/data/backups`); the nightly backup cron line (`sqlite3 /…/data/cards.db ".backup /…/data/backups/cards-$(date +\%F).db"` then delete files older than 14 days; install `sqlite3` on the VM if missing); the reset command `sudo docker exec -it card-table-backend python -m app.accounts reset-password <username>`; verify step adds `curl $HEALTH_URL/../stats/<a known username>` → 200 or 404 JSON.
- [ ] **Step 2:** In `CLAUDE.md`: under Invariants, a bullet "**Accounts and stats** live in a SQLite file (`DB_PATH`, `backend/app/db.py`); rooms stay in memory. `rooms.py` never does I/O: finished games go out as a `GameRecord` through `Room.record`. Guests play without an account." Also note the spec file name next to the others.
- [ ] **Step 3:** Commit `docs: accounts in the deploy notes and the project guide`.

### Task 8: Whole-branch check and PR

- [ ] **Step 1:** `cd backend && py -3.12 -m pytest -q`; `cd frontend && node --test`; `node --check` every `frontend/js/*.js`. All pass.
- [ ] **Step 2:** `git diff --stat origin/main` shows no CRLF churn (only intended files).
- [ ] **Step 3:** Push `feat/accounts-and-stats`, open one PR with `gh` as `yzeirbaku` (switch back afterwards). The PR body lists the by-hand VM steps from Task 7 and that deploying ends live games. The user merges and deploys.
