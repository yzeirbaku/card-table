import pytest

from app.murlan.cards import DECK
from app.murlan.game import PAUSE_SECONDS, REVEAL_SECONDS, Game, Rejected, Reveal
from app.murlan.views import view_for
from tests.murlan_helpers import (
    FakeClock, Reverse, Rotate, later_round, new_game, rig, swap_ready,
)


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
    assert g.turn == "p0" and g.top is None and g.passed == ["p1", "p2"]  # the passes stay on show too
    assert g.trick_won and [cards for _, cards, _ in g.trick] == [["4S"]]  # still on show
    g.play("p0", ["3S"])  # leads anything, even lower than before
    assert g.passed == [] and not g.trick_won and [cards for _, cards, _ in g.trick] == [["3S"]]


def test_lead_moves_on_when_the_last_player_is_out():
    g = new_game(3)
    rig(g, {"p0": ["4S"], "p1": ["5H", "6H"], "p2": ["8H", "7H"]}, "p0")
    g.play("p0", ["4S"])
    assert g.places == ["p0"] and g.turn == "p1"
    g.pass_turn("p1")
    g.pass_turn("p2")
    assert g.turn == "p1" and g.top is None


def test_nobody_passes_without_choosing_to():
    g = new_game(3)
    rig(g, {"p0": ["9S", "3D"], "p1": ["5H", "6H"], "p2": ["4H", "KH"]}, "p0")
    g.play("p0", ["9S"])
    assert g.turn == "p1" and g.passed == []  # nothing above a 9, but it's still p1's call
    g.pass_turn("p1")
    g.play("p2", ["KH"])
    g.pass_turn("p0")
    g.pass_turn("p1")
    assert g.turn == "p2" and g.top is None  # p2 leads again
    assert g.trick_won and g.trick[-1][1] == ["KH"]  # and everyone still sees the king


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
    rig(g, {"p0": ["JR", "3C", "3D", "3H", "3S", "9D", "5C", "5D", "5H", "5S"],
            "p1": ["4S", "4H", "4D", "4C", "6S"]}, "p0")
    g.play("p0", ["JR"])
    g.play("p1", ["4S", "4H", "4D", "4C"])
    assert g.top.kind == "bomb"
    with pytest.raises(Rejected, match="higher bomb"):
        g.play("p0", ["9D"])
    with pytest.raises(Rejected, match="higher bomb"):
        g.play("p0", ["3C", "3D", "3H", "3S"])
    g.play("p0", ["5C", "5D", "5H", "5S"])


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


def test_only_the_loser_cuts():
    g = later_round()
    assert g.phase == "cutting" and len(g.deck) == 54 and g.turn is None
    with pytest.raises(Rejected, match="loser"):
        g.cut("p0", 3)
    with pytest.raises(Rejected, match="Pick a card first"):
        g.take_cut("p3", True)
    with pytest.raises(Rejected, match="in the deck"):
        g.cut("p3", 54)
    g.cut("p3", 10)
    with pytest.raises(Rejected, match="already"):
        g.cut("p3", 11)
    with pytest.raises(Rejected, match="loser"):
        g.take_cut("p0", True)


def test_take_it_deals_the_cut_card_to_the_loser_and_shows_everyones_first_card():
    clock = FakeClock()
    g = later_round(clock=clock)
    g.cut("p3", 10)
    card = g.deck[10]
    g.take_cut("p3", True)
    assert g.reveal.kind == "first_cards"
    assert g.reveal.cards["p3"] == [card]
    assert set(g.reveal.cards) == set(g.seats)
    assert len({c for codes in g.reveal.cards.values() for c in codes}) == 4
    assert g.reveal.until == clock.now + REVEAL_SECONDS
    assert card in g.hands["p3"] or g.swap_given.get("p3") == card
    # dealt from the loser: p3 and p0 got the two extra cards (the swap only moves cards between them)
    assert [len(g.hands[p]) for p in ("p1", "p2")] == [13, 13]
    assert len(g.hands["p3"]) + len(g.hands["p0"]) == 28
    assert g.deck == [] and g.cut_index is None


