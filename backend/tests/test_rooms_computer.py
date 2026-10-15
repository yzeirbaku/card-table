import pytest

from app.murlan.game import Rejected
from app.murlan.game import Reveal
from app.rooms import DEAL_SECONDS, JoinRejected, RoomManager
from tests.murlan_helpers import FakeClock


def computer_room(seats: int):
    clock = FakeClock()
    room = RoomManager(clock=clock).create("murlan", seats, computer=True)
    return room, clock


def join_you(room):
    you = room.join("Ana", None)
    you.socket = object()
    room.mark_connected(you.id)
    return you


def run_until(room, clock, done, limit=5000):
    """Let time pass and the computer players move, as the room's timer would."""
    for _ in range(limit):
        if done():
            return
        due = room.update_bots()
        clock.now = max(clock.now + 0.1, due or 0)
        room.game.tick()
        room.run_bot()
    raise AssertionError("the computer players never got there")


@pytest.mark.parametrize("seats", [2, 3, 4])
def test_the_computer_players_are_seated_and_the_game_starts_as_you_join(seats):
    room, _ = computer_room(seats)
    assert room.game is None and room.seating[0] is None
    assert [p["name"] for p in room.players_view()] == (
        ["Computer"] if seats == 2 else [f"Computer {i}" for i in range(1, seats)])
    assert all(p["computer"] and p["connected"] for p in room.players_view())
    you = join_you(room)
    assert room.game is not None and room.seating[0] == you.id
    assert room.creator_id == you.id  # you pick the race
    assert room.game.phase == "choosing_target" and not room.game.pause
    assert room.room_view()["computer"] is True
    assert room.update_bots() is None  # the race is yours to pick, not theirs


def test_nobody_else_can_join_but_you_can_come_back():
    room, _ = computer_room(3)
    you = join_you(room)
    with pytest.raises(JoinRejected):
        room.join("Ben", None)
    assert room.join("Ana", you.token) is you


def test_the_computer_moves_on_its_own_after_a_pause_for_the_deal():
    room, clock = computer_room(2)
    you = join_you(room)
    room.act(you.id, {"type": "choose_target", "target": 5})
    game = room.game
    bot = next(b for b in room.bots)
    if game.turn == you.id:  # you lead first: play your 3♠ (or whatever must go down)
        room.act(you.id, {"type": "play", "cards": [game.must_include]})
    start = clock.now
    due = room.update_bots()
    assert due is not None and due >= start + DEAL_SECONDS  # the cards are still flying out
    clock.now = due - 0.01
    assert room.run_bot() is False  # not yet
    clock.now = due
    assert room.run_bot() is True
    assert game.turn == you.id or game.places or bot in game.passed or game.trick


def test_if_you_drop_the_game_waits_with_no_countdown():
    room, clock = computer_room(3)
    you = join_you(room)
    room.mark_disconnected(you.id)
    assert room.game.pause and room.game.pause.deadline is None
    clock.now += 3600
    room.game.tick()
    assert room.game.phase == "choosing_target"  # nothing was cancelled
    room.mark_connected(you.id)
    assert room.game.pause is None


def test_a_whole_game_against_the_computer_where_you_always_pass_or_lead_low():
    room, clock = computer_room(4)
    you = join_you(room)
    room.act(you.id, {"type": "choose_target", "target": 5})
    game = room.game

    def your_moves():
        if game.phase == "playing" and game.turn == you.id and not game.pause:
            if game.top is None:
                card = game.must_include or game.hands[you.id][0]
                room.act(you.id, {"type": "play", "cards": [card]})
            else:
                room.act(you.id, {"type": "pass"})
        elif game.phase == "cutting" and game.last_result.loser == you.id:
            if game.cut_index is None:
                room.act(you.id, {"type": "cut", "index": 0})
            else:
                room.act(you.id, {"type": "take_cut", "take": False})
        elif game.swap_giver() == you.id:
            room.act(you.id, {"type": "give", "card": game.swap_choices(you.id)[0]})
        elif game.phase == "agreeing_loser" and you.id in game.loser_voters():
            room.act(you.id, {"type": "pick_loser", "player_id": you.id})
        return game.phase == "game_over"

    run_until(room, clock, your_moves, limit=200000)
    with pytest.raises(Rejected):
        room.after_game(you.id, "lobby")  # no lobby here: you leave instead
    room.after_game(you.id, "play_again")
    assert room.game is not game and room.game.phase == "choosing_target"


def test_leaving_ends_the_game_and_the_next_person_is_the_creator():
    room, _ = computer_room(2)
    you = join_you(room)
    room.leave(you.id)
    assert room.game is None and room.creator_id is None and room.bot_due is None
    ben = room.join("Ben", None)
    assert room.creator_id == ben.id and room.game is not None


def test_with_both_jokers_after_first_cards_the_computer_waits_for_both_reveals():
    room, clock = computer_room(2)
    you = join_you(room)
    game = room.game
    bot = next(iter(room.bots))
    game.target = 13
    game.reveal = Reveal("first_cards", {}, clock.now + 5)
    game.next_reveal = Reveal("jokers", {}, clock.now + 12)
    game._start_play(bot)
    game.hands = {you.id: ["3S", "4S"], bot: ["5S", "6S"]}
    due = room.update_bots()
    assert due >= clock.now + 12


def test_a_computer_move_that_blows_up_falls_back_to_a_legal_one(monkeypatch):
    room, clock = computer_room(2)
    you = join_you(room)
    game = room.game
    bot = next(iter(room.bots))
    game.target = 13
    game._start_play(bot)
    game.hands = {you.id: ["3S", "4S"], bot: ["5S", "6S"]}
    monkeypatch.setattr(room.bots[bot], "act", lambda view: 1 / 0)
    clock.now = room.update_bots()
    assert room.run_bot() is True
    assert game.turn == you.id and game.trick  # it led its lowest card instead
