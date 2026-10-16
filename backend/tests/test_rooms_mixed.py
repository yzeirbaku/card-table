"""Mixed tables: friends and computer players at one table (spec 2026-10-16-mixed-tables-design.md)."""

import pytest

from app.murlan.game import Rejected
from app.rooms import RoomManager
from tests.test_rooms import room_with


def names(room):
    return [p["name"] for p in room.players_view() if p["computer"]]


def test_the_creator_seats_one_computer_at_a_table_of_3():
    room, (ana, ben) = room_with(3, "Ana", "Ben")
    room.sit(ana.id, 0)
    assert room.room_view()["computer_seats_left"] == 1
    room.add_computer(ana.id, 2)
    assert names(room) == ["Computer 1"] and room.seating[2] in room.bots
    assert room.room_view()["computer_seats_left"] == 0
    with pytest.raises(Rejected):
        room.add_computer(ana.id, 1)  # two people at least
    room.sit(ben.id, 1)  # the table is full: the game starts
    assert room.game is not None and room.game.computers == {room.seating[2]}
    assert room.game.creator == ana.id


def test_two_computers_at_a_table_of_4_and_adding_the_last_starts_the_game():
    room, (ana, ben) = room_with(4, "Ana", "Ben")
    room.sit(ana.id, 0)
    room.sit(ben.id, 1)
    room.add_computer(ana.id, 2)
    room.add_computer(ana.id, 3)
    assert names(room) == ["Computer 1", "Computer 2"]
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


def test_no_computers_at_a_table_of_2_or_a_computer_table():
    room, (ana,) = room_with(2, "Ana")
    assert room.room_view()["computer_seats_left"] == 0
    with pytest.raises(Rejected):
        room.add_computer(ana.id, 1)
    solo = RoomManager().create("murlan", 3, computer=True)
    you = solo.join("Ana", None)
    assert solo.room_view()["computer_seats_left"] == 0
    with pytest.raises(Rejected):
        solo.remove_computer(you.id, 1)


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
    assert room.seating[2] is None and names(room) == ["Computer 2"] and len(room.bots) == 1
    room.add_computer(ana.id, 2)
    assert sorted(names(room)) == ["Computer 1", "Computer 2"]
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
