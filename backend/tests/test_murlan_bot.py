import pytest

from app.murlan.bot import Bot
from app.murlan.views import view_for
from tests.murlan_helpers import new_game, rig
from tests.murlan_selfplay import Naive, play_game


@pytest.mark.parametrize("players", [2, 3, 4])
@pytest.mark.parametrize("seed", range(4))
def test_computer_players_play_whole_games_without_a_refused_move(players, seed):
    game, rounds = play_game(players, seed, target=5)
    assert game.phase == "game_over"
    assert rounds and max(game.scores) >= 5


def test_the_computer_clearly_beats_a_naive_player():
    won = total = 0
    for seed in range(6):
        game, rounds = play_game(2, 500 + seed, target=13, kinds=[Bot, Naive])
        won += sum(r.winner == "p0" for r in rounds)
        total += len(rounds)
    assert won / total > 0.6, f"{won}/{total}"


def act(game, player):
    bot = Bot(player)
    bot.observe(view_for(game, player))
    return bot.act(view_for(game, player))


def test_it_goes_out_when_it_can():
    g = new_game(3)
    rig(g, {"p0": ["3C", "8H"], "p1": ["9S", "9H"], "p2": ["6S", "7S"]}, "p0")
    g.play("p0", ["8H"])
    g.hands["p1"] = ["9S"]  # its last card: out
    assert act(g, "p1") == {"type": "play", "cards": ["9S"]}


def test_it_leaves_its_partners_trick_alone():
    g = new_game(4)
    rig(g, {"p0": ["3C", "8H"], "p1": ["4S", "5S"], "p2": ["9S", "KS"], "p3": ["6S", "7S"]}, "p0")
    g.play("p0", ["8H"])
    g.pass_turn("p1")
    assert act(g, "p2") == {"type": "pass"}  # p0 is p2's partner


def test_it_never_gives_up_or_picks_the_race():
    g = new_game(2)
    assert act(g, "p0") is None  # choosing the target is the creator's, a person
    assert act(g, "p1") is None


def test_it_goes_along_with_its_partners_pick_for_last():
    g = new_game(4)
    g.phase = "agreeing_loser"
    g.places = ["p0", "p2"]
    g.agree_picks = {"p1": "p1"}
    assert act(g, "p3") == {"type": "pick_loser", "player_id": "p1"}
    g.agree_picks = {}
    assert act(g, "p3") == {"type": "pick_loser", "player_id": "p3"}  # nobody picked yet: offers itself
    g.agree_picks = {"p3": "p3", "p1": "p3"}
    assert act(g, "p3") is None  # agreed


def test_leading_it_keeps_its_jokers_for_later():
    g = new_game(2)
    rig(g, {"p0": ["3C", "4H", "9D", "JR", "JB"], "p1": ["5S", "6S", "7S"]}, "p0")
    g.must_include = None
    move = act(g, "p0")
    assert move["type"] == "play" and not set(move["cards"]) & {"JR", "JB"}
