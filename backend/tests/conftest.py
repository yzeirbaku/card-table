import os
import tempfile

# Before anything imports app.main (whose module-level app opens the default database).
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="card-table-tests-"), "cards.db")

import pytest  # noqa: E402

import app.rooms  # noqa: E402


@pytest.fixture(autouse=True)
def no_start_countdown(monkeypatch):
    """Rooms start their game the moment the last seat is taken, as the tests expect; the
    countdown tests ask for it by name (RoomManager(start_seconds=...))."""
    monkeypatch.setattr(app.rooms, "START_SECONDS", 0.0)


@pytest.fixture(autouse=True)
def db_path(tmp_path, monkeypatch):
    """No test touches backend/data/: the app's default database is a fresh file per test."""
    path = tmp_path / "cards.db"
    monkeypatch.setenv("DB_PATH", str(path))
    return path
