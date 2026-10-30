import pytest

from app.accounts import Accounts
from app.db import open_db
from app.results import GameRecord, SeatResult
from app.stats import head_to_head, leaderboard, save_game, stats_for

GUEST, BOT = "guest", "bot"


@pytest.fixture
def conn(tmp_path):
    return open_db(tmp_path / "s.db")


@pytest.fixture
def ids(conn) -> dict[str, int]:
    accounts = Accounts(conn)
    return {name: accounts.register(name, "password1")[0].id for name in ("Yzeir", "Sebi", "Arben")}


def save(conn, ids, seats: list[str], winners: set[int], how="target") -> None:
    """One game: `seats` are usernames, GUEST or BOT; `winners` are the winning sides."""
    n = len(seats)
    side = (lambda i: i % 2) if n == 4 else (lambda i: i)
    record = GameRecord("murlan", n, 13, how, tuple(
        SeatResult(seat=i, user_id=ids.get(who), computer=who == BOT, side=side(i), score=0,
                   won=side(i) in winners)
        for i, who in enumerate(seats)))
    save_game(conn, record, ended_at=1.0)


def wl(won: int, lost: int) -> dict:
    return {"won": won, "lost": lost}


def test_unknown_user_has_no_stats(conn):
    assert stats_for(conn, "nobody") is None


def test_saving_writes_one_row_per_seat(conn, ids):
    save(conn, ids, ["Yzeir", GUEST, BOT], {0})
    rows = conn.execute("SELECT seat, user_id, computer, won FROM game_seats ORDER BY seat").fetchall()
    assert [tuple(r) for r in rows] == [(0, ids["Yzeir"], 0, 1), (1, None, 0, 0), (2, None, 1, 0)]
    game = conn.execute("SELECT players, had_computer, how FROM games").fetchone()
    assert tuple(game) == (3, 1, "target")


def test_solo_and_teams_are_kept_apart(conn, ids):
    save(conn, ids, ["Yzeir", "Sebi"], {0})
    save(conn, ids, ["Yzeir", "Sebi", "Arben"], {1})
    save(conn, ids, ["Yzeir", "Sebi", "Arben", GUEST], {0})
    stats = stats_for(conn, "yzeir")
    assert stats["username"] == "Yzeir"
    assert stats["solo"]["total"] == wl(1, 1)
    assert stats["teams"]["total"] == wl(1, 0)


def test_vs_computer_is_decided_by_the_opponents(conn, ids):
    save(conn, ids, ["Yzeir", BOT], {0})  # alone against a computer
    save(conn, ids, ["Yzeir", "Sebi", BOT], {0})  # a mixed table: Sebi is an opponent
    save(conn, ids, ["Yzeir", "Sebi", BOT, "Arben"], {0})  # a computer partner, two people across
    save(conn, ids, ["Yzeir", BOT, "Arben", BOT], {1})  # Arben and me against two computers
    stats = stats_for(conn, "Yzeir")
    assert stats["solo"]["computer"] == wl(1, 0)
    assert stats["solo"]["people"] == wl(1, 0)
    assert stats["teams"]["people"] == wl(1, 0)
    assert stats["teams"]["computer"] == wl(0, 1)


def test_guests_count_as_people(conn, ids):
    save(conn, ids, ["Yzeir", GUEST], {1})
    assert stats_for(conn, "Yzeir")["solo"]["people"] == wl(0, 1)


def test_total_is_people_plus_computer(conn, ids):
    save(conn, ids, ["Yzeir", "Sebi"], {0})
    save(conn, ids, ["Yzeir", BOT], {1})
    save(conn, ids, ["Yzeir", BOT, "Sebi"], {0})
    solo = stats_for(conn, "Yzeir")["solo"]
    assert solo == {"people": wl(2, 0), "computer": wl(0, 1), "total": wl(2, 1)}  # Sebi made the last one vs people


