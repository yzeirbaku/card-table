"""HTTP to create rooms, one WebSocket per player to play. Every message and
broadcast for a room runs under that room's lock, so all players see changes in
the same order. Timed game events (a reveal ending, the pause countdown running
out, a computer player's move coming due) wake the room through its RoomTimer.
Accounts, sign-ins and finished games live in the SQLite file (`app/db.py`)."""

import asyncio
import json
import logging
import os
import sqlite3
import time
from contextlib import suppress
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .accounts import MAX_PASSWORD, AccountError, Accounts
from .db import default_db_path, open_db
from .games import GAMES
from .murlan.game import Rejected
from .rooms import JoinRejected, Player, Room, RoomManager
from .stats import head_to_head, leaderboard, save_game, stats_for
from .timers import RoomTimer

log = logging.getLogger(__name__)

REACTIONS = frozenset({"shocked", "laughing", "angry", "asleep", "catan", "clap", "please"})
REACTION_GAP_SECONDS = 1.0  # a player's reactions closer together than this are dropped

# Local dev: the frontend is served on :5520 from localhost or a private-network address.
DEV_ORIGINS = (
    r"https?://(localhost|127\.0\.0\.1|10(\.\d{1,3}){3}|192\.168(\.\d{1,3}){2}"
    r"|172\.(1[6-9]|2\d|3[01])(\.\d{1,3}){2}):5520"
)


class CreateRoom(BaseModel):
    game: str
    players: int


SESSION_WAIT_SECONDS = 10.0  # a signed-in phone sends its session first thing after connecting


class Credentials(BaseModel):
    username: str = Field(max_length=20)  # oversized input never reaches the hashing
    password: str = Field(max_length=MAX_PASSWORD)


