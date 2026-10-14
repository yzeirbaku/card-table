"""Live rooms: join codes, seats, reconnect tokens, host, idle expiry.
In memory only - the backend must run as a single worker."""

import asyncio
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from .engine.actions import add_player, new_table, remove_player
from .engine.state import TableState

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
    token: str  # secret; lets the same phone reclaim this seat after a drop
    socket: Any = None  # the live WebSocket, or None while disconnected


@dataclass
class Room:
    code: str
    last_activity: float
    game: str
    seats: int
    status: RoomStatus = "lobby"  # "playing" once every seat is taken
    state: TableState = field(default_factory=new_table)
    players: list[Player] = field(default_factory=list)
    host_id: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def join(self, name: str, token: str | None) -> Player:
        if token:
            for p in self.players:
                if secrets.compare_digest(p.token, token):
                    return p
        name = name.strip()
        if not 1 <= len(name) <= MAX_NAME_LENGTH:
            raise JoinRejected(4400, f"Name must be 1-{MAX_NAME_LENGTH} characters")
        if self.status == "playing" or len(self.players) >= self.seats:
            raise JoinRejected(4409, "This table is full")
        player = Player(id=secrets.token_hex(4), name=name, token=secrets.token_urlsafe(16))
        self.players.append(player)
        add_player(self.state, player.id)
        if self.host_id is None:
            self.host_id = player.id
        if len(self.players) == self.seats:
            self.status = "playing"
        return player

    def leave(self, player_id: str) -> None:
        self.players = [p for p in self.players if p.id != player_id]
        remove_player(self.state, player_id)
        if self.host_id == player_id:
            self.host_id = self.players[0].id if self.players else None
        # A game can't go on with an empty seat; back to waiting for someone.
        self.status = "lobby"

    def room_view(self) -> dict[str, Any]:
        return {"game": self.game, "seats": self.seats, "status": self.status}

    def players_view(self) -> list[dict[str, Any]]:
        return [
            {
                "id": p.id,
                "name": p.name,
                "connected": p.socket is not None,
                "is_host": p.id == self.host_id,
                "hand_count": len(self.state.hands.get(p.id, [])),
            }
            for p in self.players
        ]


class RoomManager:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self.rooms: dict[str, Room] = {}

    def create(self, game: str, seats: int) -> Room:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if code not in self.rooms:
                break
        room = Room(code=code, last_activity=self._clock(), game=game, seats=seats)
        self.rooms[code] = room
        return room

    def get(self, code: str) -> Room | None:
        return self.rooms.get(code.upper())

    def touch(self, room: Room) -> None:
        room.last_activity = self._clock()

    def purge_expired(self) -> list[Room]:
        now = self._clock()
        expired = [r for r in self.rooms.values() if now - r.last_activity > IDLE_EXPIRY_SECONDS]
        for r in expired:
            del self.rooms[r.code]
        return expired
