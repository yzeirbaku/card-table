import pytest

from app.murlan.cards import DECK
from app.murlan.game import Game, Rejected
from tests.murlan_helpers import Reverse, Rotate, new_game, rig


def test_creator_picks_the_target_and_the_first_round_starts():
    g = new_game(4)
    assert g.phase == "choosing_target"
    with pytest.raises(Rejected, match="creator"):
        g.choose_target("p1", 13)
    with pytest.raises(Rejected, match="13 or 21"):
        g.choose_target("p0", 15)
    g.choose_target("p0", 21)
    assert g.target == 21 and g.phase == "playing"
    with pytest.raises(Rejected, match="already"):
        g.choose_target("p0", 13)


def test_strangers_cannot_move():
    g = new_game(2)
    with pytest.raises(Rejected, match="not playing"):
        g.choose_target("zz", 13)


@pytest.mark.parametrize("n, sizes", [(2, [18, 18]), (3, [18, 18, 18]), (4, [14, 14, 13, 13])])
def test_deal_sizes(n, sizes):
    g = new_game(n)
    g.choose_target("p0", 13)
    assert [len(g.hands[p]) for p in g.seats] == sizes
    dealt = [c for p in g.seats for c in g.hands[p]]
    assert len(set(dealt)) == len(dealt)
    assert set(dealt) <= set(DECK)
    assert g.deck == []  # nothing left lying around after the deal


def test_first_lead_is_the_three_of_spades_and_must_include_it():
    g = new_game(4)
    g.choose_target("p0", 13)
    leader = g.turn
    assert "3S" in g.hands[leader] and g.must_include == "3S"
    other = next(c for c in g.hands[leader] if c != "3S")
    with pytest.raises(Rejected, match="include the 3♠"):
        g.play(leader, [other])
    g.play(leader, ["3S"])
    assert g.must_include is None


def test_two_players_lowest_spade_dealt_leads_when_3s_is_out_of_play():
    g = new_game(2, rng=Rotate())
    g.choose_target("p0", 13)
    assert all("3S" not in h for h in g.hands.values())
    assert g.must_include == "4S" and g.turn == "p0"


def test_two_players_with_no_spade_dealt_the_lowest_card_leads():
    g = new_game(2, rng=Reverse())
    g.choose_target("p0", 13)
    assert not any(c.endswith("S") for h in g.hands.values() for c in h)
    assert g.must_include == "3D" and g.turn == "p1"


def test_passing_only_skips_that_turn():
    g = new_game(3)
    rig(g, {"p0": ["3S", "KH"], "p1": ["5H", "6H"], "p2": ["4H", "7H"]}, "p0")
    g.play("p0", ["3S"])
    g.pass_turn("p1")
    g.play("p2", ["4H"])
    g.pass_turn("p0")
    g.play("p1", ["5H"])  # p1 passed earlier and can still play
    assert g.trick[-1][0] == "p1"


def test_pile_clears_when_the_turn_gets_back_to_the_last_player():
    g = new_game(3)
    rig(g, {"p0": ["3S", "4S"], "p1": ["5H"], "p2": ["6H"]}, "p0")
    g.play("p0", ["4S"])
    g.pass_turn("p1")
    g.pass_turn("p2")
    assert g.turn == "p0" and g.trick == [] and g.top is None and g.passed == []
    g.play("p0", ["3S"])  # leads anything, even lower than before


def test_lead_moves_on_when_the_last_player_is_out():
    g = new_game(3)
    rig(g, {"p0": ["AS"], "p1": ["5H", "6H"], "p2": ["4H", "7H"]}, "p0")
    g.play("p0", ["AS"])
    assert g.places == ["p0"] and g.turn == "p1"
    g.pass_turn("p1")
    g.pass_turn("p2")
    assert g.turn == "p1" and g.top is None


def test_moves_that_are_not_allowed():
    g = new_game(2)
    rig(g, {"p0": ["3S", "5H", "5S", "8D"], "p1": ["4S", "9H", "9S", "JB"]}, "p0")
    with pytest.raises(Rejected, match="You lead"):
        g.pass_turn("p0")
    with pytest.raises(Rejected, match="not your turn"):
        g.play("p1", ["4S"])
    with pytest.raises(Rejected, match="aren't in your hand"):
        g.play("p0", ["4S"])
    with pytest.raises(Rejected, match="aren't in your hand"):
        g.play("p0", ["3S", "3S"])
    with pytest.raises(Rejected, match="don't make a play"):
        g.play("p0", ["3S", "5H"])
    g.play("p0", ["5H", "5S"])
    with pytest.raises(Rejected, match="Play a pair or a bomb"):
        g.play("p1", ["JB"])
    g.play("p1", ["9H", "9S"])
    assert g.top.kind == "pair"


