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
        room.act(ben.id, {"type": "choose_target", "target": 10})
    room.act(ana.id, {"type": "choose_target", "target": 10})
    assert room.game.target == 10


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


def test_the_others_are_told_who_left_and_ended_the_game_until_the_next_starts():
    room, (ana, ben) = full_room(2)
    assert room.room_view()["ended_by"] is None
    room.leave(ben.id)
    assert room.room_view()["ended_by"] == "Ben"
    cleo = room.join("Cleo", None)
    room.sit(cleo.id, 1)
    assert room.room_view()["ended_by"] is None


def test_leaving_the_lobby_ends_nothing():
    room, (ana, ben, cleo) = room_with(3, "Ana", "Ben", "Cleo")
    room.sit(ben.id, 0)
    room.leave(ben.id)
    assert room.ended_by is None


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


def test_an_unseated_player_who_drops_in_the_lobby_stays():
    room, (ana, ben, cleo) = room_with(3, "Ana", "Ben", "Cleo")
    cleo.socket = None
    room.mark_disconnected(cleo.id)
    assert [p.id for p in room.players] == [ana.id, ben.id, cleo.id]


def test_a_seated_player_who_drops_in_the_lobby_stays():
    room, (ana, ben, cleo) = room_with(3, "Ana", "Ben", "Cleo")
    room.sit(ana.id, 0)
    ana.socket = None
    room.mark_disconnected(ana.id)
    assert ana in room.players and room.seat_of(ana.id) == 0
    assert room.players_view()[0]["connected"] is False


def test_a_creator_whose_socket_drops_in_the_lobby_keeps_the_role():
    room, (ana, ben) = room_with(3, "Ana", "Ben")
    ana.socket = None
    room.mark_disconnected(ana.id)
    assert room.creator_id == ana.id and ana in room.players
    assert room.join("Ana", ana.token) is ana


def test_a_full_lobby_evicts_the_longest_present_offline_unseated_player():
    room, (ana, ben, cleo) = room_with(3, "Ana", "Ben", "Cleo")
    ben.socket = cleo.socket = None
    dea = room.join("Dea", None)
    assert [p.id for p in room.players] == [ana.id, cleo.id, dea.id]  # Ben was here longest


def test_an_evicted_creator_hands_off_the_role():
    room, (ana, ben, cleo) = room_with(3, "Ana", "Ben", "Cleo")
    ana.socket = None
    dea = room.join("Dea", None)
    assert ana not in room.players and dea in room.players
    assert room.creator_id == ben.id


def test_a_full_lobby_with_nobody_evictable_still_rejects():
    room, (ana, ben, cleo) = room_with(3, "Ana", "Ben", "Cleo")
    with pytest.raises(JoinRejected) as e:  # everyone online
        room.join("Dea", None)
    assert e.value.code == 4409 and e.value.message == "This table is full"
    ana.socket = None
    room.sit(ana.id, 0)  # offline but seated
    with pytest.raises(JoinRejected) as e:
        room.join("Dea", None)
    assert e.value.code == 4409 and len(room.players) == 3


def test_back_to_the_lobby_then_a_newcomer_replaces_the_offline_player():
    room, (ana, ben) = full_room(2)
    room.game.phase = "game_over"
    ben.socket = None
    room.mark_disconnected(ben.id)
    room.after_game(ana.id, "lobby")
    assert ben in room.players
    cleo = room.join("Cleo", None)
    assert [p.id for p in room.players] == [ana.id, cleo.id]


