# Friends and invites

Date: 2026-11-02. Status: approved 2026-11-02.
Builds on: `2026-10-30-accounts-and-stats-design.md` (accounts, sessions, Profile page).

## Why

Getting a game going means sharing a room code outside the app: copy it, switch
to a chat, paste, and wait for friends to open the app and type it. Now that
players have accounts, the app can know who your friends are and call them to
the table itself, with a notification on their phone.

## Goals

- Add friends by username; they accept or decline.
- From the lobby, invite friends to the table with one tap.
- The invited friend gets a **push notification**, even with the app closed.
  Tapping it opens the app straight into that room's lobby.
- An invite is also visible inside the app, for phones without notifications.

## Non-goals

- Showing who is online or in a game.
- Chat, messages, or any notification other than invites and friend requests.
- Inviting people who aren't friends, or guests.
- Blocking or reporting. These are friends; Remove friend is enough.
- Native apps or Firebase. This is the existing PWA.

## Anti-goals

- **Guests keep working exactly as today**, and the room code stays: sharing it
  outside the app still works.
- No notification spam: invites come only from accepted friends, and only to
  phones where the person turned notifications on. The one push from a
  non-friend, a friend request, is limited (see Push notifications).
- Nothing here touches the game or what `view_for` sends.
- The app never asks for notification permission unprompted. It asks only after
  the player taps to turn notifications on.

## Friends

- **Mutual.** A friend request is sent by exact username (any case). The other
  person accepts or declines. Once accepted, both are friends.
- Sending a request to someone who has already sent you one accepts theirs.
- **Decline** is silent: the sender's request just stays "Sent" until they
  cancel it. *My call:* a declined request is deleted, so the sender may ask
  again later.
- **Remove friend:** either side, silent, ends it for both.
- Also: an **Add friend** button on another player's page (opened from the
  leaderboard or partners list in Profile). It shows Friends / Request sent /
  Accept depending on the state.
- Limits (*my call*): 200 friends and 50 outgoing pending requests per account.

### Tables (migration 2)

- `friendships`: user_a, user_b (a < b), since. Primary key (user_a, user_b).
- `friend_requests`: from_user, to_user, created_at. Primary key
  (from_user, to_user).
- `push_subscriptions`: endpoint (unique), user_id, session (the hashed
  session token, `REFERENCES sessions ON DELETE CASCADE`), p256dh, auth,
  created_at. One account can have several devices. *My call:* tied to the
  session, so a phone whose session is gone (signed out, password reset) stops
  getting pushes with no extra step.

All with `ON DELETE CASCADE` on the user.

### Endpoints (all need the session)

- `GET /friends` → `{friends: [username...], incoming: [...], outgoing: [...]}`,
  friends sorted by name.
- `POST /friends/requests` `{username}`: send, or accept if they had asked you.
  Errors: no such user, yourself, already friends, limits.
- `POST /friends/requests/{username}/accept`, `.../decline`,
  `DELETE /friends/requests/{username}` (cancel your own).
- `DELETE /friends/{username}`: remove.
- CORS `allow_methods` gains `DELETE`.

## Invites

