"""Accounts: a username and a password, nothing else. Passwords are kept as scrypt
hashes; a sign-in is a random session token the phone keeps until it signs out.
Guests never touch any of this.

Run on the server to set a forgotten password (there's no email):
    python -m app.accounts reset-password <username>"""

import asyncio
import hashlib
import hmac
import re
import secrets
import sqlite3
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from getpass import getpass
from typing import NamedTuple

USERNAME = re.compile(r"[A-Za-z0-9._-]{3,20}")
MIN_PASSWORD, MAX_PASSWORD = 8, 128
MAX_FAILURES = 5  # wrong passwords for one username ...
FAILURE_WINDOW = 600.0  # ... within this many seconds, and it's locked until they age out
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
MAX_HASHES_PER_MINUTE = 30  # for everyone together: about 16 MB and 50-200 ms each on the VM
_HASHING = threading.BoundedSemaphore(2)  # hashes at once


class AccountError(Exception):
    """A refused request: the message is shown to the player, the status goes on the HTTP reply."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class User(NamedTuple):
    id: int
    username: str


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    _, n, r, p, salt, digest = stored.split("$")
    got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                         dklen=len(digest) // 2)
    return hmac.compare_digest(got.hex(), digest)


_DUMMY_HASH = hash_password(secrets.token_hex(8))  # an unknown username costs as much as a wrong password


class Accounts:
    """Hashing runs in a worker thread, so a sign-in never stalls the tables; the database
    stays on the event loop (one connection, one thread). Hashing is budgeted for everyone
    together: it's the expensive part, and anyone can ask for it."""

    def __init__(self, conn: sqlite3.Connection, clock: Callable[[], float] = time.time) -> None:
        self.conn = conn
        self.clock = clock
        self.failures: dict[str, deque[float]] = {}  # by lowercased username; a key goes once its failures age out
        self.hashes: deque[float] = deque()  # when recent hashes were spent

    async def register(self, username: str, password: str) -> tuple[User, str]:
        if not USERNAME.fullmatch(username):
            raise AccountError(400, "Usernames are 3-20 letters, digits, . _ or -")
        _check_length(password)
        if self.registered_name(username):  # before the hash: a taken name costs nothing
            raise AccountError(409, "That username is taken")
        hashed = await self._hash(hash_password, password)
        try:
            cur = self.conn.execute(
                "INSERT INTO users (username, username_key, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (username, username.lower(), hashed, self.clock()))
        except sqlite3.IntegrityError:  # taken while we hashed
            raise AccountError(409, "That username is taken") from None
        user = User(cur.lastrowid, username)
        return user, self._new_session(user)

    async def login(self, username: str, password: str) -> tuple[User, str]:
        if not USERNAME.fullmatch(username) or not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
            raise AccountError(401, "Wrong username or password")  # no such account could exist
        key = username.lower()
        if len(self._recent_failures(key)) >= MAX_FAILURES:
            raise AccountError(429, "Too many tries, wait a few minutes")
        row = self.conn.execute("SELECT id, username, password_hash FROM users WHERE username_key = ?",
                                (key,)).fetchone()
        # Counted as a failure before the hash, so tries made at the same time can't all get past the limit.
        self._spend_hash()
        self.failures.setdefault(key, deque()).append(self.clock())
        matches = await self._hash(check_password, password, row["password_hash"] if row else _DUMMY_HASH, spent=True)
        if row is None or not matches:
            raise AccountError(401, "Wrong username or password")
        self.failures.pop(key, None)
        user = User(row["id"], row["username"])
        return user, self._new_session(user)

    def logout(self, token: str) -> None:
        self.conn.execute("DELETE FROM sessions WHERE token = ?", (_digest(token),))

    def user_for(self, token: str | None) -> User | None:
        if not token:
            return None
        row = self.conn.execute(
            "SELECT users.id, users.username FROM sessions JOIN users ON users.id = sessions.user_id"
            " WHERE sessions.token = ?", (_digest(token),)).fetchone()
        return User(row["id"], row["username"]) if row else None

    def registered_name(self, username: str) -> str | None:
        """The account's name as registered, if someone has this one (in any case)."""
        row = self.conn.execute("SELECT username FROM users WHERE username_key = ?", (username.lower(),)).fetchone()
        return row["username"] if row else None

    async def reset_password(self, username: str, password: str) -> None:
        _check_length(password)
        row = self.conn.execute("SELECT id FROM users WHERE username_key = ?", (username.lower(),)).fetchone()
        if row is None:
            raise AccountError(404, "No such user")
        hashed = await self._hash(hash_password, password)
        self.conn.execute("BEGIN")
        self.conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hashed, row["id"]))
        self.conn.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
        self.conn.execute("COMMIT")
        self.failures.pop(username.lower(), None)

    def _spend_hash(self) -> None:
        now = self.clock()
        while self.hashes and now - self.hashes[0] > 60:
            self.hashes.popleft()
        if len(self.hashes) >= MAX_HASHES_PER_MINUTE:
            raise AccountError(429, "Too many sign-ins right now, try again in a minute")
        self.hashes.append(now)

    async def _hash(self, fn, *args, spent: bool = False):
        if not spent:
            self._spend_hash()

        def work():
            with _HASHING:
                return fn(*args)

        return await asyncio.to_thread(work)

    def _recent_failures(self, key: str) -> deque[float]:
        now = self.clock()
        for k in [k for k, times in self.failures.items() if now - times[-1] > FAILURE_WINDOW]:
            del self.failures[k]  # all aged out: forget the name
        recent = self.failures.get(key, deque())
        while recent and now - recent[0] > FAILURE_WINDOW:
            recent.popleft()
        return recent

    def _new_session(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        self.conn.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
                          (_digest(token), user.id, self.clock()))
        return token


def _check_length(password: str) -> None:
    if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        raise AccountError(400, f"Passwords are {MIN_PASSWORD}-{MAX_PASSWORD} characters")


def _digest(token: str) -> str:
    """Sessions are stored hashed: the database file (and its backups) can't sign anyone in."""
    return hashlib.sha256(token.encode()).hexdigest()


def main(argv: list[str]) -> int:
    from .db import default_db_path, open_db

    if len(argv) != 2 or argv[0] != "reset-password":
        print("usage: python -m app.accounts reset-password <username>")
        return 2
    password = getpass("New password: ")
    if getpass("Again: ") != password:
        print("The two passwords differ")
        return 1
    try:
        asyncio.run(Accounts(open_db(default_db_path())).reset_password(argv[1], password))
    except AccountError as e:
        print(e)
        return 1
    print(f"Password set for {argv[1]}; their phones are signed out")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
