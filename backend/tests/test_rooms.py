import random

import pytest

from app.murlan.game import Rejected
from app.rooms import CODE_ALPHABET, IDLE_EXPIRY_SECONDS, JoinRejected, Room, RoomManager
from tests.murlan_helpers import FakeClock

NAMES = ["Ana", "Ben", "Cleo", "Dea"]


def room_with(seats: int, *names: str) -> tuple[Room, list]:
    """A room with these players joined and online (a stand-in socket each)."""
    room = RoomManager().create("murlan", seats)
    room.rng = random.Random(3)
    players = []
    for name in names:
        player = room.join(name, None)
        player.socket = object()
        players.append(player)
    return room, players


def full_room(seats: int) -> tuple[Room, list]:
    """Every seat taken in join order, so the game has started."""
    room, players = room_with(seats, *NAMES[:seats])
    for i, player in enumerate(players):
        room.sit(player.id, i)
    return room, players


def test_codes_are_four_letters_and_unique():
    manager = RoomManager()
    codes = [manager.create("murlan", 4).code for _ in range(50)]
    assert len(set(codes)) == 50
    assert all(len(c) == 4 and set(c) <= set(CODE_ALPHABET) for c in codes)


def test_get_is_case_insensitive():
    manager = RoomManager()
    room = manager.create("murlan", 4)
    assert manager.get(room.code.lower()) is room


def test_first_player_is_the_creator_and_everyone_joins_unseated():
    room, (ana, ben) = room_with(4, "Ana", "Ben")
    assert room.creator_id == ana.id
    assert room.seat_of(ana.id) is None and room.seat_of(ben.id) is None
    assert room.status == "lobby" and room.game is None


def test_names_are_trimmed():
    room = RoomManager().create("murlan", 4)
    assert room.join("  Ana  ", None).name == "Ana"


@pytest.mark.parametrize("name", ["", "   ", "x" * 21])
def test_name_validation(name):
    room = RoomManager().create("murlan", 4)
    with pytest.raises(JoinRejected) as e:
        room.join(name, None)
    assert e.value.code == 4400


def test_reconnect_with_token_returns_the_same_player():
    room, (ana,) = room_with(4, "Ana")
    assert room.join("whatever", ana.token) is ana
    assert len(room.players) == 1


def test_unknown_token_joins_as_someone_new():
    room, _ = room_with(4, "Ana")
    ben = room.join("Ben", "not-a-real-token")
    assert len(room.players) == 2 and ben.name == "Ben"


def test_no_more_players_than_seats():
    room, (ana, _) = room_with(2, "Ana", "Ben")
    with pytest.raises(JoinRejected) as e:
        room.join("Cleo", None)
    assert e.value.code == 4409 and e.value.message == "This table is full"
    assert room.join("Ana", ana.token) is ana  # reconnecting still works


def test_sitting_moving_and_taken_seats():
    room, (ana, ben) = room_with(3, "Ana", "Ben")
    room.sit(ana.id, 0)
    assert room.seat_of(ana.id) == 0
    room.sit(ana.id, 2)  # moving frees the old seat
    assert room.seating == [None, None, ana.id]
    room.sit(ana.id, 2)  # your own seat: nothing happens
    with pytest.raises(Rejected, match="taken"):
        room.sit(ben.id, 2)
    for bad in (-1, 3, "1", True, None, 1.0):
        with pytest.raises(Rejected, match="no such seat"):
            room.sit(ben.id, bad)


def test_filling_the_last_seat_starts_the_game():
    room, (ana, ben) = room_with(2, "Ana", "Ben")
    room.sit(ana.id, 1)
    assert room.status == "lobby"
    room.sit(ben.id, 0)
    assert room.status == "playing"
    assert room.game.seats == [ben.id, ana.id]
    assert room.game.creator == ana.id
    assert room.game.phase == "choosing_target" and room.game.pause is None
    with pytest.raises(Rejected, match="already started"):
        room.sit(ana.id, 0)


def test_a_player_offline_when_the_game_starts_pauses_it():
    room, (ana, ben) = room_with(2, "Ana", "Ben")
    ben.socket = None
    room.sit(ana.id, 0)
    room.sit(ben.id, 1)
    assert room.game.pause is not None and room.game.disconnected == [ben.id]


def test_drops_and_returns_reach_the_game():
    room, (_, ben) = full_room(2)
    room.mark_disconnected(ben.id)
    assert room.game.pause is not None
    room.mark_connected(ben.id)
    assert room.game.pause is None


def test_actions_go_to_the_game():
    room, (ana,) = room_with(2, "Ana")
    with pytest.raises(Rejected, match="hasn't started"):
        room.act(ana.id, {"type": "pass"})
    room, (ana, ben) = full_room(2)
    with pytest.raises(Rejected, match="creator"):
        room.act(ben.id, {"type": "choose_target", "target": 13})
    room.act(ana.id, {"type": "choose_target", "target": 13})
    assert room.game.target == 13


