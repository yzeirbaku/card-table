"""Computer players at a table: with friends or alone (specs 2026-10-16-mixed-tables-design.md,
2026-10-17-bot-levels-design.md)."""

import pytest

from app.murlan.bot import LEVELS
from app.murlan.game import Rejected, Reveal
from app.rooms import DEAL_SECONDS, RoomManager
from tests.murlan_helpers import FakeClock
from tests.test_rooms import room_with


def names(room):
    return [p["name"] for p in room.players_view() if p["computer"]]


def test_the_creator_seats_a_computer_at_a_table_of_3_with_two_people():
    room, (ana, ben) = room_with(3, "Ana", "Ben")
    room.sit(ana.id, 0)
    assert room.room_view()["computer_seats_left"] == 1  # Ben has a place in the room
    room.add_computer(ana.id, 2)
    assert names(room) == ["Bip"] and room.seating[2] in room.bots
    assert room.room_view()["computer_seats_left"] == 0
    with pytest.raises(Rejected):
        room.add_computer(ana.id, 1)  # Ben's place
    room.sit(ben.id, 1)  # the table is full: the game starts
    assert room.game is not None and room.game.computers == {room.seating[2]}
    assert room.game.creator == ana.id


def test_two_computers_at_a_table_of_4_and_adding_the_last_starts_the_game():
    room, (ana, ben) = room_with(4, "Ana", "Ben")
    room.sit(ana.id, 0)
    room.sit(ben.id, 1)
    room.add_computer(ana.id, 2)
    room.add_computer(ana.id, 3)
    assert names(room) == ["Bip", "Bop"]
    assert room.game is not None and room.status == "playing"


def test_only_the_creator_and_only_in_the_lobby():
    room, (ana, ben) = room_with(4, "Ana", "Ben")
    with pytest.raises(Rejected):
        room.add_computer(ben.id, 2)
    for seat in (-1, 4, True, "2", None):
        with pytest.raises(Rejected):
            room.add_computer(ana.id, seat)
    room.sit(ana.id, 0)
    with pytest.raises(Rejected):
        room.add_computer(ana.id, 0)  # taken
    room.sit(ben.id, 1)
    room.add_computer(ana.id, 2)
    room.add_computer(ana.id, 3)
    with pytest.raises(Rejected):
        room.remove_computer(ana.id, 2)  # the game is on


@pytest.mark.parametrize("seats", [2, 3, 4])
def test_alone_you_can_fill_every_other_seat_and_the_last_one_starts_the_game(seats):
    room, (ana,) = room_with(seats, "Ana")
    room.sit(ana.id, 0)
    assert room.room_view()["computer_seats_left"] == seats - 1
    for seat in range(1, seats):
        assert room.game is None
        room.add_computer(ana.id, seat)
    assert names(room) == ["Bip", "Bop", "Zip"][:seats - 1]
    assert room.game is not None and room.game.creator == ana.id
    assert room.room_view()["computer_seats_left"] == 0


def test_one_seat_is_always_left_for_a_person():
    room, (ana,) = room_with(3, "Ana")  # Ana isn't seated yet
    room.add_computer(ana.id, 1)
    room.add_computer(ana.id, 2)
    assert room.room_view()["computer_seats_left"] == 0
    with pytest.raises(Rejected):
        room.add_computer(ana.id, 0)


def test_a_computer_takes_a_place_in_the_room():
    room, (ana, ben, cleo) = room_with(4, "Ana", "Ben", "Cleo")  # three people, none seated
    room.add_computer(ana.id, 3)
    assert room.room_view()["computer_seats_left"] == 0  # the fourth place is the computer's
    room, (ana, ben, cleo, dea) = room_with(4, "Ana", "Ben", "Cleo", "Dea")
    with pytest.raises(Rejected):
        room.add_computer(ana.id, 3)


def test_removing_a_computer_frees_its_seat_and_its_name():
    room, (ana, _) = room_with(4, "Ana", "Ben")
    room.add_computer(ana.id, 2)
    room.add_computer(ana.id, 3)
    room.remove_computer(ana.id, 2)
    assert room.seating[2] is None and names(room) == ["Bop"] and len(room.bots) == 1
    room.add_computer(ana.id, 2)
    assert sorted(names(room)) == ["Bip", "Bop"]
    with pytest.raises(Rejected):
        room.remove_computer(ana.id, 0)  # nobody there


def mixed_game():
    room, (ana, ben) = room_with(4, "Ana", "Ben")
    room.sit(ana.id, 0)
    room.sit(ben.id, 2)
    room.add_computer(ana.id, 1)
    room.add_computer(ana.id, 3)
    return room, ana, ben


def test_when_someone_leaves_the_computers_stay_seated_and_never_become_creator():
    room, ana, ben = mixed_game()
    room.leave(ana.id)
    assert room.game is None
    assert room.creator_id == ben.id  # the next person, past the computer in seat 1
    assert all(room.seating[s] in room.bots for s in (1, 3))
    room.leave(ben.id)
    assert room.creator_id is None  # only computers left: the next person to join creates
    cleo = room.join("Cleo", None)
    assert room.creator_id == cleo.id


def test_back_to_the_lobby_keeps_the_computers_in_their_seats():
    room, ana, ben = mixed_game()
    room.game.phase = "game_over"
    room.after_game(ana.id, "lobby")
    assert room.seating[0] is None and room.seating[2] is None
    assert all(room.seating[s] in room.bots for s in (1, 3))


def test_a_drop_pauses_with_a_countdown_and_a_person_decides():
    room, ana, ben = mixed_game()
    room.mark_disconnected(ana.id)
    assert room.game.pause and room.game.pause.deadline is not None  # people are waiting
    assert room.game.decider() == ben.id  # not the computer next to Ana


