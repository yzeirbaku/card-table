# Card Table — PWA conversion design

Date: 2026-10-14
Status: approved in brainstorming, pending spec review

## Why

Card Table started as an Expo app for a free-form shared deck ("make your own
rules"). Two changes of direction:

1. **Web, not native.** It becomes a PWA like the author's other projects
   (net-tracker, gold-price-tracker, formicarium): vanilla JS in `frontend/`,
   installable from the browser, runnable locally.
2. **Real games, one at a time.** The free-form sandbox is dropped. Games are
   added one by one, each with its rules enforced by the server. The first is
   **Murlan** (Albanian shedding game), designed in its own spec after we go
   over the rules together.

This spec covers step 1 only: the PWA shell, the look (themes and cards), the
main screen, rooms with a chosen game and player count, the lobby, and an empty
landscape table. No cards are dealt yet; Murlan fills the table in.

It supersedes the old design's Stack, App screens, Games library, Accounts and
Rounds/stats sections (`2026-10-12-card-table-design.md`). Accounts, the shared
games library, setups and stats are dropped for now.

Success: on the PC and on a phone over Wi-Fi, friends can create a Murlan room,
join by code, and land together on the themed landscape table.

## Stack and layout

```
card-table/
├── backend/    FastAPI (unchanged stack, single worker, in-memory rooms)
├── frontend/   vanilla-JS PWA, no build step
├── scripts/    dev_up.py, dev_down.py, build_cards.py
└── docs/
```

- **`app/` (Expo) is deleted.**
- `frontend/`: `index.html`, `styles.css`, ES modules, `config.js`,
  `manifest.webmanifest`, minimal `service-worker.js` (no caching, required for
  install), `_headers` (CSP for Cloudflare Pages later), `icons/`, `cards/`.
- One page, three views (main, lobby, table) switched by the app; no router.
- **The free-form engine stays in the backend untouched** for now (it still
  builds a table per room; the new frontend ignores it). The Murlan spec
  replaces it, including re-establishing the hidden-information invariant.

### Running locally

- `python scripts/dev_up.py` starts the backend on **:8020** and a static
  server for `frontend/` on **:5520**, both bound to `0.0.0.0` so phones on the
  same Wi-Fi can open `http://<pc-lan-ip>:5520`. It prints both the localhost
  and LAN URLs, opens the browser, and writes pids to `.dev/pids.json`.
  `python scripts/dev_down.py` stops both. Ports avoid clashing with sibling
  projects.
- `config.js` defaults the backend to the same hostname the page was loaded
  from, port 8020 (`ws:`/`http:` or `wss:`/`https:` matching the page), so a
  phone needs no configuration. Cloudflare Pages can overwrite it at deploy
  time, as in the sibling repos.
- README is rewritten for the new setup.

## Look

### Card artwork

- Faces are **Byron Knoll's Vector Playing Cards** (public domain; mirror at
  github.com/notpeter/Vector-Playing-Cards): English pattern, real court
  figures, standard pip layouts, indices in both corners.
- Replaced with our own art, drawn to match the deck:
  - **Ace of spades:** a plain large spade (the deck's ace of spades has
    unclear provenance).
  - **Jokers:** the **jester** design (cap with three bells, red/black/gold,
    "JOKER" in opposite corners): red-capped for the red joker, black-capped
    for the black one. The deck's own text-only jokers aren't used. The
    jester figure sits centred, with equal space to both corner labels.
- `scripts/build_cards.py` converts the SVGs once into WebP (≈320 px wide,
  ≈20–40 KB each) under `frontend/cards/` (`AS.webp`, `10H.webp`,
  `joker-red.webp`, …). The output is committed; the script is re-run only if
  the art changes. Its Python deps (resvg-py, Pillow) are dev-only.
- **Card styles** (a setting):
  - **Traditional:** the images as-is on white.
  - **Vintage:** the same images with a CSS treatment: warm paper
    background `#f3e8cf`, `filter: sepia(.38) saturate(.85) contrast(.96)
    brightness(.98)`, and a soft multiply vignette toward the edges.
- No four-colour suits.

### Table themes (a setting)

Each theme defines the table surface, card back, name plates, buttons and
small props. The card face style is independent of the theme.

| Theme | Surface | Card back | Name plates / buttons | Props |
|---|---|---|---|---|
| **Classic felt** (default) | green felt radial gradient, wooden rim | red diagonal stripes, white border | dark translucent plates, gold counts; gold Play, outlined Pass | — |
| **Qëndisje** (Albanian) | cream linen cloth over walnut, red cross-stitch diamond border | red with black lattice, cream border | dark plates, gold counts; red / black buttons | Turkish coffee cup |
| **Kafeneio** (Greek) | white marble tabletop, blue-white checked runner across the middle | terracotta with black meander | navy plates; blue / white-outlined buttons | coffee cup, water glass |

