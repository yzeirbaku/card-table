import pytest

from app.engine.actions import ActionRejected, add_player, apply_action, new_table
from app.engine.state import TableState
from tests.helpers import card, put_pile


@pytest.fixture
def table() -> TableState:
    state = new_table()
    add_player(state, "ana")
    add_player(state, "ben")
    return state


def deck(state: TableState):
    return max(state.piles.values(), key=lambda p: len(p.cards))


def test_move_pile_clamps(table):
    d = deck(table)
    apply_action(table, "ana", {"type": "move_pile", "pile_id": d.id, "x": 0.3, "y": 1.7})
    assert (d.x, d.y) == (0.3, 1.0)


def test_merge_puts_pile_on_top_and_removes_it(table):
    d = deck(table)
    small = put_pile(table, [card("A", "S", True), card("K", "H", True)], 0.1, 0.1)
    apply_action(table, "ana", {"type": "merge_pile", "pile_id": small.id, "onto_pile_id": d.id})
    assert small.id not in table.piles
    assert [c.rank for c in d.cards[-2:]] == ["A", "K"]


def test_merge_onto_itself_is_rejected(table):
    d = deck(table)
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", {"type": "merge_pile", "pile_id": d.id, "onto_pile_id": d.id})


def test_shuffle_keeps_cards_turns_them_down_and_reissues_ids(table):
    d = deck(table)
    d.cards[-1].face_up = True
    before_cards = sorted((c.rank, c.suit or "") for c in d.cards)
    before_ids = {c.id for c in d.cards}
    apply_action(table, "ana", {"type": "shuffle", "pile_id": d.id})
    assert sorted((c.rank, c.suit or "") for c in d.cards) == before_cards
    assert not any(c.face_up for c in d.cards)
    assert before_ids.isdisjoint({c.id for c in d.cards})


def test_flip_pile_reverses_order_and_orientation(table):
    a, b = card("A", "S", face_up=True), card("B", "S", face_up=False)
    pile = put_pile(table, [a, b])
    apply_action(table, "ana", {"type": "flip_pile", "pile_id": pile.id})
    assert pile.cards == [b, a]
    assert (b.face_up, a.face_up) == (True, False)


def test_set_layout(table):
    d = deck(table)
    apply_action(table, "ana", {"type": "set_layout", "pile_id": d.id, "layout": "fan"})
    assert d.layout == "fan"


def test_deal_round_robin_to_every_seat(table):
    d = deck(table)
    apply_action(table, "ana", {"type": "deal", "pile_id": d.id, "count": 3})
    assert len(table.hands["ana"]) == 3
    assert len(table.hands["ben"]) == 3
    assert len(d.cards) == 46


def test_deal_reissues_ids(table):
    d = deck(table)
    top_ids = {c.id for c in d.cards[-2:]}
    apply_action(table, "ana", {"type": "deal", "pile_id": d.id, "count": 1})
    dealt = {c.id for hand in table.hands.values() for c in hand}
    assert top_ids.isdisjoint(dealt)


def test_deal_more_than_available_deals_what_is_there(table):
    small = put_pile(table, [card("2", "S"), card("3", "S"), card("4", "S")], 0.2, 0.2)
    apply_action(table, "ben", {"type": "deal", "pile_id": small.id, "count": 5})
    assert len(table.hands["ana"]) == 2
    assert len(table.hands["ben"]) == 1
    assert small.id not in table.piles


def test_take_pile_into_hand(table):
    small = put_pile(table, [card("2", "S"), card("3", "S")], 0.2, 0.2)
    apply_action(table, "ben", {"type": "take_pile", "pile_id": small.id})
    assert [c.rank for c in table.hands["ben"]] == ["2", "3"]
    assert small.id not in table.piles


def test_gather_collects_everything_into_one_face_down_pile(table):
    d = deck(table)
    apply_action(table, "ana", {"type": "deal", "pile_id": d.id, "count": 5})
    put_pile(table, [d.cards.pop()], 0.1, 0.9)
    table.piles[next(iter(table.piles))].cards[-1].face_up = True
    apply_action(table, "ana", {"type": "gather"})
    (pile,) = table.piles.values()
    assert len(pile.cards) == 52
    assert (pile.x, pile.y) == (0.5, 0.5)
    assert not any(c.face_up for c in pile.cards)
    assert all(hand == [] for hand in table.hands.values())


def test_new_deck_with_jokers_resets_table_and_hands(table):
    apply_action(table, "ana", {"type": "deal", "pile_id": deck(table).id, "count": 2})
    apply_action(table, "ana", {"type": "new_deck", "jokers": 2})
    (pile,) = table.piles.values()
    assert len(pile.cards) == 54
    assert all(hand == [] for hand in table.hands.values())
    assert list(table.hands) == ["ana", "ben"]


@pytest.mark.parametrize(
    "action",
    [
        {"type": "move_pile", "pile_id": "gone", "x": 0, "y": 0},
        {"type": "shuffle", "pile_id": "gone"},
        {"type": "deal", "pile_id": "gone", "count": 1},
        {"type": "take_pile", "pile_id": "gone"},
    ],
)
def test_actions_on_vanished_pile_are_rejected(table, action):
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", action)
