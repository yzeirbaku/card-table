"""Live rooms: join codes, seats, the creator, reconnect tokens, idle expiry and,
once every seat is taken, the Murlan game. In memory only - the backend must
run as a single worker."""

import asyncio
import random
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from .murlan.game import Game, Rejected
from .murlan.protocol import apply_action
from .murlan.views import view_for

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I/O: easy to read aloud
CODE_LENGTH = 4
MAX_NAME_LENGTH = 20
IDLE_EXPIRY_SECONDS = 2 * 60 * 60

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
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        if not self.seating:
            self.seating = [None] * self.seats

    @property
    def status(self) -> RoomStatus:
        return "lobby" if self.game is None else "playing"

    def join(self, name: str, token: str | None) -> Player:
        if token:
            for p in self.players:
                if secrets.compare_digest(p.token, token):
                    return p
        name = name.strip()
        if not 1 <= len(name) <= MAX_NAME_LENGTH:
            raise JoinRejected(4400, f"Name must be 1-{MAX_NAME_LENGTH} characters")
        if self.game is not None or len(self.players) >= self.seats:
            raise JoinRejected(4409, "This table is full")
        player = Player(id=secrets.token_hex(4), name=name, token=secrets.token_urlsafe(16))
        self.players.append(player)
        if self.creator_id is None:
            self.creator_id = player.id
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

    def leave(self, player_id: str) -> None:
        seat = self.seat_of(player_id)
        self.players = [p for p in self.players if p.id != player_id]
        self._unseat(player_id)
        self.game = None  # a game can't go on with an empty seat
        if self.creator_id == player_id:
            self.creator_id = self._next_creator(seat)

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
            self.rng.shuffle(self.seating)
            self._new_game()
        elif choice == "lobby":
            self.seating = [None] * self.seats
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
        self.game = Game(list(self.seating), self.creator_id, rng=self.rng, clock=self.clock)
        for p in self.players:
            if p.socket is None:
                self.game.disconnect(p.id)

    def _unseat(self, player_id: str) -> None:
        self.seating = [None if s == player_id else s for s in self.seating]

    def _next_creator(self, seat: int | None) -> str | None:
        """Next seated player clockwise from the old creator's seat; if they
        weren't seated or nobody is, whoever has been here longest."""
        if seat is not None:
            for k in range(1, self.seats):
                player = self.seating[(seat + k) % self.seats]
                if player is not None:
                    return player
        return self.players[0].id if self.players else None

    def room_view(self) -> dict[str, Any]:
        return {"game": self.game_id, "seats": self.seats, "status": self.status}

    def players_view(self) -> list[dict[str, Any]]:
        return [
            {
                "id": p.id,
                "name": p.name,
                "connected": p.socket is not None,
                "seat": self.seat_of(p.id),
                "is_creator": p.id == self.creator_id,
            }
            for p in self.players
        ]

    def game_view(self, player_id: str) -> dict[str, Any] | None:
        return None if self.game is None else view_for(self.game, player_id)


class RoomManager:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.rooms: dict[str, Room] = {}

    def create(self, game_id: str, seats: int) -> Room:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if code not in self.rooms:
                break
        room = Room(code=code, last_activity=self.clock(), game_id=game_id, seats=seats,
                    clock=self.clock)
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
