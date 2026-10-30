import asyncio
import hashlib
import time

import pytest

import app.accounts
from app.accounts import MAX_HASHES_PER_MINUTE, AccountError, Accounts, check_password
from app.db import open_db
from tests.murlan_helpers import FakeClock

PW = "hunter2!!"
run = asyncio.run


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def accounts(tmp_path, clock) -> Accounts:
    return Accounts(open_db(tmp_path / "a.db"), clock=clock)


def status(coro) -> int:
    with pytest.raises(AccountError) as e:
        run(coro)
    return e.value.status


def test_register_signs_you_in(accounts):
    user, token = run(accounts.register("Sebi", PW))
    assert user.username == "Sebi"
    assert accounts.user_for(token) == user


def test_the_password_is_stored_hashed(accounts):
    run(accounts.register("Sebi", PW))
    stored = accounts.conn.execute("SELECT password_hash FROM users").fetchone()[0]
    assert PW not in stored
    assert stored.startswith("scrypt$")
    assert check_password(PW, stored)
    assert not check_password("hunter2!?", stored)


def test_sessions_are_stored_hashed(accounts):
    _, token = run(accounts.register("Sebi", PW))
    stored = accounts.conn.execute("SELECT token FROM sessions").fetchone()[0]
    assert stored == hashlib.sha256(token.encode()).hexdigest()  # a backup of the file signs nobody in


def test_usernames_are_unique_ignoring_case(accounts):
    run(accounts.register("Sebi", PW))
    assert status(accounts.register("sebi", PW)) == 409


def test_login_ignores_case_and_returns_the_name_as_registered(accounts):
    run(accounts.register("Sebi", PW))
    user, token = run(accounts.login("SEBI", PW))
    assert user.username == "Sebi"
    assert accounts.user_for(token) == user


@pytest.mark.parametrize("username, password", [
    ("ab", PW), ("a" * 21, PW), ("sp ace", PW), ("émile", PW), ("", PW),
    ("Sebi", "short"), ("Sebi", "x" * 129),
])
def test_bad_usernames_and_passwords_are_rejected(accounts, username, password):
    assert status(accounts.register(username, password)) == 400


def test_wrong_password_and_unknown_user_say_the_same(accounts):
    run(accounts.register("Sebi", PW))
    with pytest.raises(AccountError) as wrong:
        run(accounts.login("Sebi", "nope-nope"))
    with pytest.raises(AccountError) as unknown:
        run(accounts.login("Nobody", PW))
    assert wrong.value.status == unknown.value.status == 401
    assert str(wrong.value) == str(unknown.value)


def test_five_failures_lock_the_username_for_ten_minutes(accounts, clock):
    run(accounts.register("Sebi", PW))
    for _ in range(5):
        assert status(accounts.login("Sebi", "nope-nope")) == 401
    assert status(accounts.login("sebi", PW)) == 429
    clock.now += 601
    assert run(accounts.login("Sebi", PW))[0].username == "Sebi"


def test_a_success_clears_the_failures(accounts):
    run(accounts.register("Sebi", PW))
    for _ in range(4):
        status(accounts.login("Sebi", "nope-nope"))
    run(accounts.login("Sebi", PW))
    for _ in range(4):
        assert status(accounts.login("Sebi", "nope-nope")) == 401


def test_the_limit_is_per_username(accounts):
    run(accounts.register("Sebi", PW))
    run(accounts.register("Arben", PW))
    for _ in range(5):
        status(accounts.login("Sebi", "nope-nope"))
    assert run(accounts.login("Arben", PW))[0].username == "Arben"


def test_malformed_logins_are_refused_without_hashing_or_tracking(accounts, monkeypatch):
    monkeypatch.setattr(app.accounts, "check_password", lambda *a: pytest.fail("hashed"))
    assert status(accounts.login("x" * 100_000, PW)) == 401
    assert status(accounts.login("Sebi", "x" * 100_000)) == 401
    assert accounts.failures == {}


def test_failures_are_forgotten_once_they_age_out(accounts, clock):
    status(accounts.login("Nobody", PW))
    clock.now += 601
    status(accounts.login("Other", PW))
    assert set(accounts.failures) == {"other"}


def test_a_taken_name_is_refused_before_hashing(accounts, monkeypatch):
    run(accounts.register("Sebi", PW))
    monkeypatch.setattr(app.accounts, "hash_password", lambda *a: pytest.fail("hashed"))
    assert status(accounts.register("SEBI", PW)) == 409


def test_hashing_is_budgeted_for_everyone(accounts, clock):
    for i in range(MAX_HASHES_PER_MINUTE):
        status(accounts.login(f"user{i}", PW))
    assert status(accounts.login("someone", PW)) == 429
    assert status(accounts.register("someone", PW)) == 429
    clock.now += 61
    run(accounts.register("someone", PW))


def test_hashing_does_not_block_the_event_loop(accounts, monkeypatch):
    real = app.accounts.hash_password

    def slow(password):
        time.sleep(0.3)
        return real(password)

    monkeypatch.setattr(app.accounts, "hash_password", slow)

    async def both():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        task = asyncio.create_task(ticker())
        await accounts.register("Sebi", PW)
        task.cancel()
        return ticks

    assert run(both()) > 10  # the loop kept running while the password was hashed


def test_logout_ends_the_session(accounts):
    _, token = run(accounts.register("Sebi", PW))
    accounts.logout(token)
    assert accounts.user_for(token) is None
    accounts.logout("no-such-token")
    assert accounts.user_for(None) is None


def test_reset_password_signs_out_everywhere(accounts):
    _, one = run(accounts.register("Sebi", PW))
    _, two = run(accounts.login("Sebi", PW))
    run(accounts.reset_password("sebi", "brand-new-pw"))
    assert accounts.user_for(one) is None and accounts.user_for(two) is None
    assert run(accounts.login("Sebi", "brand-new-pw"))[0].username == "Sebi"
    assert status(accounts.login("Sebi", PW)) == 401
    assert status(accounts.reset_password("Nobody", "brand-new-pw")) == 404


def test_registered_name(accounts):
    run(accounts.register("Sebi", PW))
    assert accounts.registered_name("sEBi") == "Sebi"
    assert accounts.registered_name("Arben") is None
