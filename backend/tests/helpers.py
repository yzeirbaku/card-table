from app.engine.actions import new_pile_id
from app.engine.cards import Card, new_card_id
from app.engine.state import Layout, Pile, TableState


def card(rank: str, suit: str | None, face_up: bool = False) -> Card:
    return Card(new_card_id(), rank, suit, face_up)


def put_pile(
    state: TableState,
    cards: list[Card],
    x: float = 0.5,
    y: float = 0.5,
    layout: Layout = "stack",
) -> Pile:
    pile = Pile(new_pile_id(), x, y, layout, cards)
    state.piles[pile.id] = pile
    return pile
