"""Saving finished games and counting them up. Solo is 2- and 3-player games, teams is
4-player (a win counts for both partners). "vs computer" is any game with a computer
in a seat other than yours; the rest, guests included, is "vs people"."""

import sqlite3
from collections import defaultdict
from typing import Any

from .results import GameRecord


def save_game(conn: sqlite3.Connection, record: GameRecord, ended_at: float) -> None:
    conn.execute("BEGIN")
    try:
        cur = conn.execute(
            "INSERT INTO games (game, players, target, ended_at, how, had_computer) VALUES (?, ?, ?, ?, ?, ?)",
            (record.game, record.players, record.target, ended_at, record.how,
             any(s.computer for s in record.seats)))
        conn.executemany(
            "INSERT INTO game_seats (game_id, seat, user_id, computer, side, score, won)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(cur.lastrowid, s.seat, s.user_id, s.computer, s.side, s.score, s.won) for s in record.seats])
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def stats_for(conn: sqlite3.Connection, username: str) -> dict[str, Any] | None:
    user = conn.execute("SELECT id, username FROM users WHERE username_key = ?", (username.lower(),)).fetchone()
    if user is None:
        return None
    # Every seat of every game this user played, with which seat was theirs.
    rows = conn.execute(
        "SELECT mine.game_id, mine.seat AS my_seat, mine.won, g.players, s.seat, s.computer, u.username"
        " FROM game_seats mine JOIN games g ON g.id = mine.game_id"
        " JOIN game_seats s ON s.game_id = mine.game_id LEFT JOIN users u ON u.id = s.user_id"
        " WHERE mine.user_id = ?", (user["id"],)).fetchall()
    games: dict[int, dict[str, Any]] = {}
    for r in rows:
        g = games.setdefault(r["game_id"], {"won": bool(r["won"]), "players": r["players"], "my_seat": r["my_seat"],
                                            "computer": False, "partner": None})
        if r["seat"] == r["my_seat"]:
            continue
        g["computer"] |= bool(r["computer"])
        if r["players"] == 4 and r["seat"] == (r["my_seat"] + 2) % 4:  # across the table
            if r["computer"]:
                g["partner"] = ("computer", None)
            elif r["username"]:
                g["partner"] = ("user", r["username"])
            else:
                g["partner"] = ("guest", None)

    table = {kind: {col: {"won": 0, "lost": 0} for col in ("people", "computer", "total")}
             for kind in ("solo", "teams")}
    partners: dict[tuple[str, str | None], dict[str, int]] = defaultdict(lambda: {"won": 0, "lost": 0})
    for g in games.values():
        result = "won" if g["won"] else "lost"
        kind = "teams" if g["players"] == 4 else "solo"
        table[kind]["computer" if g["computer"] else "people"][result] += 1
        table[kind]["total"][result] += 1
        if g["partner"]:
            partners[g["partner"]][result] += 1

    order = {"user": 0, "computer": 1, "guest": 2}

    def rank(item):
        (kind, name), counts = item
        return order[kind], -(counts["won"] + counts["lost"]), (name or "").lower()

    return {
        "username": user["username"],
        **table,
        "partners": [{"kind": kind, **({"name": name} if name else {}), **counts}
                     for (kind, name), counts in sorted(partners.items(), key=rank)],
    }
