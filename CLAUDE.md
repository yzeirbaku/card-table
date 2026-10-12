# card-table — Claude guide

Personal project: shared-deck card app for friends. Spec:
`docs/superpowers/specs/2026-10-12-card-table-design.md`. Plan 1 (playable
table) is done; Plan 2 adds accounts, games library, setups, stats.

## Invariants (don't undo)

- **Server is authoritative; the app has no game logic.** The app turns gestures
  into actions and renders whatever state the server sends back.
- **Hidden info never leaves the server.** All state goes out through
  `backend/app/engine/views.py::view_for`. Card ids are re-issued when a card
  enters a hand or a pile is shuffled/gathered, so ids can't track hidden cards.
  `tests/test_views.py::test_no_view_ever_leaks_hidden_cards` guards this.
- **Single uvicorn worker.** Live rooms are in memory; a restart drops them.
- `app/src/protocol.ts` mirrors `backend/app/engine/protocol.py` + `views.py` by
  hand. Change both together.
- Dragged cards/piles are hidden with `opacity: 0`, never unmounted — unmounting
  a GestureDetector mid-drag cancels the gesture.
- App is Expo SDK 57; read `app/AGENTS.md` before touching Expo APIs.

## Git

Local only — no remote yet. Commit as `Yzeir Baku <yzeirbaku@hotmail.com>`
(set in local config). Never push without asking.