def test_leave_it_is_a_normal_hidden_deal():
    g = later_round()
    g.cut("p3", 10)
    g.take_cut("p3", False)
    assert g.reveal is None
    assert sum(len(h) for h in g.hands.values()) == 54
    assert g.phase in ("swapping", "playing") and g.deck == []


def test_loser_picks_among_tied_highest_then_winner_gives_back_3_to_10():
    g = swap_ready({"p0": ["5S", "7D", "KC", "AH"], "p1": ["4D"], "p2": ["6D"],
                    "p3": ["2S", "2H", "5C"]})
    assert g.phase == "swapping" and g.swap_giver() == "p3"
    assert g.swap_choices("p3") == ["2S", "2H"]
    assert g.swap_choices("p0") == []
    with pytest.raises(Rejected, match="not your turn"):
        g.give("p0", "5S")
    with pytest.raises(Rejected, match="highest"):
        g.give("p3", "5C")
    g.give("p3", "2H")
    assert "2H" in g.hands["p0"] and g.swap_giver() == "p0"
    assert g.swap_choices("p0") == ["5S", "7D"]
    with pytest.raises(Rejected, match="3 to 10"):
        g.give("p0", "KC")
    g.give("p0", "7D")
    assert "7D" in g.hands["p3"]
    assert g.phase == "playing" and g.turn == "p3"  # the loser leads
    assert g.reveal is None  # winner and loser aren't partners: the swap stays hidden


def test_a_single_choice_is_still_given_by_hand():
    g = swap_ready({"p0": ["9C", "KC"], "p1": ["4D"], "p2": ["6D"], "p3": ["JR", "4S"]})
    assert g.phase == "swapping" and g.swap_giver() == "p3" and g.swap_choices("p3") == ["JR"]
    g.give("p3", "JR")
    assert g.swap_giver() == "p0" and g.swap_choices("p0") == ["9C"]
    g.give("p0", "9C")
    assert g.phase == "playing" and g.turn == "p3"
    assert "JR" in g.hands["p0"] and "9C" in g.hands["p3"]


def test_a_winner_with_nothing_from_3_to_10_gives_their_lowest():
    g = swap_ready({"p0": ["QC", "JC", "KD"], "p1": ["4D"], "p2": ["6D"], "p3": ["AS", "4H"]})
    g.give("p3", "AS")
    assert g.swap_choices("p0") == ["JC"]
    g.give("p0", "JC")
    assert g.hands["p3"] == ["4H", "JC"]
    assert g.hands["p0"] == ["QC", "KD", "AS"]


def test_the_swap_is_public_between_partners():
    g = swap_ready({"p0": ["9C", "KC"], "p1": ["4D"], "p2": ["JR", "4S"], "p3": ["6D"]},
                   places=["p0", "p1", "p3", "p2"])  # winner p0, loser p2: seats 0 and 2
    g.give("p2", "JR")
    g.give("p0", "9C")
    assert g.reveal.kind == "swap"
    assert g.reveal.cards == {"p2": ["JR"], "p0": ["9C"]}


def test_no_swap_when_the_loser_was_dealt_both_jokers_and_the_winner_leads():
    g = swap_ready({"p0": ["9C"], "p1": ["4D"], "p2": ["6D"], "p3": ["JB", "JR", "4S"]})
    assert g.phase == "playing" and g.turn == "p0"
    assert g.hands["p3"] == ["JB", "JR", "4S"] and g.hands["p0"] == ["9C"]


def test_everyone_is_shown_the_loser_holds_both_jokers():
    g = swap_ready({"p0": ["9C"], "p1": ["4D"], "p2": ["6D"], "p3": ["JB", "JR", "4S"]})
    assert g.reveal.kind == "jokers" and g.reveal.cards == {"p3": ["JB", "JR"]}
    assert all(view_for(g, p)["reveal"] == {"kind": "jokers", "cards": {"p3": ["JB", "JR"]}} for p in g.seats)


