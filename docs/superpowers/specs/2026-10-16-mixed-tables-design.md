# Mixed tables, computer emojis, two easter eggs

Date: 2026-10-16. Status: approved in chat, being built.
Builds on: `2026-10-15-vs-computer-design.md` (the computer player).

## Mixed tables: friends and computers at one table

A normal (Friends) table of 3 or 4 can have computer players in it, so it can
start without waiting for a full set of friends. At least two people always
play: up to **1 computer at a 3-player table, 2 at a 4-player table**. A
2-player table has none (that's the Computer table).

### Lobby

- The **room creator** sees an **Add computer** button on each empty seat while
  more computers are allowed. Tapping it seats a computer there ("Bip",
  then "Bop": the first name not in use). If that fills the table, the game
  starts as usual (the creator picks the race).
- A computer's seat shows a 🤖 avatar, its name, and for the creator a **✕** to
  take it off the table again (only in the lobby).
- A computer also takes a place in the room: one can't be added when the people
  already in the room (seated or not) would no longer fit.
- Everyone sees which seats are computers, in the lobby and at the table (🤖 by
  the name).

### During and after a game

- Computers are always connected. If a person drops, the usual 2:00 pause runs:
  people are waiting.
- Computers never decide for the table: when the creator is away, the next
  connected **person** clockwise decides (keep waiting / end game, and what to
  do after a game). They never pick the race, and the creator role never passes
  to a computer.
- A person leaving ends the game as today; the computers stay seated in the
  lobby. **Back to the lobby** unseats the people and leaves the computers where
  they are; **Shuffle teams** reseats everyone, computers too.

### Server

- `room_view` gains `computer_seats_left`: how many more computers the creator
  may add now (0 at a Computer table, a 2-player table, or when no more fit).
- Two new client messages, creator only, lobby only:
  `{"type": "add_computer", "seat": n}` and `{"type": "remove_computer", "seat": n}`.
- `Game` takes the set of computer seats, so `decider()` skips them.

## Computer emojis

Computer players send the same reactions people do, now and then, at things
they saw happen (so still only from their view):
- a bomb of its own lands: 😂 (sometimes)
- its play is bombed: 😮 (sometimes)
- it wins the round: 😂; it finishes last: 😠 (sometimes)

Not overdone: each event is a chance, not a certainty (about 1 in 3), each
computer reacts **at most once a round**, and one computer at a time.

## Easter eggs

- **Bomb shake**: when a bomb lands on the pile, the table gives a short shake
  (for everyone). Not with reduced motion.
- **Lucky hand**: if you're dealt all four 2s, after the deal you alone see a
  big 😎 and "Four 2s. Act natural." for a few seconds. The view gives the
  player `lucky: "four_twos"` for that round (their own hand only, so nothing
  hidden leaves the server). It doesn't block play.

## Testing

- Rooms: adding and removing computers (creator only, lobby only, the limits,
  not past room capacity), the game starting when a computer fills the table,
  computers staying seated on leave / back to lobby, creator never a computer,
  decider skipping computers.
- Bot: reacts only to new events, at most once a round; views never leak.
- Game: `lucky` set only for the player dealt four 2s.
