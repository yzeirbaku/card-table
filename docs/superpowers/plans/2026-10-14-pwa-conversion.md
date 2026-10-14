# PWA Conversion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Expo app with a vanilla-JS PWA where friends create a room for a chosen game and player count, join by code, wait in a lobby, and land together on a themed landscape table.

**Architecture:** The FastAPI backend gains a small game registry and rooms that know their game, seat count and status (`lobby` → `playing` when the last seat fills). A no-build PWA in `frontend/` (ES modules, plain CSS) has three views (main, lobby, table) driven by the server's `state` messages over the existing WebSocket. Card faces are pre-rendered WebP images from a public-domain deck; themes and the Vintage card style are pure CSS.

**Tech Stack:** Python 3.12, FastAPI 0.115, pytest; vanilla JS (ES modules), CSS, `node --test` (Node 24, no npm dependencies); resvg-py 0.5.0 + Pillow 12.3.0 (dev-only, card build script).

**Spec:** `docs/superpowers/specs/2026-10-14-pwa-conversion-design.md`

## Global Constraints

- **Server is authoritative; the frontend has no game logic.** It renders whatever `state` the server sends.
- Single uvicorn worker; live rooms in memory. The old free-form engine (`backend/app/engine/`) stays untouched; the frontend ignores `view`.
- Frontend: **no build step, no npm dependencies.** `frontend/package.json` exists only so Node treats `.js` as ES modules for tests.
- Ports: backend **8020**, frontend **5520**, both bound to `0.0.0.0` in dev.
- Room code: 4 letters from `ABCDEFGHJKLMNPQRSTUVWXYZ`; names 1–20 chars after trimming.
- Games: `murlan` → "Murlan", 2–4 players (provisional until the Murlan spec).
- Themes (setting): `classic` (default), `qendisje`, `kafeneio`. Card styles (setting): `traditional` (default), `vintage`.
- Vintage = `background: #f3e8cf; filter: sepia(.38) saturate(.85) contrast(.96) brightness(.98)` plus a multiply vignette.
- Names are rendered with `textContent` only, never `innerHTML`.
- Local git only: commit freely, **never push**. Identity is set in the repo (`Yzeir Baku <yzeirbaku@hotmail.com>`). End every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Commands are written for Git Bash on Windows from the repo root `C:\Users\YzeirBaku\projects\card-table`. Backend Python: `backend/.venv/Scripts/python`.

## Review Focus

