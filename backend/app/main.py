"""HTTP to create rooms, one WebSocket per player to play. Every action and
broadcast for a room runs under that room's lock, so all players see changes
in the same order."""

import json
from contextlib import suppress
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .engine.actions import ActionRejected, apply_action
from .engine.views import view_for
from .rooms import JoinRejected, Player, Room, RoomManager


def create_app(manager: RoomManager | None = None) -> FastAPI:
    rooms = manager or RoomManager()
    app = FastAPI(title="Card Table")

    async def send_state(room: Room, player: Player) -> None:
        if player.socket is None:
            return
        message: dict[str, Any] = {
            "type": "state",
            "code": room.code,
            "players": room.players_view(),
            "view": view_for(room.state, player.id),
        }
        try:
            await player.socket.send_json(message)
        except Exception:  # a dead socket must not break the broadcast
            player.socket = None

    async def broadcast(room: Room) -> None:
        for p in list(room.players):
            await send_state(room, p)

    async def close_expired() -> None:
        for room in rooms.purge_expired():
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
        if msg.get("type") == "action":
            try:
                apply_action(room.state, player.id, msg.get("action"))
            except ActionRejected as e:
                await ws.send_json({"type": "error", "message": str(e)})
                await send_state(room, player)
                return False
            await broadcast(room)
            return False
        if msg.get("type") == "leave":
            room.leave(player.id)
            player.socket = None
            with suppress(Exception):
                await ws.close(1000, "Left the room")
            await broadcast(room)
            return True
        await ws.send_json({"type": "error", "message": "Unknown message type"})
        return False

    @app.post("/rooms")
    async def create_room() -> dict[str, str]:
        await close_expired()
        return {"code": rooms.create().code}

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
            if player.socket is ws:
                player.socket = None
                async with room.lock:
                    await broadcast(room)

    return app


app = create_app()
