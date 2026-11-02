"""The one file that outlives a restart: accounts, sign-ins and finished games, in
SQLite. Rooms stay in memory. The schema grows by numbered migrations, applied at
startup from `PRAGMA user_version`, so a redeploy keeps every row."""

import os
import sqlite3
from pathlib import Path

# Append only: a migration that has shipped is never edited, a change is a new one.
MIGRATIONS = [
    """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        username TEXT NOT NULL,
        username_key TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at REAL NOT NULL
    );
    CREATE TABLE sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at REAL NOT NULL
    );
    CREATE TABLE games (
        id INTEGER PRIMARY KEY,
        game TEXT NOT NULL,
        players INTEGER NOT NULL,
        target INTEGER,
        ended_at REAL NOT NULL,
        how TEXT NOT NULL CHECK (how IN ('target', 'leave')),
        had_computer INTEGER NOT NULL
    );
    CREATE TABLE game_seats (
        game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
        seat INTEGER NOT NULL,
        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        computer INTEGER NOT NULL,
        side INTEGER NOT NULL,
        score INTEGER NOT NULL,
        won INTEGER NOT NULL,
        PRIMARY KEY (game_id, seat)
    );
    CREATE INDEX game_seats_user ON game_seats (user_id);
    """,
    """
    CREATE TABLE friendships (
        user_a INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        user_b INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        since REAL NOT NULL,
        PRIMARY KEY (user_a, user_b),
        CHECK (user_a < user_b)
    );
    CREATE INDEX friendships_b ON friendships (user_b);
    CREATE TABLE friend_requests (
        from_user INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        to_user INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        PRIMARY KEY (from_user, to_user)
    );
    CREATE INDEX friend_requests_to ON friend_requests (to_user);
    CREATE TABLE push_subscriptions (
        endpoint TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        session TEXT NOT NULL REFERENCES sessions(token) ON DELETE CASCADE,
        p256dh TEXT NOT NULL,
        auth TEXT NOT NULL,
        created_at REAL NOT NULL
    );
    """,
]


def default_db_path() -> str:
    return os.environ.get("DB_PATH") or str(Path(__file__).resolve().parent.parent / "data" / "cards.db")


def open_db(path: str | os.PathLike) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # One connection for the app; the test client calls it from another thread.
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    done = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, script in enumerate(MIGRATIONS[done:], start=done + 1):
        # executescript would commit on its own; run the statements in one transaction instead
        conn.execute("BEGIN")
        try:
            for statement in script.split(";"):
                if statement.strip():
                    conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {number}")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