def test_non_ascii_tokens_are_just_unknown_tokens():
    room, (ana,) = room_with(3, "Ana")
    ben = room.join("Ben", "tökén-é")
    assert ben is not ana and len(room.players) == 2


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
    assert room.room_view() == {"game": "murlan", "seats": 3, "status": "lobby", "ended_by": None, "level": "medium",
                                 "computer_seats_left": 1, "starting_in": None}
    assert room.players_view() == [
        {"id": ana.id, "name": "Ana", "connected": False, "seat": None, "is_creator": True, "computer": False},
        {"id": ben.id, "name": "Ben", "connected": True, "seat": 2, "is_creator": False, "computer": False},
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


def test_shuffle_teams_always_changes_the_partners():
    def pairs(seating):
        return {frozenset((seating[0], seating[2])), frozenset((seating[1], seating[3]))}

    for seed in range(30):
        room, players = full_room(4)
        room.rng = random.Random(seed)
        before = pairs(room.seating)
        room.game.phase = "game_over"
        room.after_game(players[0].id, "shuffle_teams")
        assert sorted(room.seating) == sorted(p.id for p in players)
        assert pairs(room.seating) != before


# ---- the countdown from the last seat taken to the game ----

def counting_room(seats: int, *names: str) -> tuple[Room, list, FakeClock]:
    clock = FakeClock()
    room = RoomManager(clock, start_seconds=3).create("murlan", seats)
    players = []
    for name in names:
        player = room.join(name, None)
        player.socket = object()
        players.append(player)
    return room, players, clock


def test_the_game_starts_three_seconds_after_the_last_seat_is_taken():
    room, (ana, ben), clock = counting_room(2, "Ana", "Ben")
    room.sit(ana.id, 0)
    assert room.room_view()["starting_in"] is None
    room.sit(ben.id, 1)
    assert room.game is None and room.status == "lobby"
    assert room.room_view()["starting_in"] == 3
    clock.now += 1.25
    assert room.room_view()["starting_in"] == 1.75
    assert not room.start_if_due()
    clock.now += 1.75
    assert room.start_if_due()
    assert room.status == "playing" and room.game.seats == [ana.id, ben.id]
    assert room.starts_at is None and room.room_view()["starting_in"] is None


def test_a_computer_taking_the_last_seat_starts_the_countdown_too():
    room, (ana,), clock = counting_room(2, "Ana")
    room.sit(ana.id, 0)
    room.add_computer(ana.id, 1)
    assert room.game is None and room.room_view()["starting_in"] == 3
    clock.now += 3
    assert room.start_if_due() and room.status == "playing"


def test_seats_are_locked_during_the_countdown():
    room, (ana, ben), _ = counting_room(2, "Ana", "Ben")
    room.sit(ana.id, 0)
    room.sit(ben.id, 1)
    with pytest.raises(Rejected, match="taken"):
        room.sit(ana.id, 1)
    assert room.starts_at is not None


def test_someone_seated_leaving_calls_the_countdown_off():
    room, (ana, ben), clock = counting_room(2, "Ana", "Ben")
    room.sit(ana.id, 0)
    room.sit(ben.id, 1)
    room.leave(ben.id)
    assert room.starts_at is None and room.room_view()["starting_in"] is None
    clock.now += 10
    assert not room.start_if_due() and room.game is None
    assert room.ended_by is None  # no game was ended


def test_removing_a_computer_calls_the_countdown_off():
    room, (ana,), clock = counting_room(3, "Ana")
    room.sit(ana.id, 0)
    room.add_computer(ana.id, 1)
    room.add_computer(ana.id, 2)
    assert room.starts_at is not None
    room.remove_computer(ana.id, 2)
    assert room.starts_at is None
    clock.now += 10
    assert not room.start_if_due()


def test_the_level_can_still_change_during_the_countdown():
    room, (ana,), _ = counting_room(2, "Ana")
    room.sit(ana.id, 0)
    room.add_computer(ana.id, 1)
    room.set_level(ana.id, "hard")
    assert room.level == "hard" and room.starts_at is not None


def test_play_again_starts_at_once():
    room, (ana, ben), clock = counting_room(2, "Ana", "Ben")
    room.sit(ana.id, 0)
    room.sit(ben.id, 1)
    clock.now += 3
    room.start_if_due()
    room.game.phase = "game_over"
    room.after_game(room.game.decider(), "play_again")
    assert room.status == "playing" and room.starts_at is None


def test_back_to_the_lobby_with_computers_does_not_count_down():
    room, (ana,), clock = counting_room(2, "Ana")
    room.sit(ana.id, 0)
    room.add_computer(ana.id, 1)
    clock.now += 3
    room.start_if_due()
    room.game.phase = "game_over"
    room.after_game(ana.id, "lobby")
    assert room.starts_at is None and room.room_view()["starting_in"] is None
    room.sit(ana.id, 0)
    assert room.room_view()["starting_in"] == 3