- **Who can invite:** any signed-in player in the room while it's in the
  `lobby` and has room for one more (`len(players) < seats`: computers and
  people who haven't sat down yet both take a place). Never from a game in
  progress. Guests see no invite button.
- **Computers don't step aside.** The button shows only while there's room.
  A table whose seats are all filled, by people or computers, starts its
  countdown anyway, so there's nothing to invite into.
- **Where:** an **Invite friends** button in the lobby, next to the room code.
  It opens a sheet with your friends; each row has **Invite**, which turns into
  **Invited ✓**. Friends already in this room show as **Here** with no button.
- **What the friend gets:**
  - a push notification on each of their subscribed devices: title
    "Arben invited you", body "Murlan, 4 players". Tapping it opens the app and
    joins the room (unseated, then they tap a seat, as today);
  - and an in-app invite, for when they have no notifications: on the main
    screen, an **envelope button** in the top-left corner ("✉ Invites" with a
    red count), opposite the account chip. It is there only while invites are
    waiting. Tapping it opens a bottom sheet, **Invites**, with a row per
    invite (inviter, game and player count, ✕ to dismiss, **Join**). If the
    app is open when the invite arrives, the envelope appears without a
    notification popping up over it.
- **Invites live in memory**, next to the rooms (rooms are in memory anyway;
  a restart drops both). One invite per (room, friend): inviting again
  replaces it and pushes again. *My call:* re-inviting the same friend to the
  same room is allowed once every 30 seconds.
- **An invite disappears** when the room is gone, starts a game, has no free
  seat, the friend joins it, the friend dismisses it, or after 15 minutes
  (*my call*). If it went stale while the notification was still on the phone,
  tapping it opens the app and shows the usual join error ("That table is
  full", etc.), then the main screen.
- **Already at another table:** if the friend taps an invite (notification or
  card) while in another room, the app asks first: "You're at <their table's
  game>. Leave it and join Arben's table?" with **Stay** as the default
  button. Stay keeps them where they are. Leave goes through the normal Leave
  (so leaving a running game ends it and counts as a leave, as today), then
  joins. On a fresh start, `?join=` wins over resuming the stored room only
  after the same question; Stay resumes the stored room.
- *My call:* an invite that disappeared because the room filled is gone for
  good, even if a place frees up again. Invite again.
- `GET /invites` → `[{from, game, players, code}]` for the signed-in player,
  fetched when the main screen shows and when the app comes back to the front.
  `POST /invites/{code}/dismiss`.
- `POST /rooms/{code}/invite` `{username}`, with the session. The server checks:
  the inviter is in that room, signed in, it's a friend, the room is in the
  lobby with a free seat, the friend isn't already in it.

## Push notifications

Standard **Web Push** with VAPID: the browser's own push service (Apple,
Google, Mozilla), no Firebase, no account with anyone.

- **Keys:** one VAPID key pair, generated once
  (`python -m app.push generate-keys`), set on the VM in `.env` as
  `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`
  (`mailto:yzeirbaku@hotmail.com`). Without keys (dev, tests) pushing is off and
  everything else works, invites included, in-app only.
- **Library** (*my call*): `pywebpush` on the backend, since the encryption is
  not something to hand-roll. Sending is blocking HTTP, so it runs in a worker
  thread and never holds a room's lock. A failure is logged and ignored. A
  `404`/`410` from the push service means the subscription is dead: delete it.
- `GET /push/key` → the public key. `POST /push/subscribe` (session +
  the browser's subscription JSON) upserts by endpoint, so a phone that signs in
  as someone else and turns notifications on moves to that account. *My call:*
  signing in never subscribes by itself, even when the browser permission is
  already granted; each account turns it on with the button. `POST /push/unsubscribe` `{endpoint}`.
  **Sign out** unsubscribes this phone first.
- **Turning it on:** a row in Profile → Friends, "Notifications for invites:
  Turn on". Tapping asks the browser for permission, subscribes, and sends it to
  the server. Shown as On once subscribed. Off unsubscribes.
  - iPhone in Safari (not added to the home screen): push isn't possible there.
    The row says "Add Card Table to your Home Screen to get invites", nothing
    to tap.
  - Permission denied: "Notifications are blocked for this app in your phone's
    settings".
- **What gets pushed:** an invite, and an incoming friend request ("Sebi wants
  to be friends", tap opens Profile → Friends). Nothing else. *My call:* a
  friend request pushes at most once per sender per 24 hours (in memory), so
  request, cancel, request again can't be used to buzz someone.
- **Payload:** `{type, from, game, players, code}` (encrypted by Web Push).
  Only things the invited person is allowed to see anyway. Notification `tag`
  is the room code, so a re-invite replaces the old notification.
- **Service worker** (`frontend/service-worker.js`) gets `push` and
  `notificationclick` handlers:
  - `push`: if an app window is visible **on the main screen**, post the invite
    to it (it shows the envelope) and show no notification; otherwise (closed,
    in the background, or in a lobby or at the table) show the notification.
    *My call:* no extra invite UI in the lobby or table views. *Note for
    the builder:* iOS may revoke the subscription if a push shows nothing too
    often; if testing shows that, always show the notification and let the open
    app close it.
  - `notificationclick`: focus an open app window and tell it to join the
    room, or open `/?join=<code>` (and `/?friends` for a friend request).
- The app reads `?join=<code>` at start (after the session restore), joins that
  room signed in, then removes the parameter from the address bar. Signed out:
  just the main screen with the code filled into the Join sheet.
- `frontend/_headers`: `Cache-Control: no-cache` on `/service-worker.js`, so
  phones pick up the new worker. `connect-src` needs nothing new (subscribing
  goes through the browser, not a fetch).

## Frontend

- **Profile** gains a third tab, **Friends**: the notifications row, an
  "Add friend" field, incoming requests (Accept / Decline), friends
  (tap → their player page; Remove there), sent requests (Cancel).
- **Lobby:** the Invite friends button and sheet.
- **Main screen:** the envelope button and the Invites sheet (option E,
  picked 2026-11-02). A red dot on the account chip while a friend request
  is waiting.
- **Profile → Friends tab, lobby Invite friends button and sheet, the
  "Join Arben's table?" question, the friend button on a player's page:** as
  in the mockups approved 2026-11-02.
- Mockups: `.superpowers/brainstorm/868-1793612296/content/`
  (`friends-invites.html`, `main-invites.html`; not committed). Nothing visual
  is committed until the user has tried it in the app.
- Everything from the server goes in with `textContent`.

## Delivery

One PR, on top of the accounts PR (`feat/accounts-and-stats`; rebase onto `main`
once that merges): migration, backend, frontend, service worker, tests, and the
deploy notes (VAPID keys in the VM `.env`, the `pywebpush` dependency) in the
deploy skill.

## Tests

- Friends: request, accept, request-back-accepts, decline, cancel, remove,
  any case, yourself, limits, needs a session.
- Invites: only friends, only from inside the room, only in the lobby with a
  free seat, already-here, re-invite throttle, disappears on start / full /
  join / dismiss / room gone / 15 min.
- Push: subscribe upsert moves a phone between accounts, a 410 deletes the
  subscription, no keys means no sending, sending never runs under the room
  lock (a fake sender).
- Frontend: `?join=` handling, the Invites sheet render (`node --test`), and
  `node --check` on every file.
- Existing tests, including `test_no_view_ever_leaks_hidden_cards`, pass
  unchanged.

## Left to the builder

Module layout (e.g. `app/friends.py`, `app/push.py`, invites in `rooms.py` or
their own module), exact column names, error messages, how the main screen
learns of an invite while open (polling `/invites` on focus is enough; the
service worker message covers live ones).
