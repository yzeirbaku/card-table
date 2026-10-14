import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.rooms import RoomManager


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(RoomManager()))


def new_room(client: TestClient, players: int) -> str:
    res = client.post("/rooms", json={"game": "murlan", "players": players})
    assert res.status_code == 200
    return res.json()["code"]


def join(ws) -> tuple[dict, dict]:
    welcome = ws.receive_json()
    state = ws.receive_json()
    assert welcome["type"] == "welcome"
    assert state["type"] == "state"
    return welcome, state


def test_games_lists_murlan(client):
    assert client.get("/games").json() == [
        {"id": "murlan", "name": "Murlan", "min_players": 2, "max_players": 4}
    ]


@pytest.mark.parametrize(
    "body",
    [
        {"game": "poker", "players": 4},
        {"game": "murlan", "players": 1},
        {"game": "murlan", "players": 5},
    ],
)
def test_create_room_rejects_unknown_game_or_bad_count(client, body):
    res = client.post("/rooms", json=body)
    assert res.status_code == 400
    assert res.json()["detail"]


def test_create_room_requires_a_body(client):
    assert client.post("/rooms").status_code == 422


def test_room_starts_when_the_last_seat_fills(client):
    code = new_room(client, 2)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ana:
        _, state = join(ana)
        assert state["room"] == {"game": "murlan", "seats": 2, "status": "lobby"}
        with client.websocket_connect(f"/rooms/{code}/ws?name=Ben") as ben:
            _, ben_state = join(ben)
            assert ben_state["room"]["status"] == "playing"
            assert ana.receive_json()["room"]["status"] == "playing"


def test_reconnect_while_playing_keeps_the_seat(client):
    code = new_room(client, 2)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ana:
        welcome, _ = join(ana)
        with client.websocket_connect(f"/rooms/{code}/ws?name=Ben") as ben:
            join(ben)
            ana.receive_json()  # Ben arrived
    # Both sockets dropped; seats are kept.
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana&token={welcome['token']}") as ana:
        again, state = join(ana)
        assert again["player_id"] == welcome["player_id"]
        assert state["room"]["status"] == "playing"
        assert len(state["players"]) == 2


def test_leave_while_playing_returns_to_lobby(client):
    code = new_room(client, 2)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ana:
        join(ana)
        with client.websocket_connect(f"/rooms/{code}/ws?name=Ben") as ben:
            join(ben)
            ana.receive_json()  # Ben arrived, game started
            ben.send_json({"type": "leave"})
            update = ana.receive_json()
            assert update["room"]["status"] == "lobby"
            assert [p["name"] for p in update["players"]] == ["Ana"]


def preflight(client: TestClient, origin: str):
    return client.options(
        "/rooms",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5520",
        "http://127.0.0.1:5520",
        "http://192.168.1.20:5520",
        "http://10.0.0.5:5520",
        "http://172.20.1.2:5520",
    ],
)
def test_cors_allows_dev_origins(client, origin):
    assert preflight(client, origin).headers.get("access-control-allow-origin") == origin


@pytest.mark.parametrize(
    "origin",
    [
        "http://evil.example:5520",
        "http://192.168.1.20:8080",
        "http://172.32.0.1:5520",
        "http://localhost:5520.evil.example",
    ],
)
def test_cors_rejects_other_origins(client, origin):
    assert "access-control-allow-origin" not in preflight(client, origin).headers
