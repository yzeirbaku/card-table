"""Murlan cards as short codes: rank then suit ("7H", "10S", "AS"), plus the two
jokers "JB" (black) and "JR" (red). A code is just a card's face, so a code only
ever goes to a player who may see that face."""

from collections.abc import Iterable

SUITS = ("S", "H", "D", "C")  # spades, hearts, diamonds, clubs
RANKS = ("3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A", "2")  # low to high
BLACK_JOKER = "JB"
RED_JOKER = "JR"
JOKERS = (BLACK_JOKER, RED_JOKER)
DECK = tuple(rank + suit for suit in SUITS for rank in RANKS) + JOKERS

_IS_CARD = frozenset(DECK)
_POWER = {rank: i for i, rank in enumerate(RANKS)} | {
    BLACK_JOKER: len(RANKS),
    RED_JOKER: len(RANKS) + 1,
}
_SUIT_SYMBOLS = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}


def is_card(code: object) -> bool:
    return isinstance(code, str) and code in _IS_CARD


def rank_of(card: str) -> str:
    """"10" for "10S". A joker is its own rank."""
    return card if card in JOKERS else card[:-1]


def suit_of(card: str) -> str | None:
    return None if card in JOKERS else card[-1]


def power(card: str) -> int:
    """Beating order: 3 lowest, up to A, then 2, black joker, red joker."""
    return _POWER[rank_of(card)]


def sort_key(card: str) -> tuple[int, int]:
    suit = suit_of(card)
    return (power(card), SUITS.index(suit) if suit else 0)


def sort_cards(cards: Iterable[str]) -> list[str]:
    return sorted(cards, key=sort_key)


def card_name(card: str) -> str:
    """"3♠", "10♥", "red joker": for messages to players."""
    if card == BLACK_JOKER:
        return "black joker"
    if card == RED_JOKER:
        return "red joker"
    return rank_of(card) + _SUIT_SYMBOLS[card[-1]]
