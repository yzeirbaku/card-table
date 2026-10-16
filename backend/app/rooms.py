"""Live rooms: join codes, seats, the creator, reconnect tokens, idle expiry and,
once every seat is taken, the Murlan game. In memory only - the backend must
run as a single worker.

A computer table (`computer=True`) has its computer players seated from the
start and one seat left for the person who joins; the game starts as they do.
At a friends table of 3 or 4 the creator may seat computer players too (a mixed
table, at least two people). The computer players move on their own: after every change `update_bots` says
when the next one is due, and `run_bot` makes that move once its time comes."""

import asyncio
import logging
import random
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from .murlan.bot import Bot
from .murlan.combos import classify
from .murlan.game import Game, Rejected
from .murlan.moves import legal_plays
from .murlan.protocol import apply_action
from .murlan.views import view_for

log = logging.getLogger(__name__)

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I/O: easy to read aloud
CODE_LENGTH = 4
MAX_NAME_LENGTH = 20
IDLE_EXPIRY_SECONDS = 2 * 60 * 60
BOT_NAMES = ("Bip", "Bop", "Zip")  # short: the 🤖 by the name already says it's a computer
# A computer player takes its time, so you see each move happen: it waits out the deal animation
# and the end-of-round spotlight (see deal.js, spotlight.js), and any public reveal.
DEAL_SECONDS = 3.0
ROUND_END_SECONDS = 6.0

RoomStatus = Literal["lobby", "playing"]


