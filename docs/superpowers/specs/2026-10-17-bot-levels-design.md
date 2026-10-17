# Computer levels, one kind of table

Date: 2026-10-17. Status: approved in chat, spec under review.
Builds on: `2026-10-15-vs-computer-design.md` (the computer player) and
`2026-10-16-mixed-tables-design.md` (computers at a friends table). Replaces the
separate "vs computer" table from the first.

## Why

The computer player sometimes feels too weak and sometimes too strong. Three
levels let the table choose. While we're here, the two kinds of table (Friends
and Computer) become one: every table has a lobby, and the creator adds
computers there if they want them.

## One kind of table

- **New table sheet:** the Friends / Computer switch and its note go away.
  New table → Murlan → 2 / 3 / 4 always creates a room and opens its lobby.
- **Computers:** the room creator sees **+ 🤖 Computer** on every empty seat
  while at least one seat would still be left for a person, so up to
  `seats - 1` computers, at a table of any size (2-player included). They still
  take a place in the room: one can't be added when the people already in the
  room (seated or not) would no longer fit. ✕ removes one, in the lobby only.
  This replaces the "at least two people" rule.
- **Start:** unchanged. The game starts when the last seat is taken, whether a
  person or a computer takes it.
- **Alone with computers:** when the game has exactly one person in it, that
  person dropping out doesn't start the 2:00 countdown: the game just waits for
  them. With two or more people the countdown runs as today.
- **Game over:** Play again, Shuffle teams (4 players) and Back to the lobby,
  for every table. Back to the lobby keeps the computers seated (as today).
- **Gone:** `computer` on `POST /rooms` and on `Room`/`room_view`, and
  everything that hung off it: the prefilled seats, the straight-to-seat join,
  the one-person lock, "a table against the computer has no lobby", and the
  frontend's `computer` branches (the Leave button at game over, the leave
  sheet's wording, entering the room with `resume`). The leave sheet says
  "This ends the game for everyone." only when someone else is a person, else
  "This ends the game."
- `CLAUDE.md`'s "Computer players play fair" invariant is updated to match
  (no `computer=True` table; any table can seat computers, up to `seats - 1`).

## The level

- **One level per table**: Easy, Medium or Hard. New rooms start at **Medium**.
- **Lobby:** a **Computer level** row (Easy / Medium / Hard) above the seats.
  Everyone in the lobby sees it; only the creator can change it. It shows while
  the table has a computer or the creator could add one (so not at a full table
  of people).
- **Server:** `Room.level` (`"easy" | "medium" | "hard"`), sent as
  `room_view["level"]`. New client message, creator only, lobby only:
  `{"type": "set_level", "level": "easy" | "medium" | "hard"}`; anything else
  is rejected. Setting it updates every seated computer, and computers added
  later get it too.
- The level can't change during a game; Back to the lobby is where you change
  it.

## The computer at each level

One `Bot` class with a level setting, not three bots. Every level stays fair:
it decides from `view_for(game, its id)` and its own memory only. At every
level it goes out when it can and never makes an illegal move.

- **Hard:** today's bot, tuned. Its constants (`UNIT_COST`, `WEAK`,
  `SAVE_EARLY`, `SAVE_LATE`, `BOMB_SAVE`, `DANGER`) are tuned in self-play, and
  a few targeted improvements are tried: better swap gives, playing to a
  partner who is close to going out, and tighter counting of what the others
  can still hold. A change stays only if Hard with it beats today's bot over
  many self-play games; if nothing clearly helps, Hard is today's bot.
- **Medium:** Hard's play with a small mistake rate (about 1 move in 8 it takes
  a reasonable but worse option, such as its second-best play, or passing where
  it would have played) and a hazy memory (it forgets some of the cards it saw
  played, so it judges strength less well).
- **Easy:** a mistake about 1 move in 3, it forgets most of what was played,
  it doesn't fight harder when an opponent is about to go out, it sometimes
  beats its partner's play, and it gives a random allowed card in the swap.
- **Mistakes look human:** picked among the legal options, weighted toward the
  ones that are nearly as good, never something absurd like passing up the
  chance to go out. The mistake dice come from the bot's own RNG (seeded), so
  self-play stays reproducible; emojis keep their own separate dice.
- The exact mistake rates and memory loss are starting points, set in
  self-play to hit the strength targets below.

## Testing

- **Strength (self-play, 2 players, a few hundred games each):** Hard beats
  Medium and Medium beats Easy, each in about 60-70% of games, so the levels
  feel clearly different without Easy being hopeless. Tuned Hard beats today's
  bot (if it can't, Hard is today's bot and the targets apply to that).
- **Every level, 2, 3 and 4 players:** whole self-play games where no move is
  ever rejected and every game ends.
- **Bot:** at every level it always goes out when it can; Easy/Medium mistakes
  are legal moves; views still never leak
  (`test_no_view_ever_leaks_hidden_cards`).
- **Rooms:** `set_level` creator only, lobby only, valid values only, applied to
  seated and later computers; adding computers up to `seats - 1` (2-player
  included) and not past room capacity; a computer filling the last seat starts
  the game; no countdown only when exactly one person is in the game; Back to
  the lobby for every table, computers keep their seats; creator and
  `decider()` never a computer. `test_rooms_computer.py` folds into the
  mixed-table tests.
- **Frontend (`node --test`):** the new-table sheet has no Friends / Computer
  switch; the level row shows, is tappable only for the creator, and sends
  `set_level`.
