# Murlan vs the computer

Date: 2026-10-15. Status: approved in chat (layout B), being built.

## What

A table where you play Murlan alone against computer players. You count as one
of the players: "3 vs computer" is you and two computer players. In a 4-player
game your partner (across) is a computer.

## New table sheet (layout B)

New table → Murlan → **Players**: a **Friends / Computer** switch above the
2 / 3 / 4 row. With Computer on, a line under the row says what the count
means: "You count as one of them: 3 is you and 2 computer players". Friends
works as today (no line). Tapping a count with Computer on creates the table and goes
straight to it: no code to share, no seat to pick.

## Server

- `POST /rooms` takes `computer: true`. Such a room is created with its
  computer players already seated (seats 1…n-1, named "Computer 1"…) and seat 0
  free for you; when you join you're seated there and the game starts. You're
  the creator, so you pick the race as usual.
- Only one person can join a computer table (anyone else: "This table is full").
  Rejoining with your token works as for any table.
- Computer players are always connected. If you drop, the game waits for you
  with no countdown (no round is ever cancelled for being away).
- Game over: Play again, Shuffle teams (4 players), or **Leave** (instead of
  Back to the lobby: a computer table has no lobby).
- The state's `players` mark computer players (`computer: true`) and the room
  says `computer: true`.

## The computer player

- **Fair**: it decides from `view_for(game, its id)` only, the same view a
  browser gets, plus what it has seen during the round (a memory of every play
  and thrown hand it was shown). It never reads hands it couldn't see.
- **Never** gives up, never decides for a paused table, never picks the race.
- **Pace**: it moves a second or two after its turn comes, waits out public
  reveals, the deal animation, and the end-of-round spotlight, so you see
  everything happen.
- **Play**: it splits its hand into as few plays as it can (straights, bombs,
  triples, pairs, singles), weighing each by how likely it is to win its trick
  given the cards still unseen. Leading, it gets rid of straights and weak
  plays first and keeps 2s, jokers and bombs to win tricks later; with only one
  weak play left it cashes its winners and goes out. Following, it beats the
  pile when that fits its plan and doesn't waste a strong card early; it fights
  harder when an opponent is close to going out (it counts the cards each
  player has played), and it doesn't beat its partner.
- **Other choices**: cut anywhere, take the cut card only if it's a joker; as
  winner give back the card its hand misses least; as loser give any of its
  highest cards; when its team must agree who's last, it goes along with its
  partner's pick, or picks itself first.

## Testing

- Move generation: every legal play is listed and nothing illegal is
  (checked against `classify`/`beats` on random hands).
- Self-play: many complete games with computer players in every seat, for 2, 3
  and 4 players: no move is ever rejected and every game ends.
- Strength: in 2-player self-play the computer must clearly beat a naive
  player (always plays its lowest legal play, never passes by choice).
- Rooms/WebSocket: a computer table starts on join, the computer moves on its
  own (timers), a second person can't join, leaving works.
