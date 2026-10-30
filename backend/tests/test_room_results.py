"""Finished games go out as records for the stats (spec 2026-10-30-accounts-and-stats-design.md)."""

import random

import pytest

from app.murlan.game import PAUSE_SECONDS
from app.rooms import RoomManager
from app.results import GameRecord
from tests.murlan_helpers import FakeClock, rig

TARGET = {2: 5, 3: 10, 4: 13}
NEAR = {2: [4, 0], 3: [9, 0, 0], 4: [11, 0]}  # the first seat one round from the target


def table(seats: int, computers: tuple[int, ...] = (), record=None):
    """Every seat taken (people online, computers where asked): the game is on."""
    records: list[GameRecord] = []
    clock = FakeClock()
    room = RoomManager(clock=clock, record=record or records.append).create("murlan", seats)
    room.rng = random.Random(3)
    people_seats = [s for s in range(seats) if s not in computers]
    people = []
    for seat in people_seats:
        player = room.join(f"P{seat}", None)
        player.socket = object()
        people.append(player)
    for player, seat in zip(people, people_seats):
        room.sit(player.id, seat)
    for seat in computers:
        room.add_computer(people[0].id, seat)
    assert room.game is not None
    return room, records, clock


def finish_round(room, scores: list[int]) -> None:
    """With these scores, play a round where the seats go out in order and the last seat is last."""
    game = room.game
    game.scores = list(scores)
    seats = game.seats
    hands = {p: [f"{rank}S"] for p, rank in zip(seats[:-1], "3456")}
    hands[seats[-1]] = ["7H", "8H"]
    rig(game, hands, seats[0], target=TARGET[len(seats)])
    game.must_include = None
    for p in seats[:-1]:
        if room.game.phase == "game_over":
            break
        room.act(p, {"type": "play", "cards": hands[p]})


def by_seat(record: GameRecord) -> dict[int, bool]:
    return {s.seat: s.won for s in record.seats}


def test_reaching_the_target_records_the_game_once():
    room, records, _ = table(2)
    finish_round(room, NEAR[2])
    assert room.game.phase == "game_over"
    assert len(records) == 1
    record = records[0]
    assert (record.game, record.players, record.target, record.how) == ("murlan", 2, 5, "target")
    assert by_seat(record) == {0: True, 1: False}
    assert [s.score for s in record.seats] == [5, 0]
    with pytest.raises(Exception):
        room.act(room.game.seats[1], {"type": "pass"})
    assert len(records) == 1


def test_three_players_one_winner():
    room, records, _ = table(3)
    finish_round(room, NEAR[3])
    assert by_seat(records[0]) == {0: True, 1: False, 2: False}


def test_a_four_player_win_counts_for_both_partners():
    room, records, _ = table(4)
    finish_round(room, NEAR[4])
    record = records[0]
    assert by_seat(record) == {0: True, 1: False, 2: True, 3: False}
    assert [s.side for s in record.seats] == [0, 1, 0, 1]
    assert record.seats[0].score == record.seats[2].score == 15  # the team's score: 11 + 3 + 1


def test_user_ids_and_computers_are_carried():
    room, records, _ = table(3, computers=(2,))
    room.players[0].user_id = 7
    finish_round(room, NEAR[3])
    seats = records[0].seats
    assert [(s.user_id, s.computer) for s in seats] == [(7, False), (None, False), (None, True)]


def test_a_computer_move_that_wins_is_recorded():
    room, records, clock = table(2, computers=(1,))
    game = room.game
    you, bot = game.seats
    game.scores = [0, 4]
    rig(game, {you: ["7H", "8H"], bot: ["3S"]}, bot, target=5)
    game.must_include = None
    for _ in range(200):
        if game.phase == "game_over":
            break
        due = room.update_bots()
        clock.now = max(clock.now + 0.1, due or 0)
        room.run_bot()
    assert by_seat(records[0]) == {0: False, 1: True}


def test_leaving_hands_the_win_to_the_top_of_the_others():
    room, records, _ = table(3)
    room.game.target, room.game.scores = 10, [5, 3, 1]
    room.leave(room.game.seats[0])
    record = records[0]
    assert record.how == "leave"
    assert by_seat(record) == {0: False, 1: True, 2: False}


def test_the_leaver_loses_even_when_ahead():
    room, records, _ = table(2)
    room.game.target, room.game.scores = 5, [4, 1]
    room.leave(room.game.seats[0])
    assert by_seat(records[0]) == {0: False, 1: True}


def test_a_four_player_leave_loses_for_the_leavers_team():
    room, records, _ = table(4)
    room.game.target, room.game.scores = 13, [9, 2]
    room.leave(room.game.seats[2])
    assert by_seat(records[0]) == {0: False, 1: True, 2: False, 3: True}


def drop_second(room):
    room.mark_disconnected(room.game.seats[1])


def end_the_game(room):
    room.game.phase = "game_over"


@pytest.mark.parametrize("scores, setup", [
    ([0, 0, 0], None),  # nobody has scored
    ([5, 3, 3], None),  # the top of the others is tied
    ([5, 3, 1], drop_second),  # someone else is disconnected
    ([5, 3, 1], end_the_game),
])
def test_leave_records_nothing(scores, setup):
    room, records, _ = table(3)
    room.game.target, room.game.scores = 10, scores
    if setup:
        setup(room)
    room.leave(room.game.seats[0])
    assert room.game is None
    assert records == []


def test_leave_while_still_choosing_the_target_records_nothing():
    room, records, _ = table(2)
    assert room.game.phase == "choosing_target"
    room.leave(room.game.seats[1])
    assert records == []


def test_end_game_after_a_pause_records_nothing():
    room, records, clock = table(3)
    room.game.target, room.game.scores = 10, [5, 3, 1]
    first, second, _ = room.game.seats
    room.mark_disconnected(second)
    clock.now += PAUSE_SECONDS + 1
    room.game.tick()
    room.act(first, {"type": "decide", "choice": "end_game"})
    assert room.game.phase == "game_over"
    assert records == []


def test_play_again_records_each_game_and_the_lobby_none():
    room, records, _ = table(2)
    creator = room.creator_id
    finish_round(room, NEAR[2])
    room.after_game(creator, "play_again")
    finish_round(room, NEAR[2])
    room.after_game(creator, "lobby")
    assert len(records) == 2


def test_a_failing_recorder_does_not_break_the_room():
    def broken(record):
        raise RuntimeError("disk full")

    room, _, _ = table(2, record=broken)
    finish_round(room, NEAR[2])
    assert room.game.phase == "game_over"
