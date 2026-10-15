import pytest

from app.murlan.cards import DECK, card_name, is_card, power, rank_of, sort_cards, suit_of
from app.murlan.combos import Play, beats, classify


def test_deck_has_54_distinct_cards():
    assert len(DECK) == 54
    assert len(set(DECK)) == 54
    assert "JB" in DECK and "JR" in DECK and "10H" in DECK


def test_ranking():
    order = ["3S", "4S", "5S", "6S", "7S", "8S", "9S", "10S", "JS", "QS", "KS", "AS", "2S", "JB", "JR"]
    assert [power(c) for c in order] == sorted(power(c) for c in order)
    assert len({power(c) for c in order}) == len(order)
    assert power("7H") == power("7C")  # suits never matter


def test_card_helpers():
    assert rank_of("10S") == "10" and suit_of("10S") == "S"
    assert rank_of("JS") == "J" and rank_of("JB") == "JB" and suit_of("JR") is None
    assert card_name("3S") == "3♠" and card_name("10H") == "10♥" and card_name("JR") == "red joker"
    assert is_card("QD") and not is_card("1S") and not is_card(["QD"]) and not is_card(None)
    assert sort_cards(["JR", "2C", "3H", "3S", "KD"]) == ["3S", "3H", "KD", "2C", "JR"]


@pytest.mark.parametrize(
    "cards, expected",
    [
        (["7H"], Play("single", power("7H"), 1)),
        (["JR"], Play("single", power("JR"), 1)),
        (["7H", "7S"], Play("pair", power("7H"), 1)),
        (["7H", "7S", "7D"], Play("triple", power("7H"), 1)),
        (["7H", "7S", "7D", "7C"], Play("bomb", power("7H"), 1)),
        (["3S", "4H", "5D", "6C", "7S"], Play("straight", 3, 5)),
        (["AS", "2H", "3D", "4C", "5S"], Play("straight", 1, 5)),  # ace low
        (["2H", "3D", "4C", "5S", "6S"], Play("straight", 2, 5)),  # 2 at the low end
        (["10S", "JH", "QD", "KC", "AS"], Play("straight", 10, 5)),  # ace high
        (["9S", "10H", "JD", "QC", "KS", "AH"], Play("straight", 9, 6)),
        (["3S", "3H", "4S", "4H", "5S", "5H", "6S", "6H", "7S", "7H"], Play("double_straight", 3, 5)),
        (
            ["3S", "3H", "3D", "4S", "4H", "4D", "5S", "5H", "5D", "6S", "6H", "6D", "7S", "7H", "7D"],
            Play("triple_straight", 3, 5),
        ),
    ],
)
def test_valid_plays(cards, expected):
    assert classify(cards) == expected


@pytest.mark.parametrize(
    "cards",
    [
        [],
        ["7H", "7H"],  # the same card twice
        ["7H", "8H"],  # two different ranks
        ["JB", "JR"],  # jokers never pair
        ["7H", "JB"],
        ["3S", "4H", "5D", "6C"],  # straights need 5 ranks
        ["KS", "AH", "2D", "3C", "4S"],  # no wrapping K-A-2
        ["QS", "KH", "AD", "2C", "3S"],
        ["3S", "4H", "5D", "6C", "8S"],  # gap
        ["3S", "4H", "5D", "6C", "JB"],  # jokers never in straights
        ["3S", "3H", "4S", "4H", "5S", "5H", "6S", "6H", "7S"],  # mixed multiples
        ["3S", "3H", "4S", "4H", "5S", "5H", "6S", "6H"],  # double straight of 4 ranks
    ],
)
def test_invalid_plays(cards):
    assert classify(cards) is None


def p(*cards):
    play = classify(list(cards))
    assert play is not None
    return play


def test_singles_pairs_triples_beat_any_higher_rank():
    assert beats(p("9H"), p("4S"))
    assert not beats(p("4S"), p("9H"))
    assert not beats(p("9S"), p("9H"))  # equal doesn't beat
    assert beats(p("JB"), p("2S")) and beats(p("JR"), p("JB"))
    assert beats(p("KH", "KS"), p("5H", "5S"))
    assert beats(p("AH", "AS", "AD"), p("3H", "3S", "3D"))
    assert not beats(p("KH", "KS"), p("5H"))  # different kinds
    assert not beats(p("9H"), p("5H", "5S"))


def test_straights_need_same_length_and_exactly_one_step_higher():
    low = p("3S", "4H", "5D", "6C", "7S")
    assert beats(p("4S", "5H", "6D", "7C", "8S"), low)
    assert not beats(p("5S", "6H", "7D", "8C", "9S"), low)  # two steps
    assert not beats(p("4S", "5H", "6D", "7C", "8S", "9S"), low)  # longer
    assert beats(p("2H", "3D", "4C", "5S", "6S"), p("AS", "2H", "3D", "4C", "5S"))
    double = p("3S", "3H", "4S", "4H", "5S", "5H", "6S", "6H", "7S", "7H")
    assert beats(p("4S", "4H", "5S", "5H", "6S", "6H", "7S", "7H", "8S", "8H"), double)
    assert not beats(p("4S", "5H", "6D", "7C", "8S"), double)


def test_bombs():
    bomb = p("5H", "5S", "5D", "5C")
    assert beats(bomb, p("JR"))
    assert beats(bomb, p("AH", "AS", "AD"))
    assert beats(bomb, p("3S", "4H", "5D", "6C", "7S"))
    assert beats(p("6H", "6S", "6D", "6C"), bomb)
    assert not beats(p("4H", "4S", "4D", "4C"), bomb)
    assert not beats(p("JR"), bomb)
