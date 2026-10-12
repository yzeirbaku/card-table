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


def move(card_id: str, face_up: bool | None = None, **to) -> dict:
    action = {"type": "move_card", "card_id": card_id, "to": to}
    if face_up is not None:
        action["face_up"] = face_up
    return action


def test_top_card_to_empty_table_makes_a_new_pile(table):
    d = deck(table)
    top = d.cards[-1]
    apply_action(table, "ana", move(top.id, kind="table", x=0.2, y=0.3))
    (new,) = [p for p in table.piles.values() if p is not d]
    assert new.cards == [top]
    assert (new.x, new.y) == (0.2, 0.3)
    assert len(d.cards) == 51
    assert top.face_up is False  # table-to-table keeps orientation


def test_only_the_top_card_can_move(table):
    d = deck(table)
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", move(d.cards[0].id, kind="table", x=0.1, y=0.1))


def test_picking_up_into_hand_reissues_the_card_id(table):
    top = deck(table).cards[-1]
    old_id = top.id
    apply_action(table, "ana", move(old_id, kind="hand"))
    assert table.hands["ana"] == [top]
    assert top.id != old_id


def test_second_grab_of_same_card_is_rejected(table):
    top_id = deck(table).cards[-1].id
    apply_action(table, "ana", move(top_id, kind="hand"))
    with pytest.raises(ActionRejected):
        apply_action(table, "ben", move(top_id, kind="hand"))
    assert table.hands["ben"] == []
    assert len(table.hands["ana"]) == 1


def test_playing_from_hand_lands_face_up_by_default(table):
    c = card("A", "S")
    table.hands["ana"].append(c)
    apply_action(table, "ana", move(c.id, kind="table", x=0.5, y=0.2))
    assert c.face_up is True
    assert table.hands["ana"] == []


def test_playing_from_hand_face_down_on_request(table):
    c = card("A", "S")
    table.hands["ana"].append(c)
    apply_action(table, "ana", move(c.id, face_up=False, kind="table", x=0.5, y=0.2))
    assert c.face_up is False


def test_cannot_move_another_players_hand_card(table):
    c = card("A", "S")
    table.hands["ben"].append(c)
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", move(c.id, kind="table", x=0.5, y=0.5))
    assert table.hands["ben"] == [c]


def test_move_onto_pile_and_emptied_source_pile_disappears(table):
    d = deck(table)
    lone = put_pile(table, [card("K", "H", face_up=True)], 0.2, 0.2)
    apply_action(table, "ana", move(lone.cards[-1].id, kind="pile", pile_id=d.id))
    assert lone.id not in table.piles
    assert d.cards[-1].rank == "K"
    assert len(d.cards) == 53


def test_dropping_onto_its_own_pile_is_rejected(table):
    d = deck(table)
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", move(d.cards[-1].id, kind="pile", pile_id=d.id))


def test_dropping_onto_a_vanished_pile_is_rejected_and_card_stays(table):
    d = deck(table)
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", move(d.cards[-1].id, kind="pile", pile_id="gone"))
    assert len(d.cards) == 52


def test_pass_card_to_another_player(table):
    c = card("Q", "D")
    table.hands["ana"].append(c)
    old_id = c.id
    apply_action(table, "ana", move(c.id, kind="player", player_id="ben"))
    assert table.hands["ana"] == []
    assert table.hands["ben"] == [c]
    assert c.id != old_id


def test_pass_to_unknown_player_is_rejected(table):
    c = card("Q", "D")
    table.hands["ana"].append(c)
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", move(c.id, kind="player", player_id="zed"))
    assert table.hands["ana"] == [c]


def test_reorder_within_hand_keeps_ids(table):
    a, b, c = card("A", "S"), card("2", "S"), card("3", "S")
    table.hands["ana"].extend([a, b, c])
    ids = (a.id, b.id, c.id)
    apply_action(table, "ana", move(c.id, kind="hand", index=0))
    assert table.hands["ana"] == [c, a, b]
    assert (a.id, b.id, c.id) == ids


def test_hand_index_is_clamped(table):
    a, b = card("A", "S"), card("2", "S")
    table.hands["ana"].extend([a, b])
    apply_action(table, "ana", move(a.id, kind="hand", index=999))
    assert table.hands["ana"] == [b, a]
    apply_action(table, "ana", move(a.id, kind="hand", index=-5))
    assert table.hands["ana"] == [a, b]


def test_flip_top_card(table):
    d = deck(table)
    before = table.version
    apply_action(table, "ana", {"type": "flip_card", "card_id": d.cards[-1].id})
    assert d.cards[-1].face_up is True
    assert table.version == before + 1


def test_flip_non_top_card_is_rejected(table):
    d = deck(table)
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", {"type": "flip_card", "card_id": d.cards[0].id})


def test_coordinates_are_clamped(table):
    top = deck(table).cards[-1]
    apply_action(table, "ana", move(top.id, kind="table", x=5, y=-1))
    pile = next(p for p in table.piles.values() if p.cards == [top])
    assert (pile.x, pile.y) == (1.0, 0.0)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "move_card",
        {},
        {"type": "move_card"},
        {"type": "explode"},
        {"type": "move_card", "card_id": "x", "to": {"kind": "moon"}},
        {"type": "move_card", "card_id": "x", "to": {"kind": "table", "x": float("nan"), "y": 0}},
        {"type": "deal", "pile_id": "x", "count": 0},
    ],
)
def test_malformed_actions_rejected(table, bad):
    before = table.version
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", bad)
    assert table.version == before


def test_player_without_a_seat_is_rejected(table):
    with pytest.raises(ActionRejected):
        apply_action(table, "zed", {"type": "flip_card", "card_id": deck(table).cards[-1].id})
