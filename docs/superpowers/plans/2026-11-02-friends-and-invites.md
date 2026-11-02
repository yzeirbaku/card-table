# Friends and Invites Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Signed-in players add each other as friends, invite friends from the lobby with one tap, and the friend gets a Web Push notification (and an envelope on the main screen) that opens the app in that lobby.

**Architecture:** Friends and push subscriptions are new SQLite tables (migration 2) behind two small modules, `app/friends.py` and `app/push.py`. Invites live in memory next to the rooms (`app/invites.py`), pruned on every room broadcast. The frontend gets a Friends tab, an Invite friends sheet in the lobby, an envelope plus Invites sheet on the main screen, and a service worker that shows pushes.

**Tech Stack:** FastAPI, sqlite3, `pywebpush` (new, pinned), vanilla-JS ES modules, Web Push API, `node --test`.

**Spec:** `docs/superpowers/specs/2026-11-02-friends-and-invites-design.md`. Approved mockups: `.superpowers/brainstorm/868-1793612296/content/friends-invites.html` and `main-invites.html` (option E, the envelope). Copy the new CSS from there.

## Global Constraints

- Branch `feat/friends-and-invites` (already created from `main`; the spec is committed). Commit as configured; end every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. **Don't push**: the user tries everything in the app first.
- Repo files are LF. Use the Edit tool, or `open(p, 'w', newline='')`. Check `git diff --stat` before every commit.
- Backend tests: `cd backend && .venv/Scripts/python -m pytest -q tests/<file>`. Frontend tests: `cd frontend && node --test`. Before every commit that touches frontend JS, also run `for f in frontend/js/*.js frontend/service-worker.js; do node --check "$f"; done`.
- Server text goes into the DOM with `textContent` only, never `innerHTML`.
- Guests are untouched: no new button or request appears for a phone without a session.
- Nothing here changes `view_for` or the game. `test_no_view_ever_leaks_hidden_cards` and the rest of the suite keep passing.
- Refused requests raise `AccountError(status, message)` (from `app/accounts.py`). `main.py` already turns that into `HTTPException`, and the frontend shows `detail` as a toast.
- Limits and timings: 200 friends, 50 outgoing requests, re-invite the same friend to the same room once per **30 s**, an invite lasts **15 min** (`900` s), a friend-request push goes at most once per sender per recipient per **24 h** (`86400` s).
- Copy fixed by the spec and mockups: notification titles `"<from> invited you"` / body `"<Game>, <n> players"`, `"<from> wants to be friends"` / `"Tap to answer"`. Main-screen button `✉ Invites` plus a red count. Sheet titles `Invites`, `Invite friends`. Lobby button `＋ Invite friends`. Friend row tags `Invited ✓`, `Here`. Player page: `＋ Add friend`, `Request sent`, `Accept request`, `✓ Friends`, `Remove friend`. Question: title `Join <from>'s table?`, buttons `Stay` (default, gold) and `Leave and join` (red).

## Review Focus

1. **A table that filled and then emptied again:** the invite must not come back. Test `test_invite_gone_for_good_once_the_table_filled` (Task 4).
2. **One phone, two accounts:** after B turns notifications on, an invite for A must not reach that phone. Test `test_subscribe_moves_a_phone_to_the_new_account` (Task 3).
3. **Signed out or password reset:** the phone gets no more pushes. Test `test_signing_out_stops_pushes_to_that_phone` (Task 3).
4. **Tapping an invite to the table you're already at:** nothing happens, no question. Test `inviteAction` → `'stay'` (Task 8).
5. **Usernames in any case** (`sebi` vs `Sebi`), in requests, invites and the "Here" tag. Tests `test_requests_ignore_case` (Task 1) and `inviteRows` (Task 7).

---

### Task 1: Friends in the database

**Files:**
- Modify: `backend/app/db.py` (append migration 2 to `MIGRATIONS`)
- Modify: `backend/app/accounts.py` (public `session_key`)
- Create: `backend/app/friends.py`
- Test: `backend/tests/test_friends.py`, `backend/tests/test_db.py` (version now 2)

