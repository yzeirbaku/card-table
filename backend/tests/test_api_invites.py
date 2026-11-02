"""Invites over HTTP (spec 2026-11-02-friends-and-invites)."""

import pytest
from fastapi.testclient import TestClient

from app.db import open_db
from app.main import create_app
from app.rooms import IDLE_EXPIRY_SECONDS, RoomManager
from tests.murlan_helpers import FakeClock
from tests.test_api_accounts import bearer, connect, register
from tests.test_push import KEYS, Fake, sub
from tests.test_websocket import join, send, state


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def fake() -> Fake:
    return Fake()


@pytest.fixture
def manager(clock) -> RoomManager:
    return RoomManager(clock=clock, start_seconds=0)


@pytest.fixture
def client(tmp_path, manager, fake) -> TestClient:
    return TestClient(create_app(manager, use_timers=False, db=open_db(tmp_path / "t.db"),
                                 push_keys=KEYS, push_send=fake))


def befriend(client, a, b, b_name):
    """a asks b (named b_name) and b accepts."""
    a_name = client.get("/me", headers=bearer(a)).json()["username"]
    client.post("/friends/requests", json={"username": b_name}, headers=bearer(a))
    assert client.post(f"/friends/requests/{a_name}/accept", headers=bearer(b)).status_code == 200


def new_table(client, players=4) -> str:
    return client.post("/rooms", json={"game": "murlan", "players": players}).json()["code"]


def invite(client, code, token, username):
    return client.post(f"/rooms/{code}/invite", json={"username": username}, headers=bearer(token))


def invites_of(client, token):
    return client.get("/invites", headers=bearer(token)).json()


@pytest.fixture
def pair(client):
    """Ana and Ben, friends; Ben's phone takes pushes."""
    a, b = register(client, "Ana"), register(client, "Ben")
    befriend(client, a, b, "Ben")
    assert client.post("/push/subscribe", json={"subscription": sub()}, headers=bearer(b)).status_code == 200
    return a, b


def test_invite_a_friend_from_the_lobby(client, pair, fake):
    a, b = pair
    code = new_table(client)
    with connect(client, code, session=a) as ws:
        join(ws)
        assert invite(client, code, a, "Ben").json() == {}
    assert invites_of(client, b) == [{"from": "Ana", "game": "Murlan", "players": 4, "code": code}]
    assert fake.sent == [("https://push.example/e1", {
        "type": "invite", "from": "Ana", "game": "Murlan", "players": 4, "code": code})]
    assert client.post(f"/invites/{code.lower()}/dismiss", headers=bearer(b)).json() == {}
    assert invites_of(client, b) == []


def test_only_friends_and_only_from_inside(client, pair):
    a, b = pair
    c = register(client, "Cleo")
    code = new_table(client)
    res = invite(client, code, a, "Ben")
    assert (res.status_code, res.json()["detail"]) == (403, "You're not at this table")
    res = invite(client, "NOPE", a, "Ben")
    assert (res.status_code, res.json()["detail"]) == (404, "Table not found")
    with connect(client, code, session=a) as ws:
        join(ws)
        res = invite(client, code, a, "Cleo")
        assert (res.status_code, res.json()["detail"]) == (403, "Only friends can be invited")
        res = invite(client, code, a, "Nobody")
        assert (res.status_code, res.json()["detail"]) == (404, "No such player")
        res = invite(client, code, b, "Ana")  # signed in, but not seated at this table
        assert (res.status_code, res.json()["detail"]) == (403, "You're not at this table")
    assert invites_of(client, b) == [] and invites_of(client, c) == []


def test_invite_disappears_when_the_friend_joins(client, pair):
    a, b = pair
    code = new_table(client)
    with connect(client, code, session=a) as ws:
        join(ws)
        invite(client, code, a, "Ben")
        assert len(invites_of(client, b)) == 1
        with connect(client, code, session=b) as ws_b:
            join(ws_b)
            assert invites_of(client, b) == []
        assert invites_of(client, b) == []  # and stays gone after they leave