class JoinRejected(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Player:
    id: str
    name: str
    token: str  # secret; lets the same phone reclaim this player after a drop
    socket: Any = None  # the live WebSocket, or None while disconnected
    reacted_at: float = float("-inf")  # their last reaction, to keep a fast tapper from flooding the table
    computer: bool = False  # a computer player: always here, never has a socket


@dataclass
class Room:
    code: str
    last_activity: float
    game_id: str
    seats: int
    clock: Callable[[], float] = time.monotonic
    rng: random.Random = field(default_factory=random.SystemRandom)
    players: list[Player] = field(default_factory=list)  # everyone here, seated or not, by arrival
    seating: list[str | None] = field(default_factory=list)  # seat index (clockwise) -> player id
    creator_id: str | None = None
    game: Game | None = None  # exists from the moment every seat is taken
    ended_by: str | None = None  # the name of whoever left and so ended the last game (until the next starts)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    computer: bool = False  # you against computer players
    bots: dict[str, Bot] = field(default_factory=dict)  # the computer players' minds, by player id
    bot_due: tuple[str, float, tuple] | None = None  # (who, when, the state they're answering): the next computer move
    bot_reactions: list[tuple[str, str]] = field(default_factory=list)  # (who, reaction) computer emojis still to send
    _quiet_until: float = float("-inf")  # no computer moves before this (the deal, the round's end)
    _bots_saw: tuple[int, str] | None = None  # rounds played and phase at the last update

    def __post_init__(self) -> None:
        if not self.seating:
            self.seating = [None] * self.seats
        if self.computer:  # seats 1… are theirs; seat 0 waits for you
            for seat in range(1, self.seats):
                self._seat_bot(seat, BOT_NAMES[seat - 1])

    def _seat_bot(self, seat: int, name: str) -> None:
        bot = Player(id=secrets.token_hex(4), name=name, token=secrets.token_urlsafe(16), computer=True)
        self.players.append(bot)
        self.seating[seat] = bot.id
        self.bots[bot.id] = Bot(bot.id, random.Random(self.rng.random()))

    @property
    def status(self) -> RoomStatus:
        return "lobby" if self.game is None else "playing"

    def join(self, name: str, token: str | None) -> Player:
        if token:
            for p in self.players:
                if secrets.compare_digest(p.token.encode(), token.encode()):
                    return p
        name = name.strip()
        if not 1 <= len(name) <= MAX_NAME_LENGTH:
            raise JoinRejected(4400, f"Name must be 1-{MAX_NAME_LENGTH} characters")
        if self.game is not None or (self.computer and any(not p.computer for p in self.players)):
            raise JoinRejected(4409, "This table is full")
        if len(self.players) >= self.seats:
            # Make room by dropping whoever has been offline and unseated the longest.
            stale = next((p for p in self.players
                          if p.socket is None and self.seat_of(p.id) is None), None)
            if stale is None:
                raise JoinRejected(4409, "This table is full")
            self.leave(stale.id)
        player = Player(id=secrets.token_hex(4), name=name, token=secrets.token_urlsafe(16))
        self.players.append(player)
        if self.creator_id is None:
            self.creator_id = player.id
        if self.computer:  # straight to the free seat: the game starts
            self.sit(player.id, self.seating.index(None))
        return player

    def seat_of(self, player_id: str) -> int | None:
        return self.seating.index(player_id) if player_id in self.seating else None

    def sit(self, player_id: str, seat: object) -> None:
        if self.game is not None:
            raise Rejected("The game has already started")
        if not isinstance(seat, int) or isinstance(seat, bool) or not 0 <= seat < self.seats:
            raise Rejected("There's no such seat")
        if self.seating[seat] == player_id:
            return
        if self.seating[seat] is not None:
            raise Rejected("That seat is taken")
        self._unseat(player_id)
        self.seating[seat] = player_id
        if all(self.seating):
            self._new_game()

    @property
    def computer_seats_left(self) -> int:
        """How many more computer players the creator may seat now: a friends table of 3 or 4
        keeps at least two people, and a computer takes a place in the room like anyone."""
        if self.computer or self.game is not None or self.seats < 3:
            return 0
        return max(0, min(self.seats - 2 - len(self.bots), self.seats - len(self.players)))

    def add_computer(self, player_id: str, seat: object) -> None:
        self._check_seating_computers(player_id, seat)
        if self.seating[seat] is not None:
            raise Rejected("That seat is taken")
        if self.computer_seats_left == 0:
            raise Rejected("No more computer players fit at this table")
        names = {p.name for p in self.players if p.computer}
        self._seat_bot(seat, next(n for n in BOT_NAMES if n not in names))
        if all(self.seating):
            self._new_game()

    def remove_computer(self, player_id: str, seat: object) -> None:
        self._check_seating_computers(player_id, seat)
        bot_id = self.seating[seat]
        if bot_id not in self.bots:
            raise Rejected("There's no computer player in that seat")
        del self.bots[bot_id]
        self.players = [p for p in self.players if p.id != bot_id]
        self.seating[seat] = None

    def _check_seating_computers(self, player_id: str, seat: object) -> None:
        if self.computer:
            raise Rejected("This table is already you against the computer")
        if player_id != self.creator_id:
            raise Rejected("Only the room creator seats computer players")
        if self.game is not None:
            raise Rejected("The game has already started")
        if not isinstance(seat, int) or isinstance(seat, bool) or not 0 <= seat < self.seats:
            raise Rejected("There's no such seat")

    def leave(self, player_id: str) -> None:
        seat = self.seat_of(player_id)
        if self.game is not None and seat is not None:  # the others are told why their game ended
            self.ended_by = next(p.name for p in self.players if p.id == player_id)
        self.players = [p for p in self.players if p.id != player_id]
        self._unseat(player_id)
        self.game = None  # a game can't go on with an empty seat
        self.bot_due = None
        if self.creator_id == player_id:  # a computer never takes over: the next person to join does
            self.creator_id = None if self.computer else self._next_creator(seat)

    def act(self, player_id: str, action: object) -> None:
        if self.game is None:
            raise Rejected("The game hasn't started yet")
        apply_action(self.game, player_id, action)

    def after_game(self, player_id: str, choice: object) -> None:
        game = self.game
        if game is None or game.phase != "game_over":
            raise Rejected("The game isn't over")
        if player_id != game.decider():
            raise Rejected("The room creator chooses what's next")
        if choice == "play_again":
            self._new_game()
        elif choice == "shuffle_teams":
            if self.seats != 4:
                raise Rejected("Shuffling teams needs 4 players")
            self._reshuffle_partners()
            self._new_game()
        elif choice == "lobby":
            if self.computer:
                raise Rejected("A table against the computer has no lobby: leave instead")
            self.seating = [s if s in self.bots else None for s in self.seating]  # computers keep their seats
            self.game = None
        else:
            raise Rejected("Play again, shuffle teams or go back to the lobby")

    def mark_connected(self, player_id: str) -> None:
        if self.game is not None:
            self.game.reconnect(player_id)

    def mark_disconnected(self, player_id: str) -> None:
        if self.game is not None:
            self.game.disconnect(player_id)

    def _new_game(self) -> None:
        self.ended_by = None
        self.bot_due = None
        self._bots_saw = None
        # Against the computer nobody else is waiting on you: if you drop, the game just waits.
        self.game = Game(list(self.seating), self.creator_id, rng=self.rng, clock=self.clock,
                         no_countdown=self.computer, computers=frozenset(self.bots))
        for p in self.players:
            if p.socket is None and not p.computer:
                self.game.disconnect(p.id)

    # ---- computer players ----

    def update_bots(self) -> float | None:
        """After any change: the computer players take in the new state. Returns when the
        next computer move is due, or None if none is."""
        game = self.game
        if game is None or not self.bots:
            self.bot_due = None
            return None
        now = self.clock()
        saw, self._bots_saw = self._bots_saw, (game.rounds_played, game.phase)
        if saw is not None and saw[0] != game.rounds_played:  # a round just ended: its spotlight runs
            self._quiet_until = max(self._quiet_until, now + ROUND_END_SECONDS)
        dealing = ("swapping", "playing")
        if game.phase in dealing and (saw is None or saw[1] not in dealing):  # the cards are flying out
            self._quiet_until = max(self._quiet_until, now + DEAL_SECONDS)
        views = {b: view_for(game, b) for b in self.bots}
        for b, bot in self.bots.items():
            bot.observe(views[b])
            reaction = bot.reaction(views[b])
            if reaction and not self.bot_reactions:  # one computer at a time
                self.bot_reactions.append((b, reaction))
        mover = next((b for b, bot in self.bots.items() if bot.needs_to_act(views[b])), None)
        if mover is None:
            self.bot_due = None
            return None
        state = _moment(game)
        if self.bot_due and self.bot_due[0] == mover and self.bot_due[2] == state:
            return self.bot_due[1]  # already thinking about it
        reveals = [r.until for r in (game.reveal, game.next_reveal) if r]  # a queued reveal too (both jokers after first cards)
        start = max(now, self._quiet_until, *reveals)
        self.bot_due = (mover, start + self._think_time(game), state)
        return self.bot_due[1]

    def run_bot(self) -> bool:
        """Make the due computer move if its time has come. True if one was made."""
        due = self.bot_due
        if due is None or self.game is None or self.clock() < due[1] or due[2] != _moment(self.game):
            return False
        self.bot_due = None
        bot_id = due[0]
        try:
            action = self.bots[bot_id].act(view_for(self.game, bot_id))
            if action is None:
                return False
            self.act(bot_id, action)
        except Exception:  # shouldn't happen; never leave the table stuck on a computer's turn
            log.exception("computer move by %s failed", bot_id)
            fallback = self._fallback(bot_id)
            if fallback is None:
                return False
            try:
                self.act(bot_id, fallback)
            except Rejected:
                log.exception("computer fallback move by %s refused", bot_id)
                return False
        return True

    def _fallback(self, bot_id: str) -> dict[str, Any] | None:
        game = self.game
        if game.phase != "playing" or game.turn != bot_id:
            return None
        if game.top is not None:
            return {"type": "pass"}
        plays = legal_plays(game.hands[bot_id], None, game.must_include)
        return {"type": "play", "cards": min(plays, key=lambda c: classify(c).rank)}

    def _think_time(self, game: Game) -> float:
        if game.phase == "playing":
            return self.rng.uniform(1.2, 2.2) + (0.8 if game.trick_won else 0.0)  # a won trick: a look first
        return {"cutting": 1.4, "swapping": 1.6}.get(game.phase, 1.5)

    def _reshuffle_partners(self) -> None:
        """Reseat four players so everyone gets a new partner (seats 0+2 and 1+3 pair up)."""
        a, b, c, d = self.seating
        # Of the three ways to split four players into two pairs, drop the current one.
        pairings = [((a, c), (b, d)), ((a, b), (c, d)), ((a, d), (b, c))][1:]
        (p, q), (r, s) = self.rng.choice(pairings)
        seating = [p, r, q, s]
        if self.rng.random() < 0.5:
            seating = [r, p, s, q]
        self.seating = seating

    def _unseat(self, player_id: str) -> None:
        self.seating = [None if s == player_id else s for s in self.seating]

    def _next_creator(self, seat: int | None) -> str | None:
        """Next seated person clockwise from the old creator's seat; if they
        weren't seated or nobody is, whoever has been here longest. Never a computer."""
        if seat is not None:
            for k in range(1, self.seats):
                player = self.seating[(seat + k) % self.seats]
                if player is not None and player not in self.bots:
                    return player
        return next((p.id for p in self.players if not p.computer), None)

    def room_view(self) -> dict[str, Any]:
        return {"game": self.game_id, "seats": self.seats, "status": self.status, "ended_by": self.ended_by,
                "computer": self.computer, "computer_seats_left": self.computer_seats_left}

    def players_view(self) -> list[dict[str, Any]]:
        return [
            {
                "id": p.id,
                "name": p.name,
                "connected": p.computer or p.socket is not None,
                "seat": self.seat_of(p.id),
                "is_creator": p.id == self.creator_id,
                "computer": p.computer,
            }
            for p in self.players
        ]

    def game_view(self, player_id: str) -> dict[str, Any] | None:
        return None if self.game is None else view_for(self.game, player_id)


class RoomManager:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.rooms: dict[str, Room] = {}

    def create(self, game_id: str, seats: int, computer: bool = False) -> Room:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if code not in self.rooms:
                break
        room = Room(code=code, last_activity=self.clock(), game_id=game_id, seats=seats,
                    clock=self.clock, computer=computer)
        self.rooms[code] = room
        return room

    def get(self, code: str) -> Room | None:
        return self.rooms.get(code.upper())

    def touch(self, room: Room) -> None:
        room.last_activity = self.clock()

    def purge_expired(self) -> list[Room]:
        now = self.clock()
        expired = [r for r in self.rooms.values() if now - r.last_activity > IDLE_EXPIRY_SECONDS]
        for r in expired:
            del self.rooms[r.code]
        return expired


def _moment(game: Game) -> tuple:
    """What a computer move answers: if any of this changes before it's made, it's thought out again."""
    return (game.phase, game.turn, game.rounds_played, len(game.trick), game.trick_won, game.swap_step,
            game.cut_index, tuple(sorted(game.agree_picks.items())), tuple(game.thrown), game.pause is None)
