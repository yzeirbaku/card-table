import functools
import random

import pytest

from app.murlan import bot as bot_module
from app.murlan.bot import LEVELS, Bot
from app.murlan.combos import beats, classify
from app.murlan.views import view_for
from tests.murlan_helpers import new_game, rig
from tests.murlan_selfplay import Naive, play_game


@pytest.mark.parametrize("level", list(LEVELS))
@pytest.mark.parametrize("players", [2, 3, 4])
@pytest.mark.parametrize("seed", range(4))
def test_computer_players_play_whole_games_without_a_refused_move(level, players, seed):
    game, rounds = play_game(players, seed, target=5, kinds=[functools.partial(Bot, level=level)] * players)
    assert game.phase == "game_over"
    assert rounds and max(game.scores) >= 5


def share_of_rounds(a, b, games):
    """How many of the rounds `a` wins against `b`, 2 players, seats swapped every other game."""
    won = total = 0
    for seed in range(games):
        kinds, mine = ([a, b], "p0") if seed % 2 == 0 else ([b, a], "p1")
        _, rounds = play_game(2, 700 + seed, target=13, kinds=kinds)
        won += sum(r.winner == mine for r in rounds)
        total += len(rounds)
    return won / total


@pytest.mark.parametrize("better, worse", [("hard", "medium"), ("medium", "easy")])
def test_each_level_beats_the_one_below(better, worse):
    share = share_of_rounds(functools.partial(Bot, level=better), functools.partial(Bot, level=worse), 12)
    assert share > 0.53, share


def test_the_computer_clearly_beats_a_naive_player():
    won = total = 0
    for seed in range(6):
        game, rounds = play_game(2, 500 + seed, target=13, kinds=[Bot, Naive])
        won += sum(r.winner == "p0" for r in rounds)
        total += len(rounds)
    assert won / total > 0.6, f"{won}/{total}"


def act(game, player, level="hard"):
    bot = Bot(player, level=level)
    bot.observe(view_for(game, player))
    return bot.act(view_for(game, player))


@pytest.mark.parametrize("level", list(LEVELS))
def test_it_goes_out_when_it_can(level):
    for _ in range(20):  # however its dice fall
        g = new_game(3)
        rig(g, {"p0": ["3C", "8H"], "p1": ["9S", "9H"], "p2": ["6S", "7S"]}, "p0")
        g.play("p0", ["8H"])
        g.hands["p1"] = ["9S"]  # its last card: out
        assert act(g, "p1", level) == {"type": "play", "cards": ["9S"]}


def test_with_one_opponent_left_hard_plays_the_end_out_in_its_head():
    # p0 is out; p1 holds 5♠ 5♥ 2♣ and has seen every card but p2's K♦ Q♥. A single 5 loses
    # (K, then Q goes out on the other 5); the pair or the 2 first wins.
    g = new_game(3)
    rig(g, {"p0": ["3C"], "p1": ["5S", "5H", "2C"], "p2": ["KD", "QH"]}, "p1")
    g.must_include = None
    g.hands["p0"] = []
    g.places = ["p0"]
    view = view_for(g, "p1")
    for level, can_lose in (("hard", False), ("medium", True)):
        bot = Bot("p1", random.Random(0), level)
        bot.observe(view)
        bot.memory.seen = set(bot_module.DECK) - {"5S", "5H", "2C", "KD", "QH"}
        bot.memory.dealt = {"p0": 0, "p1": 3, "p2": 2}
        move = bot.act(view)
        if not can_lose:
            assert sorted(move["cards"]) in (["5H", "5S"], ["2C"]), move


def test_an_endgame_too_big_to_work_out_in_time_is_played_as_usual():
    # 14 cards with straights and three jokers: tens of thousands of positions. It stops at its
    # budget (rooms share one event loop) and plays its usual way instead.
    import time
    mine, theirs = ["3H", "6D", "7C", "8H", "9H", "JB", "JC", "JR", "KH"], ["10S", "2H", "4S", "8S", "KD"]
    g = new_game(3)
    rig(g, {"p0": ["3C"], "p1": mine, "p2": theirs}, "p1")
    g.must_include = None
    g.hands["p0"] = []
    g.places = ["p0"]
    view = view_for(g, "p1")
    bot = Bot("p1", random.Random(0), "hard")
    bot.observe(view)
    bot.memory.seen = set(bot_module.DECK) - set(mine) - set(theirs)
    bot.memory.dealt = {"p0": 0, "p1": len(mine), "p2": len(theirs)}
    start = time.perf_counter()
    assert bot._endgame(view, mine, True) is bot_module._OPEN
    assert time.perf_counter() - start < 1.0
    assert bot.act(view)["type"] == "play"


