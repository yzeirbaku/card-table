"""Web Push: subscriptions tied to a session, and sending (spec 2026-11-02-friends-and-invites)."""

import asyncio
import base64
import json

import pytest
from fastapi.testclient import TestClient

from app.accounts import AccountError, Accounts
from app.db import open_db
from app.main import create_app
from app.push import Push, PushKeys, generate_keys
from app.rooms import RoomManager
from tests.test_api_accounts import PW, bearer, register

KEYS = PushKeys("pub", "priv", "mailto:t@example.com")


def sub(endpoint="https://push.example/e1") -> dict:
    return {"endpoint": endpoint, "keys": {"p256dh": "p", "auth": "a"}}


class Fake:
    """A sender that records what it was given and answers with a status per endpoint."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []
        self.status: dict[str, int] = {}

    def __call__(self, info: dict, data: str, keys: PushKeys) -> int:
        self.sent.append((info["endpoint"], json.loads(data)))
        return self.status.get(info["endpoint"], 201)


@pytest.fixture
def db(tmp_path):
    return open_db(tmp_path / "t.db")


@pytest.fixture
def fake() -> Fake:
    return Fake()


@pytest.fixture
def push(db, fake) -> Push:
    return Push(db, KEYS, fake)


@pytest.fixture
def accounts(db) -> Accounts:
    return Accounts(db)


def make_user(accounts, name):
    return asyncio.run(accounts.register(name, PW))


def test_notify_sends_to_every_device_of_that_user(accounts, push, fake):
    a, token = make_user(accounts, "Sebi")
    second = accounts._new_session(a)
    push.subscribe(a, token, sub("https://push.example/phone"))
    push.subscribe(a, second, sub("https://push.example/laptop"))
    b, b_token = make_user(accounts, "Ana")
    push.subscribe(b, b_token, sub("https://push.example/other"))
    asyncio.run(push.notify(a.id, {"type": "request", "from": "Ana"}))
    assert sorted(e for e, _ in fake.sent) == ["https://push.example/laptop", "https://push.example/phone"]
    assert all(p == {"type": "request", "from": "Ana"} for _, p in fake.sent)


def test_a_gone_subscription_is_deleted(accounts, push, fake, db):
    a, token = make_user(accounts, "Sebi")
    push.subscribe(a, token, sub())
    fake.status["https://push.example/e1"] = 410
    asyncio.run(push.notify(a.id, {"type": "request", "from": "Ana"}))
    assert db.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0] == 0


def test_other_failures_keep_the_subscription(accounts, push, fake, db):
    a, token = make_user(accounts, "Sebi")
    push.subscribe(a, token, sub())
    fake.status["https://push.example/e1"] = 500
    asyncio.run(push.notify(a.id, {"type": "request", "from": "Ana"}))
    assert db.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0] == 1


def test_a_sender_that_raises_does_not_reach_the_caller(accounts, db):
    def boom(info, data, keys):
        raise RuntimeError("down")

    push = Push(db, KEYS, boom)
    a, token = make_user(accounts, "Sebi")
    push.subscribe(a, token, sub())
    asyncio.run(push.notify(a.id, {"type": "request", "from": "Ana"}))


def test_no_keys_sends_nothing(accounts, db, fake):
    push = Push(db, None, fake)
    a, token = make_user(accounts, "Sebi")
    push.subscribe(a, token, sub())
    asyncio.run(push.notify(a.id, {"type": "request", "from": "Ana"}))
    assert fake.sent == []


@pytest.mark.parametrize("bad", [
    {"endpoint": "http://push.example/e", "keys": {"p256dh": "p", "auth": "a"}},
    {"endpoint": "https://push.example/e", "keys": {"p256dh": "p"}},
    {"endpoint": "https://push.example/e", "keys": {"p256dh": "", "auth": "a"}},
    {"endpoint": "https://push.example/e"},
    {"endpoint": "https://push.example/" + "x" * 1000, "keys": {"p256dh": "p", "auth": "a"}},
    {"endpoint": 5, "keys": {"p256dh": "p", "auth": "a"}},
])
def test_bad_subscription_refused(accounts, push, bad):
    a, token = make_user(accounts, "Sebi")
    with pytest.raises(AccountError) as e:
        push.subscribe(a, token, bad)
    assert (e.value.status, str(e.value)) == (400, "Bad subscription")


def test_subscribe_moves_a_phone_to_the_new_account(accounts, push, fake):
    a, a_token = make_user(accounts, "Sebi")
    b, b_token = make_user(accounts, "Ana")
    push.subscribe(a, a_token, sub("https://push.example/E"))
    push.subscribe(b, b_token, sub("https://push.example/E"))
    asyncio.run(push.notify(a.id, {"type": "request", "from": "X"}))
    assert fake.sent == []
    asyncio.run(push.notify(b.id, {"type": "request", "from": "X"}))
    assert [e for e, _ in fake.sent] == ["https://push.example/E"]
    assert push.is_on(b_token, "https://push.example/E")
    assert not push.is_on(a_token, "https://push.example/E")


def test_signing_out_stops_pushes_to_that_phone(accounts, push, fake):
    a, token = make_user(accounts, "Sebi")
    push.subscribe(a, token, sub())
    accounts.logout(token)
    asyncio.run(push.notify(a.id, {"type": "request", "from": "X"}))
    assert fake.sent == []
    token = accounts._new_session(a)
    push.subscribe(a, token, sub())
    asyncio.run(accounts.reset_password("Sebi", "another-pass1"))
    asyncio.run(push.notify(a.id, {"type": "request", "from": "X"}))
    assert fake.sent == []


def test_allow_once(db, fake):
    now = [1000.0]
    push = Push(db, KEYS, fake, clock=lambda: now[0])
    assert push.allow_once(("k",), 60)
    assert not push.allow_once(("k",), 60)
    assert push.allow_once(("other",), 60)
    now[0] += 61
    assert push.allow_once(("k",), 60)


@pytest.fixture
def pclient(tmp_path, fake) -> TestClient:
    app = create_app(RoomManager(), use_timers=False, db=open_db(tmp_path / "p.db"),
                     push_keys=KEYS, push_send=fake)
    return TestClient(app)


def test_friend_request_push_once_a_day(pclient, fake):
    a, b = register(pclient, "Aaa"), register(pclient, "Bbb")
    assert pclient.post("/push/subscribe", json={"subscription": sub()}, headers=bearer(b)).status_code == 200
    for _ in range(2):
        res = pclient.post("/friends/requests", json={"username": "Bbb"}, headers=bearer(a))
        assert res.json()["result"] == "sent"
        pclient.delete("/friends/requests/Bbb", headers=bearer(a))
    assert fake.sent == [("https://push.example/e1", {"type": "request", "from": "Aaa"})]


def test_push_endpoints(pclient):
    token = register(pclient)
    assert pclient.get("/push/key").json() == {"key": "pub"}
    body = {"subscription": sub()}
    assert pclient.post("/push/subscribe", json=body, headers=bearer(token)).json() == {}
    status = {"endpoint": sub()["endpoint"]}
    assert pclient.post("/push/status", json=status, headers=bearer(token)).json() == {"on": True}
    assert pclient.post("/push/unsubscribe", json=status).json() == {}
    assert pclient.post("/push/status", json=status, headers=bearer(token)).json() == {"on": False}
    bad = {"subscription": {"endpoint": "http://x"}}
    assert pclient.post("/push/subscribe", json=bad, headers=bearer(token)).status_code == 400
    assert pclient.post("/push/status", json=status).status_code == 401


def test_without_keys_the_key_is_null(tmp_path, monkeypatch):
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    client = TestClient(create_app(RoomManager(), use_timers=False, db=open_db(tmp_path / "n.db")))
    assert client.get("/push/key").json() == {"key": None}


def test_generated_keys_work_with_pywebpush():
    from py_vapid import Vapid

    public, private = generate_keys()
    Vapid.from_string(private)
    raw = base64.urlsafe_b64decode(public + "=" * (-len(public) % 4))
    assert len(raw) == 65 and raw[0] == 0x04
    assert "=" not in public + private
