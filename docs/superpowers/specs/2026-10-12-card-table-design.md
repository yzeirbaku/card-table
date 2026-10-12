# Card Table — design

Date: 2026-10-12
Status: approved in brainstorming, pending spec review

## Purpose

A multiplayer mobile card app for a group of friends. Players share one deck
on a virtual table and play whatever game they want — the app does not enforce
rules, just like a real deck of cards. Games the group plays often can be saved
to a shared library (rules + a setup per player count) so next time you pick
"Murlan, 3 players" and the table is dealt for you.

Not a product. Success = a real game night works with it, both remote and in
the same room, and handling cards feels native on a phone.

Personal project: lives in `~/projects/card-table`, local git only for now —
no GitHub repo until the author decides they like it in practice.

## Stack

- **App:** Expo (React Native, TypeScript). Developed and tried in Expo Go on
  iPhone (no Apple Developer account needed). Uses only Expo Go–compatible
  libraries: react-native-gesture-handler, react-native-reanimated,
  expo-haptics, expo-secure-store.
- **Backend:** FastAPI, Python 3.12. One process serves both the WebSocket room
  engine and the HTTP API.
- **Database:** Neon Postgres (local Postgres via docker compose for dev),
  schema bootstrapped idempotently on boot like sibling projects.
- **Hosting (later):** Docker on the existing Oracle Cloud Always-Free VM,
  behind the shared Caddy (WebSockets proxied natively), on a DuckDNS
  subdomain. During development the backend runs on the PC and the phone
  connects over Wi-Fi.

**Invariant:** live rooms live in process memory, so the backend runs as a
single uvicorn worker. A restart drops live rooms (saved games/stats are safe in
Postgres). Don't deploy during game night.

## Repo layout

```
card-table/
├── app/        Expo app (TypeScript)
├── backend/    FastAPI (Python)
└── docs/
```

## Table model

**Everything is a pile.** A single card on the table is a pile of one.

- Pile: `id`, `x`, `y` (fractions 0–1 of table size, so layout is identical on
  every screen size), `layout` (`stack` | `fan`), ordered `cards`.
- Card: `id`, `rank`, `suit` (or joker), `faceUp`.
- Each player has a **hand**: a private pile visible only to its owner.

The table is shown identically to everyone (not rotated per seat). Player
avatars sit around the table edge with a hand-count badge.

### Gestures

| Gesture | Result |
|---|---|
| Drag top card of a pile to empty table | Creates a new pile |
| Drag a card onto a pile | Adds it on top (snaps) |
| Long-press then drag | Moves the whole pile |
| Tap a card | Flips it |
| Drag between hand and table | Plays / picks up |
| Drag within hand | Reorders hand |
| Drop a card on a player avatar | Passes it into their hand |
| Long-press without dragging | Pile menu: shuffle, flip all, stack/fan, deal N to each player, take all into hand |

Table menu: "Gather everything and shuffle".

Feel: lift/scale on pickup, snap on drop, light haptics on pickup, drop and
shuffle; Reanimated animations.

Out of v1: card rotation, multiple decks, dice/chips, general move undo.

## Room engine (server-authoritative)

- Clients send **actions** (move, flip, shuffle, deal, take, pass, gather,
  reorder hand). The server validates (e.g. the card is still where the client
  thinks it is), applies them in arrival order, and broadcasts.
- The server sends each player **their own view**: other players' hands are
  reduced to a count; face-down cards carry no rank/suit. Hidden card identities
  never leave the server. Shuffling happens server-side.
- Clients apply their own action optimistically; if the server rejects it
  (someone else got there first), the client reverts to the server state.
- The engine is pure Python (action + state → new state; state + player →
  view), separate from the WebSocket transport, so it is unit-testable.

### Rooms

- 4-letter join code; 2–6 players.
- Room expires 2 hours after last activity.
- Creator is host; if the host leaves, the next player becomes host. The host
  picks the game (or freeform) in the lobby.
- **Reconnect:** on joining, the client receives a seat token stored on the
  phone. Reconnecting with it restores the same seat and hand. Disconnected
  players show greyed out; their cards stay put.

## Games library

Shared by everyone using the app.

- **Game:** `name`, `rules` (plain text, includes the win condition),
  `creator` (account), optional `variant_of` (game it was copied from).
- **Setup:** belongs to one game and one player count (2–6):
  - deck: number of jokers (0/1/2), ranks to remove
  - deal: N cards per player, or "deal all" (cards that don't divide evenly
    stay in the deck pile)
  - table piles: list of {name, contents ("rest of deck" or N cards),
    face up/down, stack/fan}
  - notes: free text (e.g. "holder of 3♣ starts") — shown, not enforced

Starting a room with a game + player count that has a setup deals the table
automatically. If no setup exists for that count, the setup form is shown;
filling it requires an account. "Save current table as setup" pre-fills the form
from the live table, for review before saving.

### Permissions

| Action | Who |
|---|---|
| Play any game | Everyone, including guests |
| Create a game | Account holders |
| Edit a game's rules or existing setups | The game's creator only |
| Add a setup for a missing player count | Any account holder (append-only) |
| Copy a game as own variant | Any account holder |

## Accounts

- Optional. Guests just enter a display name.
- Username + password (bcrypt). No email, no self-service reset.
- Session token stored in expo-secure-store.

## Rounds and stats

- "End round" can be tapped by any player. The game's rules (with win
  condition) are shown; the player picks the winner(s). Everyone sees the
  result and anyone can undo it within 10 seconds.
- Saved: game, timestamp, participants (account ids or guest names), winners.
- Account holders see win rate per game on their profile. Guests appear in
  results but accumulate no stats.
- Freeform rounds (no game picked) are not recorded.
- Ending a round does not touch the table; the next round starts with "Deal
  again" (gather, shuffle, apply the setup) or a manual gather.

## App screens

1. **Home** — create room, join by code, optional login.
2. **Lobby** — players gather; host picks game or freeform; setup form if the
   player count is new for that game.
3. **Table** — shared table on top, own hand fanned at bottom, rules one tap
   away, table menu.
4. **End round** — win condition shown, pick winner(s), 10 s undo.
5. **Library & profile** — browse games, view/edit rules and setups, own stats.

## Testing

- **Room engine:** thorough pytest — every action type, ordering conflicts,
  dealing from setups, reconnect. Key test: **no player's view ever contains
  another player's hand cards or a face-down card's identity.**
- **API:** a few pytest cases focused on permissions (non-creator can't edit
  rules; guests can't create; append-only setup adding).
- **App:** manual testing on iPhone in Expo Go.

## Not in v1

In-app chat (wanted later), AI referee that understands the saved rules
(optional per game, later), spectators, big-screen/tablet table mode, push
notifications, GitHub repo and VM deployment (until the author decides to keep
it).
