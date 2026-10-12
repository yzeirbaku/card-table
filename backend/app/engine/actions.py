"""Apply player actions to a table. Pure logic: no I/O, no clock."""

import secrets

from pydantic import ValidationError

from .cards import Card, make_deck, new_card_id
from .protocol import (
    ACTION_ADAPTER,
    Deal,
    FlipCard,
    FlipPile,
    Gather,
    MergePile,
    MoveCard,
    MovePile,
    NewDeck,
    SetLayout,
    Shuffle,
    TakePile,
    ToHand,
    ToPile,
    ToPlayer,
    ToTable,
)
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


def _clamp(v: float) -> float:
    return min(1.0, max(0.0, v))


def _pile(state: TableState, pile_id: str) -> Pile:
    pile = state.piles.get(pile_id)
    if pile is None:
        raise ActionRejected("That pile is gone")
    return pile


def _locate(state: TableState, card_id: str) -> tuple[Pile | None, str | None]:
    """(pile, None) if the card is on the table, (None, owner) if in a hand."""
    for pile in state.piles.values():
        if any(c.id == card_id for c in pile.cards):
            return pile, None
    for owner, hand in state.hands.items():
        if any(c.id == card_id for c in hand):
            return None, owner
    return None, None


def apply_action(state: TableState, player_id: str, raw: object) -> None:
    if player_id not in state.hands:
        raise ActionRejected("You are not seated at this table")
    try:
        action = ACTION_ADAPTER.validate_python(raw)
    except ValidationError:
        raise ActionRejected("Invalid action") from None
    match action:
        case MoveCard():
            _move_card(state, player_id, action)
        case FlipCard():
            _flip_card(state, action)
        case MovePile():
            pile = _pile(state, action.pile_id)
            pile.x, pile.y = _clamp(action.x), _clamp(action.y)
        case MergePile():
            _merge_pile(state, action)
        case Shuffle():
            _shuffled_face_down(_pile(state, action.pile_id).cards)
        case FlipPile():
            pile = _pile(state, action.pile_id)
            pile.cards.reverse()
            for c in pile.cards:
                c.face_up = not c.face_up
        case SetLayout():
            _pile(state, action.pile_id).layout = action.layout
        case Deal():
            _deal(state, action)
        case TakePile():
            pile = _pile(state, action.pile_id)
            for c in pile.cards:
                c.id = new_card_id()
            state.hands[player_id].extend(pile.cards)
            del state.piles[pile.id]
        case Gather():
            _gather(state)
        case NewDeck():
            state.piles.clear()
            for hand in state.hands.values():
                hand.clear()
            _add_center_pile(state, _shuffled_face_down(make_deck(action.jokers)))
    state.version += 1


def _move_card(state: TableState, actor: str, a: MoveCard) -> None:
    source_pile, owner = _locate(state, a.card_id)
    if source_pile is not None:
        if source_pile.cards[-1].id != a.card_id:
            raise ActionRejected("Only the top card of a pile can be moved")
    elif owner != actor:
        # Covers "already gone" and "in someone else's hand" without revealing which.
        raise ActionRejected("That card is no longer there")
    if "from_pile_id" in a.model_fields_set:
        current = source_pile.id if source_pile is not None else None
        if current != a.from_pile_id:
            raise ActionRejected("Someone else moved that card first")

    to = a.to
    target: Pile | None = None
    if isinstance(to, ToPile):
        target = _pile(state, to.pile_id)
        if target is source_pile:
            raise ActionRejected("The card is already on that pile")
    elif isinstance(to, ToPlayer) and to.player_id not in state.hands:
        raise ActionRejected("That player has left")

    # Validation done; from here on nothing can fail.
    from_hand = source_pile is None
    if source_pile is not None:
        card = source_pile.cards.pop()
        if not source_pile.cards:
            del state.piles[source_pile.id]
    else:
        hand = state.hands[actor]
        card = hand.pop(next(i for i, c in enumerate(hand) if c.id == a.card_id))

    if isinstance(to, ToHand):
        if not from_hand:
            card.id = new_card_id()
        hand = state.hands[actor]
        index = len(hand) if to.index is None else max(0, min(to.index, len(hand)))
        hand.insert(index, card)
    elif isinstance(to, ToPlayer):
        if not (from_hand and to.player_id == actor):
            card.id = new_card_id()
        state.hands[to.player_id].append(card)
    else:
        if a.face_up is not None:
            card.face_up = a.face_up
        elif from_hand:
            card.face_up = True
        if target is not None:
            target.cards.append(card)
        else:
            assert isinstance(to, ToTable)
            pile = Pile(new_pile_id(), _clamp(to.x), _clamp(to.y), cards=[card])
            state.piles[pile.id] = pile


def _flip_card(state: TableState, a: FlipCard) -> None:
    pile, _ = _locate(state, a.card_id)
    if pile is None or pile.cards[-1].id != a.card_id:
        raise ActionRejected("Only the top card of a pile can be flipped")
    pile.cards[-1].face_up = not pile.cards[-1].face_up


def _merge_pile(state: TableState, a: MergePile) -> None:
    if a.pile_id == a.onto_pile_id:
        raise ActionRejected("Can't stack a pile onto itself")
    source = _pile(state, a.pile_id)
    target = _pile(state, a.onto_pile_id)
    target.cards.extend(source.cards)
    del state.piles[source.id]


def _deal(state: TableState, a: Deal) -> None:
    pile = _pile(state, a.pile_id)
    for _ in range(a.count):
        for seat in state.hands:
            if not pile.cards:
                break
            card = pile.cards.pop()
            card.id = new_card_id()
            state.hands[seat].append(card)
    if not pile.cards:
        del state.piles[pile.id]


def _gather(state: TableState) -> None:
    cards = [c for pile in state.piles.values() for c in pile.cards]
    for hand in state.hands.values():
        cards.extend(hand)
        hand.clear()
    state.piles.clear()
    _add_center_pile(state, _shuffled_face_down(cards))
