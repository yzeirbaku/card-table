import pytest

from app.accounts import AccountError, Accounts, check_password
from app.db import open_db
from tests.murlan_helpers import FakeClock

PW = "hunter2!!"


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def accounts(tmp_path, clock) -> Accounts:
    return Accounts(open_db(tmp_path / "a.db"), clock=clock)


def status(fn, *args) -> int:
    with pytest.raises(AccountError) as e:
        fn(*args)
    return e.value.status


def test_register_signs_you_in(accounts):
    user, token = accounts.register("Sebi", PW)
    assert user.username == "Sebi"
    assert accounts.user_for(token) == user


def test_the_password_is_stored_hashed(accounts):
    accounts.register("Sebi", PW)
    stored = accounts.conn.execute("SELECT password_hash FROM users").fetchone()[0]
    assert PW not in stored
    assert stored.startswith("scrypt$")
    assert check_password(PW, stored)
    assert not check_password("hunter2!?", stored)


def test_usernames_are_unique_ignoring_case(accounts):
    accounts.register("Sebi", PW)
    assert status(accounts.register, "sebi", PW) == 409


def test_login_ignores_case_and_returns_the_name_as_registered(accounts):
    accounts.register("Sebi", PW)
    user, token = accounts.login("SEBI", PW)
    assert user.username == "Sebi"
    assert accounts.user_for(token) == user


@pytest.mark.parametrize("username, password", [
    ("ab", PW), ("a" * 21, PW), ("sp ace", PW), ("émile", PW), ("", PW),
    ("Sebi", "short"), ("Sebi", "x" * 129),
])
def test_bad_usernames_and_passwords_are_rejected(accounts, username, password):
    assert status(accounts.register, username, password) == 400


def test_wrong_password_and_unknown_user_say_the_same(accounts):
    accounts.register("Sebi", PW)
    with pytest.raises(AccountError) as wrong:
        accounts.login("Sebi", "nope-nope")
    with pytest.raises(AccountError) as unknown:
        accounts.login("Nobody", PW)
    assert wrong.value.status == unknown.value.status == 401
    assert str(wrong.value) == str(unknown.value)


def test_five_failures_lock_the_username_for_ten_minutes(accounts, clock):
    accounts.register("Sebi", PW)
    for _ in range(5):
        assert status(accounts.login, "Sebi", "nope-nope") == 401
    assert status(accounts.login, "sebi", PW) == 429
    clock.now += 601
    assert accounts.login("Sebi", PW)[0].username == "Sebi"


def test_a_success_clears_the_failures(accounts):
    accounts.register("Sebi", PW)
    for _ in range(4):
        status(accounts.login, "Sebi", "nope-nope")
    accounts.login("Sebi", PW)
    for _ in range(4):
        assert status(accounts.login, "Sebi", "nope-nope") == 401


def test_the_limit_is_per_username(accounts):
    accounts.register("Sebi", PW)
    accounts.register("Arben", PW)
    for _ in range(5):
        status(accounts.login, "Sebi", "nope-nope")
    assert accounts.login("Arben", PW)[0].username == "Arben"


def test_logout_ends_the_session(accounts):
    _, token = accounts.register("Sebi", PW)
    accounts.logout(token)
    assert accounts.user_for(token) is None
    accounts.logout("no-such-token")
    assert accounts.user_for(None) is None


def test_reset_password_signs_out_everywhere(accounts):
    _, one = accounts.register("Sebi", PW)
    _, two = accounts.login("Sebi", PW)
    accounts.reset_password("sebi", "brand-new-pw")
    assert accounts.user_for(one) is None and accounts.user_for(two) is None
    assert accounts.login("Sebi", "brand-new-pw")[0].username == "Sebi"
    assert status(accounts.login, "Sebi", PW) == 401
    assert status(accounts.reset_password, "Nobody", "brand-new-pw") == 404
