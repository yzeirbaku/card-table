"""Games the server can host. For now only what the lobby needs: a display name
and the allowed player counts. Each game's rules arrive with its own spec."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GameInfo:
    id: str
    name: str
    min_players: int
    max_players: int


# Murlan's player range is provisional until its rules are pinned down.
GAMES: dict[str, GameInfo] = {g.id: g for g in [GameInfo("murlan", "Murlan", 2, 4)]}
