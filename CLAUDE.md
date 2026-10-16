# card-table — Claude guide

Personal project: card games for friends, one game at a time. Vanilla-JS PWA
(`frontend/`, no build step) + FastAPI (`backend/`). Specs in
`docs/superpowers/specs/`: the PWA shell is `2026-10-14-pwa-conversion-design.md`,
Murlan (the first game) is `2026-10-14-murlan-design.md`.

## Invariants (don't undo)

- **Server is authoritative; the frontend has no game logic.** It renders
  whatever `state` the server sends and turns taps into messages.
- **Hidden info never leaves the server.** All game state goes out through
  `backend/app/murlan/views.py::view_for`. Cards are codes (`"10H"`, `"JR"`); a
  code reaches a player only if it's in their hand, on the pile, in a public
  reveal that is still running, the cut card shown to the cutter, or thrown face
  up by someone who gave up the round (public for the rest of that round, and
  kept with its result like the round's last trick). How
  many cards the others hold isn't sent either.
  `tests/test_murlan_views.py::test_no_view_ever_leaks_hidden_cards` guards this.
- **Single uvicorn worker.** Live rooms are in memory; a restart drops them.
- **The Murlan game is pure Python** (`backend/app/murlan/game.py`): injected
  clock and RNG, no I/O. Timed events (reveals, the 2:00 pause) run off
  `game.deadline()` / `game.tick()`; `app/timers.py` wakes the room for them.
- Rooms: players join unseated and tap a seat; the room is `lobby` until every
  seat is taken, then the game starts (`playing`). Leaving ends the game and
  drops back to `lobby`. Games and their player ranges live in `backend/app/games.py`.
- **Computer players play fair.** A computer table (`computer=True`, spec
  `2026-10-15-vs-computer-design.md`) seats them from the start. The bot
  (`backend/app/murlan/bot.py`) decides only from `view_for(game, its id)` plus
  its memory of earlier views; it never reads the `Game`. Its moves go through
  `apply_action` like anyone's, timed by `Room.update_bots` / `run_bot`.
  Strength is checked by self-play (`tests/murlan_selfplay.py`). At a friends
  table of 3-4 the creator can seat computers too (a mixed table, at least two
  people; spec `2026-10-16-mixed-tables-design.md`); computers never become
  creator or `decider()`. Their emojis come from what their view shows.
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