1. **A phone drops signal or the page reloads mid-lobby/mid-game** → it rejoins the same seat silently, with a "Reconnecting…" banner meanwhile. *(Task 2 `test_reconnect_while_playing_keeps_the_seat`; Task 5 `network drop reconnects with the saved token`, `reconnect resets after a successful open`)*
2. **A wrong, expired or already-full code** → the player is sent back to the main screen with a clear message, and the dead seat token is forgotten so it isn't retried on next launch. *(Task 2 `test_room_full_closes_4409`; Task 5 `room not found is final and forgets the seat`, `full room shows the server's reason`)*
3. **Backend not running / unreachable** (PC asleep, wrong Wi-Fi) → no endless spinner: a "Can't reach the server" message on the main screen. *(Task 5 `never connecting gives up with a message and keeps the token`; Task 6 `fetchGames` error path checked in the browser)*
4. **Someone leaves during a game** → the remaining players drop back to the lobby with the seat open, and a newcomer can take it. *(Task 1 `test_leaving_while_playing_reopens_the_lobby`; Task 2 `test_leave_while_playing_returns_to_lobby`)*
5. **Phone held upright on the table screen** → the table renders rotated 90° so it reads correctly sideways; desktop/landscape is unrotated. *(Task 4 `orientation` tests; Task 8 browser check at 390×844 and 844×390)*

---

## File Structure

```
card-table/
├── backend/
│   ├── app/
│   │   ├── games.py            NEW  game registry (id, name, player range)
│   │   ├── rooms.py            MOD  game/seats/status, join+leave rules, room_view()
│   │   └── main.py             MOD  GET /games, POST /rooms body, "room" in state, CORS
│   └── tests/
│       ├── test_rooms.py       MOD  create(game, seats); new lobby/status tests
│       ├── test_websocket.py   MOD  new_room posts a body; room-full uses 4 seats
│       └── test_api.py         NEW  /games, create validation, start/leave/reconnect, CORS
├── frontend/
│   ├── index.html              all three views, sheets, toast, banner
│   ├── styles.css              layout: main, sheets, lobby, table, rotation
│   ├── themes.css              3 table themes, props, swatches, Vintage card style
│   ├── config.js               BACKEND_URL default (same host, port 8020)
│   ├── manifest.webmanifest, service-worker.js, _headers
│   ├── package.json            {"type":"module"} for node --test
│   ├── cards/*.webp            54 card faces (generated, committed)
│   ├── icons/icon-{192,512}.png (generated, committed)
│   ├── js/
│   │   ├── code.js             cleanCode, isCompleteCode
│   │   ├── seats.js            seatPositions (who sits where, relative to you)
│   │   ├── orientation.js      shouldRotate
│   │   ├── storage.js          createStore: name, settings, seat tokens, current room
│   │   ├── connection.js       RoomConnection: WebSocket + reconnect/backoff
│   │   ├── api.js              fetchGames, createRoom, socketUrl
│   │   ├── clipboard.js        copyText (with http fallback), canReadClipboard
│   │   ├── ui.js               showView, toast, setReconnecting
│   │   ├── sheets.js           openSheet, closeSheets
│   │   ├── main-view.js        name, New table / Join / Settings sheets
│   │   ├── lobby-view.js       code + Copy, seat list
│   │   ├── table-view.js       seats around the table, menu
│   │   └── app.js              wiring: settings, connection, view switching
│   └── tests/*.test.js         node --test
├── scripts/
│   ├── build_cards.py          SVG deck → frontend/cards + icons
│   ├── serve_frontend.py       static server with correct MIME types
│   ├── dev_up.py, dev_down.py
└── app/                        DELETED (Expo)
```

---

### Task 1: Rooms know their game, seats and status

**Files:**
- Modify: `backend/app/rooms.py`
- Modify: `backend/tests/test_rooms.py`

**Interfaces:**
- Produces:
  - `RoomManager.create(game: str, seats: int) -> Room` (no validation here; the HTTP layer validates).
  - `Room.game: str`, `Room.seats: int`, `Room.status: Literal["lobby", "playing"]`.
  - `Room.room_view() -> dict` → `{"game": str, "seats": int, "status": "lobby" | "playing"}`.
  - `Room.join` raises `JoinRejected(4409, "This table is full")` when `status == "playing"` or every seat is taken; the join that fills the last seat sets `status = "playing"`.
  - `Room.leave` always sets `status = "lobby"`.
  - `MAX_PLAYERS` is removed.

- [ ] **Step 1: Point the existing tests at the new `create` signature**

The old tests assume a 6-seat room; keep that so they still mean the same thing:

```bash
cd backend && sed -i 's/\.create()/.create("murlan", 6)/g' tests/test_rooms.py && grep -o 'create("murlan", 6)' tests/test_rooms.py | wc -l
```

Expected: `14` (every former `.create()` call).

- [ ] **Step 2: Add the failing tests**

Append to `backend/tests/test_rooms.py`:

```python
def test_room_starts_in_lobby_with_its_game_and_seats():
    room = RoomManager().create("murlan", 4)
    assert (room.game, room.seats, room.status) == ("murlan", 4, "lobby")
    assert room.room_view() == {"game": "murlan", "seats": 4, "status": "lobby"}


def test_filling_the_last_seat_starts_the_game():
    room = RoomManager().create("murlan", 2)
    room.join("Ana", None)
    assert room.status == "lobby"
    room.join("Ben", None)
    assert room.status == "playing"


def test_new_player_rejected_once_playing():
    room = RoomManager().create("murlan", 2)
    room.join("Ana", None)
    room.join("Ben", None)
    with pytest.raises(JoinRejected) as e:
        room.join("Cleo", None)
    assert e.value.code == 4409
    assert e.value.message == "This table is full"


def test_reconnect_with_token_works_while_playing():
    room = RoomManager().create("murlan", 2)
    ana = room.join("Ana", None)
    room.join("Ben", None)
    assert room.join("Ana", ana.token) is ana
    assert room.status == "playing"


def test_leaving_in_lobby_frees_the_seat():
    room = RoomManager().create("murlan", 3)
    room.join("Ana", None)
    ben = room.join("Ben", None)
    room.leave(ben.id)
    assert room.status == "lobby"
    room.join("Cleo", None)
    assert [p.name for p in room.players] == ["Ana", "Cleo"]
    assert room.status == "lobby"


def test_leaving_while_playing_reopens_the_lobby():
    room = RoomManager().create("murlan", 2)
    room.join("Ana", None)
    ben = room.join("Ben", None)
    room.leave(ben.id)
    assert room.status == "lobby"
    room.join("Cleo", None)
    assert room.status == "playing"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_rooms.py -q`
Expected: FAIL. `create()` takes no `game`/`seats` arguments (`TypeError`).

- [ ] **Step 4: Implement**

In `backend/app/rooms.py`:

Change the typing import and delete `MAX_PLAYERS`:

```python
from typing import Any, Literal
```

```python
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I/O: easy to read aloud
CODE_LENGTH = 4
MAX_NAME_LENGTH = 20
IDLE_EXPIRY_SECONDS = 2 * 60 * 60

RoomStatus = Literal["lobby", "playing"]
```

Replace the `Room` fields and `join`/`leave`, and add `room_view` (keep `players_view` as is):

```python
@dataclass
class Room:
    code: str
    last_activity: float
    game: str
    seats: int
    status: RoomStatus = "lobby"  # "playing" once every seat is taken
    state: TableState = field(default_factory=new_table)
    players: list[Player] = field(default_factory=list)
    host_id: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def join(self, name: str, token: str | None) -> Player:
        if token:
            for p in self.players:
                if secrets.compare_digest(p.token, token):
                    return p
        name = name.strip()
        if not 1 <= len(name) <= MAX_NAME_LENGTH:
            raise JoinRejected(4400, f"Name must be 1-{MAX_NAME_LENGTH} characters")
        if self.status == "playing" or len(self.players) >= self.seats:
            raise JoinRejected(4409, "This table is full")
        player = Player(id=secrets.token_hex(4), name=name, token=secrets.token_urlsafe(16))
        self.players.append(player)
        add_player(self.state, player.id)
        if self.host_id is None:
            self.host_id = player.id
        if len(self.players) == self.seats:
            self.status = "playing"
        return player

    def leave(self, player_id: str) -> None:
        self.players = [p for p in self.players if p.id != player_id]
        remove_player(self.state, player_id)
        if self.host_id == player_id:
            self.host_id = self.players[0].id if self.players else None
        # A game can't go on with an empty seat; back to waiting for someone.
        self.status = "lobby"

    def room_view(self) -> dict[str, Any]:
        return {"game": self.game, "seats": self.seats, "status": self.status}
```

Replace `RoomManager.create`:

```python
    def create(self, game: str, seats: int) -> Room:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if code not in self.rooms:
                break
        room = Room(code=code, last_activity=self._clock(), game=game, seats=seats)
        self.rooms[code] = room
        return room
```

- [ ] **Step 5: Run the room tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_rooms.py -q`
Expected: all pass (the old `test_seventh_player_rejected` still passes: the 6-seat room is full and playing, so the 7th gets 4409).

`tests/test_websocket.py` fails now (`create()` arity in `POST /rooms`); Task 2 fixes it. Don't commit a broken suite. Go straight on to Task 2 and commit both together at the end of Task 2.

---

### Task 2: HTTP + WebSocket API for games, rooms and CORS

**Files:**
- Create: `backend/app/games.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_websocket.py`
- Create: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `RoomManager.create(game, seats)`, `Room.room_view()` (Task 1).
- Produces (HTTP/WS contract used by the frontend in Tasks 5–7):
  - `GET /games` → `[{"id": "murlan", "name": "Murlan", "min_players": 2, "max_players": 4}]`
  - `POST /rooms` with JSON `{"game": str, "players": int}` → `200 {"code": "ABCD"}`; `400 {"detail": "<message>"}` for an unknown game or out-of-range count; `422` when the body is missing or malformed.
  - Every `state` message gains `"room": {"game", "seats", "status"}`.
  - WebSocket close codes (unchanged): `4404` room not found, `4400` bad name, `4409` table full (reason `"This table is full"`), `4410` room expired, `4000` seat opened on another connection.
  - CORS: origins matching `DEV_ORIGINS` (port 5520 on localhost / 127.0.0.1 / 10.x / 192.168.x / 172.16–31.x), overridable with env `CORS_ORIGIN_REGEX`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_api.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.rooms import RoomManager


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(RoomManager()))


def new_room(client: TestClient, players: int) -> str:
    res = client.post("/rooms", json={"game": "murlan", "players": players})
    assert res.status_code == 200
    return res.json()["code"]


def join(ws) -> tuple[dict, dict]:
    welcome = ws.receive_json()
    state = ws.receive_json()
    assert welcome["type"] == "welcome"
    assert state["type"] == "state"
    return welcome, state


def test_games_lists_murlan(client):
    assert client.get("/games").json() == [
        {"id": "murlan", "name": "Murlan", "min_players": 2, "max_players": 4}
    ]


@pytest.mark.parametrize(
    "body",
    [
        {"game": "poker", "players": 4},
        {"game": "murlan", "players": 1},
        {"game": "murlan", "players": 5},
    ],
)
def test_create_room_rejects_unknown_game_or_bad_count(client, body):
    res = client.post("/rooms", json=body)
    assert res.status_code == 400
    assert res.json()["detail"]


def test_create_room_requires_a_body(client):
    assert client.post("/rooms").status_code == 422


def test_room_starts_when_the_last_seat_fills(client):
    code = new_room(client, 2)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ana:
        _, state = join(ana)
        assert state["room"] == {"game": "murlan", "seats": 2, "status": "lobby"}
        with client.websocket_connect(f"/rooms/{code}/ws?name=Ben") as ben:
            _, ben_state = join(ben)
            assert ben_state["room"]["status"] == "playing"
            assert ana.receive_json()["room"]["status"] == "playing"


def test_reconnect_while_playing_keeps_the_seat(client):
    code = new_room(client, 2)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ana:
        welcome, _ = join(ana)
        with client.websocket_connect(f"/rooms/{code}/ws?name=Ben") as ben:
            join(ben)
            ana.receive_json()  # Ben arrived
    # Both sockets dropped; seats are kept.
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana&token={welcome['token']}") as ana:
        again, state = join(ana)
        assert again["player_id"] == welcome["player_id"]
        assert state["room"]["status"] == "playing"
        assert len(state["players"]) == 2


def test_leave_while_playing_returns_to_lobby(client):
    code = new_room(client, 2)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ana:
        join(ana)
        with client.websocket_connect(f"/rooms/{code}/ws?name=Ben") as ben:
            join(ben)
            ana.receive_json()  # Ben arrived, game started
            ben.send_json({"type": "leave"})
            update = ana.receive_json()
            assert update["room"]["status"] == "lobby"
            assert [p["name"] for p in update["players"]] == ["Ana"]


def preflight(client: TestClient, origin: str):
    return client.options(
        "/rooms",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5520",
        "http://127.0.0.1:5520",
        "http://192.168.1.20:5520",
        "http://10.0.0.5:5520",
        "http://172.20.1.2:5520",
    ],
)
def test_cors_allows_dev_origins(client, origin):
    assert preflight(client, origin).headers.get("access-control-allow-origin") == origin


@pytest.mark.parametrize(
    "origin",
    [
        "http://evil.example:5520",
        "http://192.168.1.20:8080",
        "http://172.32.0.1:5520",
        "http://localhost:5520.evil.example",
    ],
)
def test_cors_rejects_other_origins(client, origin):
    assert "access-control-allow-origin" not in preflight(client, origin).headers
```

In `backend/tests/test_websocket.py`, replace the `new_room` helper:

```python
def new_room(client: TestClient, players: int = 4) -> str:
    res = client.post("/rooms", json={"game": "murlan", "players": players})
    assert res.status_code == 200
    return res.json()["code"]
```

Replace `test_room_full_closes_4409`:

```python
def test_room_full_closes_4409(client):
    code = new_room(client, 4)
    with contextlib.ExitStack() as stack:
        for i in range(4):
            ws = stack.enter_context(client.websocket_connect(f"/rooms/{code}/ws?name=P{i}"))
            join(ws)
        with pytest.raises(WebSocketDisconnect) as e:
            with client.websocket_connect(f"/rooms/{code}/ws?name=Fifth") as ws:
                ws.receive_json()
        assert e.value.code == 4409
        assert e.value.reason == "This table is full"
```

In `test_create_and_join`, add after the `players` assertion:

```python
        assert state["room"] == {"game": "murlan", "seats": 4, "status": "lobby"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: FAIL. `GET /games` returns 404, `POST /rooms` ignores the body / errors, and there's no `room` key in `state`.

- [ ] **Step 3: Implement**

Create `backend/app/games.py`:

```python
"""Games the server can host. For now only what the lobby needs: a display name
and the allowed player counts. Each game's rules arrive with its own spec."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GameInfo:
    id: str
    name: str
    min_players: int
    max_players: int


# Murlan's player range is provisional until its rules are pinned down.
GAMES: dict[str, GameInfo] = {g.id: g for g in [GameInfo("murlan", "Murlan", 2, 4)]}
```

In `backend/app/main.py`, update the imports:

```python
import json
import os
from contextlib import suppress
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .engine.actions import ActionRejected, apply_action
from .engine.views import view_for
from .games import GAMES
from .rooms import JoinRejected, Player, Room, RoomManager

# Local dev: the frontend is served on :5520 from localhost or a private-network address.
DEV_ORIGINS = (
    r"https?://(localhost|127\.0\.0\.1|10(\.\d{1,3}){3}|192\.168(\.\d{1,3}){2}"
    r"|172\.(1[6-9]|2\d|3[01])(\.\d{1,3}){2}):5520"
)


class CreateRoom(BaseModel):
    game: str
    players: int
```

Right after `app = FastAPI(title="Card Table")` in `create_app`:

```python
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=os.environ.get("CORS_ORIGIN_REGEX", DEV_ORIGINS),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
```

In `send_state`, add the room to the message:

```python
        message: dict[str, Any] = {
            "type": "state",
            "code": room.code,
            "room": room.room_view(),
            "players": room.players_view(),
            "view": view_for(room.state, player.id),
        }
```

Replace the `create_room` endpoint and add `list_games`:

```python
    @app.get("/games")
    async def list_games() -> list[dict[str, Any]]:
        return [asdict(g) for g in GAMES.values()]

    @app.post("/rooms")
    async def create_room(body: CreateRoom) -> dict[str, str]:
        await close_expired()
        game = GAMES.get(body.game)
        if game is None:
            raise HTTPException(400, f"Unknown game: {body.game}")
        if not game.min_players <= body.players <= game.max_players:
            raise HTTPException(
                400, f"{game.name} is for {game.min_players}-{game.max_players} players"
            )
        return {"code": rooms.create(game.id, body.players).code}
```

- [ ] **Step 4: Run the whole suite to verify it passes**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all pass (83 old + new). Starlette 0.41 checks `allow_origin_regex` with `fullmatch`, so `http://localhost:5520.evil.example` is rejected without anchors.

- [ ] **Step 5: Commit (Tasks 1 + 2)**

```bash
git add backend/app/games.py backend/app/rooms.py backend/app/main.py backend/tests/test_rooms.py backend/tests/test_websocket.py backend/tests/test_api.py
git commit -m "feat(backend): rooms have a game, seats and lobby/playing status

GET /games lists hostable games; POST /rooms takes {game, players}.
A room starts when its last seat fills and drops back to the lobby
when someone leaves. CORS allows the dev frontend on :5520.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Card artwork and app icons

**Files:**
- Create: `scripts/build_cards.py`
- Create (generated): `frontend/cards/*.webp` (54 files), `frontend/icons/icon-192.png`, `frontend/icons/icon-512.png`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `frontend/cards/{rank}{suit}.webp` for ranks `2..10,J,Q,K,A` and suits `C D H S` (e.g. `10H.webp`, `AS.webp`), plus `joker-red.webp`, `joker-black.webp`, each 320×466. Icons at `frontend/icons/icon-192.png` and `icon-512.png`. Tasks 6–7 reference `/cards/AH.webp`, `/cards/AC.webp`, `/cards/joker-red.webp`, `/icons/icon-192.png`, `/icons/icon-512.png`.

- [ ] **Step 1: Ignore the dev state folder**

Append to `.gitignore`:

```
.dev/
```

- [ ] **Step 2: Write the build script**

Create `scripts/build_cards.py`:

```python
"""Build frontend/cards/*.webp and frontend/icons/icon-*.png from Byron Knoll's public-domain Vector Playing Cards.

Run once (output is committed); re-run only if the art changes:
    py -3.12 -m pip install resvg-py==0.5.0 pillow==12.3.0
    py -3.12 scripts/build_cards.py

Source SVGs are downloaded from a pinned commit of the public-domain mirror and
cached in .dev/card-src/. Two cards are our own: the ace of spades (the deck's
has unclear provenance, so it is rebuilt from the ace of hearts with a spade)
and the two jester jokers (the deck's jokers are text only).
"""

from __future__ import annotations

import re
import sys
import urllib.request
from io import BytesIO
from pathlib import Path

import resvg_py
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / ".dev" / "card-src"
OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "frontend"
SOURCE = ("https://raw.githubusercontent.com/notpeter/Vector-Playing-Cards/"
          "861b338eb931d635c442b568071e3829e552f383/cards-svg/{name}.svg")
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
SUITS = ["C", "D", "H", "S"]
WIDTH = 320  # px; cards show at most ~110 CSS px wide, so this covers 3x screens

# The heart shape used by AH.svg (indices and centre), in a -8..8 x -9..9 box.
HEART = ("M 3.676,-9 C 0.433,-9 0,-5.523 0,-5.523 0,-5.523 -0.433,-9 -3.676,-9 "
         "-5.946,-9 -8,-7.441 -8,-4.5 -8,-0.614 -1.4208493,3.2938141 0,9 "
         "1.35201,3.2985969 8,-0.614 8,-4.5 8,-7.441 5.946,-9 3.676,-9 z")
# A spade drawn in the same box, so it drops into the same transforms.
SPADE = ("M 0,-9 C -1.5,-5.5 -8,-2.5 -8,1.6 -8,4.3 -6,5.8 -4,5.8 -2.3,5.8 -1,5 "
         "-0.4,3.8 -0.6,6.2 -1.8,8 -3.5,9 L 3.5,9 C 1.8,8 0.6,6.2 0.4,3.8 "
         "1,5 2.3,5.8 4,5.8 6,5.8 8,4.3 8,1.6 8,-2.5 1.5,-5.5 0,-9 z")

CARD_W, CARD_H = 167.0869141, 242.6669922


def fetch(name: str) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / f"{name}.svg"
    if not cached.exists():
        with urllib.request.urlopen(SOURCE.format(name=name), timeout=60) as res:
            cached.write_bytes(res.read())
    return cached.read_text(encoding="utf-8")


def strip_pt(svg: str) -> str:
    # The source gives width/height in pt, which resvg rejects; the viewBox keeps proportions.
    return re.sub(r'(width|height)="([\d.]+)pt"', r'\1="\2"', svg, count=2)


def ace_of_spades() -> str:
    svg = fetch("AH")
    if svg.count(HEART) != 3:
        raise SystemExit("AH.svg changed: expected the heart path 3 times")
    # Drop the heart's two shine highlights: they sit where the heart's lobes were.
    svg, shines = re.subn(r'<path[^>]*?id="path3762[^"]*"[^>]*/>', "", svg, flags=re.S)
    if shines != 2:
        raise SystemExit(f"AH.svg changed: expected 2 shine paths, found {shines}")
    return svg.replace(HEART, SPADE).replace("#df0000", "#000000")


