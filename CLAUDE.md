# card-table — Claude guide

Personal project: card games for friends, one game at a time. Vanilla-JS PWA
(`frontend/`, no build step) + FastAPI (`backend/`). Specs in
`docs/superpowers/specs/`; the current one is `2026-10-14-pwa-conversion-design.md`.
Murlan (the first game) gets its own spec next.

## Invariants (don't undo)

- **Server is authoritative; the frontend has no game logic.** It renders
  whatever `state` the server sends.
- **Hidden info never leaves the server.** All state goes out through
  `backend/app/engine/views.py::view_for`. Card ids are re-issued when a card
  enters a hand or a pile is shuffled/gathered, so ids can't track hidden cards.
  `tests/test_views.py::test_no_view_ever_leaks_hidden_cards` guards this.
- **Single uvicorn worker.** Live rooms are in memory; a restart drops them.
- Rooms: `lobby` until the last seat fills, then `playing`; leaving drops back
  to `lobby`. Games and their player ranges live in `backend/app/games.py`.
- Frontend: no npm dependencies and no bundler. `frontend/package.json` only
  makes Node treat `.js` as ES modules for `node --test`.
- Names and anything from the server go into the DOM via `textContent`, never
  `innerHTML`.
- Dev ports: backend 8020, frontend 5520 (`scripts/dev_up.py`).

## Git

Remote: `origin` = https://github.com/yzeirbaku/card-table (personal account
`yzeirbaku`, via the stored git credentials, not the `gh` CLI, which is logged in
to a work account). Commit as `Yzeir Baku <yzeirbaku@hotmail.com>` (set in
local config). No feature branches: commit and push straight to `main`.
