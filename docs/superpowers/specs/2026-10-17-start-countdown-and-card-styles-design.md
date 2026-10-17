# Start countdown, Atlas and Modern cards

Date: 2026-10-17. Status: approved, built.

## Start countdown

Filling the last seat used to throw everyone straight onto the table.

- When the last seat is taken (by a person or a computer), the server sets
  `Room.starts_at` 3 seconds ahead (`START_SECONDS`) and sends
  `room_view["starting_in"]` (seconds left, else `null`). The room stays
  `lobby`; the room timer wakes it at `starts_at` and the game starts
  (`Room.start_if_due`), so every phone and the computers agree on the moment.
- A seat freed meanwhile (a seated player leaves, the creator removes a
  computer) calls it off. Nobody can change seats then (all are taken), and the
  level can still change. Play again / Shuffle teams start at once, as before.
- Lobby: a dimmed, blurred overlay with a big gold 3 · 2 · 1 and
  "Game starting…"; taps go through it (Leave, ✕ on a computer).
- Tests: `tests/conftest.py` sets the countdown to 0 so existing tests keep
  starting at once; the countdown tests ask for it with
  `RoomManager(start_seconds=...)`.

## Atlas and Modern card styles

Two more card styles beside Traditional and Vintage, picked from mockups of
real decks (Aisleriot's vector decks; Dondorf was too low-resolution, Guyenne
has no corner indices, Ancient French uses V/D/R):

- **Atlas:** the Russian "satin" deck (Charlemagne, 1862) with English indices
  and jokers (Aisleriot `atlasnye.svg`, LGPL 3, from Dmitry Fomin's CC0 deck).
- **Modern:** flat graphic courts by Charles Esquiaqui (Aisleriot
  `neoclassical.svg`, LGPL 3 / CC BY 4.0).
- `scripts/build_card_styles.py` renders each sheet (pinned commit), cuts the
  cards along their edges and scales them to 320 x 466 into
  `frontend/cards/atlas/` and `frontend/cards/modern/`. Credits and licences in
  `frontend/cards/CREDITS.txt`, and a credits line under Cards in Settings.
- `cardImage(code, style)` picks the folder; `useCardStyle` (dom.js) switches
  every face shown (`img[data-card]`, the main screen's cards included) and
  preloads that style's pictures. Settings shows the four styles two by two,
  each tile with its K♥.