def joker(cap: str, accent: str) -> str:
    """Jester joker: `cap` colours the two side points and the corner letters,
    `accent` the middle point."""
    letters = "".join(
        f'<text x="15" y="{30 + i * 21}" text-anchor="middle">{c}</text>' for i, c in enumerate("JOKER")
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_W}" height="{CARD_H}" viewBox="0 0 {CARD_W} {CARD_H}">
  <rect x="0.25" y="0.25" width="{CARD_W - 0.5}" height="{CARD_H - 0.5}" rx="6.9" fill="#fff" stroke="#000" stroke-width="0.5"/>
  <g font-family="Arial" font-size="19" font-weight="bold" fill="{cap}">{letters}</g>
  <g font-family="Arial" font-size="19" font-weight="bold" fill="{cap}" transform="rotate(180 {CARD_W / 2} {CARD_H / 2})">{letters}</g>
  <g transform="translate({CARD_W / 2 - 57.5} {CARD_H / 2 - 57.5}) scale(1.15)">
    <path d="M36 66 C40 42 46 24 50 9 C54 24 60 42 64 66 Z" fill="{accent}"/>
    <path d="M22 68 C14 52 4 44 7 29 C19 34 33 45 41 64 Z" fill="{cap}"/>
    <path d="M59 64 C67 45 81 34 93 29 C96 44 86 52 78 68 Z" fill="{cap}"/>
    <path d="M41 64 C38 50 36 40 36 34 C43 44 46 54 47 64 Z" fill="#e8b33a" opacity=".55"/>
    <rect x="18" y="64" width="64" height="13" rx="4" fill="#d4a640" stroke="#8a6a1f" stroke-width="1"/>
    <g fill="{cap}"><path d="M26 70.5l4-4 4 4-4 4z"/><path d="M42 70.5l4-4 4 4-4 4z"/><path d="M58 70.5l4-4 4 4-4 4z"/><path d="M74 70.5l3-3 3 3-3 3z"/></g>
    <g fill="#f0c75e" stroke="#8a6a1f" stroke-width="1.2"><circle cx="7" cy="29" r="5"/><circle cx="50" cy="9" r="5"/><circle cx="93" cy="29" r="5"/></g>
    <g fill="#8a6a1f"><circle cx="7" cy="31" r="1.2"/><circle cx="50" cy="11" r="1.2"/><circle cx="93" cy="31" r="1.2"/></g>
    <text x="50" y="94" text-anchor="middle" font-family="Georgia, serif" font-size="11" fill="#1a1a1a">★ ★ ★</text>
  </g>