def test_invite_goes_when_the_inviter_leaves(client, pair):
    a, b = pair
    c, d = register(client, "Cem"), register(client, "Dan")
    befriend(client, c, b, "Ben")
    befriend(client, a, d, "Dan")
    code = new_table(client)
    with connect(client, code, session=c) as ws_c:
        join(ws_c)
        invite(client, code, c, "Ben")
        with connect(client, code, session=a) as ws:
            join(ws)
            invite(client, code, a, "Dan")
            assert len(invites_of(client, d)) == 1
            send(ws, type="leave")
            assert invites_of(client, d) == []
            assert [i["from"] for i in invites_of(client, b)] == ["Cem"]


def test_invite_disappears_when_the_game_starts(client, pair):
    a, b = pair
    code = new_table(client, 2)
    with connect(client, code, session=a) as ws:
        join(ws)
        invite(client, code, a, "Ben")
        send(ws, type="sit", seat=0)
        state(ws)
        send(ws, type="add_computer", seat=1)
        assert state(ws)["game"] is not None
        assert invites_of(client, b) == []


def test_invite_gone_for_good_once_the_table_filled(client, pair):
    a, b = pair
    c = register(client, "Cleo")
    code = new_table(client, 2)
    with connect(client, code, session=a) as ws:
        join(ws)
        invite(client, code, a, "Ben")
        assert len(invites_of(client, b)) == 1
        with connect(client, code, session=c) as ws_c:
            join(ws_c)
            send(ws_c, type="leave")
        state(ws)  # the table heard Cleo leave: there is room again
        assert invites_of(client, b) == []  # but the old invite stays gone
        assert invite(client, code, a, "Ben").status_code == 200  # a fresh one is another matter
        assert len(invites_of(client, b)) == 1


def test_invite_disappears_when_the_room_expires(client, pair, manager, clock):
    a, b = pair
    code = new_table(client)
    with connect(client, code, session=a) as ws:
        join(ws)
        invite(client, code, a, "Ben")
    manager.get(code).last_activity = clock() - IDLE_EXPIRY_SECONDS - 1
    new_table(client)  # creating a table purges the idle ones
    assert manager.get(code) is None
    assert invites_of(client, b) == []


def test_already_here_and_started_refusals(client, pair):
    a, b = pair
    code = new_table(client, 2)
    with connect(client, code, session=a) as ws_a, connect(client, code, session=b) as ws_b:
        join(ws_a)
        state(ws_a)
        join(ws_b)
        res = invite(client, code, a, "Ben")
        assert (res.status_code, res.json()["detail"]) == (409, "Ben is already here")
        send(ws_a, type="sit", seat=0)
        send(ws_b, type="sit", seat=1)
        res = invite(client, code, a, "Ben")
        assert (res.status_code, res.json()["detail"]) == (409, "The game has started")


def test_full_table_and_throttle_refusals(client, pair):
    a, b = pair
    c = register(client, "Cleo")
    befriend(client, a, c, "Cleo")
    code = new_table(client, 2)
    with connect(client, code, session=a) as ws:
        join(ws)
        assert invite(client, code, a, "Ben").status_code == 200
        res = invite(client, code, a, "Ben")
        assert (res.status_code, res.json()["detail"]) == (429, "Invited just now, wait a moment")
        with connect(client, code, session=c) as ws_c:
            join(ws_c)
            res = invite(client, code, a, "Ben")
            assert (res.status_code, res.json()["detail"]) == (409, "The table is full")


def test_invite_names_ignore_case(client, pair):
    a, b = pair
    code = new_table(client)
    with connect(client, code, session=a) as ws:
        join(ws)
        assert invite(client, code, a, "ben").status_code == 200
        assert invite(client, code, a, "BEN").status_code == 429  # the same person, so the same throttle
    assert len(invites_of(client, b)) == 1


def test_invites_need_a_session(client):
    assert client.get("/invites").status_code == 401
    assert client.post("/invites/ABCD/dismiss").status_code == 401
    assert client.post("/rooms/ABCD/invite", json={"username": "Ben"}).status_code == 401
