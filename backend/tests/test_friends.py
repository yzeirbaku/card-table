import asyncio

import pytest

import app.friends
from app.accounts import AccountError, Accounts
from app.db import open_db
from app.friends import Friends
from tests.murlan_helpers import FakeClock

PW = "hunter2!!"
run = asyncio.run


@pytest.fixture
def conn(tmp_path):
    return open_db(tmp_path / "t.db")


@pytest.fixture
def friends(conn) -> Friends:
    return Friends(conn, clock=FakeClock())


@pytest.fixture
def make_user(conn):
    accounts = Accounts(conn)

    def make(name):
        return run(accounts.register(name, PW))[0]

    return make


def refusal(fn, *args) -> tuple[int, str]:
    with pytest.raises(AccountError) as e:
        fn(*args)
    return e.value.status, str(e.value)


def test_request_then_accept(friends, make_user):
    a, b = make_user("A_user"), make_user("B_user")
    assert friends.request(a, "B_user") == ("sent", b)
    assert friends.overview(a)["outgoing"] == ["B_user"]
    assert friends.overview(b)["incoming"] == ["A_user"]
    friends.accept(b, "A_user")
    for me, other in ((a, "B_user"), (b, "A_user")):
        o = friends.overview(me)
        assert o == {"friends": [other], "incoming": [], "outgoing": []}
    assert friends.are_friends(a.id, b.id) and friends.are_friends(b.id, a.id)


def test_request_back_accepts(friends, make_user):
    a, b = make_user("A_user"), make_user("B_user")
    friends.request(a, "B_user")
    assert friends.request(b, "A_user") == ("accepted", a)
    assert friends.are_friends(a.id, b.id)
    assert friends.overview(a)["outgoing"] == [] and friends.overview(b)["outgoing"] == []


def test_requests_ignore_case(friends, make_user):
    a, b = make_user("A_user"), make_user("Sebi")
    assert friends.request(a, "sEbI") == ("sent", b)
    assert friends.overview(a)["outgoing"] == ["Sebi"]
    assert friends.user_named("SEBI") == b
    assert friends.user_named("nobody") is None


def test_refusals(friends, make_user):
    a, b = make_user("A_user"), make_user("B_user")
    assert refusal(friends.request, a, "nobody") == (404, "No such player")
    assert refusal(friends.request, a, "a_USER") == (400, "That's you")
    friends.request(a, "B_user")
    friends.accept(b, "A_user")
    assert refusal(friends.request, a, "B_user") == (409, "You're already friends")
    assert refusal(friends.accept, a, "B_user") == (404, "No request from B_user")
    assert refusal(friends.accept, a, "nobody") == (404, "No such player")


def test_request_twice_is_quiet(friends, make_user, conn):
    a, b = make_user("A_user"), make_user("B_user")
    friends.request(a, "B_user")
    assert friends.request(a, "B_user") == ("sent", b)
    assert conn.execute("SELECT count(*) FROM friend_requests").fetchone()[0] == 1


def test_decline_cancel_remove(friends, make_user, conn):
    a, b = make_user("A_user"), make_user("B_user")
    friends.request(a, "B_user")
    friends.decline(b, "A_user")
    assert friends.overview(a)["outgoing"] == [] and friends.overview(b)["incoming"] == []
    friends.request(a, "B_user")  # the sender can ask again
    friends.cancel(a, "B_user")
    assert friends.overview(b)["incoming"] == []
    friends.request(a, "B_user")
    friends.accept(b, "A_user")
    friends.remove(a, "B_user")
    assert not friends.are_friends(a.id, b.id)
    assert friends.overview(b)["friends"] == []
    # quiet when there's nothing to delete
    friends.decline(a, "B_user")
    friends.cancel(a, "B_user")
    friends.remove(a, "B_user")
    friends.remove(a, "nobody")
    assert conn.execute("SELECT count(*) FROM friend_requests").fetchone()[0] == 0


def test_limits(friends, make_user, monkeypatch):
    a, b, c, d = (make_user(n) for n in ("A_user", "B_user", "C_user", "D_user"))
    monkeypatch.setattr(app.friends, "MAX_OUTGOING", 2)
    friends.request(a, "B_user")
    friends.request(a, "C_user")
    assert refusal(friends.request, a, "D_user") == (409, "Too many requests waiting for an answer")
    friends.request(a, "B_user")  # already waiting: not a new one

    monkeypatch.setattr(app.friends, "MAX_FRIENDS", 1)
    friends.accept(b, "A_user")  # b: 1 friend, a: 1 friend
    # c's accept of a's request: a is already at the limit
    assert refusal(friends.accept, c, "A_user") == (409, "A_user has too many friends")
    # d asking a (at limit) is refused, and b asking d fine, then d accepting b is over b's limit
    assert refusal(friends.request, d, "A_user") == (409, "A_user has too many friends")
    assert refusal(friends.request, a, "D_user") == (409, "You have too many friends")


def test_deleting_a_user_cascades(friends, make_user, conn):
    a, b, c = make_user("A_user"), make_user("B_user"), make_user("C_user")
    friends.request(a, "B_user")
    friends.accept(b, "A_user")
    friends.request(a, "C_user")
    conn.execute("DELETE FROM users")
    assert conn.execute("SELECT count(*) FROM friendships").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM friend_requests").fetchone()[0] == 0
