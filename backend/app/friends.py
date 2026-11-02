"""Friends: who can invite whom. A request goes one way until the other side accepts
(or asks back); a friendship is stored once, with the lower id first. Like Accounts,
plain SQL on the one connection, no I/O besides it."""

import sqlite3
import time
from collections.abc import Callable
from typing import Literal

from .accounts import AccountError, User

MAX_FRIENDS = 200
MAX_OUTGOING = 50  # requests waiting for an answer, per player


class Friends:
    def __init__(self, conn: sqlite3.Connection, clock: Callable[[], float] = time.time) -> None:
        self.conn = conn
        self.clock = clock

    def user_named(self, username: str) -> User | None:
        row = self.conn.execute("SELECT id, username FROM users WHERE username_key = ?",
                                (username.lower(),)).fetchone()
        return User(row["id"], row["username"]) if row else None

    def overview(self, user: User) -> dict:
        def names(sql: str) -> list[str]:
            rows = self.conn.execute(sql, (user.id,)).fetchall()
            return sorted((r["username"] for r in rows), key=str.lower)

        return {
            "friends": names(
                "SELECT users.username FROM friendships JOIN users"
                " ON users.id = CASE WHEN friendships.user_a = ?1 THEN friendships.user_b ELSE friendships.user_a END"
                " WHERE friendships.user_a = ?1 OR friendships.user_b = ?1"),
            "incoming": names(
                "SELECT users.username FROM friend_requests JOIN users ON users.id = friend_requests.from_user"
                " WHERE friend_requests.to_user = ?"),
            "outgoing": names(
                "SELECT users.username FROM friend_requests JOIN users ON users.id = friend_requests.to_user"
                " WHERE friend_requests.from_user = ?"),
        }

    def request(self, user: User, username: str) -> tuple[Literal["sent", "accepted"], User]:
        other = self.user_named(username)
        if other is None:
            raise AccountError(404, "No such player")
        if other.id == user.id:
            raise AccountError(400, "That's you")
        if self.are_friends(user.id, other.id):
            raise AccountError(409, "You're already friends")
        if self._has_request(other.id, user.id):  # they asked first: asking back is saying yes
            self._befriend(user, other)
            return "accepted", other
        if self._has_request(user.id, other.id):
            return "sent", other
        self._check_room(user, other)
        if self._count("SELECT count(*) FROM friend_requests WHERE from_user = ?", user.id) >= MAX_OUTGOING:
            raise AccountError(409, "Too many requests waiting for an answer")
        self.conn.execute("INSERT INTO friend_requests (from_user, to_user, created_at) VALUES (?, ?, ?)",
                          (user.id, other.id, self.clock()))
        return "sent", other

    def accept(self, user: User, username: str) -> None:
        other = self.user_named(username)
        if other is None:
            raise AccountError(404, "No such player")
        if not self._has_request(other.id, user.id):
            raise AccountError(404, f"No request from {other.username}")
        self._befriend(user, other)

    def decline(self, user: User, username: str) -> None:
        self._delete_request(username, to_user=user.id)

    def cancel(self, user: User, username: str) -> None:
        self._delete_request(username, from_user=user.id)

    def remove(self, user: User, username: str) -> None:
        other = self.user_named(username)
        if other is not None:
            a, b = sorted((user.id, other.id))
            self.conn.execute("DELETE FROM friendships WHERE user_a = ? AND user_b = ?", (a, b))

    def are_friends(self, a_id: int, b_id: int) -> bool:
        a, b = sorted((a_id, b_id))
        return self.conn.execute("SELECT 1 FROM friendships WHERE user_a = ? AND user_b = ?",
                                 (a, b)).fetchone() is not None

    def _befriend(self, user: User, other: User) -> None:
        self._check_room(user, other)
        a, b = sorted((user.id, other.id))
        self.conn.execute("BEGIN")
        try:
            self.conn.execute(
                "DELETE FROM friend_requests WHERE (from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?)",
                (user.id, other.id, other.id, user.id))
            self.conn.execute("INSERT INTO friendships (user_a, user_b, since) VALUES (?, ?, ?)",
                              (a, b, self.clock()))
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def _check_room(self, user: User, other: User) -> None:
        if self._friend_count(user.id) >= MAX_FRIENDS:
            raise AccountError(409, "You have too many friends")
        if self._friend_count(other.id) >= MAX_FRIENDS:
            raise AccountError(409, f"{other.username} has too many friends")

    def _friend_count(self, user_id: int) -> int:
        return self._count("SELECT count(*) FROM friendships WHERE user_a = ?1 OR user_b = ?1", user_id)

    def _count(self, sql: str, user_id: int) -> int:
        return self.conn.execute(sql, (user_id,)).fetchone()[0]

    def _has_request(self, from_id: int, to_id: int) -> bool:
        return self.conn.execute("SELECT 1 FROM friend_requests WHERE from_user = ? AND to_user = ?",
                                 (from_id, to_id)).fetchone() is not None

    def _delete_request(self, username: str, from_user: int | None = None, to_user: int | None = None) -> None:
        other = self.user_named(username)
        if other is None:
            return
        self.conn.execute("DELETE FROM friend_requests WHERE from_user = ? AND to_user = ?",
                          (from_user or other.id, to_user or other.id))
