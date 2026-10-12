import pytest

from app.engine.actions import add_player, new_table, remove_player
from app.engine.cards import make_deck
from tests.helpers import card


def test_standard_deck_has_52_unique_cards():
    deck = make_deck()
    assert len(deck) == 52
    assert len({(c.rank, c.suit) for c in deck}) == 52
    assert len({c.id for c in deck}) == 52


def test_jokers_are_added():
    deck = make_deck(jokers=2)
    assert len(deck) == 54
    assert [c.rank for c in deck].count("JOKER") == 2


def test_joker_count_out_of_range_rejected():
    with pytest.raises(ValueError):
        make_deck(jokers=3)


def test_new_table_is_one_face_down_deck_in_the_center():
    state = new_table()
    (pile,) = state.piles.values()
    assert (pile.x, pile.y) == (0.5, 0.5)
    assert len(pile.cards) == 52
    assert not any(c.face_up for c in pile.cards)
    assert state.hands == {}


def test_add_player_gives_an_empty_hand_in_seat_order():
    state = new_table()
    add_player(state, "ana")
    add_player(state, "ben")
    assert list(state.hands) == ["ana", "ben"]
    assert state.hands["ana"] == []


def test_removed_players_hand_returns_face_down_to_the_center():
    state = new_table()
    add_player(state, "ana")
    held = [card("A", "S", face_up=True), card("K", "H", face_up=True)]
    state.hands["ana"].extend(held)
    remove_player(state, "ana")
    assert "ana" not in state.hands
    returned = [p for p in state.piles.values() if len(p.cards) == 2]
    assert len(returned) == 1
    assert {(c.rank, c.suit) for c in returned[0].cards} == {("A", "S"), ("K", "H")}
    assert not any(c.face_up for c in returned[0].cards)


def test_removing_player_with_empty_hand_adds_no_pile():
    state = new_table()
    add_player(state, "ana")
    remove_player(state, "ana")
    assert len(state.piles) == 1
