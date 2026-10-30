"""A finished game as the stats keep it. Rooms build these; the app saves them."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SeatResult:
    seat: int
    user_id: int | None  # None for guests and computers
    computer: bool
    side: int  # the team in 4-player games, else the seat
    score: int  # the side's score at the end
    won: bool


@dataclass(frozen=True)
class GameRecord:
    game: str
    players: int
    target: int | None
    how: Literal["target", "leave"]
    seats: tuple[SeatResult, ...]
