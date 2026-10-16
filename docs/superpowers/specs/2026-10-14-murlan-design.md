# Murlan — design

Date: 2026-10-14
Status: rules agreed with the author in brainstorming; pending spec review
Builds on: `2026-10-14-pwa-conversion-design.md` (PWA shell, rooms, lobby, table)

## Purpose

Murlan is the first real game on Card Table: the Albanian shedding game, played
the way the author's group plays it. The server enforces every rule; the app
only shows what the server sends and turns taps into actions.

Success: a full game of 2, 3 or 4 friends on their phones (same room or
remote), from seat choice to final score, with the swap, the cut and team
scoring behaving exactly as below, and no way to see anyone else's cards.

## Rules

### Players, teams, deal

| Players | Teams | Deal |
|---|---|---|
| 4 | Two teams of 2; **partners sit across** from each other | All 54 cards (14, 14, 13, 13; the two extra cards go to the first two players dealt) |
| 3 | Individual | All 54 cards, 18 each |
| 2 | Individual | 18 each; the other 18 are out of play, unseen |

Deck: 52 cards + 2 jokers (one **black**, one **red**).

### Ranking

`3 < 4 < 5 < 6 < 7 < 8 < 9 < 10 < J < Q < K < A < 2 < black joker < red joker`.
Suits never matter for beating anything.

### Plays

- **Single**: any card, including a joker.
- **Pair**, **three of a kind**: same rank. Jokers are never part of a pair or
  any other combination; they are only played as singles.
- **Bomb**: four of a kind.
- **Straight**: 5 or more cards of consecutive rank, no jokers. A and 2 go at
  either end: low (A-2-3-4-5…, 2-3-4-5-6…) or high (…10-J-Q-K-A, …J-Q-K-A-2).
  No wrapping round the corner: K-A-2-3 is not a straight. Positions in
  straight order, read one of two ways: A=1, 2=2, 3…K=3…13, or 3…K=3…13,
  A=14, 2=15; a straight is a run of consecutive positions, length ≥ 5.
  (Changed 2026-10-15 at the author's request: before, 2 could only be low.)
- **Double straight**: 5 or more consecutive ranks, a pair of each (≥ 10 cards).
- **Triple straight**: 5 or more consecutive ranks, three of each (≥ 15 cards).

### Beating

- Single, pair, three of a kind: same type, **any higher rank**.
- Straights (single, double, triple): same type, **same length**, and
  **exactly one step higher** (lowest position + 1). 3-7 is beaten only by 4-8.
- A **bomb** beats anything that isn't a bomb (including a joker and any
  straight). A bomb is beaten only by a higher bomb.
- Bombs are played only on your turn, like everything else, and can be led.

### Turns and tricks

- Play goes **clockwise** by seat. On your turn: play something that beats the
  top of the pile, or **pass**.
- **Passing only skips that turn.** You can play again next time it's your turn.
- **Passing is always your own choice.** The game never passes for you, even when
  nothing in your hand beats the pile: when you pass is part of the strategy.
- When the turn comes back to the player who made the last play (everyone else
  passed), the trick is won and that player leads anything. The won trick (dimmed)
  and who passed stay on show until that lead clears them.
- If the player who made the last play has already gone out, the lead goes to
  the next player clockwise who still has cards.
- A player who plays their last card is **out** and takes the next finishing
  place.

### Who starts

- **First round of a game:** the holder of **3♠** leads, and the lead must
  include the 3♠ (single, pair, triple, bomb, or part of any straight). In a
  2-player game, where 3♠ may be out of play: the holder of the **lowest spade
  dealt** (4♠, then 5♠, …) leads, and the lead must include it.
- **Later rounds:** the previous round's **loser** leads anything, unless the
  loser was dealt both jokers (see the swap), in which case the **winner**
  leads.

### End of a round and points

- **4 players:** places score 3, 2, 1, 0; each team adds its two players.
  If one team takes 1st and 2nd (5 points), the round ends immediately: the
  other team gets 1 point between them, and **both of them must agree** who
  is the loser (each picks a name; when the picks match, that player is last).
- **3 players:** 2, 1, 0. The round ends when two players are out.
- **2 players:** winner 1, loser 0. The round ends when one player is out.
- The round's **winner** is 1st place and the **loser** is last place (or the
  agreed loser).