</svg>"""


def render(svg: str, width: int = WIDTH) -> Image.Image:
    png = resvg_py.svg_to_bytes(svg_string=strip_pt(svg), width=width)
    return Image.open(BytesIO(bytes(png))).convert("RGBA")


def icon(ace: str, size: int) -> Image.Image:
    """App icon: the ace of hearts, slightly tilted, on green felt."""
    img = Image.new("RGBA", (size, size), "#1d5a37")
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for r in range(size // 2, 0, -max(1, size // 64)):  # soft lighter centre, like the felt
        alpha = int(70 * (1 - r / (size / 2)))
        ImageDraw.Draw(glow).ellipse([size / 2 - r, size / 2 - r, size / 2 + r, size / 2 + r], fill=(60, 150, 95, alpha))
    img = Image.alpha_composite(img, glow)
    card = render(ace, width=int(size * 0.5)).rotate(-8, expand=True, resample=Image.BICUBIC)
    img.alpha_composite(card, ((size - card.width) // 2, (size - card.height) // 2))
    return img.convert("RGB")


def main() -> None:
    cards_dir, icons_dir = OUT_DIR / "cards", OUT_DIR / "icons"
    cards_dir.mkdir(parents=True, exist_ok=True)
    icons_dir.mkdir(parents=True, exist_ok=True)
    cards: dict[str, str] = {}
    for rank in RANKS:
        for suit in SUITS:
            name = f"{rank}{suit}"
            cards[name] = ace_of_spades() if name == "AS" else fetch(name)
    cards["joker-red"] = joker("#c8102e", "#1a1a1a")
    cards["joker-black"] = joker("#1a1a1a", "#c8102e")
    for name, svg in cards.items():
        render(svg).save(cards_dir / f"{name}.webp", "WEBP", quality=85, method=6)
    for size in (192, 512):
        icon(cards["AH"], size).save(icons_dir / f"icon-{size}.png", optimize=True)
    total = sum(p.stat().st_size for p in cards_dir.glob("*.webp"))
    print(f"wrote {len(cards)} cards ({total // 1024} KB) and 2 icons under {OUT_DIR}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run it in a throwaway venv**

```bash
py -3.12 -m venv .dev/cards-venv
.dev/cards-venv/Scripts/python -m pip install -q resvg-py==0.5.0 pillow==12.3.0
.dev/cards-venv/Scripts/python scripts/build_cards.py
```

Expected (first run downloads 53 SVGs, ~1–2 min): `wrote 54 cards (~779 KB) and 2 icons under ...\frontend`.
Then `ls frontend/cards | wc -l` → `54`.

- [ ] **Step 4: Look at the output**

Build a contact sheet and open it with the image viewer (Read tool):

```bash
.dev/cards-venv/Scripts/python -c "
from PIL import Image
names=['AS','AH','joker-red','joker-black','KC','QD','10D','7S']
ims=[Image.open(f'frontend/cards/{n}.webp').convert('RGBA') for n in names]
w,h=ims[0].size; m=Image.new('RGBA',(w*4+50,h*2+30),(30,90,55,255))
[m.paste(im,(10+(i%4)*(w+10),10+(i//4)*(h+10)),im) for i,im in enumerate(ims)]
m.save('.dev/cards-check.png')"
```

Expected: A♠ is a clean black spade (no white smudge); the jokers show a centred jester cap with "JOKER" down the top-left and (rotated) bottom-right; the K♣ and Q♦ show full court figures. `frontend/icons/icon-192.png` is the tilted A♥ on green.

- [ ] **Step 5: Commit**

```bash
git add .gitignore scripts/build_cards.py frontend/cards frontend/icons
git commit -m "feat(frontend): card faces and app icons from the public-domain deck

Byron Knoll's Vector Playing Cards rendered to WebP, with our own ace
of spades and jester jokers.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Pure frontend modules (code, seats, orientation, storage)

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/js/code.js`, `frontend/js/seats.js`, `frontend/js/orientation.js`, `frontend/js/storage.js`
- Test: `frontend/tests/code.test.js`, `frontend/tests/seats.test.js`, `frontend/tests/orientation.test.js`, `frontend/tests/storage.test.js`

**Interfaces:**
- Produces:
  - `cleanCode(input: string) -> string` (uppercase letters only, max 4); `isCompleteCode(code: string) -> boolean`.
  - `seatPositions(players: Player[], meId: string) -> {player, position: 'left'|'top'|'right'}[]`; others in seat order clockwise starting with the player after you; throws for more than 4 players; `[]` if `meId` isn't seated.
  - `shouldRotate(width: number, height: number) -> boolean` (true when portrait).
  - `THEMES = ['classic','qendisje','kafeneio']`, `CARD_STYLES = ['traditional','vintage']`.
  - `createStore(storage = localStorage)` → `{ getName(), setName(name), getSettings() -> {theme, cardStyle}, setSettings(patch), getToken(code), setToken(code, token), clearToken(code), getCurrentRoom(), setCurrentRoom(code|null) }`. Everything lives under one key, `card-table`, as JSON; unreadable or invalid data falls back to defaults.

- [ ] **Step 1: Write the failing tests**

`frontend/package.json`:

```json
{
  "private": true,
  "type": "module",
  "scripts": { "test": "node --test" }
}
```

`frontend/tests/code.test.js`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { cleanCode, isCompleteCode } from '../js/code.js';

test('cleanCode uppercases and drops spaces and symbols', () => {
  assert.equal(cleanCode(' kq mz '), 'KQMZ');
  assert.equal(cleanCode('k-q.m z'), 'KQMZ');
});

test('cleanCode drops digits and caps the length at 4', () => {
  assert.equal(cleanCode('k7qm'), 'KQM');
  assert.equal(cleanCode('KQMZX'), 'KQMZ');
});

test('isCompleteCode needs exactly four letters', () => {
  assert.equal(isCompleteCode('KQMZ'), true);
  assert.equal(isCompleteCode('KQM'), false);
  assert.equal(isCompleteCode(''), false);
});
```

`frontend/tests/seats.test.js`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { seatPositions } from '../js/seats.js';

const players = (...ids) => ids.map((id) => ({ id, name: id }));
const layout = (ps, me) => seatPositions(ps, me).map(({ player, position }) => [player.id, position]);

test('2 players: the other sits across', () => {
  assert.deepEqual(layout(players('a', 'b'), 'b'), [['a', 'top']]);
});

test('3 players: the next player sits on your left', () => {
  assert.deepEqual(layout(players('a', 'b', 'c'), 'a'), [['b', 'left'], ['c', 'right']]);
});

test('4 players, seen from the third seat', () => {
  assert.deepEqual(layout(players('a', 'b', 'c', 'd'), 'c'), [['d', 'left'], ['a', 'top'], ['b', 'right']]);
});

test('not seated: nobody to place', () => {
  assert.deepEqual(layout(players('a', 'b'), 'zz'), []);
});

test('more than 4 players is not supported', () => {
  assert.throws(() => seatPositions(players('a', 'b', 'c', 'd', 'e'), 'a'));
});
```

`frontend/tests/orientation.test.js`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { shouldRotate } from '../js/orientation.js';

test('portrait phone gets rotated', () => assert.equal(shouldRotate(390, 844), true));
test('landscape phone does not', () => assert.equal(shouldRotate(844, 390), false));
test('square or desktop does not', () => {
  assert.equal(shouldRotate(800, 800), false);
  assert.equal(shouldRotate(1440, 900), false);
});
```

`frontend/tests/storage.test.js`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { createStore } from '../js/storage.js';

function memoryStorage(initial = {}) {
  const map = new Map(Object.entries(initial));
  return { getItem: (k) => (map.has(k) ? map.get(k) : null), setItem: (k, v) => map.set(k, String(v)) };
}

test('defaults when nothing is saved', () => {
  const store = createStore(memoryStorage());
  assert.equal(store.getName(), '');
  assert.deepEqual(store.getSettings(), { theme: 'classic', cardStyle: 'traditional' });
  assert.equal(store.getToken('ABCD'), null);
  assert.equal(store.getCurrentRoom(), null);
});

test('name and settings round-trip and survive a new store', () => {
  const storage = memoryStorage();
  const store = createStore(storage);
  store.setName('Yzeir');
  store.setSettings({ theme: 'kafeneio' });
  store.setSettings({ cardStyle: 'vintage' });
  const again = createStore(storage);
  assert.equal(again.getName(), 'Yzeir');
  assert.deepEqual(again.getSettings(), { theme: 'kafeneio', cardStyle: 'vintage' });
});

test('unknown theme or card style falls back to the default', () => {
  const store = createStore(memoryStorage({ 'card-table': JSON.stringify({ theme: 'neon', cardStyle: 'x' }) }));
  assert.deepEqual(store.getSettings(), { theme: 'classic', cardStyle: 'traditional' });
});

test('corrupted storage falls back to defaults', () => {
  const store = createStore(memoryStorage({ 'card-table': '{not json' }));
  assert.equal(store.getName(), '');
  store.setName('Ana');
  assert.equal(store.getName(), 'Ana');
});

test('tokens are kept per room and can be cleared', () => {
  const store = createStore(memoryStorage());
  store.setToken('ABCD', 't1');
  store.setToken('WXYZ', 't2');
  store.clearToken('ABCD');
  assert.equal(store.getToken('ABCD'), null);
  assert.equal(store.getToken('WXYZ'), 't2');
});

test('current room can be set and cleared', () => {
  const store = createStore(memoryStorage());
  store.setCurrentRoom('ABCD');
  assert.equal(store.getCurrentRoom(), 'ABCD');
  store.setCurrentRoom(null);
  assert.equal(store.getCurrentRoom(), null);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && node --test`
Expected: FAIL with `Cannot find module '.../js/code.js'` (and the same for the others).

- [ ] **Step 3: Implement**

`frontend/js/code.js`:

```js
export const CODE_LENGTH = 4;

/** Room codes are 4 letters; accept whatever was typed or pasted and keep just that. */
export function cleanCode(input) {
  return input.toUpperCase().replace(/[^A-Z]/g, '').slice(0, CODE_LENGTH);
}

export function isCompleteCode(code) {
  return /^[A-Z]{4}$/.test(code);
}
```

`frontend/js/seats.js`:

```js
// Spots for the other players around the table, in clockwise order starting on your left.
const SPOTS = { 1: [], 2: ['top'], 3: ['left', 'right'], 4: ['left', 'top', 'right'] };

/** Where everyone else sits, seen from `meId`. Players are in seat (join) order. */
export function seatPositions(players, meId) {
  const spots = SPOTS[players.length];
  if (!spots) throw new Error(`No table layout for ${players.length} players`);
  const me = players.findIndex((p) => p.id === meId);
  if (me < 0) return [];
  const others = [...players.slice(me + 1), ...players.slice(0, me)];
  return others.map((player, i) => ({ player, position: spots[i] }));
}
```

`frontend/js/orientation.js`:

```js
/** The table is a landscape layout; on a portrait viewport it is rotated 90° with CSS. */
export function shouldRotate(width, height) {
  return height > width;
}
```

`frontend/js/storage.js`:

```js
const KEY = 'card-table';
export const THEMES = ['classic', 'qendisje', 'kafeneio'];
export const CARD_STYLES = ['traditional', 'vintage'];

/** Everything the device remembers: name, settings, seat tokens per room, the room you're in. */
export function createStore(storage = globalThis.localStorage) {
  const read = () => {
    try {
      const data = JSON.parse(storage.getItem(KEY));
      return data && typeof data === 'object' ? data : {};
    } catch {
      return {};
    }
  };
  const update = (patch) => storage.setItem(KEY, JSON.stringify({ ...read(), ...patch }));

  return {
    getName: () => read().name ?? '',
    setName: (name) => update({ name }),
    getSettings() {
      const { theme, cardStyle } = read();
      return {
        theme: THEMES.includes(theme) ? theme : THEMES[0],
        cardStyle: CARD_STYLES.includes(cardStyle) ? cardStyle : CARD_STYLES[0],
      };
    },
    setSettings: (patch) => update(patch),
    getToken: (code) => read().tokens?.[code] ?? null,
    setToken: (code, token) => update({ tokens: { ...read().tokens, [code]: token } }),
    clearToken(code) {
      const tokens = { ...read().tokens };
      delete tokens[code];
      update({ tokens });
    },
    getCurrentRoom: () => read().room ?? null,
    setCurrentRoom: (code) => update({ room: code }),
  };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && node --test`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/js/code.js frontend/js/seats.js frontend/js/orientation.js frontend/js/storage.js frontend/tests
git commit -m "feat(frontend): code cleanup, seat placement, orientation and device storage

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Room connection with reconnect

**Files:**
- Create: `frontend/js/connection.js`
- Test: `frontend/tests/connection.test.js`

**Interfaces:**
- Consumes: `createStore` (Task 4).
- Produces: `class RoomConnection` with constructor options
  `{ code, store, urlFor(code, name, token) -> string, onWelcome(playerId), onState(stateMsg), onError(message), onReconnecting(boolean), onClosed(message), WebSocketImpl = globalThis.WebSocket, wait = setTimeout }`
  and methods `connect()`, `leave()` (sends `{"type":"leave"}`, forgets the seat, no reconnect), `close()` (stops without leaving or forgetting).
  Behaviour:
  - `welcome` → `store.setToken(code, token)`, `store.setCurrentRoom(code)`, `onWelcome(player_id)`.
  - `state` → `onState(msg)`; `error` → `onError(msg.message)`.
  - Close `4404` → final, forget seat, `onClosed('No table with that code')`.
  - Close `4410` → final, forget seat, `onClosed('That table has closed')`.
  - Close `4400` / `4409` → final, forget seat, `onClosed(reason from server)`.
  - Close `4000` → final, keep seat, `onClosed('This seat was opened somewhere else')`.
  - Any other close: if the socket never opened since `connect()` → final, keep seat, `onClosed("Can't reach the server")`. Otherwise → `onReconnecting(true)` and retry after 0.5, 1, 2, 4, 8, 8… s. A successful open → `onReconnecting(false)` and the backoff resets.

- [ ] **Step 1: Write the failing tests**

`frontend/tests/connection.test.js`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { RoomConnection } from '../js/connection.js';
import { createStore } from '../js/storage.js';

class FakeSocket {
  static OPEN = 1;
  static all = [];
  constructor(url) {
    this.url = url;
    this.sent = [];
    this.readyState = 0;
    FakeSocket.all.push(this);
  }
  send(data) { this.sent.push(JSON.parse(data)); }
  close() { this.readyState = 3; }
  // test helpers
  open() { this.readyState = 1; this.onopen?.(); }
  message(msg) { this.onmessage?.({ data: JSON.stringify(msg) }); }
  drop(code, reason = '') { this.readyState = 3; this.onclose?.({ code, reason }); }
}

function memoryStorage() {
  const map = new Map();
  return { getItem: (k) => (map.has(k) ? map.get(k) : null), setItem: (k, v) => map.set(k, String(v)) };
}

function setup() {
  FakeSocket.all = [];
  const store = createStore(memoryStorage());
  store.setName('Ana');
  const events = [];
  const delays = [];
  const conn = new RoomConnection({
    code: 'ABCD',
    store,
    urlFor: (code, name, token) => `ws://test/${code}?name=${name}&token=${token ?? ''}`,
    onWelcome: (id) => events.push(['welcome', id]),
    onState: (msg) => events.push(['state', msg.code]),
    onError: (m) => events.push(['error', m]),
    onReconnecting: (on) => events.push(['reconnecting', on]),
    onClosed: (m) => events.push(['closed', m]),
    WebSocketImpl: FakeSocket,
    wait: (fn, ms) => { delays.push(ms); fn(); },
  });
  conn.connect();
  return { conn, store, events, delays, socket: () => FakeSocket.all.at(-1) };
}

test('welcome saves the seat token and current room', () => {
  const { store, events, socket } = setup();
  socket().open();
  socket().message({ type: 'welcome', player_id: 'p1', token: 'tok', code: 'ABCD' });
  assert.equal(store.getToken('ABCD'), 'tok');
  assert.equal(store.getCurrentRoom(), 'ABCD');
  assert.deepEqual(events.at(-1), ['welcome', 'p1']);
});

test('state and error messages are passed on; garbage is ignored', () => {
  const { events, socket } = setup();
  socket().open();
  socket().onmessage({ data: '{not json' });
  socket().message({ type: 'state', code: 'ABCD' });
  socket().message({ type: 'error', message: 'Nope' });
  assert.deepEqual(events.slice(-2), [['state', 'ABCD'], ['error', 'Nope']]);
});

test('network drop reconnects with the saved token', () => {
  const { events, delays, socket } = setup();
  socket().open();
  socket().message({ type: 'welcome', player_id: 'p1', token: 'tok', code: 'ABCD' });
  socket().drop(1006);
  assert.equal(FakeSocket.all.length, 2);
  assert.match(socket().url, /token=tok/);
  assert.deepEqual(delays, [500]);
  assert.deepEqual(events.at(-1), ['reconnecting', true]);
  socket().open();
  assert.deepEqual(events.at(-1), ['reconnecting', false]);
});

test('reconnect backs off and resets after a successful open', () => {
  const { delays, socket } = setup();
  socket().open();
  socket().drop(1006); // retry 1 (never opens)
  socket().drop(1006); // retry 2
  socket().drop(1006); // retry 3
  socket().open();
  socket().drop(1006);
  assert.deepEqual(delays, [500, 1000, 2000, 500]);
});

test('room not found is final and forgets the seat', () => {
  const { store, events, socket } = setup();
  store.setToken('ABCD', 'old');
  store.setCurrentRoom('ABCD');
  socket().drop(4404, 'Room not found');
  assert.equal(FakeSocket.all.length, 1);
  assert.equal(store.getToken('ABCD'), null);
  assert.equal(store.getCurrentRoom(), null);
  assert.deepEqual(events.at(-1), ['closed', 'No table with that code']);
});

test("full room shows the server's reason", () => {
  const { events, socket } = setup();
  socket().drop(4409, 'This table is full');
  assert.deepEqual(events.at(-1), ['closed', 'This table is full']);
});

test('seat opened elsewhere stops without forgetting the seat', () => {
  const { store, events, socket } = setup();
  socket().open();
  socket().message({ type: 'welcome', player_id: 'p1', token: 'tok', code: 'ABCD' });
  socket().drop(4000, 'Opened on another connection');
  assert.equal(FakeSocket.all.length, 1);
  assert.equal(store.getToken('ABCD'), 'tok');
  assert.deepEqual(events.at(-1), ['closed', 'This seat was opened somewhere else']);
});

test('never connecting gives up with a message and keeps the token', () => {
  const { store, events, socket } = setup();
  store.setToken('ABCD', 'tok');
  socket().drop(1006);
  assert.equal(FakeSocket.all.length, 1);
  assert.equal(store.getToken('ABCD'), 'tok');
  assert.deepEqual(events.at(-1), ['closed', "Can't reach the server"]);
});

test('leave sends leave, forgets the seat and does not reconnect', () => {
  const { conn, store, socket } = setup();
  socket().open();
  socket().message({ type: 'welcome', player_id: 'p1', token: 'tok', code: 'ABCD' });
  const ws = socket();
  conn.leave();
  ws.drop(1000);
  assert.deepEqual(ws.sent, [{ type: 'leave' }]);
  assert.equal(FakeSocket.all.length, 1);
  assert.equal(store.getToken('ABCD'), null);
  assert.equal(store.getCurrentRoom(), null);
});

test('close stops quietly and keeps the seat', () => {
  const { conn, store, events, socket } = setup();
  socket().open();
  socket().message({ type: 'welcome', player_id: 'p1', token: 'tok', code: 'ABCD' });
  const before = events.length;
  const ws = socket();
  conn.close();
  ws.drop(1000);
  assert.equal(FakeSocket.all.length, 1);
  assert.equal(store.getToken('ABCD'), 'tok');
  assert.equal(events.length, before);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && node --test tests/connection.test.js`
Expected: FAIL with `Cannot find module '.../js/connection.js'`.

- [ ] **Step 3: Implement**

`frontend/js/connection.js`:

```js
// Server close codes that end the connection for good, with what to tell the player.
// null = use the reason the server sent. `forget` = the seat token is no good any more.
const FINAL = {
  4404: { message: 'No table with that code', forget: true },
  4410: { message: 'That table has closed', forget: true },
  4400: { message: null, forget: true },
  4409: { message: null, forget: true },
  4000: { message: 'This seat was opened somewhere else', forget: false },
};
const RETRY_MS = [500, 1000, 2000, 4000, 8000];

/** One player's WebSocket to a room: saves the seat token, reconnects after drops. */
export class RoomConnection {
  constructor({ code, store, urlFor, onWelcome, onState, onError, onReconnecting, onClosed,
    WebSocketImpl = globalThis.WebSocket, wait = setTimeout }) {
    Object.assign(this, { code, store, urlFor, onWelcome, onState, onError, onReconnecting, onClosed, WebSocketImpl, wait });
    this.stopped = false;
    this.attempt = 0;
    this.opened = false; // has any socket opened since connect()?
    this.ws = null;
  }

  connect() {
    const ws = new this.WebSocketImpl(this.urlFor(this.code, this.store.getName(), this.store.getToken(this.code)));
    this.ws = ws;
    ws.onopen = () => {
      this.opened = true;
      this.attempt = 0;
      this.onReconnecting(false);
    };
    ws.onmessage = (event) => this.handle(event.data);
    ws.onclose = (event) => {
      if (this.stopped || ws !== this.ws) return;
      const final = FINAL[event.code];
      if (final) return this.finish(final.message ?? (event.reason || 'Disconnected'), final.forget);
      if (!this.opened) return this.finish("Can't reach the server", false);
      this.onReconnecting(true);
      const delay = RETRY_MS[Math.min(this.attempt, RETRY_MS.length - 1)];
      this.attempt += 1;
      this.wait(() => { if (!this.stopped) this.connect(); }, delay);
    };
  }

  handle(data) {
    let msg;
    try {
      msg = JSON.parse(data);
    } catch {
      return;
    }
    if (msg.type === 'welcome') {
      this.store.setToken(this.code, msg.token);
      this.store.setCurrentRoom(this.code);
      this.onWelcome(msg.player_id);
    } else if (msg.type === 'state') {
      this.onState(msg);
    } else if (msg.type === 'error') {
      this.onError(msg.message);
    }
  }

  leave() {
    if (this.ws?.readyState === this.WebSocketImpl.OPEN) this.ws.send(JSON.stringify({ type: 'leave' }));
    this.close();
    this.forget();
  }

  close() {
    this.stopped = true;
    this.ws?.close();
  }

  finish(message, forget) {
    this.stopped = true;
    if (forget) this.forget();
    this.onClosed(message);
  }

  forget() {
    this.store.clearToken(this.code);
    this.store.setCurrentRoom(null);
  }
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && node --test`
Expected: all tests pass (Task 4's and these).

Check the backoff test by hand against the code: open → drop (opened) → retry with 500 → that socket drops without opening, but `this.opened` stays true from the first socket, so it retries with 1000, then 2000; the next socket opens (attempt resets to 0) and the following drop retries with 500. That gives `[500, 1000, 2000, 500]`.

- [ ] **Step 5: Commit**

```bash
git add frontend/js/connection.js frontend/tests/connection.test.js
git commit -m "feat(frontend): room connection with seat tokens and reconnect

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Dev stack, PWA shell, styling and the main screen

**Files:**
- Create: `scripts/serve_frontend.py`, `scripts/dev_up.py`, `scripts/dev_down.py`
- Create: `frontend/index.html`, `frontend/styles.css`, `frontend/themes.css`, `frontend/config.js`, `frontend/manifest.webmanifest`, `frontend/service-worker.js`, `frontend/_headers`
- Create: `frontend/js/api.js`, `frontend/js/clipboard.js`, `frontend/js/ui.js`, `frontend/js/sheets.js`, `frontend/js/main-view.js`, `frontend/js/app.js` (interim; Task 7 replaces it)

**Interfaces:**
- Consumes: `/games`, `POST /rooms` (Task 2); `cleanCode`, `isCompleteCode`, `createStore` (Task 4); card images and icons (Task 3).
- Produces:
  - `api.js`: `fetchGames() -> Promise<Game[]>`, `createRoom(game: string, players: number) -> Promise<string code>`, `socketUrl(code, name, token) -> string`. Network failure → `Error("Can't reach the server")`; HTTP error → `Error(detail)`.
  - `clipboard.js`: `copyText(text) -> Promise<boolean>`, `canReadClipboard() -> boolean`.
  - `ui.js`: `showView('main'|'lobby'|'table')`, `toast(message)`, `setReconnecting(boolean)`.
  - `sheets.js`: `openSheet(id)`, `closeSheets()`.
  - `main-view.js`: `initMain({ store, enterRoom(code), applySettings(settings) })`.
  - DOM ids used by Task 7: `view-lobby`, `view-table`, `btn-copy`, `btn-lobby-leave`, `btn-table-menu`, `table-menu`, `btn-table-leave`; classes `.lobby-game`, `.lobby-code`, `.lobby-count`, `.lobby-seats`, `.seats`, `.seat-me`.
  - Body classes: `theme-{classic|qendisje|kafeneio} cards-{traditional|vintage}`.
  - Table view rotation: `#view-table.rotated`.

- [ ] **Step 1: Dev scripts**

`scripts/serve_frontend.py`:

```python
"""Static server for frontend/ with explicit MIME types (Windows' registry can map
.js to text/plain, which breaks ES modules, and Python doesn't know .webp) and no
caching, so edits show up on reload.

Usage: py -3.12 scripts/serve_frontend.py [port]   (dev_up.py runs this for you)
"""

import functools
import http.server
import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html",
        ".js": "text/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".webmanifest": "application/manifest+json",
        ".webp": "image/webp",
        ".png": "image/png",
        ".svg": "image/svg+xml",
    }

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5520
    handler = functools.partial(Handler, directory=str(FRONTEND_DIR))
    with http.server.ThreadingHTTPServer(("0.0.0.0", port), handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
```

`scripts/dev_up.py`:

```python
"""Start the local dev stack: backend on :8020, frontend on :5520.

Usage from the repo root:
    py -3.12 scripts/dev_up.py      # start, open the browser
    py -3.12 scripts/dev_down.py    # stop

Both listen on all interfaces, so a phone on the same Wi-Fi can open the LAN URL
printed at the end (allow Python through Windows Firewall on private networks).
Pids go to .dev/pids.json, logs to .dev/backend.log and .dev/frontend.log.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
DEV_STATE_DIR = REPO_ROOT / ".dev"
PIDS_PATH = DEV_STATE_DIR / "pids.json"
BACKEND_PORT = 8020
FRONTEND_PORT = 5520


def venv_python() -> str:
    for candidate in (BACKEND_DIR / ".venv" / "Scripts" / "python.exe", BACKEND_DIR / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    raise SystemExit(
        "No backend venv. Create it with:\n"
        "  cd backend && py -3.12 -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt"
    )


def lan_ip() -> str | None:
    # Connecting a UDP socket sends nothing; it just picks the outgoing interface.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def start(cmd: list[str], cwd: Path, log_name: str) -> int:
    log = (DEV_STATE_DIR / log_name).open("w")
    return subprocess.Popen(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT).pid


def wait_for(url: str, what: str) -> None:
    for _ in range(40):
        try:
            urllib.request.urlopen(url, timeout=1).read()
            return
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(0.5)
    raise SystemExit(f"{what} did not start; see .dev/ logs, then run scripts/dev_down.py")


def main() -> int:
    if PIDS_PATH.exists():
        print("Dev stack already running (.dev/pids.json exists). Run scripts/dev_down.py first.")
        return 1
    DEV_STATE_DIR.mkdir(exist_ok=True)
    backend = start(
        [venv_python(), "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(BACKEND_PORT)],
        BACKEND_DIR,
        "backend.log",
    )
    frontend = start(
        [sys.executable, str(REPO_ROOT / "scripts" / "serve_frontend.py"), str(FRONTEND_PORT)],
        REPO_ROOT,
        "frontend.log",
    )
    PIDS_PATH.write_text(json.dumps({"backend_pid": backend, "frontend_pid": frontend}))
    wait_for(f"http://127.0.0.1:{BACKEND_PORT}/games", "Backend")
    wait_for(f"http://127.0.0.1:{FRONTEND_PORT}/", "Frontend")

    local = f"http://localhost:{FRONTEND_PORT}"
    print(f"Card Table is up:\n  This PC:            {local}")
    ip = lan_ip()
    if ip:
        print(f"  Phone (same Wi-Fi): http://{ip}:{FRONTEND_PORT}")
    webbrowser.open(local)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`scripts/dev_down.py`:

```python
"""Stop the dev stack started by dev_up.py."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

PIDS_PATH = Path(__file__).resolve().parent.parent / ".dev" / "pids.json"


def kill(pid: int, label: str) -> None:
    if os.name == "nt":
        r = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, text=True)
        print(f"  {label} (pid {pid}): {'stopped' if r.returncode == 0 else 'already gone'}")
    else:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"  {label} (pid {pid}): stopped")
        except ProcessLookupError:
            print(f"  {label} (pid {pid}): already gone")


def main() -> int:
    if not PIDS_PATH.exists():
        print("Nothing running (no .dev/pids.json).")
        return 0
    pids = json.loads(PIDS_PATH.read_text())
    kill(pids["backend_pid"], "backend")
    kill(pids["frontend_pid"], "frontend")
    PIDS_PATH.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: PWA shell files**

`frontend/config.js`:

```js
// Overwritten at deploy time (Cloudflare Pages). Locally the backend runs on port 8020
// of whatever host served this page, so a phone on the Wi-Fi needs no setup.
window.BACKEND_URL = window.BACKEND_URL || `${location.protocol}//${location.hostname}:8020`;
```

`frontend/manifest.webmanifest`:

```json
{
  "name": "Card Table",
  "short_name": "Card Table",
  "description": "Card games with friends",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#123d25",
  "theme_color": "#123d25",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
```

`frontend/service-worker.js`:

```js
// Minimal service worker so the app can be installed. No caching.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
```

`frontend/_headers` (used by Cloudflare Pages later; add the deployed backend host to `connect-src` then):

```
/*
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' http://localhost:8020 ws://localhost:8020; frame-ancestors 'none'; object-src 'none'; base-uri 'self'

/*.html
  Cache-Control: no-cache

/cards/*
  Cache-Control: public, max-age=604800
```

- [ ] **Step 3: Markup**

`frontend/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="theme-color" content="#123d25" />
  <link rel="manifest" href="/manifest.webmanifest" />
  <link rel="apple-touch-icon" href="/icons/icon-192.png" />
  <link rel="stylesheet" href="/styles.css" />
  <link rel="stylesheet" href="/themes.css" />
  <title>Card Table</title>
  <script src="/config.js"></script>
</head>
<body class="theme-classic cards-traditional">
  <main id="view-main" class="view felt">
    <h1 class="title">Card Table</h1>
    <label class="name-field">
      <span class="label">Your name</span>
      <input id="name-input" maxlength="20" autocomplete="nickname" placeholder="Your name" />
    </label>
    <div class="menu-cards">
      <button class="menu-card tilt-left" id="btn-new" type="button">
        <span class="card-face"><img src="/cards/AH.webp" alt="" /></span><span class="tag">New table</span>
      </button>
      <button class="menu-card tilt-right" id="btn-join" type="button">
        <span class="card-face"><img src="/cards/AC.webp" alt="" /></span><span class="tag">Join</span>
      </button>
      <button class="menu-card tilt-slight" id="btn-settings" type="button">
        <span class="card-face"><img src="/cards/joker-red.webp" alt="" /></span><span class="tag">Settings</span>
      </button>
    </div>
  </main>

  <section id="view-lobby" class="view felt" hidden>
    <p class="lobby-game"></p>
    <div class="lobby-code-row">
      <span class="lobby-code"></span>
      <button id="btn-copy" class="small-btn" type="button">Copy</button>
    </div>
    <p class="lobby-hint">Share this code. The game starts when every seat is taken.</p>
    <p class="lobby-count"></p>
    <ul class="lobby-seats"></ul>
    <button id="btn-lobby-leave" class="btn ghost" type="button">Leave</button>
  </section>

  <section id="view-table" class="view" hidden>
    <div class="table-frame">
      <div class="table">
        <div class="surface">
          <div class="cloth"></div><div class="stitch"></div><div class="runner"></div>
          <div class="prop cup"></div><div class="prop glass"></div>
        </div>
        <button id="btn-table-menu" class="table-menu-btn" type="button" aria-label="Menu">☰</button>
        <div id="table-menu" class="table-menu" hidden>
          <button id="btn-table-leave" type="button">Leave table</button>
        </div>
        <div class="seats"></div>
        <div class="play-area"></div>
        <div class="hand-area"><span class="hand-hint">Your hand</span></div>
        <div class="seat seat-me"></div>
      </div>
    </div>
  </section>

  <div id="sheet-backdrop" class="sheet-backdrop" hidden></div>

  <section id="sheet-new" class="sheet" hidden>
    <h2 class="sheet-title">Pick a game</h2>
    <div class="sheet-step" data-step="game"><div class="choice-list" id="game-list"></div></div>
    <div class="sheet-step" data-step="players" hidden>
      <p class="sheet-sub" id="players-game"></p>
      <div class="choice-row" id="player-counts"></div>
    </div>
  </section>

  <section id="sheet-join" class="sheet" hidden>
    <h2 class="sheet-title">Join a table</h2>
    <form id="join-form" class="join-form">
      <input id="join-code" class="code-input" maxlength="8" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="CODE" />
      <button id="btn-paste" class="small-btn" type="button" hidden>Paste</button>
      <button class="btn primary" type="submit">Join</button>
    </form>
  </section>

  <section id="sheet-settings" class="sheet" hidden>
    <h2 class="sheet-title">Settings</h2>
    <p class="sheet-sub">Table</p>
    <div class="theme-swatches" id="theme-swatches">
      <button type="button" data-theme="classic" class="swatch swatch-classic"><span>Classic</span></button>
      <button type="button" data-theme="qendisje" class="swatch swatch-qendisje"><span>Qëndisje</span></button>
      <button type="button" data-theme="kafeneio" class="swatch swatch-kafeneio"><span>Kafeneio</span></button>
    </div>
    <p class="sheet-sub">Cards</p>
    <div class="segmented" id="card-styles">
      <button type="button" data-cards="traditional">Traditional</button>
      <button type="button" data-cards="vintage">Vintage</button>
    </div>
  </section>

  <div id="banner" class="banner" hidden>Reconnecting…</div>
  <div id="toast" class="toast" role="status" hidden></div>
  <script type="module" src="/js/app.js"></script>
</body>
</html>
```

- [ ] **Step 4: Styles**

`frontend/styles.css`:

```css
* { box-sizing: border-box; margin: 0; padding: 0; }
[hidden] { display: none !important; }
html, body { height: 100%; }
body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; background: #123d25; color: #f3e6c4; overflow: hidden; -webkit-tap-highlight-color: transparent; }
button { font: inherit; color: inherit; background: none; border: none; cursor: pointer; }
input { font: inherit; }

/* ---------- shared ---------- */
.felt { background: radial-gradient(ellipse at 50% 30%, #2f7d4f 0%, #1d5a37 55%, #123d25 100%); }
.view { position: fixed; inset: 0; overflow-y: auto; }
.label { display: block; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; margin: 0 0 6px 2px; opacity: .75; }
.btn { display: block; width: 100%; padding: 13px; border-radius: 12px; font-size: 15px; font-weight: 700; text-align: center; }
.btn.primary { background: linear-gradient(#f3d27a, #d4a640); color: #3a2a08; box-shadow: 0 3px 6px rgba(0,0,0,.35); }
.btn.ghost { border: 1.5px solid rgba(243,230,196,.6); }
.small-btn { padding: 6px 12px; border-radius: 8px; font-size: 13px; font-weight: 700; border: 1.5px solid rgba(243,230,196,.6); }
.card-face { position: relative; display: block; aspect-ratio: 320 / 466; }
.card-face img { display: block; width: 100%; height: 100%; border-radius: 6% / 4.2%; box-shadow: 0 4px 12px rgba(0,0,0,.45); }

/* ---------- main ---------- */
#view-main { display: flex; flex-direction: column; align-items: center; gap: 22px; padding: max(44px, env(safe-area-inset-top)) 26px 30px; }
.title { font-family: Georgia, serif; font-size: 30px; font-weight: 700; color: #f0c75e; }
.name-field { width: 100%; max-width: 340px; }
.name-field input { width: 100%; padding: 11px 13px; border-radius: 10px; font-size: 16px; background: rgba(0,0,0,.3); color: #f3e6c4; border: 1px solid rgba(243,230,196,.35); }
.menu-cards { display: grid; grid-template-columns: auto auto; justify-content: center; gap: 18px 34px; }
.menu-card { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.menu-card .card-face { width: 96px; transition: translate .15s; }
.menu-card:active .card-face { translate: 0 -4px; }
.menu-card .tag { font-family: Georgia, serif; font-size: 15px; font-weight: 700; color: #f0c75e; text-shadow: 0 1px 2px rgba(0,0,0,.5); }
.tilt-left .card-face { rotate: -7deg; }
.tilt-right .card-face { rotate: 6deg; }
.tilt-slight .card-face { rotate: -2deg; }
#btn-settings { grid-column: 1 / -1; }

/* ---------- sheets ---------- */
.sheet-backdrop { position: fixed; inset: 0; z-index: 20; background: rgba(0,0,0,.45); }
.sheet { position: fixed; left: 0; right: 0; bottom: 0; z-index: 21; max-width: 480px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px;
         padding: 22px 22px max(26px, env(safe-area-inset-bottom)); background: #fffdf7; color: #1a1a1a; border-radius: 18px 18px 0 0; box-shadow: 0 -6px 24px rgba(0,0,0,.35); }
.sheet-title { font-family: Georgia, serif; font-size: 22px; }
.sheet-sub { font-size: 13px; color: #6b5f4a; }
.sheet .small-btn { border-color: #ddd2b8; }
.choice-list { display: flex; flex-direction: column; gap: 10px; }
.choice-row { display: flex; gap: 10px; }
.choice-list button, .choice-row button { padding: 14px; border-radius: 12px; border: 1.5px solid #ddd2b8; background: #f6f1e4; font-size: 16px; font-weight: 700; }
.choice-row button { flex: 1; font-size: 20px; }
.join-form { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.join-form .btn { flex-basis: 100%; }
.code-input { flex: 1; min-width: 0; padding: 12px; border-radius: 10px; border: 1.5px solid #ddd2b8; background: #f6f1e4; font-size: 24px; font-weight: 700; letter-spacing: 6px; text-align: center; text-transform: uppercase; }
.theme-swatches { display: flex; gap: 10px; }
.swatch { position: relative; flex: 1; height: 64px; border-radius: 10px; border: 3px solid transparent; box-shadow: 0 1px 3px rgba(0,0,0,.3); }
.swatch span { position: absolute; left: 6px; bottom: 4px; padding: 1px 6px; border-radius: 999px; background: rgba(0,0,0,.55); color: #fff; font-size: 11px; font-weight: 700; }
.swatch.on { border-color: #d4a640; }
.segmented { display: flex; }
.segmented button { flex: 1; padding: 10px; border: 1.5px solid #ddd2b8; background: #fffdf7; font-weight: 700; }
.segmented button:first-child { border-radius: 10px 0 0 10px; }
.segmented button:last-child { border-radius: 0 10px 10px 0; }
.segmented button.on { background: #1a1a1a; color: #f6eedd; border-color: #1a1a1a; }

/* ---------- lobby ---------- */
#view-lobby { display: flex; flex-direction: column; align-items: center; gap: 14px; padding: max(44px, env(safe-area-inset-top)) 26px 30px; text-align: center; }
.lobby-game { font-family: Georgia, serif; font-size: 22px; color: #f0c75e; }
.lobby-code-row { display: flex; align-items: center; gap: 12px; }
.lobby-code { font-family: Georgia, serif; font-size: 52px; font-weight: 700; letter-spacing: 8px; user-select: all; -webkit-user-select: all; }
.lobby-hint { max-width: 280px; font-size: 13px; opacity: .8; }
.lobby-count { font-weight: 700; }
.lobby-seats { display: flex; flex-direction: column; gap: 8px; width: 100%; max-width: 320px; list-style: none; }
.lobby-seats li { padding: 11px 14px; border-radius: 10px; background: rgba(0,0,0,.3); text-align: left; }
.lobby-seats li.taken::after { content: " ✓"; color: #7fd18b; }
.lobby-seats li.offline { opacity: .55; }
.lobby-seats li.open { background: none; border: 1px dashed rgba(243,230,196,.4); font-style: italic; opacity: .6; }
#view-lobby .btn { max-width: 320px; margin-top: auto; }

/* ---------- table ---------- */
#view-table { overflow: hidden; background: #000; }
.table-frame { position: absolute; inset: 0; }
/* Portrait phone: lay the landscape table on its side so it reads with the phone turned. */
#view-table.rotated .table-frame { inset: auto; top: 0; left: 0; width: 100vh; height: 100vw; width: 100dvh; height: 100dvw;
                                   transform-origin: top left; transform: rotate(90deg) translateY(-100%); }
.table { position: absolute; inset: 0; overflow: hidden; }
.surface { position: absolute; inset: 0; }
.surface > * { position: absolute; display: none; } /* each theme turns on the layers it uses */
.table-menu-btn { position: absolute; top: 12px; left: 14px; z-index: 5; width: 34px; height: 34px; border-radius: 9px; background: var(--plate-bg); color: var(--plate-fg); font-size: 17px; }
.table-menu { position: absolute; top: 52px; left: 14px; z-index: 6; overflow: hidden; border-radius: 10px; background: #fffdf7; box-shadow: 0 6px 18px rgba(0,0,0,.4); }
.table-menu button { display: block; padding: 12px 18px; color: #1a1a1a; font-weight: 700; }
.seat { position: absolute; z-index: 4; display: flex; flex-direction: column; align-items: center; gap: 5px; }
.seat-top { top: 10px; left: 50%; transform: translateX(-50%); }
.seat-left { left: 22px; top: 34%; }
.seat-right { right: 22px; top: 34%; }
.seat-me { left: 16px; bottom: 16px; }
.plate { display: flex; align-items: center; gap: 7px; padding: 4px 11px; border-radius: 999px; font-size: 13px; white-space: nowrap; background: var(--plate-bg); color: var(--plate-fg); box-shadow: 0 1px 3px rgba(0,0,0,.35); }
.plate .count { font-weight: 700; color: var(--plate-count); }
.plate .dot { width: 7px; height: 7px; border-radius: 50%; background: #4ade80; }
.plate.offline { opacity: .6; }
.plate.offline .dot { background: #9ca3af; }
.backs { display: flex; }
.card-back { width: 22px; height: 32px; margin-left: -14px; border-radius: 3px; background: var(--card-back); border: 1.5px solid var(--card-back-edge); box-shadow: 0 1px 2px rgba(0,0,0,.5); }
.card-back:first-child { margin-left: 0; }
.play-area { position: absolute; left: 50%; top: 42%; z-index: 3; width: 34%; height: 30%; transform: translate(-50%, -50%); border-radius: 16px; border: 1.5px dashed var(--zone-line); }
.hand-area { position: absolute; left: 22%; right: 22%; bottom: 12px; z-index: 3; height: 26%; display: grid; place-items: center; border-radius: 14px; border: 1.5px dashed var(--zone-line); }
.hand-hint { font-size: 12px; color: var(--zone-line); }

/* ---------- toast & banner ---------- */
.toast { position: fixed; left: 50%; bottom: max(24px, env(safe-area-inset-bottom)); z-index: 40; max-width: 90vw; transform: translateX(-50%);
         padding: 11px 16px; border-radius: 12px; background: #1a1a1a; color: #fff; font-size: 14px; box-shadow: 0 6px 18px rgba(0,0,0,.4); }
.banner { position: fixed; top: max(8px, env(safe-area-inset-top)); left: 50%; z-index: 40; transform: translateX(-50%);
          padding: 6px 14px; border-radius: 999px; background: #b45309; color: #fff; font-size: 13px; font-weight: 700; }
```

`frontend/themes.css`:

```css
/* Table themes set the variables the table uses and switch on their surface layers
   (.cloth, .stitch, .runner, .prop). Card faces don't depend on the theme. */

.theme-classic {
  --plate-bg: rgba(0,0,0,.45); --plate-fg: #f3e6c4; --plate-count: #f0c75e;
  --card-back: repeating-linear-gradient(45deg, #8e1b22 0 4px, #a8262e 4px 8px); --card-back-edge: #fff;
  --zone-line: rgba(243,230,196,.35);
}
.theme-classic .surface { background: radial-gradient(ellipse at 50% 45%, #2f7d4f 0%, #1d5a37 55%, #123d25 100%); }
.theme-classic .surface::before { content: ""; position: absolute; inset: 0; box-shadow: inset 0 0 0 10px #5b3a1e, inset 0 0 0 13px #8a5a2f, inset 0 0 40px rgba(0,0,0,.5); }

/* Albanian: embroidered linen over walnut */
.theme-qendisje {
  --plate-bg: #1d1a17; --plate-fg: #f6efe0; --plate-count: #e8b33a;
  --card-back: repeating-linear-gradient(45deg, transparent 0 3px, rgba(0,0,0,.65) 3px 4px), repeating-linear-gradient(-45deg, transparent 0 3px, rgba(0,0,0,.65) 3px 4px), #b3121f;
  --card-back-edge: #fbf7ec;
  --zone-line: rgba(90,60,30,.45);
}
.theme-qendisje .surface { background: repeating-linear-gradient(92deg, rgba(0,0,0,.07) 0 2px, transparent 2px 9px), repeating-linear-gradient(88deg, rgba(255,255,255,.03) 0 1px, transparent 1px 23px), linear-gradient(180deg, #6b3d22, #4a2814); }
.theme-qendisje .cloth { display: block; inset: 10px 12px; border-radius: 6px; background-color: #f1ebdc; box-shadow: 0 4px 14px rgba(0,0,0,.5);
  background-image: repeating-linear-gradient(0deg, rgba(0,0,0,.035) 0 1px, transparent 1px 3px), repeating-linear-gradient(90deg, rgba(0,0,0,.03) 0 1px, transparent 1px 3px); }
.theme-qendisje .stitch { display: block; inset: 20px 22px;
  --st: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='14' height='14'><path d='M7 1.5L12.5 7L7 12.5L1.5 7Z' fill='none' stroke='%23b3121f' stroke-width='1.6'/><path d='M7 4.5L9.5 7L7 9.5L4.5 7Z' fill='%23b3121f'/></svg>");
  background-image: var(--st), var(--st), var(--st), var(--st); background-repeat: repeat-x, repeat-x, repeat-y, repeat-y;
  background-position: left top, left bottom, left top, right top; background-size: 12px 12px; }
.theme-qendisje .cup { display: block; right: 78px; top: 34px; }

/* Greek: kafeneio marble with a checked runner */
.theme-kafeneio {
  --plate-bg: #14305e; --plate-fg: #fff; --plate-count: #9cc3ff;
  --card-back: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16'><path d='M0 14.5H16M13 14.5V1.5H2.5V11.5H9.5V5H6V8.5' fill='none' stroke='%23161616' stroke-width='1.8'/></svg>") 0 0 / 8px 8px, #c4622d;
  --card-back-edge: #fbf7ec;
  --zone-line: rgba(20,48,94,.4);
}
.theme-kafeneio .surface { background: linear-gradient(115deg, transparent 38%, rgba(130,130,145,.28) 39.5%, transparent 41%), linear-gradient(62deg, transparent 70%, rgba(130,130,145,.22) 71%, transparent 72.5%), linear-gradient(150deg, transparent 15%, rgba(130,130,145,.18) 16%, transparent 17.5%), radial-gradient(ellipse at 30% 25%, #ffffff, #e4e4e8 80%); }
.theme-kafeneio .runner { display: block; left: 0; right: 0; top: 22%; height: 44%; border-top: 6px solid #fff; border-bottom: 6px solid #fff; box-shadow: 0 2px 8px rgba(0,0,0,.25);
  background: linear-gradient(90deg, rgba(31,78,156,.5) 50%, transparent 50%) 0 0 / 12px 12px, linear-gradient(rgba(31,78,156,.5) 50%, transparent 50%) 0 0 / 12px 12px, #fbfbfd; }
.theme-kafeneio .cup { display: block; right: 80px; bottom: 30%; }
.theme-kafeneio .glass { display: block; right: 66px; top: 16px; }

/* Props, drawn from above */
.prop.cup { width: 46px; height: 46px; border-radius: 50%; background: #fbfbfb; box-shadow: 0 3px 8px rgba(0,0,0,.35), inset 0 0 0 1px #ddd; }
.prop.cup::before { content: ""; position: absolute; inset: 9px; border-radius: 50%; background: radial-gradient(circle at 45% 40%, #7a4a26 0 30%, #3b2010 70%); box-shadow: 0 0 0 3px #fff, 0 0 0 4px #d6d6d6; }
.prop.cup::after { content: ""; position: absolute; right: -1px; top: 19px; width: 9px; height: 8px; border-radius: 4px; background: #fff; box-shadow: 0 0 0 1px #d6d6d6; }
.prop.glass { width: 22px; height: 22px; border-radius: 50%; background: radial-gradient(circle at 35% 35%, rgba(255,255,255,.95), rgba(235,240,245,.65) 60%, rgba(200,210,220,.7)); box-shadow: 0 2px 5px rgba(0,0,0,.35); }

/* Settings swatches */
.swatch-classic { background: radial-gradient(#2f7d4f, #123d25); }
.swatch-qendisje { background: #f1ebdc; box-shadow: inset 0 0 0 4px #b3121f, 0 1px 3px rgba(0,0,0,.3); }
.swatch-kafeneio { background: linear-gradient(90deg, rgba(31,78,156,.5) 50%, transparent 50%) 0 0 / 8px 8px, linear-gradient(rgba(31,78,156,.5) 50%, transparent 50%) 0 0 / 8px 8px, #fff; }

/* Card style: Vintage ages the same images */
.cards-vintage .card-face img { background: #f3e8cf; filter: sepia(.38) saturate(.85) contrast(.96) brightness(.98); }
.cards-vintage .card-face::after { content: ""; position: absolute; inset: 0; border-radius: 6% / 4.2%; pointer-events: none;
  background: radial-gradient(ellipse at 50% 50%, transparent 55%, rgba(120,80,30,.22) 100%); mix-blend-mode: multiply; }
```

- [ ] **Step 5: Small UI modules**

`frontend/js/api.js`:

```js
const base = () => window.BACKEND_URL;

async function request(path, options) {
  let res;
  try {
    res = await fetch(`${base()}${path}`, options);
  } catch {
    throw new Error("Can't reach the server");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Something went wrong');
  return data;
}

export const fetchGames = () => request('/games');

export async function createRoom(game, players) {
  const { code } = await request('/rooms', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ game, players }),
  });
  return code;
}

export function socketUrl(code, name, token) {
  const url = new URL(`${base()}/rooms/${code}/ws`);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.searchParams.set('name', name);
  if (token) url.searchParams.set('token', token);
  return url.toString();
}
```

`frontend/js/clipboard.js`:

```js
/** Copy text; falls back to execCommand on plain-http pages (a phone on the LAN). */
export async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // fall through to the old way
    }
  }
  const area = document.createElement('textarea');
  area.value = text;
  area.setAttribute('readonly', '');
  area.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
  document.body.append(area);
  area.select();
  area.setSelectionRange(0, text.length);
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch {
    ok = false;
  }
  area.remove();
  return ok;
}

/** Reading the clipboard needs a secure context (https or localhost). */
export function canReadClipboard() {
  return Boolean(navigator.clipboard?.readText && window.isSecureContext);
}
```

`frontend/js/ui.js`:

```js
const VIEWS = ['main', 'lobby', 'table'];
let toastTimer;

export function showView(name) {
  for (const view of VIEWS) document.getElementById(`view-${view}`).hidden = view !== name;
}

export function toast(message) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3500);
}

export function setReconnecting(on) {
  document.getElementById('banner').hidden = !on;
}
```

`frontend/js/sheets.js`:

```js
export function openSheet(id) {
  closeSheets();
  document.getElementById(id).hidden = false;
  document.getElementById('sheet-backdrop').hidden = false;
}

export function closeSheets() {
  document.querySelectorAll('.sheet').forEach((sheet) => { sheet.hidden = true; });
  document.getElementById('sheet-backdrop').hidden = true;
}
```

`frontend/js/main-view.js`:

```js
import { fetchGames, createRoom } from './api.js';
import { canReadClipboard } from './clipboard.js';
import { cleanCode, isCompleteCode } from './code.js';
import { openSheet, closeSheets } from './sheets.js';
import { toast } from './ui.js';

const MAX_NAME = 20;

export function initMain({ store, enterRoom, applySettings }) {
  const nameInput = document.getElementById('name-input');
  nameInput.value = store.getName();
  nameInput.addEventListener('input', () => store.setName(nameInput.value.trim()));

  const hasName = () => {
    const name = nameInput.value.trim();
    if (name.length >= 1 && name.length <= MAX_NAME) return true;
    toast('Enter your name first');
    nameInput.focus();
    return false;
  };

  // New table: pick game, then player count, then the room is created.
  document.getElementById('btn-new').addEventListener('click', async () => {
    if (!hasName()) return;
    showStep('game');
    openSheet('sheet-new');
    const list = document.getElementById('game-list');
    list.replaceChildren();
    try {
      const games = await fetchGames();
      list.replaceChildren(...games.map((game) => choice(game.name, () => pickPlayers(game))));
    } catch (err) {
      closeSheets();
      toast(err.message);
    }
  });

  function pickPlayers(game) {
    showStep('players');
    document.getElementById('players-game').textContent = `${game.name}: how many players?`;
    const counts = [];
    for (let n = game.min_players; n <= game.max_players; n++) counts.push(choice(String(n), () => create(game, n)));
    document.getElementById('player-counts').replaceChildren(...counts);
  }

  async function create(game, players) {
    try {
      const code = await createRoom(game.id, players);
      closeSheets();
      enterRoom(code);
    } catch (err) {
      toast(err.message);
    }
  }

  function showStep(step) {
    document.querySelectorAll('#sheet-new .sheet-step').forEach((el) => { el.hidden = el.dataset.step !== step; });
    document.querySelector('#sheet-new .sheet-title').textContent = step === 'game' ? 'Pick a game' : 'Players';
  }

  // Join: one code box, optional Paste button.
  const codeInput = document.getElementById('join-code');
  document.getElementById('btn-join').addEventListener('click', () => {
    if (!hasName()) return;
    codeInput.value = '';
    document.getElementById('btn-paste').hidden = !canReadClipboard();
    openSheet('sheet-join');
    codeInput.focus();
  });
  codeInput.addEventListener('input', () => { codeInput.value = cleanCode(codeInput.value); });
  document.getElementById('btn-paste').addEventListener('click', async () => {
    try {
      codeInput.value = cleanCode(await navigator.clipboard.readText());
    } catch {
      toast('Paste the code into the box');
    }
  });
  document.getElementById('join-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const code = cleanCode(codeInput.value);
    if (!isCompleteCode(code)) {
      toast('Codes are 4 letters');
      return;
    }
    closeSheets();
    enterRoom(code);
  });

  // Settings: theme + card style, applied immediately.
  document.getElementById('btn-settings').addEventListener('click', () => {
    markSettings(store.getSettings());
    openSheet('sheet-settings');
  });
  const change = (patch) => {
    store.setSettings(patch);
    const settings = store.getSettings();
    applySettings(settings);
    markSettings(settings);
  };
  document.getElementById('theme-swatches').addEventListener('click', (event) => {
    const button = event.target.closest('[data-theme]');
    if (button) change({ theme: button.dataset.theme });
  });
  document.getElementById('card-styles').addEventListener('click', (event) => {
    const button = event.target.closest('[data-cards]');
    if (button) change({ cardStyle: button.dataset.cards });
  });
}

function markSettings({ theme, cardStyle }) {
  document.querySelectorAll('[data-theme]').forEach((b) => b.classList.toggle('on', b.dataset.theme === theme));
  document.querySelectorAll('[data-cards]').forEach((b) => b.classList.toggle('on', b.dataset.cards === cardStyle));
}

function choice(label, onClick) {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = label;
  button.addEventListener('click', onClick);
  return button;
}
```

Interim `frontend/js/app.js` (Task 7 replaces it):

```js
import { initMain } from './main-view.js';
import { closeSheets } from './sheets.js';
import { createStore } from './storage.js';
import { toast } from './ui.js';

const store = createStore();

function applySettings({ theme, cardStyle }) {
  document.body.className = `theme-${theme} cards-${cardStyle}`;
}

applySettings(store.getSettings());
initMain({ store, applySettings, enterRoom: (code) => toast(`Table ${code}: lobby comes in the next task`) });
document.getElementById('sheet-backdrop').addEventListener('click', closeSheets);
```

- [ ] **Step 6: Run it and check the main screen in the browser**

```bash
py -3.12 scripts/dev_up.py
```

Expected: prints `This PC: http://localhost:5520` and a `Phone (same Wi-Fi)` URL, opens the browser.

Check in the browser (Claude-in-Chrome tools or by hand), at a phone-sized viewport (e.g. 390×844):
1. Felt background, gold "Card Table", name field, A♥ "New table" and A♣ "Join" side by side, the jester "Settings" below. No console errors. `curl -sI http://localhost:5520/js/app.js | grep -i content-type` → `text/javascript`.
2. Tap New table with an empty name → toast "Enter your name first".
3. Type a name, reload → the name is still there.
4. New table → sheet lists "Murlan" → tap → buttons 2, 3, 4 → tap 4 → toast `Table XXXX: lobby comes in the next task`.
5. Join → type `kq mz` → the box shows `KQMZ`; Join with `KQ` → toast "Codes are 4 letters". On `http://localhost` the Paste button shows; on the LAN URL it is hidden.
6. Settings → tap Vintage → the three menu cards turn warm/aged; tap Traditional → back. Pick Qëndisje → the swatch gets the gold border; reload → still selected.
7. Stop the backend only (`taskkill /F /PID <backend_pid from .dev/pids.json>`), tap New table → toast "Can't reach the server". Then `py -3.12 scripts/dev_down.py` and `dev_up.py` again.

Run the frontend tests again: `cd frontend && node --test` → all pass.

- [ ] **Step 7: Commit**

```bash
git add scripts/serve_frontend.py scripts/dev_up.py scripts/dev_down.py frontend/index.html frontend/styles.css frontend/themes.css frontend/config.js frontend/manifest.webmanifest frontend/service-worker.js frontend/_headers frontend/js/api.js frontend/js/clipboard.js frontend/js/ui.js frontend/js/sheets.js frontend/js/main-view.js frontend/js/app.js
git commit -m "feat(frontend): PWA shell, themes and the main screen

New table (game, then player count), Join by code, and Settings
(table theme, card style). dev_up.py runs backend :8020 and
frontend :5520.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Lobby, table and the room flow

**Files:**
- Create: `frontend/js/lobby-view.js`, `frontend/js/table-view.js`
- Modify (replace): `frontend/js/app.js`

**Interfaces:**
- Consumes: `RoomConnection` (Task 5); `seatPositions`, `shouldRotate`, `createStore` (Task 4); `socketUrl`, `fetchGames` (Task 6); `copyText` (Task 6); DOM from Task 6.
- Produces:
  - `lobby-view.js`: `initLobby({ onLeave })`, `showLobbyLoading(code)`, `renderLobby(state, meId, gameName)`.
  - `table-view.js`: `initTable({ onLeave })`, `renderTable(state, meId)`.

- [ ] **Step 1: Lobby view**

`frontend/js/lobby-view.js`:

```js
import { copyText } from './clipboard.js';

export function initLobby({ onLeave }) {
  const copyButton = document.getElementById('btn-copy');
  copyButton.addEventListener('click', async () => {
    const ok = await copyText(document.querySelector('.lobby-code').textContent);
    copyButton.textContent = ok ? 'Copied ✓' : 'Tap the code';
    setTimeout(() => { copyButton.textContent = 'Copy'; }, 1500);
  });
  document.getElementById('btn-lobby-leave').addEventListener('click', onLeave);
}

/** Before the first state arrives: show the code so it can be shared right away. */
export function showLobbyLoading(code) {
  document.querySelector('.lobby-game').textContent = '';
  document.querySelector('.lobby-code').textContent = code;
  document.querySelector('.lobby-count').textContent = 'Connecting…';
  document.querySelector('.lobby-seats').replaceChildren();
}

export function renderLobby(state, meId, gameName) {
  const { seats } = state.room;
  document.querySelector('.lobby-game').textContent = gameName;
  document.querySelector('.lobby-code').textContent = state.code;
  document.querySelector('.lobby-count').textContent = `${state.players.length}/${seats} players`;
  const rows = [];
  for (let i = 0; i < seats; i++) {
    const player = state.players[i];
    const row = document.createElement('li');
    if (player) {
      row.textContent = player.id === meId ? `${player.name} (you)` : player.name;
      row.className = player.connected ? 'taken' : 'taken offline';
    } else {
      row.textContent = 'waiting…';
      row.className = 'open';
    }
    rows.push(row);
  }
  document.querySelector('.lobby-seats').replaceChildren(...rows);
}
```

- [ ] **Step 2: Table view**

`frontend/js/table-view.js`:

```js
import { seatPositions } from './seats.js';

const MAX_BACKS = 7; // card backs drawn per opponent; the count shows the real number

export function initTable({ onLeave }) {
  const menu = document.getElementById('table-menu');
  document.getElementById('btn-table-menu').addEventListener('click', () => { menu.hidden = !menu.hidden; });
  document.getElementById('btn-table-leave').addEventListener('click', () => {
    menu.hidden = true;
    onLeave();
  });
}

export function renderTable(state, meId) {
  const me = state.players.find((p) => p.id === meId);
  document.querySelector('.seat-me').replaceChildren(...(me ? [plate(me, false)] : []));
  document.querySelector('.seats').replaceChildren(
    ...seatPositions(state.players, meId).map(({ player, position }) => seat(player, position)),
  );
}

function seat(player, position) {
  const el = div(`seat seat-${position}`);
  const backs = div('backs');
  for (let i = 0; i < Math.min(player.hand_count, MAX_BACKS); i++) backs.append(div('card-back'));
  el.append(backs, plate(player, true));
  return el;
}

function plate(player, withCount) {
  const el = div(player.connected ? 'plate' : 'plate offline');
  const name = document.createElement('span');
  name.textContent = player.name;
  el.append(div('dot'), name);
  if (withCount) {
    const count = document.createElement('span');
    count.className = 'count';
    count.textContent = String(player.hand_count);
    el.append(count);
  }
  return el;
}

function div(className) {
  const el = document.createElement('div');
  el.className = className;
  return el;
}
```

- [ ] **Step 3: Wire it together**

Replace `frontend/js/app.js`:

```js
import { fetchGames, socketUrl } from './api.js';
import { RoomConnection } from './connection.js';
import { initLobby, renderLobby, showLobbyLoading } from './lobby-view.js';
import { initMain } from './main-view.js';
import { shouldRotate } from './orientation.js';
import { closeSheets } from './sheets.js';
import { createStore } from './storage.js';
import { initTable, renderTable } from './table-view.js';
import { setReconnecting, showView, toast } from './ui.js';

const store = createStore();
const gameNames = {};
let connection = null;
let meId = null;

function applySettings({ theme, cardStyle }) {
  document.body.className = `theme-${theme} cards-${cardStyle}`;
}

function gameName(id) {
  return gameNames[id] ?? id.charAt(0).toUpperCase() + id.slice(1);
}

function render(state) {
  if (state.room.status === 'playing') {
    showView('table');
    renderTable(state, meId);
  } else {
    showView('lobby');
    renderLobby(state, meId, gameName(state.room.game));
  }
}

function enterRoom(code) {
  connection?.close();
  meId = null;
  showLobbyLoading(code);
  showView('lobby');
  connection = new RoomConnection({
    code,
    store,
    urlFor: socketUrl,
    onWelcome: (id) => { meId = id; },
    onState: render,
    onError: toast,
    onReconnecting: setReconnecting,
    onClosed: (message) => {
      connection = null;
      setReconnecting(false);
      showView('main');
      toast(message);
    },
  });
  connection.connect();
}

function leaveRoom() {
  connection?.leave();
  connection = null;
  setReconnecting(false);
  showView('main');
}

function updateRotation() {
  document.getElementById('view-table').classList.toggle('rotated', shouldRotate(innerWidth, innerHeight));
}

applySettings(store.getSettings());
initMain({ store, enterRoom, applySettings });
initLobby({ onLeave: leaveRoom });
initTable({ onLeave: leaveRoom });
document.getElementById('sheet-backdrop').addEventListener('click', closeSheets);
addEventListener('resize', updateRotation);
updateRotation();

fetchGames()
  .then((games) => { for (const g of games) gameNames[g.id] = g.name; })
  .catch(() => {}); // names fall back to the id; the New table sheet reports errors itself

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/service-worker.js').catch(() => {});

// Back to the table you were at (reload, app reopened, phone slept).
const current = store.getCurrentRoom();
if (current && store.getToken(current)) enterRoom(current);
```

- [ ] **Step 4: Check the flow in the browser**

With `dev_up.py` running (restart it if Task 6's run was stopped), use two browser windows/tabs, A and B. In B, open DevTools → Application → Local Storage and keep it separate by using a different browser profile or an incognito window, so the two don't share `card-table` storage.

1. A: name "Ana" → New table → Murlan → 2. → Lobby shows "Murlan", a 4-letter code, Copy, "1/2 players", "Ana (you) ✓", "waiting…".
2. A: tap Copy → button shows "Copied ✓"; paste somewhere → it's the code.
3. B: name "Ben" → Join → paste/type the code → Join. → Both switch to the **table**: Classic felt, A sees "Ben" at the top and "Ana" bottom-left; B sees "Ana" at the top.
4. A: reload the page → after a moment A is back on the table (same seat; B's plate never shows a duplicate player).
5. B: ☰ → Leave table → B is on the main screen; A drops back to the lobby with "1/2 players" and an open seat.
6. A: Settings is on the main screen, so leave first, change theme to Kafeneio, create a 2-player room again and join from B → table shows marble with the blue runner, navy plates, the cup and glass. Repeat with Qëndisje (linen, red stitch border, cup).
7. Resize A's window to 390×844 (portrait) on the table → the table is drawn on its side (`#view-table.rotated`). 844×390 → normal.
8. B: Join with a made-up code `ZZZZ` → back on main with toast "No table with that code".
9. With a 2-player room already full (A and B at the table), a third tab C: Join that code → toast "This table is full".
10. Stop only the backend while A and B sit at the table → both show the "Reconnecting…" banner. Start it again → the room is gone (in-memory), so both land on the main screen with "No table with that code".

`cd frontend && node --test` → all pass. `cd backend && .venv/Scripts/python -m pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/js/lobby-view.js frontend/js/table-view.js frontend/js/app.js
git commit -m "feat(frontend): lobby with copyable code, landscape table, reconnect

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Remove the Expo app, update docs, final check

**Files:**
- Delete: `app/` (whole folder)
- Modify: `README.md`, `CLAUDE.md`, `.gitignore`

- [ ] **Step 1: Delete the Expo app**

```bash
git rm -r -q app
rm -rf app   # leftovers that weren't tracked (node_modules, .expo)
```

In `.gitignore`, delete the `app/.env` and `node_modules/` lines (nothing uses them now).

- [ ] **Step 2: Rewrite `README.md`**

~~~markdown
# Card Table

Card games with friends, one game at a time: create a table, share the 4-letter
code, and play on your phones. Vanilla-JS PWA + FastAPI backend. Murlan is the
first game (in progress).

## Run locally

One-time backend setup (Python 3.12):

```bash
cd backend
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
```

Then from the repo root:

```bash
py -3.12 scripts/dev_up.py     # backend :8020 + frontend :5520, opens the browser
py -3.12 scripts/dev_down.py   # stop both
```

`dev_up.py` also prints a `http://<your-pc-ip>:5520` address: open it on a phone on
the same Wi-Fi. Allow Python through Windows Firewall (private networks).
The Copy button and installing to the home screen work best on `localhost` or
https; on the plain-http LAN address you can still long-press to paste a code.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest
cd frontend && node --test
```

## Card art

Faces are Byron Knoll's public-domain *Vector Playing Cards* (English pattern),
with our own ace of spades and jester jokers. `scripts/build_cards.py`
regenerates `frontend/cards/` and `frontend/icons/` (see the script's docstring);
the output is committed.
~~~

- [ ] **Step 3: Update `CLAUDE.md`**

Replace the whole file with:

```markdown
# card-table — Claude guide

Personal project: card games for friends, one game at a time. Vanilla-JS PWA
(`frontend/`, no build step) + FastAPI (`backend/`). Specs in
`docs/superpowers/specs/`; the current one is `2026-10-14-pwa-conversion-design.md`.
Murlan (the first game) gets its own spec next.

## Invariants (don't undo)

- **Server is authoritative; the frontend has no game logic.** It renders
  whatever `state` the server sends.
- **Hidden info never leaves the server.** All state goes out through
  `backend/app/engine/views.py::view_for`. Card ids are re-issued when a card
  enters a hand or a pile is shuffled/gathered, so ids can't track hidden cards.
  `tests/test_views.py::test_no_view_ever_leaks_hidden_cards` guards this.
- **Single uvicorn worker.** Live rooms are in memory; a restart drops them.
- Rooms: `lobby` until the last seat fills, then `playing`; leaving drops back
  to `lobby`. Games and their player ranges live in `backend/app/games.py`.
- Frontend: no npm dependencies and no bundler. `frontend/package.json` only
  makes Node treat `.js` as ES modules for `node --test`.
- Names and anything from the server go into the DOM via `textContent`, never
  `innerHTML`.
- Dev ports: backend 8020, frontend 5520 (`scripts/dev_up.py`).

## Git

Local only, no remote yet. Commit as `Yzeir Baku <yzeirbaku@hotmail.com>`
(set in local config). Never push without asking.
```

- [ ] **Step 4: Full verification**

```bash
cd backend && .venv/Scripts/python -m pytest -q && cd ..
cd frontend && node --test && cd ..
git grep -n -i "expo\|protocol.ts\|app/src" -- ':!docs' || echo "no stale references"
py -3.12 scripts/dev_up.py
```

Expected: both suites pass; `no stale references`; dev stack starts. Re-run Task 7 Step 4 checks 1, 3, 5 and 7 quickly (create → join → table → leave; rotation) to confirm nothing broke. Then `py -3.12 scripts/dev_down.py`.

Ask the user to try it on their phone over Wi-Fi with the printed LAN URL.

- [ ] **Step 5: Commit**

```bash
git add -A app README.md CLAUDE.md .gitignore
git commit -m "chore: remove the Expo app; docs for the PWA

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