def bearer_token(authorization: str | None) -> str | None:
    scheme, _, token = (authorization or "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def create_app(manager: RoomManager | None = None, *, use_timers: bool = True,
               db: sqlite3.Connection | None = None) -> FastAPI:
    rooms = manager or RoomManager()
    db = db if db is not None else open_db(default_db_path())
    accounts = Accounts(db)
    rooms.record = lambda record: save_game(db, record, time.time())
    timers: dict[int, RoomTimer] = {}  # by id(room): a purged room's timer can't be reused
    app = FastAPI(title="Card Table")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=os.environ.get("CORS_ORIGIN_REGEX", DEV_ORIGINS),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

    async def send_state(room: Room, player: Player) -> bool:
        """Send the player their view. False if their socket turned out dead."""
        if player.socket is None:
            return True
        message: dict[str, Any] = {
            "type": "state",
            "code": room.code,
            "room": room.room_view(),
            "players": room.players_view(),
            "game": room.game_view(player.id),
        }
        try:
            await player.socket.send_json(message)
        except Exception:  # a dead socket must not break the broadcast
            sock, player.socket = player.socket, None
            with suppress(Exception):  # a half-open client then reconnects
                await sock.close()
            room.mark_disconnected(player.id)
            return False
        return True

    async def broadcast(room: Room) -> None:
        try:
            room.update_bots()  # they see every change, as the people at the table do
        except Exception:  # a computer player's bug must not take the table down with it
            log.exception("computer players failed to take in room %s", room.code)
            room.bot_due = None
        # A socket that dies mid-broadcast changes the state (the game pauses), so
        # the players already sent to get another round with the new state.
        for _ in range(len(room.players) + 1):
            results = [await send_state(room, p) for p in list(room.players)]
            if all(results):
                break
        reactions, room.bot_reactions = room.bot_reactions, []
        for player_id, reaction in reactions:  # a computer's emoji, at what everyone has just seen
            await send_reaction(room, player_id, reaction)
        if use_timers:
            schedule(room)

    def schedule(room: Room) -> None:
        if rooms.get(room.code) is not room:  # purged: no timers for it
            return
        timer = timers.setdefault(id(room), RoomTimer(rooms.clock))
        times = [room.game.deadline() if room.game else None, room.bot_due[1] if room.bot_due else None,
                 room.starts_at]
        timer.set(min((t for t in times if t is not None), default=None), lambda: wake(room))

    async def wake(room: Room) -> None:
        async with room.lock:
            if rooms.get(room.code) is not room:  # purged while this wake was pending
                return
            room.start_if_due()
            if room.game is not None:
                room.game.tick()
                room.run_bot()
            await broadcast(room)

    async def react(room: Room, player: Player, ws: WebSocket, reaction: Any) -> None:
        """A seated player's emoji, shown to everyone at the table. Nothing in the game changes."""
        if not isinstance(reaction, str) or reaction not in REACTIONS:
            await ws.send_json({"type": "error", "message": "Unknown reaction"})
            return
        if room.game is None or player.id not in room.game.seats:
            await ws.send_json({"type": "error", "message": "Reactions are for players at the table"})
            return
        now = rooms.clock()
        if now - player.reacted_at < REACTION_GAP_SECONDS:
            return
        player.reacted_at = now
        await send_reaction(room, player.id, reaction)

    async def send_reaction(room: Room, player_id: str, reaction: str) -> None:
        message = {"type": "reaction", "player_id": player_id, "reaction": reaction}
        for p in list(room.players):
            if p.socket is not None:
                with suppress(Exception):  # a dead socket is cleaned up by its own receive loop
                    await p.socket.send_json(message)

    async def close_expired() -> None:
        for room in rooms.purge_expired():
            timer = timers.pop(id(room), None)
            if timer is not None:
                timer.cancel()
            for p in room.players:
                if p.socket is not None:
                    with suppress(Exception):
                        await p.socket.close(4410, "Room expired")

    async def handle(room: Room, player: Player, ws: WebSocket, text: str) -> bool:
        """Process one client message. Returns True when the player left."""
        if player not in room.players or player.socket is not ws:  # removed or replaced: stale
            if player.socket is ws:
                player.socket = None
            with suppress(Exception):
                await ws.close(1000, "Removed from the room")
            return True
        try:
            msg = json.loads(text)
        except ValueError:
            msg = None
        if not isinstance(msg, dict):
            await ws.send_json({"type": "error", "message": "Malformed message"})
            return False
        rooms.touch(room)
        kind = msg.get("type")
        if kind == "react":
            await react(room, player, ws, msg.get("reaction"))
            return False
        if kind == "leave":
            room.leave(player.id)
            player.socket = None
            with suppress(Exception):
                await ws.close(1000, "Left the room")
            await broadcast(room)
            return True
        try:
            if kind == "action":
                room.act(player.id, msg.get("action"))
            elif kind == "sit":
                room.sit(player.id, msg.get("seat"))
            elif kind == "add_computer":
                room.add_computer(player.id, msg.get("seat"))
            elif kind == "remove_computer":
                room.remove_computer(player.id, msg.get("seat"))
            elif kind == "set_level":
                room.set_level(player.id, msg.get("level"))
            elif kind == "after_game":
                room.after_game(player.id, msg.get("choice"))
            else:
                await ws.send_json({"type": "error", "message": "Unknown message type"})
                return False
        except Rejected as e:
            await ws.send_json({"type": "error", "message": str(e)})
            if not await send_state(room, player):  # their socket died: the game paused, tell the rest
                await broadcast(room)
            return False
        await broadcast(room)
        return False

    async def signed_in(credentials: Credentials, sign) -> dict[str, str]:
        try:
            user, token = await sign(credentials.username, credentials.password)
        except AccountError as e:
            raise HTTPException(e.status, str(e)) from None
        return {"token": token, "username": user.username}

    @app.post("/auth/register")
    async def register(body: Credentials) -> dict[str, str]:
        return await signed_in(body, accounts.register)

    @app.post("/auth/login")
    async def login(body: Credentials) -> dict[str, str]:
        return await signed_in(body, accounts.login)

    async def session_user(ws: WebSocket) -> Any:
        """The first message of a signed-in socket is its session; not in the URL, which ends up in logs."""
        try:
            msg = await asyncio.wait_for(ws.receive_json(), SESSION_WAIT_SECONDS)
        except (asyncio.TimeoutError, WebSocketDisconnect, ValueError, RuntimeError):
            return None
        if not isinstance(msg, dict) or msg.get("type") != "session" or not isinstance(msg.get("session"), str):
            return None
        return accounts.user_for(msg["session"])

    @app.post("/auth/logout")
    async def logout(authorization: str | None = Header(None)) -> dict[str, str]:
        token = bearer_token(authorization)
        if token:
            accounts.logout(token)
        return {}

    @app.get("/me")
    async def me(authorization: str | None = Header(None)) -> dict[str, str]:
        user = accounts.user_for(bearer_token(authorization))
        if user is None:
            raise HTTPException(401, "Signed out")
        return {"username": user.username}

    @app.get("/stats/{username}")
    async def stats(username: str) -> dict[str, Any]:
        found = stats_for(db, username)
        if found is None:
            raise HTTPException(404, "No such player")
        return found

    @app.get("/leaderboard")
    async def players() -> dict[str, Any]:
        return leaderboard(db)

    @app.get("/head-to-head/{username}")
    async def versus(username: str, other: str = Query(alias="with")) -> dict[str, Any]:
        found = head_to_head(db, username, other)
        if found is None:
            raise HTTPException(404, "No such player")
        return found

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

    @app.websocket("/rooms/{code}/ws")
    async def room_socket(
        ws: WebSocket, code: str, name: str = "", token: str | None = None, signed_in: bool = False
    ) -> None:
        await ws.accept()
        await close_expired()
        user = await session_user(ws) if signed_in else None
        room = rooms.get(code)
        # A dead session still gets its own seat back (the seat token proves it); only a new join needs one.
        if signed_in and user is None and (room is None or room.holder(token) is None):
            with suppress(Exception):
                await ws.close(4401, "Signed out")
            return
        if room is None:
            await ws.close(4404, "Room not found")
            return
        async with room.lock:
            owner = None if user or room.holder(token) else accounts.registered_name(name.strip())
            if owner:  # a guest can't play under someone's account name
                await ws.close(4400, f"{owner} has an account. Sign in to play as {owner}")
                return
            try:
                player = room.join(name, token, user)
            except JoinRejected as e:
                await ws.close(e.code, e.message)
                return
            old, player.socket = player.socket, ws
            if old is not None:
                with suppress(Exception):
                    await old.close(4000, "Opened on another connection")
            room.mark_connected(player.id)
            rooms.touch(room)
            try:
                await ws.send_json(
                    {"type": "welcome", "player_id": player.id, "token": player.token,
                     "code": room.code}
                )
            except Exception:  # same cleanup as a disconnect
                if player.socket is ws:
                    player.socket = None
                    if player.token != token and room.game is None:  # new here and never got their token: their retry is someone new
                        room.leave(player.id)
                    else:
                        room.mark_disconnected(player.id)
                    await broadcast(room)
                with suppress(Exception):
                    await ws.close()
                return
            await broadcast(room)
        try:
            while True:
                try:
                    text = await ws.receive_text()
                except RuntimeError:  # receiving on a socket that already closed
                    break
                async with room.lock:
                    if await handle(room, player, ws, text):
                        break
        except WebSocketDisconnect:
            pass
        finally:
            async with room.lock:
                if player.socket is ws:
                    player.socket = None
                    room.mark_disconnected(player.id)
                    await broadcast(room)

    return app


app = create_app()
