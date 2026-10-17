import contextlib

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.rooms import IDLE_EXPIRY_SECONDS, RoomManager
from tests.murlan_helpers import FakeClock


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def client(clock) -> TestClient:
    # No room timers here: these tests share no event loop between sockets.
    return TestClient(create_app(RoomManager(clock), use_timers=False))


def new_room(client: TestClient, players: int = 2) -> str:
    res = client.post("/rooms", json={"game": "murlan", "players": players})
    assert res.status_code == 200
    return res.json()["code"]


def connect(client: TestClient, code: str, name: str, token: str | None = None):
    query = f"name={name}" + (f"&token={token}" if token else "")
    return client.websocket_connect(f"/rooms/{code}/ws?{query}")


def join(ws) -> tuple[dict, dict]:
    welcome = ws.receive_json()
    assert welcome["type"] == "welcome"
    return welcome, state(ws)


def state(ws) -> dict:
    msg = ws.receive_json()
    assert msg["type"] == "state", msg
    return msg


def send(ws, **msg) -> None:
    ws.send_json(msg)


def act(ws, **action) -> None:
    ws.send_json({"type": "action", "action": action})


def seat_and_start(ana, ben) -> tuple[dict, dict]:
    """Ana sits at 0, Ben at 1, Ana picks 13. Returns both states after the deal."""
    send(ana, type="sit", seat=0)
    state(ana), state(ben)
    send(ben, type="sit", seat=1)
    state(ana), state(ben)
    act(ana, type="choose_target", target=10)
    return state(ana), state(ben)


@contextlib.contextmanager
def started_game(client: TestClient):
    """Ana (creator, seat 0) and Ben (seat 1) in a dealt 2-player game.
    Yields (ana_ws, ben_ws, ana_welcome, ben_welcome, ana_state, ben_state)."""
    code = new_room(client)
    with connect(client, code, "Ana") as ana:
        a, _ = join(ana)
        with connect(client, code, "Ben") as ben:
            b, _ = join(ben)
            state(ana)  # Ben arrived
            sa, sb = seat_and_start(ana, ben)
            yield ana, ben, a, b, sa, sb


def test_create_and_join(client):
    code = new_room(client)
    with connect(client, code, "Ana") as ws:
        welcome, s = join(ws)
        assert welcome["code"] == code
        assert s["players"] == [{"id": welcome["player_id"], "name": "Ana", "connected": True,
                                 "seat": None, "is_creator": True, "computer": False}]
        assert s["room"] == {"game": "murlan", "seats": 2, "status": "lobby", "ended_by": None, "level": "medium",
                             "computer_seats_left": 1, "starting_in": None}
        assert s["game"] is None


def test_seats_fill_then_the_creator_picks_the_target(client):
    code = new_room(client)
    with connect(client, code, "Ana") as ana:
        a, _ = join(ana)
        with connect(client, code, "Ben") as ben:
            b, _ = join(ben)
            state(ana)
            send(ana, type="sit", seat=1)
            assert state(ana)["players"][0]["seat"] == 1
            state(ben)
            send(ben, type="sit", seat=1)
            assert ben.receive_json() == {"type": "error", "message": "That seat is taken"}
            state(ben)
            send(ben, type="sit", seat=0)
            sa, _ = state(ana), state(ben)
            assert sa["room"]["status"] == "playing"
            assert sa["game"]["phase"] == "choosing_target"
            assert sa["game"]["seats"] == [b["player_id"], a["player_id"]]
            act(ben, type="choose_target", target=10)
            assert ben.receive_json() == {"type": "error",
                                          "message": "The room creator picks the target"}
            state(ben)
            act(ana, type="choose_target", target=10)
            sa, sb = state(ana), state(ben)
            assert sa["game"]["phase"] == "playing"
            assert len(sa["game"]["hand"]) == 18 and len(sb["game"]["hand"]) == 18
            assert set(sa["game"]["hand"]).isdisjoint(sb["game"]["hand"])


def test_out_of_turn_moves_are_rejected_and_legal_ones_broadcast(client):
    with started_game(client) as (ana, ben, a, b, sa, sb):
        if sa["game"]["turn"] == a["player_id"]:
            (lead, lead_state), (other, other_state) = (ana, sa), (ben, sb)
        else:
            (lead, lead_state), (other, other_state) = (ben, sb), (ana, sa)
        act(other, type="play", cards=[other_state["game"]["hand"][0]])
        assert other.receive_json() == {"type": "error", "message": "It's not your turn"}
        state(other)
        card = lead_state["game"]["must_include"]
        act(lead, type="play", cards=[card])
        s1, s2 = state(ana), state(ben)
        expected = [{"player_id": lead_state["game"]["turn"], "cards": [card], "kind": "single"}]
        assert s1["game"]["pile"] == s2["game"]["pile"] == expected
        lead_now = s1 if lead is ana else s2
        assert len(lead_now["game"]["hand"]) == 17
        assert "counts" not in s1["game"]


