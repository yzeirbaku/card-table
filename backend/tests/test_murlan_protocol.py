import pytest

from app.murlan.game import Rejected
from app.murlan.protocol import apply_action
from tests.murlan_helpers import new_game


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "pass",
        {},
        {"type": "dance"},
        {"type": "choose_target", "target": 15},
        {"type": "play", "cards": []},
        {"type": "play", "cards": "3S"},
        {"type": "cut", "index": 54},
        {"type": "cut", "index": -1},
        {"type": "pass", "extra": 1},
        {"type": "decide", "choice": "shrug"},
    ],
)
def test_malformed_actions_are_rejected(raw):
    with pytest.raises(Rejected, match="Malformed"):
        apply_action(new_game(2), "p0", raw)


def test_actions_reach_the_game():
    g = new_game(2)
    apply_action(g, "p0", {"type": "choose_target", "target": 13})
    assert g.target == 13
    leader = g.turn
    apply_action(g, leader, {"type": "play", "cards": [g.must_include]})
    assert g.trick and g.trick[0][0] == leader
    other = next(p for p in g.seats if p != leader)
    apply_action(g, other, {"type": "pass"})
    assert g.turn == leader and g.top is None  # 2 players: a pass gives the lead back


def test_game_rejections_come_through():
    g = new_game(2)
    with pytest.raises(Rejected, match="creator"):
        apply_action(g, "p1", {"type": "choose_target", "target": 21})