def test_two_players_swap_the_same_way():
    g = swap_ready({"p0": ["4C", "9H"], "p1": ["KS", "3D"]}, n=2)
    assert g.swap_giver() == "p1"
    g.give("p1", "KS")
    assert g.swap_giver() == "p0" and g.hands["p0"] == ["4C", "9H", "KS"]
    g.give("p0", "9H")
    assert g.hands["p1"] == ["3D", "9H"] and g.turn == "p1"


def test_a_drop_pauses_and_a_return_resumes_exactly():
    clock = FakeClock()
    g = new_game(3, clock=clock)
    g.choose_target("p0", 13)
    turn, hands = g.turn, {p: list(h) for p, h in g.hands.items()}
    g.disconnect("p1")
    assert g.pause.deadline == clock.now + PAUSE_SECONDS
    assert g.deadline() == clock.now + PAUSE_SECONDS
    with pytest.raises(Rejected, match="paused"):
        g.play(turn, [g.must_include])
    clock.now += PAUSE_SECONDS - 1
    g.tick()
    assert not g.pause.timed_out
    g.reconnect("p1")
    assert g.pause is None and g.phase == "playing"
    assert g.turn == turn and g.hands == hands


def test_timeout_cancels_the_round_then_keep_waiting_deals_a_fresh_one():
    clock = FakeClock()
    g = new_game(2, clock=clock)
    rig(g, {"p0": ["3S", "9H"], "p1": ["4S", "5S"]}, "p0")
    g.scores = [5, 3]
    g.disconnect("p1")
    clock.now += PAUSE_SECONDS
    g.tick()
    assert g.phase == "round_cancelled"
    assert g.pause.timed_out and g.pause.deadline is None and g.deadline() is None
    assert all(h == [] for h in g.hands.values()) and g.scores == [5, 3]
    assert g.decider() == "p0"
    with pytest.raises(Rejected, match="decides"):
        g.decide("p1", "keep_waiting")
    with pytest.raises(Rejected, match="paused"):
        g.play("p0", ["3S"])
    g.decide("p0", "keep_waiting")
    assert g.pause.keep_waiting
    with pytest.raises(Rejected, match="nothing to decide"):
        g.decide("p0", "keep_waiting")
    g.reconnect("p1")
    assert g.pause is None and g.phase == "playing"  # no completed round yet: a first-round deal
    assert len(g.hands["p0"]) == 18 and g.rounds_played == 0


def test_end_game_is_still_possible_while_keeping_waiting():
    clock = FakeClock()
    g = new_game(2, clock=clock)
    rig(g, {"p0": ["3S"], "p1": ["4S"]}, "p0")
    g.scores = [5, 3]
    g.disconnect("p1")
    clock.now += PAUSE_SECONDS
    g.tick()
    g.decide("p0", "keep_waiting")
    with pytest.raises(Rejected, match="decides"):
        g.decide("p1", "end_game")
    g.decide("p0", "end_game")
    assert g.phase == "game_over" and g.pause is None and g.winner_side == 0


def test_end_game_after_a_timeout_uses_the_current_scores():
    clock = FakeClock()
    g = new_game(4, clock=clock)
    rig(g, {"p0": ["3S"], "p1": ["4S"], "p2": ["5S"], "p3": ["6S"]}, "p0")
    g.scores = [7, 4]
    g.disconnect("p0")  # the creator is the one who's gone
    clock.now += PAUSE_SECONDS
    g.tick()
    assert g.decider() == "p1"
    with pytest.raises(Rejected, match="Keep waiting or end"):
        g.decide("p1", "shrug")
    g.decide("p1", "end_game")
    assert g.phase == "game_over" and g.winner_side == 0 and g.pause is None