def test_malformed_actions_are_rejected(client):
    with started_game(client) as (ana, *_):
        act(ana, type="play", cards="3S")
        assert ana.receive_json() == {"type": "error", "message": "Malformed action"}
        assert state(ana)["game"]["phase"] == "playing"


def test_bad_messages_get_errors_and_the_connection_survives(client):
    code = new_room(client)
    with connect(client, code, "Ana") as ws:
        join(ws)
        ws.send_text("not json")
        assert ws.receive_json() == {"type": "error", "message": "Malformed message"}
        send(ws, type="dance")
        assert ws.receive_json() == {"type": "error", "message": "Unknown message type"}
        act(ws, type="pass")
        assert ws.receive_json() == {"type": "error", "message": "The game hasn't started yet"}
        state(ws)
        send(ws, type="sit", seat=7)
        assert ws.receive_json() == {"type": "error", "message": "There's no such seat"}
        state(ws)
        send(ws, type="sit", seat=0)
        assert state(ws)["players"][0]["seat"] == 0


def test_reconnect_mid_round_restores_the_hand(client):
    code = new_room(client)
    with connect(client, code, "Ana") as ana:
        join(ana)
        with connect(client, code, "Ben") as ben:
            b, _ = join(ben)
            state(ana)
            _, sb = seat_and_start(ana, ben)
            hand = sb["game"]["hand"]
        paused = state(ana)  # Ben dropped
        assert paused["game"]["pause"]["waiting_for"] == [b["player_id"]]
        assert [p["connected"] for p in paused["players"]] == [True, False]
        with connect(client, code, "Ben", b["token"]) as ben:
            again, s = join(ben)
            assert again["player_id"] == b["player_id"]
            assert s["game"]["hand"] == hand and s["game"]["pause"] is None
            assert state(ana)["game"]["pause"] is None


def test_leave_while_playing_returns_everyone_to_the_lobby(client):
    with started_game(client) as (ana, ben, a, *_):
        send(ben, type="leave")
        update = state(ana)
        assert update["room"]["status"] == "lobby" and update["game"] is None
        assert update["players"] == [{"id": a["player_id"], "name": "Ana", "connected": True,
                                      "seat": 0, "is_creator": True, "computer": False}]


def test_pause_times_out_without_any_message(monkeypatch):
    monkeypatch.setattr("app.murlan.game.PAUSE_SECONDS", 0.2)
    # `with TestClient(...)`: one event loop for every socket, so room timers can run.
    # If this test hangs, the room timer never woke the game.
    with TestClient(create_app(RoomManager())) as client:
        code = new_room(client)
        with connect(client, code, "Ana") as ana:
            join(ana)
            with connect(client, code, "Ben") as ben:
                join(ben)
                state(ana)
                seat_and_start(ana, ben)
            assert state(ana)["game"]["pause"]["timed_out"] is False  # Ben dropped
            later = state(ana)  # nobody sent anything: the timer woke the room
            assert later["game"]["phase"] == "round_cancelled"
            assert later["game"]["pause"]["timed_out"] is True


def test_the_game_starts_when_the_countdown_runs_out_without_any_message():
    # If this test hangs, the room timer never started the game.
    with TestClient(create_app(RoomManager(start_seconds=0.2))) as client:
        code = new_room(client)
        with connect(client, code, "Ana") as ana:
            join(ana)
            with connect(client, code, "Ben") as ben:
                join(ben)
                state(ana)
                send(ana, type="sit", seat=0)
                state(ana), state(ben)
                send(ben, type="sit", seat=1)
                counting = state(ana)["room"]
                assert counting["status"] == "lobby" and 0 < counting["starting_in"] <= 0.2
                state(ben)
                started = state(ana)  # nobody sent anything: the timer started the game
                assert started["room"]["status"] == "playing" and started["room"]["starting_in"] is None
                assert started["game"]["phase"] == "choosing_target"


def test_unknown_room_closes_4404(client):
    with pytest.raises(WebSocketDisconnect) as e:
        with connect(client, "ZZZZ", "Ana") as ws:
            ws.receive_json()
    assert e.value.code == 4404


def test_bad_name_closes_4400(client):
    code = new_room(client)
    with pytest.raises(WebSocketDisconnect) as e:
        with connect(client, code, "") as ws:
            ws.receive_json()
    assert e.value.code == 4400


