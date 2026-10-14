import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.rooms import RoomManager


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(RoomManager(), use_timers=False))


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