**Interfaces:**
- Produces: in `app/accounts.py`, `session_key(token: str) -> str`, the stored (hashed) form of a session, which is today's `_digest`. Keep `_digest` as an alias or rename its callers.
- Produces: in `app/friends.py`, `MAX_FRIENDS = 200`, `MAX_OUTGOING = 50`, and `class Friends(conn, clock=time.time)` with:
  - `user_named(username: str) -> User | None` (any case)
  - `overview(user: User) -> dict` → `{"friends": [str], "incoming": [str], "outgoing": [str]}`, usernames as registered, each list sorted case-insensitively
  - `request(user: User, username: str) -> tuple[Literal["sent", "accepted"], User]`
  - `accept(user, username) -> None`, `decline(user, username) -> None`, `cancel(user, username) -> None`, `remove(user, username) -> None`
  - `are_friends(a_id: int, b_id: int) -> bool`

- [ ] **Step 1: Write the failing tests** in `tests/test_friends.py`. Use the `Accounts(open_db(tmp_path / "t.db"))` and `asyncio.run(accounts.register(...))` setup that `tests/test_accounts.py` uses for users. Tests:
  - `test_request_then_accept`: A requests B → `("sent", B)`. `overview(A)["outgoing"] == ["B"]`, `overview(B)["incoming"] == ["A"]`. `accept(B, "A")` makes both `friends == [other]`, empties the request lists, and `are_friends(a.id, b.id)` holds both ways.
  - `test_request_back_accepts`: A requests B, then B requests A → `"accepted"`, and they are friends.
  - `test_requests_ignore_case`: `request(A, "sEbI")` reaches Sebi, and the overview shows `"Sebi"`.
  - `test_refusals`: unknown name → `AccountError` 404 `"No such player"`. Yourself → 400 `"That's you"`. Already friends → 409 `"You're already friends"`. Accepting a request that doesn't exist → 404 `"No request from <name>"`.
  - `test_request_twice_is_quiet`: a second request to the same person returns `"sent"`, with still one row.
  - `test_decline_cancel_remove`: decline deletes the request (the sender can ask again), cancel deletes your own request, remove ends the friendship for both. All three are quiet when there's nothing to delete.
  - `test_limits`: with `MAX_OUTGOING` monkeypatched to 2, a third outgoing request is refused with 409 `"Too many requests waiting for an answer"`. With `MAX_FRIENDS` patched to 1, a request or accept that would pass it is refused with 409 `"<name> has too many friends"` or `"You have too many friends"`.
  - `test_deleting_a_user_cascades`: `DELETE FROM users` leaves no friendship or request rows.
  - In `tests/test_db.py`, update the version assertion to 2 and assert the three new tables exist.

- [ ] **Step 2: Run them and watch them fail.** `.venv/Scripts/python -m pytest -q tests/test_friends.py tests/test_db.py`. Expected: ImportError / assertion failures.

- [ ] **Step 3: Implement.** Migration 2 is one script appended to `MIGRATIONS`:
  ```sql
  CREATE TABLE friendships (
      user_a INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      user_b INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      since REAL NOT NULL,
      PRIMARY KEY (user_a, user_b),
      CHECK (user_a < user_b)
  );
  CREATE INDEX friendships_b ON friendships (user_b);
  CREATE TABLE friend_requests (
      from_user INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      to_user INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      created_at REAL NOT NULL,
      PRIMARY KEY (from_user, to_user)
  );
  CREATE INDEX friend_requests_to ON friend_requests (to_user);
  CREATE TABLE push_subscriptions (
      endpoint TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      session TEXT NOT NULL REFERENCES sessions(token) ON DELETE CASCADE,
      p256dh TEXT NOT NULL,
      auth TEXT NOT NULL,
      created_at REAL NOT NULL
  );
  ```
  `Friends` follows `Accounts`' style: plain `conn.execute`, and `BEGIN`/`COMMIT` around accepting (delete the request, insert the friendship). A friendship is stored with `user_a = min(ids)`.

- [ ] **Step 4: Run the tests** (same command). Expected: PASS.

- [ ] **Step 5: Commit**: `feat(friends): friendships and requests in the database`.

---

