import contextlib

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.rooms import IDLE_EXPIRY_SECONDS, RoomManager


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def client(clock) -> TestClient:
    return TestClient(create_app(RoomManager(clock)))


def new_room(client: TestClient) -> str:
    res = client.post("/rooms")
    assert res.status_code == 200
    return res.json()["code"]


def join(ws) -> tuple[dict, dict]:
    welcome = ws.receive_json()
    state = ws.receive_json()
    assert welcome["type"] == "welcome"
    assert state["type"] == "state"
    return welcome, state


def deck_id(state: dict) -> str:
    return max(state["view"]["piles"], key=lambda p: len(p["cards"]))["id"]


def act(ws, action: dict) -> None:
    ws.send_json({"type": "action", "action": action})


def test_create_and_join(client):
    code = new_room(client)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ws:
        welcome, state = join(ws)
        assert welcome["code"] == code
        assert state["players"] == [
            {"id": welcome["player_id"], "name": "Ana", "connected": True, "is_host": True,
             "hand_count": 0}
        ]
        assert len(state["view"]["piles"]) == 1
        assert state["view"]["hand"] == []


def test_actions_are_broadcast_with_private_hands(client):
    code = new_room(client)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ana:
        _, state = join(ana)
        with client.websocket_connect(f"/rooms/{code}/ws?name=Ben") as ben:
            join(ben)
            assert len(ana.receive_json()["players"]) == 2  # Ben arrived
            act(ana, {"type": "deal", "pile_id": deck_id(state), "count": 2})
            a, b = ana.receive_json(), ben.receive_json()
            assert len(a["view"]["hand"]) == 2
            assert len(b["view"]["hand"]) == 2
            assert {c["id"] for c in a["view"]["hand"]}.isdisjoint(
                {c["id"] for c in b["view"]["hand"]}
            )
            assert [p["hand_count"] for p in a["players"]] == [2, 2]


def test_rejected_action_gets_error_and_fresh_state(client):
    code = new_room(client)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ws:
        _, state = join(ws)
        act(ws, {"type": "flip_card", "card_id": "nope"})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "top card" in error["message"]
        fresh = ws.receive_json()
        assert fresh["type"] == "state"
        assert fresh["view"]["version"] == state["view"]["version"]


def test_malformed_messages_get_errors_and_connection_survives(client):
    code = new_room(client)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ws:
        _, state = join(ws)
        ws.send_text("not json")
        assert ws.receive_json() == {"type": "error", "message": "Malformed message"}
        ws.send_json({"type": "dance"})
        assert ws.receive_json() == {"type": "error", "message": "Unknown message type"}
        ws.send_text('{"type":"action","action":{"type":"move_pile","pile_id":"x","x":NaN,"y":0}}')
        assert ws.receive_json()["type"] == "error"
        ws.receive_json()  # fresh state after rejection
        act(ws, {"type": "shuffle", "pile_id": deck_id(state)})
        assert ws.receive_json()["type"] == "state"


def test_unknown_room_closes_4404(client):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/rooms/ZZZZ/ws?name=Ana") as ws:
            ws.receive_json()
    assert e.value.code == 4404


def test_bad_name_closes_4400(client):
    code = new_room(client)
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(f"/rooms/{code}/ws?name=") as ws:
            ws.receive_json()
    assert e.value.code == 4400


def test_room_full_closes_4409(client):
    code = new_room(client)
    with contextlib.ExitStack() as stack:
        for i in range(6):
            ws = stack.enter_context(client.websocket_connect(f"/rooms/{code}/ws?name=P{i}"))
            join(ws)
        with pytest.raises(WebSocketDisconnect) as e:
            with client.websocket_connect(f"/rooms/{code}/ws?name=Seventh") as ws:
                ws.receive_json()
        assert e.value.code == 4409


def test_reconnect_with_token_keeps_seat_and_hand(client):
    code = new_room(client)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ws:
        welcome, state = join(ws)
        act(ws, {"type": "deal", "pile_id": deck_id(state), "count": 3})
        hand = ws.receive_json()["view"]["hand"]
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana&token={welcome['token']}") as ws:
        again, state = join(ws)
        assert again["player_id"] == welcome["player_id"]
        assert state["view"]["hand"] == hand
        assert len(state["players"]) == 1


def test_disconnected_player_shows_as_not_connected(client):
    code = new_room(client)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ana:
        join(ana)
        with client.websocket_connect(f"/rooms/{code}/ws?name=Ben") as ben:
            join(ben)
            ana.receive_json()
        update = ana.receive_json()
        assert [p["connected"] for p in update["players"]] == [True, False]


def test_leave_frees_the_seat_and_returns_cards(client):
    code = new_room(client)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ana:
        _, state = join(ana)
        with client.websocket_connect(f"/rooms/{code}/ws?name=Ben") as ben:
            join(ben)
            ana.receive_json()
            act(ana, {"type": "deal", "pile_id": deck_id(state), "count": 2})
            ana.receive_json()
            ben.receive_json()
            ben.send_json({"type": "leave"})
            update = ana.receive_json()
            assert [p["name"] for p in update["players"]] == ["Ana"]
            on_table = sum(len(p["cards"]) for p in update["view"]["piles"])
            assert on_table == 52 - 2  # only Ana's 2 cards are off the table


def test_expired_room_is_gone(client, clock):
    code = new_room(client)
    clock.now += IDLE_EXPIRY_SECONDS + 1
    new_room(client)  # creating a room purges expired ones
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ws:
            ws.receive_json()
    assert e.value.code == 4404
