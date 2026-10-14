"""HTTP to create rooms, one WebSocket per player to play. Every message and
broadcast for a room runs under that room's lock, so all players see changes in
the same order. Timed game events (a reveal ending, the pause countdown running
out) wake the room through its RoomTimer."""

import json
import os
from contextlib import suppress
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .games import GAMES
from .murlan.game import Rejected
from .rooms import JoinRejected, Player, Room, RoomManager
from .timers import RoomTimer

# Local dev: the frontend is served on :5520 from localhost or a private-network address.
DEV_ORIGINS = (
    r"https?://(localhost|127\.0\.0\.1|10(\.\d{1,3}){3}|192\.168(\.\d{1,3}){2}"
    r"|172\.(1[6-9]|2\d|3[01])(\.\d{1,3}){2}):5520"
)


class CreateRoom(BaseModel):
    game: str
    players: int


def create_app(manager: RoomManager | None = None, *, use_timers: bool = True) -> FastAPI:
    rooms = manager or RoomManager()
    timers: dict[str, RoomTimer] = {}
    app = FastAPI(title="Card Table")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=os.environ.get("CORS_ORIGIN_REGEX", DEV_ORIGINS),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    async def send_state(room: Room, player: Player) -> None:
        if player.socket is None:
            return
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
            player.socket = None
            room.mark_disconnected(player.id)

    async def broadcast(room: Room) -> None:
        for p in list(room.players):
            await send_state(room, p)
        if use_timers:
            schedule(room)

    def schedule(room: Room) -> None:
        timer = timers.setdefault(room.code, RoomTimer(rooms.clock))
        timer.set(room.game.deadline() if room.game else None, lambda: wake(room))

    async def wake(room: Room) -> None:
        async with room.lock:
            if rooms.get(room.code) is not room:  # purged while this wake was pending
                return
            if room.game is not None:
                room.game.tick()
            await broadcast(room)

    async def close_expired() -> None:
        for room in rooms.purge_expired():
            timer = timers.pop(room.code, None)
            if timer is not None:
                timer.cancel()
            for p in room.players:
                if p.socket is not None:
                    with suppress(Exception):
                        await p.socket.close(4410, "Room expired")

    async def handle(room: Room, player: Player, ws: WebSocket, text: str) -> bool:
        """Process one client message. Returns True when the player left."""
        try:
            msg = json.loads(text)
        except ValueError:
            msg = None
        if not isinstance(msg, dict):
            await ws.send_json({"type": "error", "message": "Malformed message"})
            return False
        rooms.touch(room)
        kind = msg.get("type")
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
            elif kind == "after_game":
                room.after_game(player.id, msg.get("choice"))
            else:
                await ws.send_json({"type": "error", "message": "Unknown message type"})
                return False
        except Rejected as e:
            await ws.send_json({"type": "error", "message": str(e)})
            await send_state(room, player)
            return False
        await broadcast(room)
        return False

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
        ws: WebSocket, code: str, name: str = "", token: str | None = None
    ) -> None:
        await ws.accept()
        await close_expired()
        room = rooms.get(code)
        if room is None:
            await ws.close(4404, "Room not found")
            return
        async with room.lock:
            try:
                player = room.join(name, token)
            except JoinRejected as e:
                await ws.close(e.code, e.message)
                return
            old, player.socket = player.socket, ws
            if old is not None:
                with suppress(Exception):
                    await old.close(4000, "Opened on another connection")
            room.mark_connected(player.id)
            rooms.touch(room)
            await ws.send_json(
                {"type": "welcome", "player_id": player.id, "token": player.token,
                 "code": room.code}
            )
            await broadcast(room)
        try:
            while True:
                text = await ws.receive_text()
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