def test_ending_on_a_tie_is_a_draw():
    clock = FakeClock()
    g = new_game(2, clock=clock)
    rig(g, {"p0": ["3S"], "p1": ["4S"]}, "p0")
    g.scores = [6, 6]
    g.disconnect("p1")
    clock.now += PAUSE_SECONDS
    g.tick()
    g.decide("p0", "end_game")
    assert g.phase == "game_over" and g.winner_side is None


def test_creator_drops_during_the_target_pick_and_comes_back():
    clock = FakeClock()
    g = new_game(3, clock=clock)
    g.disconnect("p0")
    clock.now += PAUSE_SECONDS
    g.tick()
    assert g.phase == "round_cancelled" and g.decider() == "p1"
    g.reconnect("p0")
    assert g.phase == "choosing_target" and g.pause is None
    g.choose_target("p0", 13)
    assert g.phase == "playing"


def test_a_cancelled_later_round_restarts_with_the_cut():
    clock = FakeClock()
    g = later_round(clock=clock)
    g.disconnect("p2")
    clock.now += PAUSE_SECONDS
    g.tick()
    g.reconnect("p2")
    assert g.phase == "cutting" and len(g.deck) == 54


def test_reveals_expire_on_tick():
    clock = FakeClock()
    g = later_round(clock=clock)
    g.cut("p3", 0)
    g.take_cut("p3", True)
    assert g.deadline() == clock.now + REVEAL_SECONDS
    queued = g.next_reveal is not None  # this deal gave the loser both jokers: that reveal follows
    clock.now += REVEAL_SECONDS * (2 if queued else 1)
    g.tick()
    assert g.reveal is None and g.deadline() is None


def test_a_second_drop_restarts_the_countdown():
    clock = FakeClock()
    g = new_game(3, clock=clock)
    g.choose_target("p0", 13)
    g.disconnect("p1")
    clock.now += 30
    g.disconnect("p2")
    assert g.pause.deadline == clock.now + PAUSE_SECONDS
    g.reconnect("p1")
    assert g.pause is not None  # p2 is still away
    g.reconnect("p2")
    assert g.pause is None


def test_a_returning_player_does_not_shorten_the_next_droppers_time():
    clock = FakeClock()
    g = new_game(3, clock=clock)
    g.choose_target("p0", 13)
    g.disconnect("p1")
    clock.now += 100
    g.disconnect("p2")
    g.reconnect("p1")
    assert g.pause.deadline == clock.now + PAUSE_SECONDS
    clock.now += PAUSE_SECONDS - 1
    g.tick()
    assert g.phase == "playing"


def test_a_swap_reveal_waits_for_the_first_cards_reveal():
    clock = FakeClock()
    g = later_round(places=["p0", "p1", "p3", "p2"], clock=clock)  # p0 and p2 are partners
    g.deck = []
    for p, hand in {"p0": ["9C", "KC"], "p1": ["4D"], "p2": ["JR", "4S"], "p3": ["6D"]}.items():
        g.hands[p] = hand
    g.reveal = Reveal("first_cards", {p: ["3S"] for p in g.seats}, clock.now + REVEAL_SECONDS)
    g._after_deal()
    g.give("p2", "JR")
    g.give("p0", "9C")
    assert g.phase == "playing"
    assert g.reveal.kind == "first_cards" and g.next_reveal.kind == "swap"
    assert all(view_for(g, p)["reveal"]["kind"] == "first_cards" for p in g.seats)
    assert g.deadline() == clock.now + REVEAL_SECONDS
    clock.now += REVEAL_SECONDS
    g.tick()
    assert g.reveal.kind == "swap" and g.next_reveal is None
    assert g.reveal.cards == {"p2": ["JR"], "p0": ["9C"]}
    assert g.deadline() == clock.now + REVEAL_SECONDS
    clock.now += REVEAL_SECONDS
    g.tick()
    assert g.reveal is None and g.deadline() is None


def test_no_pause_once_the_game_is_over():
    g = new_game(2)
    g.phase = "game_over"
    g.disconnect("p1")
    assert g.pause is None and g.disconnected == ["p1"]
    assert g.decider() == "p0"