### Task 2: Friends over HTTP

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api_friends.py`

**Interfaces:**
- Consumes: `Friends` (Task 1).
- Produces, all with `Authorization: Bearer <session>`, and 401 `"Signed out"` without a valid session:
  - `GET /friends` → overview
  - `POST /friends/requests` `{"username"}` → `{"result": "sent"|"accepted", **overview}`
  - `POST /friends/requests/{username}/accept` and `.../decline` → overview
  - `DELETE /friends/requests/{username}` (cancel) → overview
  - `DELETE /friends/{username}` → overview
- Produces: `current_user(authorization: str | None) -> User`, an inner helper in `create_app` that raises 401. Later endpoints use it.
- CORS `allow_methods=["GET", "POST", "DELETE"]`.

- [ ] **Step 1: Write the failing tests.** Reuse `client`, `register` and `bearer` from `tests/test_api_accounts.py` (import them, as that file imports from `test_websocket`).
  - `test_friend_flow_over_http`: request, accept, then both `GET /friends` show each other.
  - `test_friends_need_a_session`: each endpoint returns 401 without the header.
  - `test_refusal_detail`: a request to an unknown name returns `(404, "No such player")`.
  - `test_cors_allows_delete`: a preflight for `DELETE` from a dev origin is allowed (copy the pattern of `test_cors_allows_the_authorization_header`).

- [ ] **Step 2: Run, expect failures.** `pytest -q tests/test_api_friends.py`.

- [ ] **Step 3: Implement the endpoints** in `create_app`, with `friends = Friends(db)`. The request body model is `class Username(BaseModel): username: str = Field(max_length=20)`.

- [ ] **Step 4: Run** `pytest -q tests/test_api_friends.py tests/test_api_accounts.py`. Expected: PASS.

- [ ] **Step 5: Commit**: `feat(friends): friend requests over HTTP`.

---

### Task 3: Push subscriptions and sending

**Files:**
- Create: `backend/app/push.py`
- Modify: `backend/app/main.py`, `backend/requirements.txt` (`pywebpush==2.0.3`; if pip can't find that version, pin the newest 2.x and say so in the commit)
- Test: `backend/tests/test_push.py`

**Interfaces:**
- Consumes: `session_key` (Task 1), `current_user` (Task 2).
- Produces: in `app/push.py`:
  - `@dataclass(frozen=True) class PushKeys: public: str; private: str; subject: str`
  - `keys_from_env() -> PushKeys | None`, from `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` and `VAPID_SUBJECT` (default `mailto:yzeirbaku@hotmail.com`); `None` unless both keys are set
  - `Sender = Callable[[dict, str, PushKeys], int]`, which sends one push and returns the HTTP status (0 on a network error)
  - `send_webpush(info: dict, data: str, keys: PushKeys) -> int`: `pywebpush.webpush(subscription_info=info, data=data, vapid_private_key=keys.private, vapid_claims={"sub": keys.subject}, ttl=900, timeout=10)`, returning `response.status_code`. On `WebPushException` it returns the exception's response status, or 0.
  - `class Push(conn, keys: PushKeys | None, send: Sender = send_webpush, clock=time.time)` with:
    - `subscribe(user: User, session_token: str, sub: dict) -> None`: upsert by endpoint, so the row moves to this user and this session. Raises 400 `"Bad subscription"` unless `endpoint` is an `https://` string of at most 1000 characters and `keys.p256dh` / `keys.auth` are non-empty strings.
    - `unsubscribe(endpoint: str) -> None`
    - `is_on(session_token: str, endpoint: str) -> bool`
    - `async notify(user_id: int, payload: dict) -> None`: does nothing without keys. Otherwise, for each of the user's subscriptions, calls `await asyncio.to_thread(send, info, json.dumps(payload), keys)`. A 404 or 410 deletes that subscription; any other failure is logged and ignored.
    - `allow_once(key: tuple, seconds: float) -> bool`: in-memory throttle, True the first time within `seconds`
  - CLI `python -m app.push generate-keys`: generates a P-256 key with `cryptography` (a `pywebpush` dependency) and prints `VAPID_PUBLIC_KEY=<base64url of the 65-byte uncompressed point>` and `VAPID_PRIVATE_KEY=<base64url of the 32-byte private value>`, both without padding
