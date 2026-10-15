"""What a set of cards is as a play, and whether one play beats another.
Pure functions, no game state."""

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from .cards import JOKERS, power, rank_of

Kind = Literal["single", "pair", "triple", "bomb", "straight", "double_straight", "triple_straight"]
STRAIGHTS: tuple[Kind, ...] = ("straight", "double_straight", "triple_straight")
KIND_NAMES: dict[str, str] = {
    "single": "a single card",
    "pair": "a pair",
    "triple": "three of a kind",
    "bomb": "a bomb",
    "straight": "a straight",
    "double_straight": "a double straight",
    "triple_straight": "a triple straight",
}
MIN_STRAIGHT = 5
_SAME_RANK: dict[int, Kind] = {1: "single", 2: "pair", 3: "triple", 4: "bomb"}
# Position in straight order, read one of two ways: A and 2 at the bottom (A=1, 2=2: A-2-3-4-5,
# 2-3-4-5-6) or at the top (A=14, 2=15: 10-J-Q-K-A, J-Q-K-A-2). Never round the corner: K-A-2-3.
_POSITION = {"3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10,
             "J": 11, "Q": 12, "K": 13}
_LOW = {"A": 1, "2": 2}
_HIGH = {"A": 14, "2": 15}


@dataclass(frozen=True)
class Play:
    kind: Kind
    rank: int  # same-rank plays: the cards' power; straights: lowest position
    length: int  # straights: how many ranks; otherwise 1


def classify(cards: list[str]) -> Play | None:
    """The play these cards make, or None if they don't make one."""
    if not cards or len(set(cards)) != len(cards):
        return None
    if len(cards) == 1:
        return Play("single", power(cards[0]), 1)
    if any(c in JOKERS for c in cards):
        return None  # jokers only ever go down as singles
    counts = Counter(rank_of(c) for c in cards)
    if len(counts) == 1:
        return Play(_SAME_RANK[len(cards)], power(cards[0]), 1)
    multiples = set(counts.values())
    if len(multiples) != 1 or len(counts) < MIN_STRAIGHT:
        return None
    multiple = multiples.pop()
    if multiple > 3:
        return None
    low = _run_start(counts.keys())
    if low is None:
        return None
    return Play(STRAIGHTS[multiple - 1], low, len(counts))


def _run_start(ranks) -> int | None:
    """Lowest position if the ranks are consecutive in straight order, else None."""
    for ends in (_LOW, _HIGH):
        positions = sorted(ends.get(r) or _POSITION[r] for r in ranks)
        if positions[-1] - positions[0] == len(positions) - 1:
            return positions[0]
    return None


def beats(new: Play, top: Play) -> bool:
    if new.kind == "bomb":
        return top.kind != "bomb" or new.rank > top.rank
    if new.kind != top.kind:
        return False
    if new.kind in STRAIGHTS:
        return new.length == top.length and new.rank == top.rank + 1
    return new.rank > top.rank
