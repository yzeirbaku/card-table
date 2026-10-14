"""Games the server can host: a display name and the allowed player counts for
the lobby. Murlan's rules live in app/murlan/ (spec:
docs/superpowers/specs/2026-10-14-murlan-design.md)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GameInfo:
    id: str
    name: str
    min_players: int
    max_players: int


GAMES: dict[str, GameInfo] = {g.id: g for g in [GameInfo("murlan", "Murlan", 2, 4)]}