### Before each later round: the cut

1. The loser sees the face-down deck spread out (everyone else sees "Arben is
   cutting…") and taps anywhere in it. The card at that spot is revealed **to the
   loser only**.
2. The loser chooses **Take it** or **Leave it**.
   - **Take it:** that card becomes the loser's first card, and **everyone's
     first card is dealt face up**: all players see all first cards during the
     deal (a few seconds), then they go into hands and are hidden like any other
     card.
   - **Leave it:** a normal hidden deal.
3. The first round of a game has no cut (no loser yet).

### After the deal: the swap

- The **loser gives the winner their highest card** (red joker, black joker,
  2, A, K, …). If they hold several cards of that same highest rank, the loser
  taps which one.
- The **winner gives back any card from 3 to 10** of their choice. If they
  have none, they give their **lowest** card.
- The swap is **hidden**, except when the winner and loser are **teammates**
  (their team scored 3): then **everyone sees both cards** for a few seconds.
- If the **loser was dealt both jokers**, there is **no swap** and the
  **winner leads** the round. Everyone is shown the loser's two jokers for a few
  seconds, so it's clear why there's no swap.
- 2- and 3-player games swap the same way.

### Winning the game

- When all seats are filled, the **room creator** picks the target: **5, 10, 13
  or 21**. Everyone else sees "Waiting for Yzeir to choose the target…". The game
  starts when it's picked.
- After each round, if any side has reached the target, the **highest score
  wins**. On an exact tie for the highest score, play **one more round** at a
  time until one side is ahead.

### Giving up (added 2026-10-15)

- On their turn in the playing phase, a player can **give up the round**
  (with an "are you sure" first) instead of playing or passing. (Changed
  2026-10-16 at the author's request: before, any time, not only on their turn.)
- Their cards are thrown **face up**: public to everyone until that round's
  result has been shown.
- They finish **last**; a second player to give up finishes second-last, and so
  on. With 2 players the round ends at once and the other player wins it. With 3
  or 4 the others play on for the places left; the round ends when one player is
  left holding cards.
- 4 players: if one team takes 1st and 2nd and one of the other team gave up,
  there's no vote for last: the one who gave up is last.
- Play moves on to the next player. If they had just won the trick (their lead),
  the lead passes on as when a player goes out. If they held the 3♠ before the first
  lead, the next player leads anything.

### Disconnects

- If any seated player drops, the game **pauses** for everyone with
  "Ben disconnected, waiting… 2:00" counting down.
- If they reconnect in time, they're back in their seat with their cards and
  the game resumes exactly where it was.
- If the countdown runs out, **the current round is cancelled with no points**
  (scores stay as they were before the round), and the connected players are
  asked **Keep waiting** or **End game**:
  - Keep waiting: the pause continues with no countdown; when the player is
    back, a fresh round is dealt (with the cut/swap of the last *completed*
    round, if any).
  - End game: the game ends with the current scores (game-over screen).
  - The room creator's choice decides (if the creator is the one who's gone,
    the next player clockwise decides).
- Reconnecting always returns a player to the same seat in the same room.

### After a game

Final scores for everyone, and the room creator picks:
- **Play again, same teams**: same seats; the creator picks the target again.
- **Shuffle teams** (4 players only): seats are randomly reassigned (so
  partners change), then target pick.
- **Back to the lobby**: everyone is unseated and picks a seat again; players
  can leave and others can join.

## Lobby changes (all games)

Seats become places at the table. The lobby shows the table from above with its
seats (4: bottom, left, top, right; 3: three around; 2: across). A player who
joins is in the room but **unseated** until they tap an empty seat. In a
4-player Murlan, teammates are the two seats across from each other, so
choosing a seat chooses your partner; the lobby labels the two teams. The room
moves on (to the target pick) when every seat is taken. Leaving frees your
seat; leaving mid-game ends the game, and the others are first told who left
(a popup on the table) before going back to the lobby. The room creator is the first player in the room; if they leave, the next
player clockwise becomes creator.

## Architecture

- **Server-side Murlan module** `backend/app/murlan/`:
  - `cards.py`: card codes (`"7H"`, `"10S"`, `"JB"` black joker, `"JR"` red
    joker), rank order, straight positions, deck building.
  - `combos.py`: classify a set of cards into a play
    (single/pair/triple/bomb/straight/double straight/triple straight, with
    its rank or lowest position and length) or reject it; `beats(new, top)`.
    Pure functions, no state.
  - `game.py`: the round/game state machine, as phases:
    `choosing_target → cutting → swapping → playing → agreeing_loser → … →
    game_over`, plus `round_cancelled` after a pause runs out; a pause
    (someone dropped) can overlay any phase. Pure Python with an injectable clock and RNG; methods take a
    player id and an action and either change state or raise a rejection with
    a message for the player.
  - `views.py`: `view_for(game, player_id)` builds what one player may see:
    their own hand, the pile, scores, phase, whose turn, and any public
    reveals (swap between teammates, face-up first cards during
    a "take it" deal, the loser's two jokers when there's no swap). **No view ever contains another player's hidden cards**,
    nor how many cards anyone else holds (players finishing are still shown).
- **Rooms** (`backend/app/rooms.py`) gain seats (`seat_index → player`),
  unseated players, the creator, and the game instance. The WebSocket handler
  routes `murlan` actions to the game and broadcasts each player's view.
- **The old free-form engine (`backend/app/engine/`) and its tests are
  deleted.** The hidden-information invariant and its "no view ever leaks"
  test move to `backend/app/murlan/views.py` and its tests. CLAUDE.md is
  updated accordingly.
- **Pause timer:** the 2-minute countdown is a per-room asyncio task in the
  single worker; game logic reads time from the injectable clock so tests
  drive it without sleeping.
- **Frontend** (no game logic): table screen renders the view — your hand
  (tap cards to select; **Play** sends the selection, **Pass** passes, and is
  greyed out while cards are picked so it isn't hit for Play; or drag cards onto
  the pile to play them, your picks coming along; an
  illegal play comes back as a toast with the server's reason), the pile as a
  compact messy stack (each play lands slightly turned on the last), opponents'
  card backs (a fixed fan, no count), whose turn, and the scores in a bar above
  the table with the menu. Your name sits above your hand (gold on your turn),
  Pass stacked over Play in the bottom-right, with a gap between them; a pass shows as a
  red PASS stamp on that player's cards (above your name for you). The end of a
  round dims the table and spotlights the winner (crown, gold banner, points
  rising by the scores) for a few seconds before what comes next; a won game's
  banner stays until tapped. Each
  new deal is animated: backs go out round the table one at a time and your
  hand turns face up at the end. Plus overlays for the
  target pick, the cut (spread deck, tap, Take it / Leave it), the swap
  (you always pick and give your card yourself, even when only one is
  allowed), agreeing the loser, the pause
  countdown with Keep waiting / End game, round result, and game over with the
  three options. Lobby gets the seat picker. Themes and card styles from the
  PWA spec apply throughout (card backs use the theme's back).

## Testing

- **combos (pytest):** every play type valid/invalid; ace and 2 low/high,
  no K-A-2-3 wrap, jokers rejected in combos; beating rules (any higher for
  singles/pairs/triples, exactly +1 and same length for straights of each
  multiplicity, bombs over everything, higher bomb over bomb).
- **game (pytest):** deals per player count; first lead must include 3♠ /
  lowest spade (2 players); pass doesn't lock out; the trick is won on return
  to the last player and stays on show until the next lead; lead passes when the last player is out; finishing places and
  points per player count; 4-player early end (1st+2nd same team) with loser
  agreement; swap (highest card with tie choice, 3–10 or lowest back, public
  only between teammates, skipped with both jokers and winner leads); cut take
  vs leave and the public first-card reveal; target pick by creator; game end
  with highest score and tie-break rounds; pause → resume; pause → timeout →
  round cancelled → keep waiting / end game; play again / shuffle teams /
  back to lobby.
- **views (pytest):** no view ever contains another player's hidden cards
  across randomized full games (including cut and swap reveals only where
  allowed).
- **WebSocket (pytest):** seat picking, start → target → playing, action
  rejections come back as errors, reconnect mid-round restores the hand.
- **Frontend (`node --test`):** pure helpers (card code → image, selection
  state, seat → screen position for the seat picker).
- **End to end:** two and four browser players through a full round on each
  theme; then the author on phones over Wi-Fi.

## Out of scope

Other games, accounts and stats, chat, spectators, animations beyond simple
transitions and the deal, turn timers for connected players, deployment.