- Produces: `create_app(..., push_keys: PushKeys | None | EllipsisType = ..., push_send: Sender | None = None)`. `...` means `keys_from_env()`. Endpoints:
  - `GET /push/key` → `{"key": str | None}`
  - `POST /push/subscribe` `{"subscription": {...}}` (session) → `{}`
  - `POST /push/unsubscribe` `{"endpoint"}` → `{}`
  - `POST /push/status` `{"endpoint"}` (session) → `{"on": bool}`
- Wires the friend-request push: when `POST /friends/requests` returns `"sent"` and `push.allow_once(("request", user.id, target.id), 86400)` holds, `await push.notify(target.id, {"type": "request", "from": user.username})`.

- [ ] **Step 1: Write the failing tests.** Use a fake sender that records `(endpoint, json.loads(data))` and returns a status you set per endpoint. Use `PushKeys("pub", "priv", "mailto:t@example.com")`.
  - `test_notify_sends_to_every_device_of_that_user`
  - `test_a_gone_subscription_is_deleted`: the sender returns 410, and the row is gone afterwards.
  - `test_no_keys_sends_nothing`
  - `test_bad_subscription_refused`: an `http://` endpoint, missing keys, or an over-long endpoint.
  - `test_subscribe_moves_a_phone_to_the_new_account`: A subscribes endpoint E, then B subscribes E. `notify(A)` sends nothing and `notify(B)` sends to E.
  - `test_signing_out_stops_pushes_to_that_phone`: subscribe, then `accounts.logout(token)`, and `notify` sends nothing. The same holds after `reset_password`.
  - `test_allow_once`: with an injected clock, True, False, then True again after `seconds`.
  - `test_friend_request_push_once_a_day` (over HTTP): request, cancel, request again → one push, `{"type": "request", "from": "A"}`.
  - `test_push_endpoints`: `/push/key` returns `"pub"`, `subscribe` then `status` returns `{"on": true}`, and `unsubscribe` then `status` returns `{"on": false}`.
  - `test_generated_keys_work_with_pywebpush`: run the CLI's key function, then `py_vapid.Vapid.from_string(private)` loads and the public key decodes to 65 bytes starting with `0x04`.

- [ ] **Step 2: Run, expect failures.** `pip install -r requirements.txt` into `.venv` first, then `pytest -q tests/test_push.py`.

- [ ] **Step 3: Implement** `app/push.py` and the endpoints.

- [ ] **Step 4: Run** `pytest -q tests/test_push.py tests/test_api_friends.py`. Expected: PASS.

- [ ] **Step 5: Commit**: `feat(push): Web Push subscriptions, tied to the session`.

---

### Task 4: Invites

**Files:**
- Create: `backend/app/invites.py`
- Modify: `backend/app/rooms.py` (`Room.open_to`), `backend/app/main.py`
- Test: `backend/tests/test_invites.py` (unit), `backend/tests/test_api_invites.py`

**Interfaces:**
- Consumes: `Friends.are_friends` and `user_named`, `Push.notify`, `current_user`.
- Produces: `Room.open_to(user_id: int) -> bool`: `self.game is None and len(self.players) < self.seats and no player has that user_id`.
- Produces: in `app/invites.py`, `INVITE_SECONDS = 900`, `REINVITE_SECONDS = 30`, and:
  - `@dataclass class Invite: code: str; from_name: str; to_id: int; game: str; players: int; sent_at: float`, where `game` is the display name (`GAMES[id].name`)
  - `class Invites(clock)`, keyed by `(code, to_id)`, with:
    - `add(invite) -> bool`: False if the same key was sent less than 30 s ago; otherwise replaces it
    - `pending(user_id, is_open: Callable[[str, int], bool]) -> list[Invite]`: drops expired invites and those `is_open` refuses, then returns the rest newest first
    - `dismiss(user_id, code) -> None`
    - `prune(code, keep: Callable[[int], bool]) -> None`: drops every invite for `code` whose `to_id` fails `keep`
