import pytest

from app.rooms import CODE_ALPHABET, IDLE_EXPIRY_SECONDS, JoinRejected, RoomManager


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_codes_are_four_letters_and_unique():
    manager = RoomManager()
    codes = [manager.create().code for _ in range(50)]
    assert len(set(codes)) == 50
    assert all(len(c) == 4 and set(c) <= set(CODE_ALPHABET) for c in codes)


def test_get_is_case_insensitive():
    manager = RoomManager()
    room = manager.create()
    assert manager.get(room.code.lower()) is room


def test_first_player_is_host_and_gets_a_hand():
    room = RoomManager().create()
    ana = room.join("Ana", None)
    assert room.host_id == ana.id
    assert room.state.hands[ana.id] == []


def test_names_are_trimmed():
    room = RoomManager().create()
    assert room.join("  Ana  ", None).name == "Ana"


@pytest.mark.parametrize("name", ["", "   ", "x" * 21])
def test_name_validation(name):
    room = RoomManager().create()
    with pytest.raises(JoinRejected) as e:
        room.join(name, None)
    assert e.value.code == 4400


def test_reconnect_with_token_returns_the_same_seat():
    room = RoomManager().create()
    ana = room.join("Ana", None)
    again = room.join("whatever", ana.token)
    assert again is ana
    assert len(room.players) == 1


def test_unknown_token_takes_a_new_seat():
    room = RoomManager().create()
    room.join("Ana", None)
    ben = room.join("Ben", "not-a-real-token")
    assert len(room.players) == 2
    assert ben.name == "Ben"


def test_seventh_player_rejected():
    room = RoomManager().create()
    for i in range(6):
        room.join(f"P{i}", None)
    with pytest.raises(JoinRejected) as e:
        room.join("Seventh", None)
    assert e.value.code == 4409


def test_reconnect_still_works_when_full():
    room = RoomManager().create()
    first = room.join("P0", None)
    for i in range(1, 6):
        room.join(f"P{i}", None)
    assert room.join("P0", first.token) is first


def test_leave_returns_hand_and_passes_host_on():
    room = RoomManager().create()
    ana = room.join("Ana", None)
    ben = room.join("Ben", None)
    deck = next(iter(room.state.piles.values()))
    room.state.hands[ana.id].append(deck.cards.pop())
    room.leave(ana.id)
    assert [p.id for p in room.players] == [ben.id]
    assert room.host_id == ben.id
    assert ana.id not in room.state.hands
    assert sum(len(p.cards) for p in room.state.piles.values()) == 52


def test_last_player_leaving_clears_host():
    room = RoomManager().create()
    ana = room.join("Ana", None)
    room.leave(ana.id)
    assert room.host_id is None


def test_players_view():
    room = RoomManager().create()
    ana = room.join("Ana", None)
    ben = room.join("Ben", None)
    room.state.hands[ben.id].append(next(iter(room.state.piles.values())).cards.pop())
    ana.socket = object()
    assert room.players_view() == [
        {"id": ana.id, "name": "Ana", "connected": True, "is_host": True, "hand_count": 0},
        {"id": ben.id, "name": "Ben", "connected": False, "is_host": False, "hand_count": 1},
    ]


def test_idle_rooms_expire_after_two_hours():
    clock = FakeClock()
    manager = RoomManager(clock)
    room = manager.create()
    clock.now += IDLE_EXPIRY_SECONDS
    assert manager.purge_expired() == []
    clock.now += 1
    assert manager.purge_expired() == [room]
    assert manager.get(room.code) is None


def test_activity_keeps_a_room_alive():
    clock = FakeClock()
    manager = RoomManager(clock)
    room = manager.create()
    clock.now += IDLE_EXPIRY_SECONDS - 10
    manager.touch(room)
    clock.now += IDLE_EXPIRY_SECONDS - 10
    assert manager.purge_expired() == []
