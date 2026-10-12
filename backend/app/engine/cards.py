"""Card identities and decks."""

import secrets
from dataclasses import dataclass

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["S", "H", "D", "C"]  # spades, hearts, diamonds, clubs
JOKER = "JOKER"


def new_card_id() -> str:
    """Opaque id. Re-issued whenever a card enters a hand or is shuffled, so an
    id seen face up earlier can't be used to track the card once it's hidden."""
    return secrets.token_hex(6)


@dataclass
class Card:
    id: str
    rank: str
    suit: str | None  # None for jokers
    face_up: bool = False


def make_deck(jokers: int = 0) -> list[Card]:
    if not 0 <= jokers <= 2:
        raise ValueError("jokers must be 0, 1 or 2")
    cards = [Card(new_card_id(), rank, suit) for suit in SUITS for rank in RANKS]
    cards += [Card(new_card_id(), JOKER, None) for _ in range(jokers)]
    return cards
