"""Accounts over HTTP, and signed-in players at a table (spec 2026-10-30-accounts-and-stats-design.md)."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.db import open_db
from app.main import create_app
from app.rooms import RoomManager
from tests.test_room_results import NEAR, finish_round
from tests.test_websocket import join, new_room, send, state

PW = "password1"


@pytest.fixture
def manager() -> RoomManager:
    return RoomManager()


@pytest.fixture
def client(tmp_path, manager) -> TestClient:
    return TestClient(create_app(manager, use_timers=False, db=open_db(tmp_path / "t.db")))


def register(client, username="Sebi", password=PW) -> str:
    res = client.post("/auth/register", json={"username": username, "password": password})
    assert res.status_code == 200, res.json()
    assert res.json()["username"] == username
    return res.json()["token"]


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def connect(client, code, name="whatever", session=None, token=None):
    query = f"name={name}" + (f"&session={session}" if session else "") + (f"&token={token}" if token else "")
    return client.websocket_connect(f"/rooms/{code}/ws?{query}")


def test_register_then_me(client):
    token = register(client)
    assert client.get("/me", headers=bearer(token)).json() == {"username": "Sebi"}


def test_login_errors_come_back_as_detail(client):
    register(client)
    res = client.post("/auth/register", json={"username": "SEBI", "password": PW})
    assert (res.status_code, res.json()["detail"]) == (409, "That username is taken")
    for _ in range(5):
        res = client.post("/auth/login", json={"username": "Sebi", "password": "nope-nope"})
        assert (res.status_code, res.json()["detail"]) == (401, "Wrong username or password")
    res = client.post("/auth/login", json={"username": "Sebi", "password": PW})
    assert (res.status_code, res.json()["detail"]) == (429, "Too many tries, wait a few minutes")


def test_login_returns_a_working_session(client):
    register(client)
    res = client.post("/auth/login", json={"username": "sebi", "password": PW})
    assert res.json()["username"] == "Sebi"
    assert client.get("/me", headers=bearer(res.json()["token"])).status_code == 200


def test_logout_then_me_is_401(client):
    token = register(client)
    assert client.post("/auth/logout", headers=bearer(token)).status_code == 200
    res = client.get("/me", headers=bearer(token))
    assert (res.status_code, res.json()["detail"]) == (401, "Signed out")
    assert client.get("/me").status_code == 401
    assert client.post("/auth/logout").status_code == 200


def test_stats_endpoint(client):
    register(client)
    assert client.get("/stats/sebi").json()["username"] == "Sebi"
    res = client.get("/stats/nobody")
    assert (res.status_code, res.json()["detail"]) == (404, "No such player")


def test_cors_allows_the_authorization_header(client):
    res = client.options("/me", headers={
        "Origin": "http://localhost:5520",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization",
    })
    assert res.status_code == 200
    assert "authorization" in res.headers["access-control-allow-headers"].lower()


def test_a_bad_session_closes_the_socket_with_4401(client):
    code = new_room(client)
    with connect(client, code, session="not-a-session") as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert (e.value.code, e.value.reason) == (4401, "Signed out")


def test_signed_in_players_sit_under_their_username(client):
    session = register(client)
    code = new_room(client)
    with connect(client, code, name="Someone else", session=session) as ws:
        _, first = join(ws)
        assert [p["name"] for p in first["players"]] == ["Sebi"]
        assert "user_id" not in first["players"][0]


def test_one_account_once_per_room(client):
    session = register(client)
    code = new_room(client)
    with connect(client, code, session=session) as first:
        welcome, _ = join(first)
        with connect(client, code, session=session) as second:
            with pytest.raises(WebSocketDisconnect) as e:
                second.receive_json()
        assert (e.value.code, e.value.reason) == (4409, "You're already at this table")
        with connect(client, code, session=session, token=welcome["token"]) as again:
            assert again.receive_json()["type"] == "welcome"  # the seat token still gets them back


def test_a_finished_game_shows_in_stats(client, manager):
    sebi, arben = register(client, "Sebi"), register(client, "Arben")
    code = new_room(client)
    with connect(client, code, session=sebi) as one, connect(client, code, session=arben) as two:
        join(one)
        join(two)
        send(one, type="sit", seat=0)
        send(two, type="sit", seat=1)
        room = manager.get(code)
        for _ in range(20):  # wait for both seats to be taken
            if room.game is not None:
                break
            state(one)
        finish_round(room, NEAR[2])
    assert client.get("/stats/Sebi").json()["solo"]["people"] == {"won": 1, "lost": 0}
    assert client.get("/stats/Arben").json()["solo"]["people"] == {"won": 0, "lost": 1}


def test_leaderboard_and_head_to_head_endpoints(client):
    register(client, "Sebi"), register(client, "Arben")
    assert client.get("/leaderboard").json() == {"solo": [], "teams": []}
    assert client.get("/head-to-head/Sebi", params={"with": "arben"}).json() == {
        "against": {"won": 0, "lost": 0}, "together": {"won": 0, "lost": 0}}
    res = client.get("/head-to-head/Sebi", params={"with": "nobody"})
    assert (res.status_code, res.json()["detail"]) == (404, "No such player")
