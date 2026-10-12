"""Per-player views. The ONLY way table state leaves the server: other
players' hands are omitted and face-down cards carry no rank or suit."""

from typing import Any

from .cards import Card
from .state import TableState


def _card(card: Card, visible: bool) -> dict[str, Any]:
    if not visible:
        return {"id": card.id, "face_up": False}
    return {"id": card.id, "face_up": True, "rank": card.rank, "suit": card.suit}


def view_for(state: TableState, player_id: str) -> dict[str, Any]:
    return {
        "version": state.version,
        "piles": [
            {
                "id": p.id,
                "x": p.x,
                "y": p.y,
                "layout": p.layout,
                "cards": [_card(c, c.face_up) for c in p.cards],
            }
            for p in state.piles.values()
        ],
        "hand": [_card(c, True) for c in state.hands.get(player_id, [])],
    }
