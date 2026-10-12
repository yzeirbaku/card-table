"""Apply player actions to a table. Pure logic: no I/O, no clock."""

import secrets

from .cards import Card, make_deck, new_card_id
from .state import Pile, TableState

_rng = secrets.SystemRandom()
CENTER = (0.5, 0.5)


class ActionRejected(Exception):
    """The action is invalid or stale. The message is shown to the player."""


def new_pile_id() -> str:
    return secrets.token_hex(4)


def _shuffled_face_down(cards: list[Card]) -> list[Card]:
    for c in cards:
        c.face_up = False
        c.id = new_card_id()
    _rng.shuffle(cards)
    return cards


def _add_center_pile(state: TableState, cards: list[Card]) -> None:
    pile = Pile(new_pile_id(), *CENTER, cards=cards)
    state.piles[pile.id] = pile


def new_table(jokers: int = 0) -> TableState:
    state = TableState()
    _add_center_pile(state, _shuffled_face_down(make_deck(jokers)))
    return state


def add_player(state: TableState, player_id: str) -> None:
    state.hands.setdefault(player_id, [])
    state.version += 1


def remove_player(state: TableState, player_id: str) -> None:
    cards = state.hands.pop(player_id, [])
    if cards:
        _add_center_pile(state, _shuffled_face_down(cards))
    state.version += 1