def test_medium_never_slips_into_beating_its_partner():
    g = new_game(4)
    rig(g, {"p0": ["3C", "8H"], "p1": ["4S", "5S"], "p2": ["9S", "KS", "AD"], "p3": ["6S", "7S"]}, "p0")
    g.play("p0", ["8H"])
    g.pass_turn("p1")
    for seed in range(60):
        bot = Bot("p2", random.Random(seed), "medium")
        view = view_for(g, "p2")
        bot.observe(view)
        assert bot.act(view) == {"type": "pass"}  # p0 is p2's partner


def test_a_slip_is_another_legal_play_or_a_pass():
    g = new_game(2)
    rig(g, {"p0": ["3C", "8H"], "p1": ["4S", "9S", "9H", "QD", "KC", "AS", "2H"]}, "p0")
    g.play("p0", ["8H"])
    always = bot_module.Level(mistakes=1.0, memory=1.0, watchful=True, loyal=1.0, careful_give=True, solves_endgames=False)
    best = act(g, "p1")
    for seed in range(30):
        bot = Bot("p1", random.Random(seed))
        bot.level = always
        view = view_for(g, "p1")
        bot.observe(view)
        move = bot.act(view)
        assert move != best
        if move["type"] == "play":
            assert set(move["cards"]) <= set(g.hands["p1"]) and beats(classify(move["cards"]), classify(["8H"]))


def test_easy_forgets_most_of_what_was_played_hard_nothing():
    g = new_game(2)
    rig(g, {"p0": ["3C", "4D", "5H", "6S", "7C", "8D", "9H", "10S"], "p1": ["2S", "2H"]}, "p0")
    g.must_include = None
    g.play("p0", ["3C", "4D", "5H", "6S", "7C", "8D", "9H", "10S"][:5])
    for level, most in (("easy", 3), ("hard", 5)):
        bot = Bot("p1", random.Random(1), level)
        bot.observe(view_for(g, "p1"))
        assert len(bot.memory.seen) <= most if level == "easy" else len(bot.memory.seen) == 5


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


# ---- emojis ----

BOMB_HANDS = {"p0": ["3C", "9S", "9H", "9D", "9C", "KH"], "p1": ["4S", "5S", "6H"], "p2": ["6S", "7S", "8H"]}


def test_it_sends_an_emoji_at_its_own_bomb_once_a_round_at_most(monkeypatch):
    monkeypatch.setattr(bot_module, "REACT_CHANCE", 1.0)
    g = new_game(3)
    rig(g, BOMB_HANDS, "p1")
    bot = Bot("p0")
    assert bot.reaction(view_for(g, "p0")) is None  # nothing new yet
    g.play("p1", ["5S"])
    assert bot.reaction(view_for(g, "p0")) is None  # not a bomb
    g.pass_turn("p2")
    g.play("p0", ["9S", "9H", "9D", "9C"])
    assert bot.reaction(view_for(g, "p0")) == "laughing"
    assert bot.reaction(view_for(g, "p0")) is None  # the same bomb again: nothing


def test_its_play_bombed_is_a_shock_and_the_other_seats_say_nothing(monkeypatch):
    monkeypatch.setattr(bot_module, "REACT_CHANCE", 1.0)
    g = new_game(3)
    rig(g, BOMB_HANDS, "p2")
    bots = {p: Bot(p) for p in ("p1", "p2")}
    for p, bot in bots.items():
        bot.reaction(view_for(g, p))
    g.play("p2", ["8H"])
    g.play("p0", ["9S", "9H", "9D", "9C"])
    assert bots["p2"].reaction(view_for(g, "p2")) == "shocked"
    assert bots["p1"].reaction(view_for(g, "p1")) is None


def test_mostly_it_keeps_quiet(monkeypatch):
    monkeypatch.setattr(bot_module, "REACT_CHANCE", 0.0)
    g = new_game(3)
    rig(g, BOMB_HANDS, "p0")
    bot = Bot("p0")
    bot.reaction(view_for(g, "p0"))
    g.play("p0", ["9S", "9H", "9D", "9C"])
    assert bot.reaction(view_for(g, "p0")) is None


def test_it_reacts_to_winning_the_round(monkeypatch):
    monkeypatch.setattr(bot_module, "REACT_CHANCE", 1.0)
    g = new_game(2)
    rig(g, {"p0": ["2S"], "p1": ["4S", "5S"]}, "p0")
    bot = Bot("p0")
    bot.reaction(view_for(g, "p0"))
    g.play("p0", ["2S"])  # out: the round is over
    assert bot.reaction(view_for(g, "p0")) == "laughing"