def test_a_lower_card_does_not_beat_the_pile():
    g = new_game(2)
    rig(g, {"p0": ["9D", "3C"], "p1": ["4S", "KS"]}, "p0")
    g.play("p0", ["9D"])
    with pytest.raises(Rejected, match="doesn't beat"):
        g.play("p1", ["4S"])
    g.play("p1", ["KS"])


def test_a_bomb_beats_a_joker_and_only_a_higher_bomb_beats_a_bomb():
    g = new_game(2)
    rig(g, {"p0": ["JR", "3C", "3D", "3H", "3S", "9D"],
            "p1": ["4S", "4H", "4D", "4C", "5S"]}, "p0")
    g.play("p0", ["JR"])
    g.play("p1", ["4S", "4H", "4D", "4C"])
    assert g.top.kind == "bomb"
    with pytest.raises(Rejected, match="higher bomb"):
        g.play("p0", ["9D"])
    with pytest.raises(Rejected, match="higher bomb"):
        g.play("p0", ["3C", "3D", "3H", "3S"])


def test_two_players_round_and_points():
    g = new_game(2)
    rig(g, {"p0": ["3S"], "p1": ["4S", "5S"]}, "p0")
    g.play("p0", ["3S"])
    assert g.scores == [1, 0]
    assert g.last_result.places == ["p0", "p1"]
    assert g.last_result.winner == "p0" and g.last_result.loser == "p1"
    assert g.rounds_played == 1 and g.phase == "cutting"


def test_three_players_round_ends_when_two_are_out():
    g = new_game(3)
    rig(g, {"p0": ["3S"], "p1": ["4S"], "p2": ["5S", "6S"]}, "p0")
    g.play("p0", ["3S"])
    g.play("p1", ["4S"])
    assert g.scores == [2, 1, 0]
    assert g.last_result.places == ["p0", "p1", "p2"]


def test_four_players_teams_add_their_points():
    g = new_game(4)
    rig(g, {"p0": ["3S"], "p1": ["4S"], "p2": ["5S"], "p3": ["6S", "7S"]}, "p0")
    g.play("p0", ["3S"])
    g.play("p1", ["4S"])
    assert g.phase == "playing"  # 1st and 2nd are on different teams
    g.play("p2", ["5S"])
    # p0 3 + p2 1 for seats 0+2; p1 2 + p3 0 for seats 1+3
    assert g.scores == [4, 2]
    assert g.last_result.loser == "p3"


def test_four_players_one_team_first_and_second_then_the_others_agree_on_last():
    g = new_game(4)
    rig(g, {"p0": ["3S"], "p1": ["4S", "9S"], "p2": ["5S"], "p3": ["6S", "7S"]}, "p0")
    g.play("p0", ["3S"])
    g.pass_turn("p1")
    g.play("p2", ["5S"])
    assert g.phase == "agreeing_loser" and g.turn is None
    assert g.loser_voters() == ["p1", "p3"]
    with pytest.raises(Rejected, match="other team"):
        g.pick_loser("p0", "p1")
    with pytest.raises(Rejected, match="one of the two"):
        g.pick_loser("p1", "p0")
    g.pick_loser("p1", "p3")
    g.pick_loser("p3", "p1")  # they don't agree yet
    assert g.phase == "agreeing_loser"
    g.pick_loser("p3", "p3")
    assert g.scores == [5, 1]
    assert g.last_result.places == ["p0", "p2", "p1", "p3"]
    assert g.phase == "cutting"


def test_reaching_the_target_wins():
    g = new_game(2)
    rig(g, {"p0": ["3S"], "p1": ["4S"]}, "p0")
    g.scores = [12, 5]
    g.play("p0", ["3S"])
    assert g.phase == "game_over" and g.winner_side == 0 and g.scores == [13, 5]
    with pytest.raises(Rejected, match="over"):
        g.pass_turn("p1")


def test_a_tie_at_the_top_plays_another_round():
    g = new_game(3)
    rig(g, {"p0": ["3S"], "p1": ["4S"], "p2": ["5S", "6S"]}, "p0")
    g.scores = [12, 13, 0]
    g.play("p0", ["3S"])
    g.play("p1", ["4S"])
    assert g.scores == [14, 14, 0] and g.phase == "cutting"


def test_sides():
    assert new_game(4).side_players(0) == ["p0", "p2"]
    assert new_game(4).side_players(1) == ["p1", "p3"]
    assert new_game(3).side_count == 3
    assert new_game(2).side_of("p1") == 1


def test_game_needs_two_to_four_players_and_a_seated_creator():
    with pytest.raises(ValueError):
        Game(["a"], "a")
    with pytest.raises(ValueError):
        Game(["a", "b", "c", "d", "e"], "a")
    with pytest.raises(ValueError):
        Game(["a", "b"], "zz")
