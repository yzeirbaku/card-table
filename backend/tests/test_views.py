import random

from app.engine.actions import ActionRejected, add_player, apply_action, new_table
from app.engine.state import TableState
from app.engine.views import view_for
from tests.helpers import card, put_pile

PLAYERS = ["ana", "ben", "cai"]


def seated_table() -> TableState:
    state = new_table(jokers=2)
    for p in PLAYERS:
        add_player(state, p)
    return state


def all_card_dicts(view: dict) -> list[dict]:
    return [c for p in view["piles"] for c in p["cards"]] + view["hand"]


def test_face_down_cards_hide_rank_and_suit():
    state = seated_table()
    view = view_for(state, "ana")
    (pile,) = view["piles"]
    assert len(pile["cards"]) == 54
    assert all(set(c) == {"id", "face_up"} and c["face_up"] is False for c in pile["cards"])


def test_face_up_cards_are_visible_to_everyone():
    state = seated_table()
    put_pile(state, [card("Q", "H", face_up=True)], 0.2, 0.2)
    for p in PLAYERS:
        shown = [c for c in all_card_dicts(view_for(state, p)) if c.get("rank") == "Q"]
        assert shown == [{"id": shown[0]["id"], "face_up": True, "rank": "Q", "suit": "H"}]


def test_own_hand_is_visible_and_other_hands_are_absent():
    state = seated_table()
    mine, theirs = card("A", "S"), card("K", "D")
    state.hands["ana"].append(mine)
    state.hands["ben"].append(theirs)
    view = view_for(state, "ana")
    assert view["hand"] == [{"id": mine.id, "face_up": True, "rank": "A", "suit": "S"}]
    assert theirs.id not in {c["id"] for c in all_card_dicts(view)}


def test_view_shape():
    state = seated_table()
    view = view_for(state, "ana")
    assert set(view) == {"version", "piles", "hand"}
    assert set(view["piles"][0]) == {"id", "x", "y", "layout", "cards"}


def random_action(state: TableState, rng: random.Random, actor: str) -> dict:
    piles = list(state.piles.values())
    tops = [p.cards[-1].id for p in piles]
    hand = [c.id for c in state.hands[actor]]
    pile_id = rng.choice(piles).id if piles else "none"

    def dest() -> dict:
        kind = rng.choice(["pile", "table", "hand", "player"])
        if kind == "pile":
            return {"kind": "pile", "pile_id": pile_id}
        if kind == "player":
            return {"kind": "player", "player_id": rng.choice(PLAYERS)}
        if kind == "hand":
            return {"kind": "hand", "index": rng.randint(0, 5)}
        return {"kind": "table", "x": rng.random(), "y": rng.random()}

    options = [
        lambda: {"type": "move_card", "card_id": rng.choice(tops + hand or ["x"]), "to": dest()},
        lambda: {"type": "move_card", "card_id": rng.choice(hand or ["x"]), "to": dest(),
                 "face_up": rng.choice([True, False])},
        lambda: {"type": "flip_card", "card_id": rng.choice(tops or ["x"])},
        lambda: {"type": "flip_pile", "pile_id": pile_id},
        lambda: {"type": "shuffle", "pile_id": pile_id},
        lambda: {"type": "deal", "pile_id": pile_id, "count": rng.randint(1, 4)},
        lambda: {"type": "take_pile", "pile_id": pile_id},
        lambda: {"type": "merge_pile", "pile_id": pile_id, "onto_pile_id": rng.choice(tops and [p.id for p in piles] or ["none"])},
        lambda: {"type": "set_layout", "pile_id": pile_id, "layout": rng.choice(["stack", "fan"])},
        lambda: {"type": "gather"},
    ]
    return rng.choice(options)()


def test_no_view_ever_leaks_hidden_cards():
    """Property test: whatever happens, a player's view only reveals face-up
    table cards and their own hand, and never mentions other hands' card ids."""
    for seed in range(20):
        rng = random.Random(seed)
        state = seated_table()
        for _ in range(150):
            actor = rng.choice(PLAYERS)
            try:
                apply_action(state, actor, random_action(state, rng, actor))
            except ActionRejected:
                pass
            total = sum(len(p.cards) for p in state.piles.values()) + sum(
                len(h) for h in state.hands.values()
            )
            assert total == 54, "cards were lost or duplicated"
            for viewer in PLAYERS:
                view = view_for(state, viewer)
                allowed = {c.id for p in state.piles.values() for c in p.cards if c.face_up}
                allowed |= {c.id for c in state.hands[viewer]}
                others = {c.id for p, h in state.hands.items() if p != viewer for c in h}
                for c in all_card_dicts(view):
                    assert c["id"] not in others
                    if "rank" in c or "suit" in c:
                        assert c["id"] in allowed
