import itertools
import random

import pytest

from app.murlan.cards import DECK
from app.murlan.combos import Play, beats, classify
from app.murlan.moves import legal_plays


def shapes(plays):
    return {classify(cards) for cards in plays}


def brute_force(hand, top, must_include):
    found = set()
    for size in range(1, len(hand) + 1):
        for cards in itertools.combinations(hand, size):
            play = classify(list(cards))
            if play is None or (must_include and must_include not in cards):
                continue
            if top is None or beats(play, top):
                found.add(play)
    return found


@pytest.mark.parametrize("seed", range(150))
def test_every_legal_play_is_listed_and_nothing_else(seed):
    rng = random.Random(seed)
    hand = rng.sample(DECK, rng.randint(1, 12))
    top = None
    if seed % 3:  # something on the pile: a play made from other cards
        rest = [c for c in DECK if c not in hand]
        top = classify(rng.choice([p for p in legal_plays(rng.sample(rest, 14), None)]))
    must = rng.choice(hand) if seed % 5 == 0 and top is None else None
    plays = legal_plays(hand, top, must)
    for cards in plays:
        assert all(c in hand for c in cards) and len(set(cards)) == len(cards)
        assert classify(cards) is not None
        assert must is None or must in cards
    assert shapes(plays) == brute_force(hand, top, must)
    assert len(plays) == len(shapes(plays))  # one set of cards per shape


def test_straights_may_end_on_a_and_2_but_never_wrap():
    hand = ["10S", "JS", "QS", "KS", "AS", "2S", "3S"]
    found = {tuple(c[:-1] for c in cards) for cards in legal_plays(hand, None) if len(cards) >= 5}
    assert ("10", "J", "Q", "K", "A") in found
    assert ("J", "Q", "K", "A", "2") in found
    assert ("10", "J", "Q", "K", "A", "2") in found
    assert not any("3" in run and "K" in run for run in found)


def test_low_straight_with_a_and_2():
    hand = ["AS", "2H", "3S", "4D", "5C"]
    assert any(len(cards) == 5 for cards in legal_plays(hand, None))


def test_the_card_that_must_go_down_is_the_one_picked():
    hand = ["3H", "3S", "4S"]
    plays = legal_plays(hand, None, must_include="3S")
    assert ["3S"] in plays
    assert all("3S" in cards for cards in plays)


def test_a_bomb_beats_a_straight_and_jokers_only_go_alone():
    hand = ["7S", "7H", "7D", "7C", "JR"]
    top = Play("straight", 3, 5)
    assert shapes(legal_plays(hand, top)) == {Play("bomb", 4, 1)}
    assert ["JR"] in legal_plays(hand, None)