def test_partners_by_account_then_computer_then_guest(conn, ids):
    save(conn, ids, ["Yzeir", GUEST, "Arben", GUEST], {1})
    save(conn, ids, ["Yzeir", GUEST, "Sebi", GUEST], {0})
    save(conn, ids, ["Yzeir", GUEST, "Sebi", GUEST], {0})
    save(conn, ids, ["Yzeir", "Sebi", GUEST, BOT], {0})
    save(conn, ids, ["Yzeir", "Sebi", BOT, "Arben"], {1})
    assert stats_for(conn, "Yzeir")["partners"] == [
        {"kind": "user", "name": "Sebi", **wl(2, 0)},
        {"kind": "user", "name": "Arben", **wl(0, 1)},
        {"kind": "computer", **wl(0, 1)},
        {"kind": "guest", **wl(1, 0)},
    ]


def entry(name: str, won: int, lost: int, ranked: bool = True) -> dict:
    return {"username": name, "won": won, "lost": lost, "ranked": ranked}


def test_the_leaderboard_ranks_by_win_rate_from_five_games(conn, ids):
    for _ in range(4):
        save(conn, ids, ["Arben", "Sebi"], {0})  # Arben 4-0, Sebi 0-4
    save(conn, ids, ["Arben", "Sebi"], {1})  # Arben 4-1, Sebi 1-4
    for _ in range(3):
        save(conn, ids, ["Yzeir", "Sebi"], {0})  # Yzeir 3-0 (too few), Sebi 1-7
    assert leaderboard(conn)["solo"] == [
        entry("Arben", 4, 1), entry("Sebi", 1, 7), entry("Yzeir", 3, 0, ranked=False)]
    assert leaderboard(conn)["teams"] == []


def test_the_leaderboard_counts_only_games_against_people(conn, ids):
    for _ in range(6):
        save(conn, ids, ["Yzeir", BOT], {0})
    save(conn, ids, ["Yzeir", "Sebi", BOT], {1})
    assert leaderboard(conn)["solo"] == [entry("Sebi", 1, 0, ranked=False), entry("Yzeir", 0, 1, ranked=False)]


def test_leaderboard_ties_go_to_more_wins_then_name(conn, ids):
    for _ in range(5):
        save(conn, ids, ["Arben", GUEST], {0})
        save(conn, ids, ["Sebi", GUEST], {0})
    for _ in range(5):
        save(conn, ids, ["Yzeir", GUEST], {0})
        save(conn, ids, ["Yzeir", GUEST], {0})
    assert [e["username"] for e in leaderboard(conn)["solo"]] == ["Yzeir", "Arben", "Sebi"]


def test_the_teams_leaderboard_counts_a_win_for_both_partners(conn, ids):
    save(conn, ids, ["Yzeir", "Sebi", "Arben", GUEST], {0})
    assert leaderboard(conn)["teams"] == [
        entry("Arben", 1, 0, ranked=False), entry("Yzeir", 1, 0, ranked=False), entry("Sebi", 0, 1, ranked=False)]


def test_head_to_head_counts_only_games_one_of_you_won(conn, ids):
    save(conn, ids, ["Yzeir", "Arben"], {0})
    save(conn, ids, ["Yzeir", "Arben", "Sebi"], {1})
    save(conn, ids, ["Yzeir", "Arben", "Sebi"], {2})  # Sebi won: not between Yzeir and Arben
    save(conn, ids, ["Yzeir", "Sebi", "Arben", GUEST], {0})  # partners
    save(conn, ids, ["Yzeir", "Arben", GUEST, "Sebi"], {1})  # opposite teams: Arben's won
    assert head_to_head(conn, "yzeir", "Arben") == {"against": wl(1, 2), "together": wl(1, 0)}
    assert head_to_head(conn, "Arben", "Yzeir") == {"against": wl(2, 1), "together": wl(1, 0)}
    assert head_to_head(conn, "Yzeir", "nobody") is None