def test_more_players_than_seats_closes_4409(client):
    code = new_room(client, 2)
    with connect(client, code, "Ana") as ana:
        join(ana)
        with connect(client, code, "Ben") as ben:
            join(ben)
            state(ana)
            with pytest.raises(WebSocketDisconnect) as e:
                with connect(client, code, "Cleo") as ws:
                    ws.receive_json()
            assert e.value.code == 4409 and e.value.reason == "This table is full"


def test_expired_room_is_gone(client, clock):
    code = new_room(client)
    clock.now += IDLE_EXPIRY_SECONDS + 1
    new_room(client)  # creating a room purges expired ones
    with pytest.raises(WebSocketDisconnect) as e:
        with connect(client, code, "Ana") as ws:
            ws.receive_json()
    assert e.value.code == 4404


def test_a_socket_that_dies_during_a_broadcast_pauses_the_game():
    manager = RoomManager()
    client = TestClient(create_app(manager, use_timers=False))
    with started_game(client) as (ana, ben, a, b, sa, sb):
        room = next(iter(manager.rooms.values()))

        class Dead:
            async def send_json(self, _):
                raise RuntimeError("gone")

        # The player on the move plays; the other one's socket dies mid-broadcast.
        if sa["game"]["turn"] == a["player_id"]:
            lead, lead_state, other_id = ana, sa, b["player_id"]
        else:
            lead, lead_state, other_id = ben, sb, a["player_id"]
        victim = next(p for p in room.players if p.id == other_id)
        victim.socket = Dead()
        act(lead, type="play", cards=[lead_state["game"]["must_include"]])
        state(lead)  # the first pass, before the dead socket was found
        assert state(lead)["game"]["pause"] is not None  # the re-run: already paused
        assert victim.socket is None
        assert room.game.disconnected == [other_id] and room.game.pause is not None


def test_a_dead_socket_is_closed_and_a_broadcast_reruns_until_clean():
    manager = RoomManager()
    client = TestClient(create_app(manager, use_timers=False))
    code = new_room(client, 3)
    with connect(client, code, "Ana") as ana:
        join(ana)
        room = manager.get(code)
        closed = []

        class Dead:
            async def send_json(self, _):
                raise RuntimeError("gone")

            async def close(self, *a):
                closed.append(1)

        extra = [room.join(n, None) for n in ("Ben", "Cleo")]
        for p in extra:
            p.socket = Dead()
        send(ana, type="sit", seat=0)
        state(ana)
        assert closed == [1, 1] and all(p.socket is None for p in extra)


def test_a_creator_who_drops_in_the_lobby_comes_back_as_creator(client):
    code = new_room(client, 2)
    with connect(client, code, "Ana") as ana:
        a, _ = join(ana)
    with connect(client, code, "Ana", a["token"]) as ana:
        again, s = join(ana)
        assert again["player_id"] == a["player_id"] and s["players"][0]["is_creator"] is True


def test_a_newcomer_evicts_an_offline_player_from_a_full_lobby(client):
    code = new_room(client, 2)
    with connect(client, code, "Ana") as ana:
        join(ana)
        with connect(client, code, "Ben") as ben:
            b, _ = join(ben)
            state(ana)
        state(ana)  # Ben dropped
        with connect(client, code, "Cleo") as cleo:
            _, s = join(cleo)
            assert [p["name"] for p in s["players"]] == ["Ana", "Cleo"]


@contextlib.contextmanager
def welcomes_fail():
    from starlette.websockets import WebSocket

    original = WebSocket.send_json

    async def flaky(self, data, *a, **k):
        if isinstance(data, dict) and data.get("type") == "welcome":
            raise RuntimeError("gone")
        return await original(self, data, *a, **k)

    WebSocket.send_json = flaky
    try:
        yield
    finally:
        WebSocket.send_json = original


def test_a_failed_welcome_for_someone_new_takes_them_back_out():
    # They never got their token, so their retry is someone new: left in, they'd be a creator nobody can reach.
    manager = RoomManager()
    client = TestClient(create_app(manager, use_timers=False))
    code = new_room(client, 2)
    room = manager.get(code)
    with welcomes_fail(), contextlib.suppress(Exception):
        with connect(client, code, "Ana") as ws:
            ws.receive_json()
    assert room.players == [] and room.creator_id is None
    with connect(client, code, "Ana") as ws:
        welcome, s = join(ws)
        assert [p["is_creator"] for p in s["players"]] == [True]


