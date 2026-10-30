"""Saving finished games and counting them up. Solo is 2- and 3-player games, teams is
4-player (a win counts for both partners). A game is "vs computer" when every
opponent was a computer; the rest, mixed tables and guests included, is "vs people".
Your partner in a 4-player game is not an opponent."""

import sqlite3
from collections import defaultdict
from typing import Any

from .results import GameRecord

MIN_RANKED_GAMES = 5  # on the leaderboard, fewer games than this are listed but not ranked


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


def _user(conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return conn.execute("SELECT id, username FROM users WHERE username_key = ?", (username.lower(),)).fetchone()


def _games(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    """Every game this user played, from their seat: won, kind, vs computer, partner, and the
    other seats as (user_id, side, won)."""
    rows = conn.execute(
        "SELECT mine.game_id, mine.seat AS my_seat, mine.side AS my_side, mine.won AS my_won, g.players,"
        " s.seat, s.side, s.won, s.computer, s.user_id, u.username"
        " FROM game_seats mine JOIN games g ON g.id = mine.game_id"
        " JOIN game_seats s ON s.game_id = mine.game_id AND s.seat != mine.seat"
        " LEFT JOIN users u ON u.id = s.user_id"
        " WHERE mine.user_id = ?", (user_id,)).fetchall()
    games: dict[int, dict[str, Any]] = {}
    for r in rows:
        g = games.setdefault(r["game_id"], {"won": bool(r["my_won"]), "kind": "teams" if r["players"] == 4 else "solo",
                                            "side": r["my_side"], "vs_person": False, "partner": None, "others": []})
        g["others"].append((r["user_id"], r["side"], bool(r["won"])))
        if r["side"] != r["my_side"]:
            g["vs_person"] |= not r["computer"]
        elif r["computer"]:
            g["partner"] = ("computer", None)
        elif r["username"]:
            g["partner"] = ("user", r["username"])
        else:
            g["partner"] = ("guest", None)
    return list(games.values())


def _wl() -> dict[str, int]:
    return {"won": 0, "lost": 0}


def stats_for(conn: sqlite3.Connection, username: str) -> dict[str, Any] | None:
    user = _user(conn, username)
    if user is None:
        return None
    table = {kind: {col: _wl() for col in ("people", "computer", "total")} for kind in ("solo", "teams")}
    partners: dict[tuple[str, str | None], dict[str, int]] = defaultdict(_wl)
    for g in _games(conn, user["id"]):
        result = "won" if g["won"] else "lost"
        table[g["kind"]]["people" if g["vs_person"] else "computer"][result] += 1
        table[g["kind"]]["total"][result] += 1
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


def leaderboard(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """Everyone's games against people, solo and teams: ranked by win % from MIN_RANKED_GAMES
    games (ties: more wins, then name), the rest after them by games played."""
    boards: dict[str, list[dict[str, Any]]] = {"solo": [], "teams": []}
    for user in conn.execute("SELECT id, username FROM users").fetchall():
        counts = {"solo": _wl(), "teams": _wl()}
        for g in _games(conn, user["id"]):
            if g["vs_person"]:
                counts[g["kind"]]["won" if g["won"] else "lost"] += 1
        for kind, c in counts.items():
            played = c["won"] + c["lost"]
            if played:
                boards[kind].append({"username": user["username"], **c, "ranked": played >= MIN_RANKED_GAMES})

    def order(e):
        played = e["won"] + e["lost"]
        rate = e["won"] / played
        return (not e["ranked"], 0 if e["ranked"] else -played, -rate, -e["won"], e["username"].lower())

    return {kind: sorted(board, key=order) for kind, board in boards.items()}


def head_to_head(conn: sqlite3.Connection, username: str, other: str) -> dict[str, Any] | None:
    """From `username`'s side: games against `other` that one of the two won, and games as partners."""
    user, them = _user(conn, username), _user(conn, other)
    if user is None or them is None:
        return None
    against, together = _wl(), _wl()
    for g in _games(conn, user["id"]):
        for user_id, side, won in g["others"]:
            if user_id != them["id"]:
                continue
            if side == g["side"]:
                together["won" if g["won"] else "lost"] += 1
            elif g["won"]:
                against["won"] += 1
            elif won:
                against["lost"] += 1
    return {"against": against, "together": together}