- Produces: endpoints
  - `POST /rooms/{code}/invite` `{"username"}` (session) → `{}`. Refusals, checked in this order:
    1. 404 `"Table not found"`
    2. 403 `"You're not at this table"`
    3. 404 `"No such player"`
    4. 403 `"Only friends can be invited"`
    5. 409 `"The game has started"`
    6. 409 `"<name> is already here"`
    7. 409 `"The table is full"`
    8. 429 `"Invited just now, wait a moment"`

    On success it sends the push: `{"type": "invite", "from", "game", "players", "code"}`.
  - `GET /invites` (session) → `[{"from", "game", "players", "code"}]`
  - `POST /invites/{code}/dismiss` (session) → `{}`
- In `broadcast(room)`, after sending: `invites.prune(room.code, room.open_to)`. In `close_expired`, for each purged room: `invites.prune(room.code, lambda _: False)`. `pending`'s `is_open` is `lambda code, uid: (r := rooms.get(code)) is not None and r.open_to(uid)`.

- [ ] **Step 1: Write the failing tests.**
  - Unit: `test_reinvite_throttled_then_replaced`, `test_expires_after_15_minutes`, `test_dismiss`, `test_prune`.
  - API, with the fake sender from Task 3:
    - `test_invite_a_friend_from_the_lobby`: A creates a room and joins signed in, A invites B. B's `GET /invites` returns `[{"from": "A", "game": "Murlan", "players": 4, "code": code}]`, and one push went to B.
    - `test_only_friends_and_only_from_inside`: covers refusals 2 and 4.
    - `test_invite_disappears_when_the_friend_joins`
    - `test_invite_disappears_when_the_game_starts`: fill the seats with computers.
    - `test_invite_gone_for_good_once_the_table_filled`: a third person fills a 2-seat lobby and then leaves. B's invite stays gone.
    - `test_invite_disappears_when_the_room_expires`: advance the manager clock past `IDLE_EXPIRY_SECONDS` and trigger `close_expired` via `POST /rooms`.
    - `test_already_here_and_started_refusals`
    - `test_invite_names_ignore_case`: `{"username": "b"}` works.
    - `test_invites_need_a_session`

    Use `connect(...)` from `test_api_accounts.py` to sit people at a table.

- [ ] **Step 2: Run, expect failures.** `pytest -q tests/test_invites.py tests/test_api_invites.py`.

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run the whole backend suite**: `pytest -q`. Expected: all pass (the self-play tests are slow; let them finish).

- [ ] **Step 5: Commit**: `feat(invites): invite friends from the lobby, with a push`.

---

### Task 5: Frontend plumbing: API calls, push helpers, service worker

**Files:**
- Modify: `frontend/js/api.js`, `frontend/service-worker.js`, `frontend/_headers`
- Create: `frontend/js/push.js`, `frontend/js/social.js`
- Test: `frontend/tests/push.test.js`, `frontend/tests/social.test.js`

**Interfaces:**
- Produces: in `api.js`, all taking the session token first where the server needs one:
  - `fetchFriends(token)`, `requestFriend(token, username)`, `acceptFriend(token, username)`, `declineFriend(token, username)`, `cancelRequest(token, username)`, `removeFriend(token, username)`. Each resolves to the overview (`requestFriend` also has `.result`).
  - `inviteFriend(token, code, username)`, `fetchInvites(token)`, `dismissInvite(token, code)`
  - `fetchPushKey()`, `pushSubscribe(token, subscription)`, `pushUnsubscribe(endpoint)`, `pushStatus(token, endpoint)`
