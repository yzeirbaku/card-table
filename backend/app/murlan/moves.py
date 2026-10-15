"""Every play a hand could make right now. Pure functions, no game state: the
computer player picks from these. Suits never matter for beating anything, so
for each shape only one set of cards is listed (the lowest suits, or the card
the first lead must include)."""

from collections import defaultdict

from .cards import JOKERS, rank_of, sort_key
from .combos import MIN_STRAIGHT, Play, beats, classify

# Straight order: A and 2 sit at either end (A=1, 2=2 or A=14, 2=15), never round the corner.
_RANK_AT = {1: "A", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "10",
            11: "J", 12: "Q", 13: "K", 14: "A", 15: "2"}
_SAME_RANK_SIZES = (1, 2, 3, 4)  # single, pair, triple, bomb


def by_rank(hand: list[str]) -> dict[str, list[str]]:
    """Cards grouped by rank, lowest suit first. Jokers are left out (they only go down alone)."""
    groups: dict[str, list[str]] = defaultdict(list)
    for card in sorted(hand, key=sort_key):
        if card not in JOKERS:
            groups[rank_of(card)].append(card)
    return groups


def straight_runs(counts: dict[str, int], multiple: int) -> list[tuple[str, ...]]:
    """Every run of ranks (5 or more) the counts hold `multiple` of each, in run order.
    The same ranks reachable two ways (A-2-3…K both low and high) are listed once."""
    runs: list[tuple[str, ...]] = []
    seen: set[frozenset[str]] = set()
    for start in range(1, 16):
        for end in range(start + MIN_STRAIGHT - 1, 16):
            ranks = tuple(_RANK_AT[p] for p in range(start, end + 1))
            if len(set(ranks)) != len(ranks):
                break  # A or 2 twice: longer runs from here only get worse
            if counts.get(ranks[-1], 0) < multiple:
                break  # a gap: nothing longer from this start
            if all(counts.get(r, 0) >= multiple for r in ranks):
                key = frozenset(ranks)
                if key not in seen:
                    seen.add(key)
                    runs.append(ranks)
    return runs


def legal_plays(hand: list[str], top: Play | None, must_include: str | None = None) -> list[list[str]]:
    """Every distinct play from `hand` that may go down now: beats `top` (anything, if
    leading) and includes `must_include` if set."""
    groups = by_rank(hand)
    if must_include and must_include not in JOKERS:  # the card that must go down is the one picked from its rank
        group = groups.get(rank_of(must_include))
        if group and must_include in group:
            group.remove(must_include)
            group.insert(0, must_include)
    shapes: list[list[str]] = [[j] for j in JOKERS if j in hand]
    for cards in groups.values():
        shapes.extend(cards[:size] for size in _SAME_RANK_SIZES if len(cards) >= size)
    counts = {r: len(cards) for r, cards in groups.items()}
    for multiple in (1, 2, 3):
        for run in straight_runs(counts, multiple):
            shapes.append([c for r in run for c in groups[r][:multiple]])
    plays = []
    for cards in shapes:
        if must_include and must_include not in cards:
            continue
        play = classify(cards)
        if play is None:  # can't happen; the game would refuse it anyway
            continue
        if top is None or beats(play, top):
            plays.append(cards)
    return plays