def test_a_failed_welcome_on_a_reconnect_keeps_them_and_clears_the_socket():
    manager = RoomManager()
    client = TestClient(create_app(manager, use_timers=False))
    code = new_room(client, 2)
    room = manager.get(code)
    with connect(client, code, "Ana") as ws:
        welcome, _ = join(ws)
    with welcomes_fail(), contextlib.suppress(Exception):
        with connect(client, code, "Ana", welcome["token"]) as ws:
            ws.receive_json()
    assert [p.id for p in room.players] == [welcome["player_id"]] and room.players[0].socket is None


def test_a_removed_player_s_socket_is_closed_on_its_next_message():
    manager = RoomManager()
    client = TestClient(create_app(manager, use_timers=False))
    code = new_room(client, 2)
    with connect(client, code, "Ana") as ana:
        join(ana)
        room = manager.get(code)
        room.players.clear()
        send(ana, type="sit", seat=0)
        with pytest.raises(WebSocketDisconnect):
            ana.receive_json()


def test_a_message_on_a_replaced_socket_is_not_applied():
    manager = RoomManager()
    client = TestClient(create_app(manager, use_timers=False))
    code = new_room(client, 2)
    with connect(client, code, "Ana") as ws:
        welcome, _ = join(ws)
        room = manager.get(code)
        player = next(p for p in room.players if p.id == welcome["player_id"])
        newer = object()  # the player now has another live socket; `ws` is stale
        player.socket = newer
        send(ws, type="sit", seat=0)
        with pytest.raises(WebSocketDisconnect):  # the stale socket is closed
            ws.receive_json()
        assert room.seat_of(player.id) is None  # and the message was not applied
        assert player.socket is newer


def test_a_reaction_goes_to_everyone_at_the_table(client):
    with started_game(client) as (ana, ben, a, _b, _sa, _sb):
        send(ana, type="react", reaction="laughing")
        expected = {"type": "reaction", "player_id": a["player_id"], "reaction": "laughing"}
        assert ana.receive_json() == expected
        assert ben.receive_json() == expected


def test_unknown_reactions_and_reactions_outside_a_game_are_refused(client):
    with started_game(client) as (ana, ben, _a, _b, _sa, _sb):
        send(ana, type="react", reaction="dancing")
        assert ana.receive_json()["type"] == "error"
        send(ana, type="react", reaction=["shocked"])
        assert ana.receive_json()["type"] == "error"
    code = new_room(client)
    with connect(client, code, "Ana") as ana:
        join(ana)
        send(ana, type="react", reaction="shocked")  # in the lobby: nobody's at a table
        assert ana.receive_json()["type"] == "error"


def test_reactions_faster_than_one_a_second_are_dropped(client, clock):
    with started_game(client) as (ana, ben, a, _b, _sa, _sb):
        send(ana, type="react", reaction="shocked")
        assert ana.receive_json()["reaction"] == "shocked"
        send(ana, type="react", reaction="angry")  # too soon: nothing happens
        send(ana, type="nonsense")  # its error proves the server got past the dropped one
        assert ana.receive_json()["type"] == "error"
        clock.now += 1
        send(ana, type="react", reaction="asleep")
        assert ana.receive_json()["reaction"] == "asleep"
        assert [ben.receive_json()["reaction"] for _ in range(2)] == ["shocked", "asleep"]


def test_alone_with_a_computer_it_moves_by_itself(monkeypatch):
    monkeypatch.setattr("app.rooms.DEAL_SECONDS", 0.05)
    monkeypatch.setattr("app.rooms.Room._think_time", lambda self, game: 0.05)
    # `with TestClient(...)`: one event loop for every socket, so the room's timer can run.
    with TestClient(create_app(RoomManager())) as client:
        code = new_room(client)
        with connect(client, code, "Ana") as ana:
            welcome, s = join(ana)
            me = welcome["player_id"]
            send(ana, type="set_level", level="hard")
            assert state(ana)["room"]["level"] == "hard"
            send(ana, type="sit", seat=0)
            state(ana)
            send(ana, type="add_computer", seat=1)
            s = state(ana)
            assert s["room"]["status"] == "playing"
            assert [p["name"] for p in s["players"] if p["computer"]] == ["Bip"]
            act(ana, type="choose_target", target=5)
            s = state(ana)
            game = s["game"]
            if game["turn"] == me:  # you lead: the card that must go down
                act(ana, type="play", cards=[game["must_include"]])
                s = state(ana)
            for _ in range(5):  # nobody else sends anything: the computer's move arrives on its own
                if s["game"]["turn"] == me:
                    break
                s = state(ana)
            assert s["game"]["turn"] == me and s["game"]["pile"]