- Produces: in `push.js`:
  - `pushSupport(env = globalThis) -> 'ok' | 'ios-browser' | 'unsupported' | 'blocked'`
    - `'ios-browser'`: iPhone or iPad user agent, no `PushManager`, and not standalone (`navigator.standalone !== true` and `matchMedia('(display-mode: standalone)')` doesn't match)
    - `'blocked'`: `Notification.permission === 'denied'`
  - `keyBytes(base64url: string) -> Uint8Array`
  - `async pushIsOn(token) -> boolean`
  - `async turnPushOn(token) -> boolean` (false if permission isn't granted)
  - `async turnPushOff(token) -> void`: unsubscribes in the browser, then on the server, best effort
- Produces: in `social.js` (pure, no DOM):
  - `relationOf(overview, name) -> 'friends' | 'sent' | 'incoming' | 'none'` (any case)
  - `canInvite(state, signedIn) -> boolean`: signed in, `room.status === 'lobby'` and `players.length < room.seats`
  - `inviteRows(friends, state) -> [{ name, here: boolean }]`, `here` meaning a non-computer player with that name in any case
  - `inviteAction({ signedIn, currentCode, target }) -> 'signin' | 'stay' | 'join' | 'ask'`
  - `readLaunch(search) -> { join: string | null, from: string | null, friends: boolean }`, using `cleanCode` / `isCompleteCode` from `code.js`. A bad code gives `join: null`.
- Service worker:
  - `push`: parse `event.data.json()`. Show the notification (titles and bodies from Global Constraints, `icon: '/icons/icon-192.png'`). Use `tag` `invite-<code>` or `request-<from>`, and `data.url` `/?join=<code>&from=<from>` or `/?friends`. Then post `{ type: 'push', payload, tag }` to every window client.
  - `notificationclick`: close the notification. Then focus the first window client and post `{ type: 'open', url }` to it, or `clients.openWindow(url)` if there is none.
- `_headers`: add a `/service-worker.js` block with `Cache-Control: no-cache`.

- [ ] **Step 1: Write the failing tests.**
  - `keyBytes` round trip.
  - `pushSupport` with fake envs: Android Chrome → `'ok'`, iPhone Safari tab → `'ios-browser'`, iPhone standalone with PushManager → `'ok'`, denied → `'blocked'`, no serviceWorker on desktop → `'unsupported'`.
  - `relationOf` in all four states and any case.
  - `canInvite`: a guest → false, playing → false, full → false.
  - `inviteRows`: `"sebi"` in the room marks friend `"Sebi"` as here; a computer named like a friend doesn't.
  - `inviteAction`: signed out → `'signin'`, no current room → `'join'`, same code → `'stay'`, another code → `'ask'`.
  - `readLaunch`: `'?join=kq7m&from=Arben'`, `'?friends'`, `'?join=12'` → `join: null`.

- [ ] **Step 2: Run, expect failures.** `cd frontend && node --test`.

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run** `node --test` and `node --check` on every file (Global Constraints). Expected: PASS, no output from `--check`.

- [ ] **Step 5: Commit**: `feat(frontend): friends and push API calls, service worker shows invites`.

---

### Task 6: Profile → Friends tab and the friend button on a player's page

**Files:**
- Create: `frontend/js/friends.js`
- Modify: `frontend/index.html` (Friends tab and pane, `.friend-state` in `.profile-who`, `#btn-remove-friend` in the player pane, `.chip-dot` in `#btn-account`, a page-level `#page-confirm`), `frontend/js/account.js`, `frontend/js/ui.js`, `frontend/styles.css`

**Interfaces:**
- Consumes: Task 5's API calls, `push.js` and `relationOf`.
- Produces: `ui.js` `askConfirm({ title, text, stay, go }) -> Promise<boolean>`, which shows `#page-confirm`. It's a `.confirm` with `position: fixed; z-index: 30`, reuses `.confirm-box`, puts the gold `stay` button first, and resolves `true` only on `go`.
- Produces: `friends.js` `initFriends({ store, openPlayer, onChange })` returning:
  - `load()`: fetches the overview
  - `overview()`: the last one fetched
  - `render()`: fills the Friends pane
  - `act(kind, name)`: `kind` is one of `'request'`, `'accept'`, `'decline'`, `'cancel'` or `'remove'`; it updates and re-renders
- Produces: `account.js`'s return object gains `openProfile(tab)` (used by `?friends` in Task 8).
- The Friends pane, top to bottom, as in the mockup:
  1. The notifications row: text per `pushSupport` and `pushIsOn`; Turn on / Turn off call `turnPushOn` / `turnPushOff`.
  2. The Add field, submitting `act('request', value)`. Toast `Request sent to <name>`, or `You and <name> are friends now` for `"accepted"`.
  3. Requests (Decline / Accept).
  4. Friends (tap → `openPlayer`).
  5. Sent (Cancel).

  Headings are hidden when their list is empty.
- The tab label shows `.count-badge` with `incoming.length` when it's above 0. The chip dot shows while `incoming.length > 0`; `load()` runs on sign-in, in `check()`, and when the profile opens.
- On the player page, `.friend-state` follows `relationOf`:
  - `'none'`: gold `＋ Add friend` button
  - `'sent'`: `Request sent`, disabled
  - `'incoming'`: gold `Accept request`
  - `'friends'`: `✓ Friends`, not a button

  `#btn-remove-friend` shows only for `'friends'` and asks `askConfirm({ title: 'Remove <name>?', text: "You'll stop being friends. They aren't told.", stay: 'Keep', go: 'Remove' })`.
- Sign out first awaits `turnPushOff(token)` (best effort, at most 3 s), then does today's sign-out.

- [ ] **Step 1: Implement** the markup, styles (from `friends-invites.html` groups 5 and 6) and code.
- [ ] **Step 2: Check** `node --test` and `node --check` on every file.
- [ ] **Step 3: Try it on the dev stack** (memory `dev-stack-launch`: uvicorn without reload, plus `serve_frontend.py`, each as its own background Bash). Use two browsers, signed in as two accounts: send, accept, decline, cancel, remove, the badge and dot, the player-page button in every state. Push needs keys: run `python -m app.push generate-keys` and set them in the backend's environment for the dev run. Chrome on localhost can subscribe.
- [ ] **Step 4: Commit**: `feat(frontend): Friends tab, friend button on a player's page`.

---

### Task 7: Lobby → Invite friends

**Files:**
- Create: `frontend/js/invite-friends.js`
- Modify: `frontend/index.html` (`#btn-lobby-invite` under the plaque, `#sheet-invite`), `frontend/js/lobby-view.js`, `frontend/js/app.js`, `frontend/styles.css`

**Interfaces:**
- Consumes: `canInvite`, `inviteRows`, `fetchFriends`, `inviteFriend`.
- Produces: `invite-friends.js` `initInviteFriends({ store })` → `{ open(state) }`.
- `renderLobby` toggles `#btn-lobby-invite` with `canInvite(state, Boolean(store.getSession()))`; `initLobby` takes the store, or a `signedIn()` callback.
- The sheet:
  - Sub-line: `<Game> · <seats - players.length> seats free. They get a notification.` (`seat` when it's 1).
  - One row per friend from `inviteRows`: `Here` tag, or an `Invite` button. On success the button becomes `Invited ✓` (disabled) for as long as the sheet is open; a refusal shows a toast with `detail`.
  - With no friends: `You haven't added any friends yet. Add them in your Profile, under Friends, or share the table code.`
  - The open sheet re-renders its rows on every lobby state, so a friend who arrives turns into `Here`. It closes when the game starts (`render` already closes sheets for the rules).

- [ ] **Step 1: Implement** (styles from `friends-invites.html` group 2).
- [ ] **Step 2: Check** `node --test` and `node --check` on every file.
- [ ] **Step 3: Try it on the dev stack** with two accounts. Check:
  - The button shows only when signed in with a free seat, and disappears when the last seat is taken.
  - `Invited ✓`.
  - The 30 s re-invite toast.
  - `Here` after the friend joins.
- [ ] **Step 4: Commit**: `feat(frontend): invite friends from the lobby`.

---

### Task 8: Main screen: envelope, Invites sheet, opening from a notification

**Files:**
- Create: `frontend/js/invites.js`
- Modify: `frontend/index.html` (`#btn-invites` in `#view-main`, `#sheet-invites`), `frontend/js/app.js`, `frontend/js/main-view.js` (export a way to open the Join sheet with a code filled in), `frontend/js/ui.js` (`onViewShown(fn)` hook called by `showView`), `frontend/styles.css`

**Interfaces:**
- Consumes: `fetchInvites`, `dismissInvite`, `inviteAction`, `readLaunch`, `askConfirm`, `account.openProfile`.
- Produces: `invites.js` `initInvites({ store, onJoin })` → `{ refresh() }`:
  - `#btn-invites` (top-left, `✉ Invites` + `.badge` count) is hidden unless at least one invite is pending.
  - It opens `#sheet-invites`, with one row per invite: ring with the initial, the name, `<game> · <n> players`, ✕ (dismiss), and gold `Join` → `onJoin(code, from)`.
  - `refresh()` runs on: the main view shown, `visibilitychange` to visible, sign-in and sign-out (signed out hides the button), and a service-worker `push` message.
- `app.js` gets `goToInvite(code, from)`, following `inviteAction`:
  - `'signin'`: the main screen with the Join sheet open and the code filled in
  - `'stay'`: nothing
  - `'join'`: `enterRoom(code)`
  - `'ask'`: `askConfirm({ title: \`Join ${from ?? 'the other'}'s table?\`, ... })`. The text is `You're in a game of <Game>. Leaving ends it for everyone at this table.` while the last state is `playing`, otherwise `You'll leave the table you're at.` Buttons `Stay` / `Leave and join`. On go: `leaveRoom()`, then `enterRoom(code)`.

  When `from` is missing the title is `Join the other table?`.
- Startup:
  1. `readLaunch(location.search)`, then `history.replaceState` to `/`.
  2. `friends` → `account.openProfile('friends')`.
  3. `join` with a resumable stored room: resume it, and run `goToInvite` after the first state arrives. That way the question knows whether a game is on, and Stay simply stays.
  4. `join` without one: `goToInvite` right away.
- Service-worker messages:
  - `{type: 'open', url}` → apply `readLaunch` to that URL the same way.
  - `{type: 'push', tag}` → `invites.refresh()`; if the main view is showing and the page is visible, close the notification with that tag (`registration.getNotifications({ tag })`).

- [ ] **Step 1: Implement** (styles from `main-invites.html` option E: `.env-btn`, `.badge`; the sheet rows reuse `.friend-row`).
- [ ] **Step 2: Check** `node --test` and `node --check` on every file.
- [ ] **Step 3: Try it on the dev stack**:
  - The envelope appears or disappears as invites come and go.
  - Join and ✕.
  - `?join=CODE&from=X` signed in, signed out, and while at another table (both texts, Stay resumes).
  - `?friends`.
  - A real push in desktop Chrome with keys set: the notification shows; with the app on the main screen it closes and the envelope appears.
- [ ] **Step 4: Commit**: `feat(frontend): invites on the main screen, open the app from a notification`.

---

### Task 9: Deploy notes, docs, final check, user try-out

**Files:**
- Modify: `.claude/skills/deploy/SKILL.md`, `CLAUDE.md`

- [ ] **Step 1: Write the deploy notes.** In `SKILL.md`, add a one-time "Push notifications" setup:
  - Generate keys on the VM: `sudo docker exec card-table-backend python -m app.push generate-keys`. The first deploy with this code must already be built, so run it after the image rebuild, then restart.
  - Add `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` and `VAPID_SUBJECT=mailto:yzeirbaku@hotmail.com` to `~/apps/card-table/.env`. Check that the compose file passes `.env` into the container; add `env_file: .env` if it only interpolates.
  - **Never change the keys afterwards:** every phone's subscription would silently stop working.
  - `pywebpush` is a new dependency; the image rebuild installs it.
- [ ] **Step 2: Update `CLAUDE.md`.** Add one bullet under Invariants: friends and push subscriptions are in SQLite (migration 2); invites live in memory next to the rooms; pushes carry only the invite (`from`, game, players, code); spec `2026-11-02-friends-and-invites-design.md`.
- [ ] **Step 3: Run everything:** `cd backend && .venv/Scripts/python -m pytest -q`, `cd frontend && node --test`, and `node --check` on every file. Expected: all pass.
- [ ] **Step 4: Commit**: `docs: deploy notes and CLAUDE.md for friends and invites`.
- [ ] **Step 5: Hand it to the user** to try on the running dev stack (phone over Wi-Fi for the layout; push only works on localhost or https, so test push on the desktop browser). Push the branch and open the PR as `yzeirbaku` only after they approve (`gh auth switch -u yzeirbaku`, then switch back).
