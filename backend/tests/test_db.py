import app.db
from app.db import MIGRATIONS, migrate, open_db


def version(conn) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def tables(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def add_user(conn) -> None:
    with conn:
        conn.execute("INSERT INTO users (username, username_key, password_hash, created_at)"
                     " VALUES ('Sebi', 'sebi', 'x', 0)")


def test_a_new_database_gets_every_table(tmp_path):
    conn = open_db(tmp_path / "x.db")
    assert version(conn) == len(MIGRATIONS)
    assert {"users", "sessions", "games", "game_seats"} <= tables(conn)


def test_migrate_only_applies_newer_migrations(tmp_path, monkeypatch):
    conn = open_db(tmp_path / "x.db")
    add_user(conn)
    monkeypatch.setattr(app.db, "MIGRATIONS", [*MIGRATIONS, "CREATE TABLE extra (x)"])
    migrate(conn)
    assert conn.execute("SELECT username FROM users").fetchone()[0] == "Sebi"
    assert "extra" in tables(conn)
    assert version(conn) == len(MIGRATIONS) + 1


def test_reopening_keeps_the_data(tmp_path):
    conn = open_db(tmp_path / "x.db")
    add_user(conn)
    conn.close()
    assert open_db(tmp_path / "x.db").execute("SELECT count(*) FROM users").fetchone()[0] == 1


def test_the_parent_folder_is_created(tmp_path):
    open_db(tmp_path / "a" / "b" / "x.db")
    assert (tmp_path / "a" / "b" / "x.db").exists()