Themes are implemented as CSS (custom properties + a theme class on `<body>`);
props are small CSS-drawn elements placed in corners away from seats.

## Screens and flow

### Main screen (portrait)

Classic felt background (always, regardless of theme), "Card Table" title in
gold serif, **Your name** field (saved on the device), then three real cards
laid on the felt with gold labels underneath:

- **A♥ — New table** → sheet: (1) pick game (from `GET /games`; only Murlan
  now), (2) pick player count (buttons for that game's allowed counts), then the
  room is created and the player goes to the lobby.
- **A♣ — Join** → sheet with one 4-letter code box (input cleaned: uppercased,
  spaces stripped) and a **Paste** button shown only where
  `navigator.clipboard.readText` is available (secure contexts); otherwise the
  user long-presses to paste.
- **Jester Joker — Settings** → sheet with the three theme swatches and a
  Traditional / Vintage switch. Applies immediately; saved on the device.

Name is required (1–20 characters) before New table or Join.

### Lobby (portrait)

Game name, the **room code in large letters** with a small **Copy** button
(`navigator.clipboard.writeText`, falling back to a hidden-textarea
`execCommand('copy')` on plain-http LAN pages; shows "Copied ✓"), seat list
("Yzeir ✓, Arben ✓, waiting…, waiting…" with a 2/4 count), and **Leave**. The
host has no special controls.

**When the last seat fills, the room starts automatically** and every player
switches to the table.

### Table (landscape)

The chosen theme fills the screen. You sit at the bottom; opponents are placed
clockwise around the top/left/right in seat order relative to you (2 players:
across; 3: left and right; 4: left, across, right). Each seat shows name,
connected indicator and card count. Middle play area and bottom hand area are
empty for now. ☰ menu with **Leave**.

**Orientation:** iOS web apps can't lock orientation, so when the table is
shown and the viewport is portrait, the table layout is rotated 90° with CSS so
it reads correctly with the phone held sideways (this also works with iOS
rotation lock on). On landscape viewports (desktop, sideways phones) it renders
normally. The main screen and lobby stay portrait-only in design but remain
usable in landscape.

### Reconnect and errors

- The seat token is saved per room code in `localStorage`. Reloading, losing
  signal or reopening the app rejoins the same seat (lobby or table). While the
  socket is down, a small "Reconnecting…" banner shows and the app retries with
  backoff.
- Toasts for: room not found, room full, game already started, invalid name,
  backend unreachable.

## Backend changes

- **`app/games.py`**: registry of game info `{id, name, min_players,
  max_players}`. Initially `murlan`, "Murlan", 2–4 (to be confirmed in the
  Murlan spec). `GET /games` returns the list.
- **`POST /rooms`** takes `{"game": str, "players": int}`; `400` with a message
  for unknown game or out-of-range count; returns `{"code"}`.
- **`Room`** gains `game`, `seats`, `status` (`"lobby" | "playing"`).
  `MAX_PLAYERS` is replaced by `seats`.
  - Join with a valid token: always reconnects, any status.
  - New player: rejected `4409 "Room is full"` when all seats are taken, and
    `4409 "Game already started"` while `playing`.
  - The join that fills the last seat sets `status = "playing"`.
  - Leave in lobby frees the seat. Leave while playing frees the seat and sets
    `status = "lobby"` (Murlan will refine). A dropped connection keeps the seat.
- **State message** gains `"room": {"game", "seats", "status"}`; the rest is
  unchanged.
- **CORS:** `CORSMiddleware` allowing origins on port 5520 from localhost,
  127.0.0.1 and private-network addresses (10.x, 172.16–31.x, 192.168.x),
  configurable via an env var for the future Pages domain.

## Testing

- **Backend (pytest):** create room valid/invalid game and count; `GET /games`;
  filling seats flips to `playing`; full and already-started rejections;
  token reconnect while playing; leave in lobby vs. while playing; CORS header
  for an allowed and a disallowed origin. All existing tests stay green.
- **Frontend (`node --test`, no dependencies):** pure modules for seat
  placement relative to you, whether to rotate, code input cleanup, settings and
  token storage.
- **End to end:** drive the real flow in the browser (create → lobby → second
  tab joins → both on the table) for each theme and card style; then the author
  tries it on a phone over Wi-Fi.

## Out of scope

Murlan rules and cards in play (next spec), accounts, games library, stats,
in-app chat, deployment (Cloudflare Pages + VM), offline caching.
