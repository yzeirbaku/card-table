"""Table state. Everything on the table is a pile; a lone card is a pile of one."""

from dataclasses import dataclass, field
from typing import Literal

from .cards import Card

Layout = Literal["stack", "fan"]


@dataclass
class Pile:
    id: str
    x: float  # pile centre as a fraction (0-1) of table width
    y: float  # ... and of table height
    layout: Layout = "stack"
    cards: list[Card] = field(default_factory=list)  # cards[-1] is the top


@dataclass
class TableState:
    piles: dict[str, Pile] = field(default_factory=dict)
    # player_id -> hand. Insertion order is seat order (used for dealing).
    hands: dict[str, list[Card]] = field(default_factory=dict)
    version: int = 0