def test_with_two_people_a_drop_still_has_its_countdown_at_a_table_of_3():
    room, (ana, ben) = room_with(3, "Ana", "Ben")
    room.sit(ana.id, 0)
    room.sit(ben.id, 1)
    room.add_computer(ana.id, 2)
    room.mark_disconnected(ben.id)
    assert room.game.pause.deadline is not None


# ---- the computer level ----

def test_the_level_starts_at_medium_and_the_creator_sets_it_for_every_computer():
    room, (ana, ben) = room_with(4, "Ana", "Ben")
    assert room.room_view()["level"] == "medium"
    room.add_computer(ana.id, 2)
    assert room.bots[room.seating[2]].level == LEVELS["medium"]
    room.set_level(ana.id, "easy")
    assert room.room_view()["level"] == "easy"
    assert room.bots[room.seating[2]].level == LEVELS["easy"]
    room.add_computer(ana.id, 3)  # a computer seated later plays at the table's level too
    assert room.bots[room.seating[3]].level == LEVELS["easy"]


def test_only_the_creator_sets_the_level_only_in_the_lobby_and_only_to_a_level():
    room, (ana, ben) = room_with(2, "Ana", "Ben")
    with pytest.raises(Rejected):
        room.set_level(ben.id, "hard")
    for level in ("insane", None, 3, ["hard"]):
        with pytest.raises(Rejected):
            room.set_level(ana.id, level)
    room.sit(ana.id, 0)
    room.sit(ben.id, 1)
    with pytest.raises(Rejected):
        room.set_level(ana.id, "hard")  # the game is on
    assert room.level == "medium"


def test_back_in_the_lobby_the_level_can_change():
    room, (ana,) = room_with(2, "Ana")
    room.sit(ana.id, 0)
    room.add_computer(ana.id, 1)
    room.game.phase = "game_over"
    room.after_game(ana.id, "lobby")
    room.set_level(ana.id, "hard")
    assert next(iter(room.bots.values())).level == LEVELS["hard"]


# ---- alone with computer players ----

def alone(seats: int):
    """You, seated at 0, and computer players in every other seat: the game is on."""
    clock = FakeClock()
    room = RoomManager(clock=clock).create("murlan", seats)
    you = room.join("Ana", None)
    you.socket = object()
    room.mark_connected(you.id)
    room.sit(you.id, 0)
    for seat in range(1, seats):
        room.add_computer(you.id, seat)
    return room, clock, you


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
def test_alone_the_race_is_yours_to_pick(seats):
    room, _, you = alone(seats)
    assert all(p["connected"] for p in room.players_view())
    assert room.game.phase == "choosing_target" and not room.game.pause
    assert room.update_bots() is None  # the race is yours to pick, not theirs


def test_the_computer_moves_on_its_own_after_a_pause_for_the_deal():
    room, clock, you = alone(2)
    room.act(you.id, {"type": "choose_target", "target": 5})
    game = room.game
    bot = next(b for b in room.bots)
    if game.turn == you.id:  # you lead first: play your 3S (or whatever must go down)
        room.act(you.id, {"type": "play", "cards": [game.must_include]})
    start = clock.now
    due = room.update_bots()
    assert due is not None and due >= start + DEAL_SECONDS  # the cards are still flying out
    clock.now = due - 0.01
    assert room.run_bot() is False  # not yet
    clock.now = due
    assert room.run_bot() is True
    assert game.turn == you.id or game.places or bot in game.passed or game.trick


def test_alone_if_you_drop_the_game_waits_with_no_countdown():
    room, clock, you = alone(3)
    room.mark_disconnected(you.id)
    assert room.game.pause and room.game.pause.deadline is None
    clock.now += 3600
    room.game.tick()
    assert room.game.phase == "choosing_target"  # nothing was cancelled
    room.mark_connected(you.id)
    assert room.game.pause is None


@pytest.mark.parametrize("level", ["easy", "medium", "hard"])
def test_a_whole_game_alone_where_you_always_pass_or_lead_low(level):
    clock = FakeClock()
    room = RoomManager(clock=clock).create("murlan", 4)
    you = room.join("Ana", None)
    you.socket = object()
    room.set_level(you.id, level)
    room.sit(you.id, 0)
    for seat in (1, 2, 3):
        room.add_computer(you.id, seat)
    room.act(you.id, {"type": "choose_target", "target": 5})
    game = room.game

    def your_moves():
        if game.phase == "playing" and game.turn == you.id and not game.pause and not game.reveal:  # play waits for a reveal
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
    room.after_game(you.id, "lobby")  # every table has a lobby
    assert room.seating[0] is None and all(s in room.bots for s in room.seating[1:])


def test_leaving_alone_ends_the_game_and_the_next_person_is_the_creator():
    room, _, you = alone(2)
    room.leave(you.id)
    assert room.game is None and room.creator_id is None and room.bot_due is None
    ben = room.join("Ben", None)
    assert room.creator_id == ben.id and room.game is None  # the lobby: Ben takes the seat


def test_with_both_jokers_after_first_cards_the_computer_waits_for_both_reveals():
    room, clock, you = alone(2)
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
    room, clock, you = alone(2)
    game = room.game
    bot = next(iter(room.bots))
    game.target = 13
    game._start_play(bot)
    game.hands = {you.id: ["3S", "4S"], bot: ["5S", "6S"]}
    monkeypatch.setattr(room.bots[bot], "act", lambda view: 1 / 0)
    clock.now = room.update_bots()
    assert room.run_bot() is True
    assert game.turn == you.id and game.trick  # it led its lowest card instead
