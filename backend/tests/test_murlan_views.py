import json
import random

import pytest

from app.murlan.cards import DECK
from app.murlan.combos import beats, classify
from app.murlan.game import PAUSE_SECONDS, REVEAL_SECONDS, Game, Rejected
from app.murlan.views import view_for
from tests.murlan_helpers import FakeClock, later_round, new_game

CARDS = frozenset(DECK)


def card_codes(value) -> set[str]:
    """Every card code anywhere in a view."""
    if isinstance(value, str):
        return {value} if value in CARDS else set()
    if isinstance(value, dict):
        return set().union(set(), *(card_codes(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(set(), *(card_codes(v) for v in value))
    return set()


def test_a_player_sees_their_own_hand_and_nothing_of_the_others():
    g = new_game(3)
    g.choose_target("p0", 13)
    v = view_for(g, "p1")
    assert v["hand"] == g.hands["p1"]
    assert "counts" not in v  # how many cards the others hold is hidden too
    assert not (set(g.hands["p0"]) | set(g.hands["p2"])) & card_codes(v)
    assert v["phase"] == "playing" and v["target"] == 13 and v["round"] == 1
    assert v["seats"] == ["p0", "p1", "p2"] and v["creator"] == "p0" and v["decider"] == "p0"
    assert v["sides"] == [{"players": ["p0"], "score": 0}, {"players": ["p1"], "score": 0},
                          {"players": ["p2"], "score": 0}]
    json.dumps(v)


def test_only_the_leader_is_told_which_card_to_include():
    g = new_game(4)
    g.choose_target("p0", 13)
    assert view_for(g, g.turn)["must_include"] == "3S"
    assert all(view_for(g, p)["must_include"] is None for p in g.seats if p != g.turn)


def test_teams_in_four_player_views():
    g = new_game(4)
    assert view_for(g, "p0")["sides"] == [{"players": ["p0", "p2"], "score": 0},
                                          {"players": ["p1", "p3"], "score": 0}]


def test_the_cut_card_is_shown_to_the_cutter_only_and_survives_a_reconnect():
    g = later_round()
    g.cut("p3", 5)
    card = g.deck[5]
    assert view_for(g, "p3")["cut"] == {"cutter": "p3", "deck_size": 54, "index": 5, "card": card}
    assert view_for(g, "p0")["cut"]["card"] is None
    assert card not in card_codes(view_for(g, "p0"))
    g.disconnect("p3")
    g.reconnect("p3")
    assert view_for(g, "p3")["cut"]["card"] == card


def test_swap_choices_go_to_the_giver_only():
    g = later_round()
    g.deck = []
    g.hands = {"p0": ["5S", "7D"], "p1": ["4D"], "p2": ["6D"], "p3": ["2S", "2H", "5C"]}
    g._after_deal()
    assert view_for(g, "p3")["swap"] == {"giver": "p3", "receiver": "p0", "choices": ["2S", "2H"]}
    assert view_for(g, "p0")["swap"] == {"giver": "p3", "receiver": "p0", "choices": []}


def test_first_cards_are_public_while_the_reveal_lasts():
    clock = FakeClock()
    g = later_round(clock=clock)
    g.cut("p3", 7)
    g.take_cut("p3", True)
    first = dict(g.reveal.cards)
    assert all(view_for(g, p)["reveal"] == {"kind": "first_cards", "cards": first} for p in g.seats)
    clock.now += REVEAL_SECONDS  # even before anyone calls tick(), the view stops showing it
    assert all(view_for(g, p)["reveal"] is None for p in g.seats)


def test_pause_view_counts_down():
    clock = FakeClock()
    g = new_game(2, clock=clock)
    g.choose_target("p0", 13)
    g.disconnect("p1")
    clock.now += 30
    assert view_for(g, "p0")["pause"] == {"waiting_for": ["p1"], "seconds_left": 90,
                                          "timed_out": False, "keep_waiting": False}
    clock.now += PAUSE_SECONDS
    g.tick()
    assert view_for(g, "p0")["pause"]["seconds_left"] is None
    assert view_for(g, "p0")["phase"] == "round_cancelled"


def test_two_player_out_of_play_cards_never_show():
    g = new_game(2)
    g.choose_target("p0", 13)
    dealt = set(g.hands["p0"]) | set(g.hands["p1"])
    for p in g.seats:
        assert card_codes(view_for(g, p)) <= dealt


# ---- randomized whole games: no view ever shows a card it shouldn't ----

def bot_play(game: Game, player: str, rng: random.Random) -> list[str] | None:
    """A legal play for `player` (singles, same-rank sets, bombs), or None to pass."""
    hand = game.hands[player]
    top = game.top
    if top is None:
        return [game.must_include] if game.must_include else [rng.choice(hand)]
    by_rank: dict[str, list[str]] = {}
    for c in hand:
        if c not in ("JB", "JR"):
            by_rank.setdefault(c[:-1], []).append(c)
    size = {"single": 1, "pair": 2, "triple": 3, "bomb": 4}.get(top.kind)
    if size == 1:
        options = [[c] for c in hand]
    elif size:
        options = [cards[:size] for cards in by_rank.values() if len(cards) >= size]
    else:
        options = []
    options += [cards for cards in by_rank.values() if len(cards) == 4]
    options = [o for o in options if beats(classify(o), top)]
    return rng.choice(options) if options and rng.random() < 0.8 else None


def random_step(game: Game, rng: random.Random, clock: FakeClock) -> None:
    """One random legal move, or now and then a drop, a return or time passing."""
    if game.pause:
        decider = game.decider()
        if game.pause.timed_out and not game.pause.keep_waiting and decider and rng.random() < 0.5:
            game.decide(decider, "end_game" if rng.random() < 0.1 else "keep_waiting")
        elif rng.random() < 0.6:
            game.reconnect(rng.choice(game.disconnected))
        else:
            clock.now += 70
            game.tick()
        return
    roll = rng.random()
    if roll < 0.01:
        game.disconnect(rng.choice(game.seats))
        return
    if roll < 0.05:
        clock.now += 3
        game.tick()
        return
    if game.phase == "choosing_target":
        game.choose_target(game.creator, 13)
    elif game.phase == "cutting":
        loser = game.last_result.loser
        if game.cut_index is None:
            game.cut(loser, rng.randrange(len(game.deck)))
        else:
            game.take_cut(loser, rng.random() < 0.5)
    elif game.phase == "swapping":
        giver = game.swap_giver()
        game.give(giver, rng.choice(game.swap_choices(giver)))
    elif game.phase == "agreeing_loser":
        voters = game.loser_voters()
        game.pick_loser(rng.choice(voters), rng.choice(voters))
    elif game.phase == "playing":
        player = game.turn
        cards = bot_play(game, player, rng)
        if cards is None:
            game.pass_turn(player)
        else:
            game.play(player, cards)


def check_views(game: Game) -> None:
    pile = {c for _, cards, _ in game.trick for c in cards}
    showing = game.reveal is not None and game.clock() < game.reveal.until
    public = set(game.reveal.cards.values()) if showing else set()
    for p in game.seats:
        view = view_for(game, p)
        allowed = set(game.hands[p]) | pile | public
        if game.phase == "cutting" and p == game.last_result.loser and game.cut_index is not None:
            allowed.add(game.deck[game.cut_index])
        leaked = card_codes(view) - allowed
        assert not leaked, f"{p} sees {leaked} during {game.phase}"
        json.dumps(view)


@pytest.mark.parametrize("n", [2, 3, 4])
@pytest.mark.parametrize("seed", range(6))
def test_no_view_ever_leaks_hidden_cards(n, seed):
    rng = random.Random(seed)
    clock = FakeClock()
    game = Game([f"p{i}" for i in range(n)], "p0", rng=random.Random(seed + 100), clock=clock)
    for _ in range(4000):
        check_views(game)
        if game.phase == "game_over":
            break
        try:
            random_step(game, rng, clock)
        except Rejected as e:  # the bot only makes legal moves
            pytest.fail(f"bot move rejected: {e}")
    check_views(game)
    assert game.rounds_played >= 1 or game.phase == "game_over"