def test_leaving_mid_game_returns_everyone_to_the_lobby():
    room, (ana, ben) = full_room(2)
    room.leave(ben.id)
    assert room.status == "lobby" and room.game is None
    assert room.seating == [ana.id, None]
    assert [p.id for p in room.players] == [ana.id]
    cleo = room.join("Cleo", None)
    cleo.socket = object()
    room.sit(cleo.id, 1)
    assert room.status == "playing"


def test_the_creator_role_passes_clockwise():
    room, (ana, ben, cleo, _) = room_with(4, *NAMES)
    room.sit(ana.id, 2)
    room.sit(ben.id, 0)
    room.sit(cleo.id, 3)
    room.leave(ana.id)  # seat 2: next clockwise is seat 3
    assert room.creator_id == cleo.id
    room.leave(cleo.id)  # seat 3: wraps round to seat 0
    assert room.creator_id == ben.id


def test_an_unseated_creator_hands_over_to_whoever_has_been_here_longest():
    room, (ana, ben, cleo) = room_with(3, "Ana", "Ben", "Cleo")
    room.sit(cleo.id, 1)
    room.leave(ana.id)
    assert room.creator_id == ben.id


def test_last_player_leaving_clears_the_creator():
    room, (ana,) = room_with(3, "Ana")
    room.leave(ana.id)
    assert room.creator_id is None and room.players == []


def test_after_game_needs_a_finished_game_and_the_decider():
    room, (ana, ben) = full_room(2)
    with pytest.raises(Rejected, match="isn't over"):
        room.after_game(ana.id, "play_again")
    room.game.phase = "game_over"
    with pytest.raises(Rejected, match="creator chooses"):
        room.after_game(ben.id, "play_again")
    with pytest.raises(Rejected, match="Play again"):
        room.after_game(ana.id, "dance")
    with pytest.raises(Rejected, match="needs 4"):
        room.after_game(ana.id, "shuffle_teams")


def test_play_again_keeps_the_seats():
    room, (ana, ben) = full_room(2)
    old = room.game
    old.phase = "game_over"
    room.after_game(ana.id, "play_again")
    assert room.game is not old
    assert room.game.seats == [ana.id, ben.id] and room.game.phase == "choosing_target"


def test_shuffle_teams_reseats_four_players():
    room, players = full_room(4)
    room.game.phase = "game_over"
    room.after_game(players[0].id, "shuffle_teams")
    assert sorted(room.seating) == sorted(p.id for p in players)
    assert room.game.seats == room.seating and room.game.phase == "choosing_target"


def test_back_to_the_lobby_unseats_everyone():
    room, (ana, _) = full_room(2)
    room.game.phase = "game_over"
    room.after_game(ana.id, "lobby")
    assert room.status == "lobby" and room.seating == [None, None] and len(room.players) == 2


def test_the_next_player_decides_when_the_creator_is_away():
    room, (ana, ben) = full_room(2)
    room.game.phase = "game_over"
    room.mark_disconnected(ana.id)
    room.after_game(ben.id, "lobby")
    assert room.status == "lobby"


def test_room_and_player_views():
    room, (ana, ben) = room_with(3, "Ana", "Ben")
    room.sit(ben.id, 2)
    ana.socket = None
    assert room.room_view() == {"game": "murlan", "seats": 3, "status": "lobby"}
    assert room.players_view() == [
        {"id": ana.id, "name": "Ana", "connected": False, "seat": None, "is_creator": True},
        {"id": ben.id, "name": "Ben", "connected": True, "seat": 2, "is_creator": False},
    ]
    assert room.game_view(ana.id) is None
    started, (first, _) = full_room(2)
    assert started.game_view(first.id)["phase"] == "choosing_target"


def test_idle_rooms_expire_after_two_hours():
    clock = FakeClock()
    manager = RoomManager(clock)
    room = manager.create("murlan", 4)
    clock.now += IDLE_EXPIRY_SECONDS
    assert manager.purge_expired() == []
    clock.now += 1
    assert manager.purge_expired() == [room]
    assert manager.get(room.code) is None


def test_activity_keeps_a_room_alive():
    clock = FakeClock()
    manager = RoomManager(clock)
    room = manager.create("murlan", 4)
    clock.now += IDLE_EXPIRY_SECONDS - 10
    manager.touch(room)
    clock.now += IDLE_EXPIRY_SECONDS - 10
    assert manager.purge_expired() == []


def test_rooms_hand_their_clock_to_the_game():
    clock = FakeClock()
    room = RoomManager(clock).create("murlan", 2)
    a, b = room.join("Ana", None), room.join("Ben", None)
    a.socket = b.socket = object()
    room.sit(a.id, 0)
    room.sit(b.id, 1)
    assert room.game.clock is clock
