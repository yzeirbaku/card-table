import pytest

from app.murlan.game import Rejected
from app.murlan.views import view_for
from tests.murlan_helpers import new_game, rig


def test_two_players_giving_up_ends_the_round_and_the_other_wins_it():
    g = new_game(2)
    rig(g, {"p0": ["3C", "9H"], "p1": ["4S", "5S"]}, "p1")
    g.give_up("p1")
    assert g.last_result.places == ["p0", "p1"]
    assert g.scores == [1, 0]
    assert g.last_result.out == 0  # nobody played their last card


def test_three_players_whoever_gives_up_is_last_and_the_others_play_on():
    g = new_game(3)
    rig(g, {"p0": ["3C"], "p1": ["4S", "5S"], "p2": ["6S", "7S"]}, "p2")
    g.give_up("p2")
    assert g.phase == "playing" and g.hands["p2"] == [] and g.gave_up == ["p2"]
    assert g.turn == "p0"
    g.play("p0", ["3C"])  # out first: only p1 is left holding cards, so the round is over
    assert g.last_result.places == ["p0", "p1", "p2"]
    assert g.scores == [2, 1, 0]


def test_four_players_one_team_out_first_and_second_with_the_other_team_one_down():
    g = new_game(4)
    rig(g, {"p0": ["9S", "9H"], "p1": ["3C"], "p2": ["10S", "10H"], "p3": ["4C"]}, "p0")
    g.give_up("p0")
    g.play("p1", ["3C"])  # p1 out, 1st; p2 is next (p0 has no cards)
    assert g.turn == "p2"
    g.pass_turn("p2")
    g.play("p3", ["4C"])  # p3 out, 2nd: p1 & p3 took 1st and 2nd
    assert g.phase != "agreeing_loser"  # p0 gave up, so p0 is last; nobody has to agree
    assert g.last_result.places == ["p1", "p3", "p2", "p0"]
    assert g.scores == [1, 5]


def test_giving_up_on_your_turn_moves_the_turn_on_and_frees_the_first_lead():
    g = new_game(3)
    rig(g, {"p0": ["3S", "8H"], "p1": ["4S", "5S"], "p2": ["6S", "7S"]}, "p0")
    g.must_include = "3S"
    g.give_up("p0")
    assert g.turn == "p1"
    assert g.must_include is None  # the 3♠ went with p0's cards
    g.play("p1", ["5S"])  # leads anything


def test_the_lead_passes_on_when_the_player_who_won_the_trick_gives_up():
    g = new_game(3)
    rig(g, {"p0": ["3C", "8H"], "p1": ["4S", "5S"], "p2": ["6S", "7S"]}, "p0")
    g.play("p0", ["8H"])
    g.pass_turn("p1")
    g.pass_turn("p2")  # the trick is p0's: their lead
    g.give_up("p0")
    assert g.turn == "p1" and g.top is None  # p1 leads anything
    g.play("p1", ["4S"])


def test_giving_up_is_refused_when_its_not_your_turn():
    g = new_game(3)
    rig(g, {"p0": ["3C", "8H"], "p1": ["4S", "5S"], "p2": ["6S", "7S"]}, "p0")
    for p in ("p1", "p2"):
        with pytest.raises(Rejected):
            g.give_up(p)
    assert g.gave_up == [] and g.hands["p1"] == ["4S", "5S"]


def test_giving_up_is_refused_outside_play_and_once_youre_done():
    g = new_game(3)
    with pytest.raises(Rejected):
        g.give_up("p0")  # choosing the target
    rig(g, {"p0": ["3C"], "p1": ["4S", "5S"], "p2": ["6S", "7S"]}, "p1")
    g.give_up("p1")
    with pytest.raises(Rejected):
        g.give_up("p1")
    with pytest.raises(Rejected):
        g.give_up("p9")


def test_thrown_cards_are_face_up_for_everyone_until_the_round_is_over():
    g = new_game(3)
    rig(g, {"p0": ["3C"], "p1": ["4S", "5S"], "p2": ["6S", "7S"]}, "p2")
    g.give_up("p2")
    assert all(view_for(g, p)["thrown"] == {"p2": ["6S", "7S"]} for p in g.seats)
    g.play("p0", ["3C"])  # the round ends: the throw is kept with the result, for the end of round
    assert view_for(g, "p1")["thrown"] == {}
    assert view_for(g, "p1")["last_round"]["thrown"] == {"p2": ["6S", "7S"]}


def test_a_player_who_passed_and_then_gives_up_no_longer_shows_as_passed():
    g = new_game(4)
    rig(g, {"p0": ["3C"], "p1": ["4S", "5S"], "p2": ["6S", "7S"], "p3": ["8S", "9S"]}, "p0")
    g.play("p0", ["3C"])  # out
    for p in ("p1", "p2", "p3"):
        g.pass_turn(p)  # the trick is won; p0 is out, so p1 leads, the passes still on show
    assert g.turn == "p1" and g.passed == ["p1", "p2", "p3"]
    g.give_up("p1")
    assert g.passed == ["p2", "p3"]


def test_giving_up_is_refused_while_the_game_is_paused():
    g = new_game(3)
    rig(g, {"p0": ["3C"], "p1": ["4S", "5S"], "p2": ["6S", "7S"]}, "p0")
    g.disconnect("p2")
    with pytest.raises(Rejected):
        g.give_up("p0")
