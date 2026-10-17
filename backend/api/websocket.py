"""
Web-Pennmush WebSocket Handler
Author: Jordan Koch (GitHub: kochj23)

Manages real-time WebSocket connections for MUSH gameplay.
"""
import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, Optional, Set
from urllib.parse import urlsplit

from fastapi import WebSocket, WebSocketDisconnect

from backend import auth
from backend.config import settings
from backend.database import AsyncSessionLocal
from backend.models import DBObject, ObjectType
from backend.engine.commands import CommandParser
from backend.engine.objects import ObjectManager
from backend.security import rate_limiter, input_validator, security_logger

log = logging.getLogger("webpennmush.ws")

# WebSocket close codes
POLICY_VIOLATION = 1008
MESSAGE_TOO_BIG = 1009
TRY_AGAIN_LATER = 1013


def _as_output(message: str) -> str:
    """Wrap plain text as the JSON frame the client expects (pass JSON through)."""
    if message.startswith("{") and message.endswith("}"):
        return message
    return json.dumps({"type": "output", "message": message})


class ConnectionManager:
    """
    Manages active WebSocket connections.
    Maps player IDs to WebSocket connections for real-time messaging.
    Maintains a room-to-player cache to avoid DB queries on every broadcast.
    """

    def __init__(self):
        # Active connections: player_id -> WebSocket
        self.active_connections: Dict[int, WebSocket] = {}
        # Track sessions: websocket -> player_id
        self.session_map: Dict[WebSocket, int] = {}
        # Track last activity: player_id -> datetime
        self.last_activity: Dict[int, datetime] = {}
        # Room-to-player cache: room_id -> set of player_ids
        self._room_cache: Dict[int, Set[int]] = {}
        # Open sockets per client IP (authenticated or not) and in total
        self.ip_counts: Dict[str, int] = defaultdict(int)
        self.total_sockets = 0

    def try_reserve(self, ip: str) -> Optional[str]:
        """Reserve a socket slot for an IP; returns a refusal reason or None."""
        if self.total_sockets >= settings.WS_MAX_TOTAL:
            return "Server is full. Try again later."
        if self.ip_counts[ip] >= settings.WS_MAX_PER_IP:
            return "Too many connections from your address."
        self.ip_counts[ip] += 1
        self.total_sockets += 1
        return None

    def release(self, ip: str):
        if self.ip_counts.get(ip, 0) > 0:
            self.ip_counts[ip] -= 1
            if self.ip_counts[ip] == 0:
                del self.ip_counts[ip]
        self.total_sockets = max(0, self.total_sockets - 1)

    async def connect(self, websocket: WebSocket, player_id: int):
        """Register a new connection (websocket must already be accepted).
        A second login for the same player replaces (and closes) the old socket."""
        old = self.active_connections.get(player_id)
        if old is not None and old is not websocket:
            self.session_map.pop(old, None)
            try:
                await old.send_text(json.dumps({"type": "error", "message": "Logged in from another session."}))
                await old.close(code=POLICY_VIOLATION)
            except Exception:
                pass
        self.active_connections[player_id] = websocket
        self.session_map[websocket] = player_id

    def disconnect(self, websocket: WebSocket):
        """Remove a connection and invalidate room cache for that player"""
        player_id = self.session_map.get(websocket)
        if player_id:
            if self.active_connections.get(player_id) is websocket:
                self.active_connections.pop(player_id, None)
            self.session_map.pop(websocket, None)
            # Remove player from all cached rooms
            for room_players in self._room_cache.values():
                room_players.discard(player_id)
        return player_id

    def update_room_cache(self, player_id: int, old_room_id: int = None, new_room_id: int = None):
        """Update the room cache when a player moves, connects, or disconnects."""
        if old_room_id is not None and old_room_id in self._room_cache:
            self._room_cache[old_room_id].discard(player_id)
        if new_room_id is not None:
            if new_room_id not in self._room_cache:
                self._room_cache[new_room_id] = set()
            self._room_cache[new_room_id].add(player_id)

    def invalidate_room_cache(self, room_id: int):
        """Force a cache miss for a specific room (e.g., after a teleport)."""
        self._room_cache.pop(room_id, None)

    async def send_personal_message(self, message: str, player_id: int):
        """Send a message to a specific player"""
        websocket = self.active_connections.get(player_id)
        if websocket:
            try:
                await websocket.send_text(message)
            except Exception:
                # Connection is broken, clean up
                self.active_connections.pop(player_id, None)

    async def broadcast_to_room(self, message: str, room_id: int, exclude_player_id: int = None):
        """Send a message to all connected players in a room, using cache when available."""
        if room_id in self._room_cache:
            player_ids = self._room_cache[room_id]
        else:
            # Cache miss: query DB and populate cache
            async with AsyncSessionLocal() as session:
                obj_mgr = ObjectManager(session)
                players = await obj_mgr.get_players_in_room(room_id)
                player_ids = {p.id for p in players}
                self._room_cache[room_id] = player_ids

        payload = _as_output(message)
        for pid in list(player_ids):
            if pid != exclude_player_id and pid in self.active_connections:
                await self.send_personal_message(payload, pid)

    async def broadcast_global(self, message: str):
        """Send a message to all connected players"""
        payload = _as_output(message)
        for player_id, websocket in list(self.active_connections.items()):
            await self.send_personal_message(payload, player_id)

    def get_connected_count(self) -> int:
        """Get number of connected players"""
        return len(self.active_connections)


# Global connection manager
manager = ConnectionManager()


def origin_allowed(origin: Optional[str], host: Optional[str]) -> bool:
    """
    Cross-site WebSocket hijacking guard. Browsers always send Origin; it must
    be in ALLOWED_ORIGINS, or (when that is empty) match the Host we were
    reached on. Non-browser clients without an Origin header are allowed (they
    still have to authenticate).
    """
    if origin is None:
        return True
    origin = origin.strip().rstrip("/")
    if settings.ALLOWED_ORIGINS:
        return origin in [o.rstrip("/") for o in settings.ALLOWED_ORIGINS]
    try:
        parts = urlsplit(origin)
    except ValueError:
        return False
    return bool(host) and parts.scheme in ("http", "https") and parts.netloc.lower() == host.lower()


class FrameLimiter:
    """Per-connection frame limit (all frame types, incl. pings)."""

    def __init__(self, max_frames: int, window_s: float = 10.0):
        self.max_frames = max_frames
        self.window_s = window_s
        self.stamps = []

    def allow(self, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        cutoff = now - self.window_s
        self.stamps = [t for t in self.stamps if t > cutoff]
        if len(self.stamps) >= self.max_frames:
            return False
        self.stamps.append(now)
        return True


async def _recv_json(websocket: WebSocket, timeout: Optional[float] = None) -> dict:
    """Receive one text frame, enforce the size cap, parse JSON object."""
    if timeout is not None:
        text = await asyncio.wait_for(websocket.receive_text(), timeout)
    else:
        text = await websocket.receive_text()
    if len(text.encode("utf-8")) > settings.WS_MAX_MESSAGE_BYTES:
        raise _TooBig()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("frame must be a JSON object")
    return data


class _TooBig(Exception):
    pass


async def _authenticate(websocket: WebSocket, ip: str) -> Optional[DBObject]:
    """First frame must be {"type":"auth", token} or {"type":"auth", username, password}."""
    try:
        auth_data = await _recv_json(websocket, settings.WS_AUTH_TIMEOUT_S)
    except asyncio.TimeoutError:
        await websocket.send_json({"type": "error", "message": "Authentication timed out"})
        return None
    if auth_data.get("type") != "auth":
        await websocket.send_json({"type": "error", "message": "Authentication required"})
        return None

    async with AsyncSessionLocal() as session:
        token = auth_data.get("token")
        if token:
            pid = auth.verify_token(str(token))
            player = await session.get(DBObject, pid) if pid is not None else None
            if not player or player.type != ObjectType.PLAYER or auth.is_pending(player):
                await websocket.send_json({"type": "error", "message": "Session expired. Please log in again."})
                return None
            from backend.engine.moderation import ModerationManager
            banned, _ = await ModerationManager(session).is_banned(player.id)
            if banned:
                await websocket.send_json({"type": "error", "message": "This account is banned."})
                return None
        else:
            creds = {k: str(auth_data.get(k) or "") for k in ("username", "password")}
            result = await auth.authenticate(session, creds["username"], creds["password"], ip)
            if not result.ok:
                if result.status == 429:
                    security_logger.log_rate_limit_exceeded(ip, "login")
                await websocket.send_json({"type": "error", "message": result.error})
                return None
            player = result.player

        player.is_connected = True
        player.last_login = datetime.utcnow()
        await session.commit()
        return player


async def handle_websocket(websocket: WebSocket):
    """
    Handle WebSocket connection lifecycle.
    Order: Origin check -> per-IP/global caps -> handshake rate -> auth (with
    timeout) -> command loop (size, frame-rate and command-rate limits, one
    short-lived DB session per command).
    """
    ip = auth.client_ip(websocket)
    if not origin_allowed(websocket.headers.get("origin"), websocket.headers.get("host")):
        security_logger.log_suspicious_input("ws_origin", websocket.headers.get("origin", ""), None)
        await websocket.close(code=POLICY_VIOLATION)
        return
    if not rate_limiter.is_allowed(ip, "ws_connect_ip"):
        await websocket.close(code=TRY_AGAIN_LATER)
        return
    refusal = manager.try_reserve(ip)
    if refusal:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": refusal})
        await websocket.close(code=TRY_AGAIN_LATER)
        return

    player_id = None
    try:
        await websocket.accept()
        await websocket.send_json({"type": "auth_required", "message": "Please authenticate"})

        player = await _authenticate(websocket, ip)
        if player is None:
            await websocket.close(code=POLICY_VIOLATION)
            return

        player_id = player.id
        await manager.connect(websocket, player_id)
        manager.last_activity[player_id] = datetime.utcnow()
        if player.location_id is not None:
            manager.update_room_cache(player_id, new_room_id=player.location_id)

        await websocket.send_json({
            "type": "welcome",
            "message": f"Welcome back, {player.name}!",
            "player_id": player.id,
            "player_name": player.name,
        })

        async with AsyncSessionLocal() as session:
            fresh = await session.get(DBObject, player_id)
            look_output = await CommandParser(session).cmd_look(fresh, "")
        await websocket.send_json({"type": "output", "message": look_output})

        if player.location_id:
            await manager.broadcast_to_room(f"{player.name} has connected.", player.location_id,
                                            exclude_player_id=player.id)

        frames = FrameLimiter(settings.WS_FRAMES_PER_10S)
        while True:
            try:
                data = await _recv_json(websocket)
            except _TooBig:
                await websocket.send_json({"type": "error", "message": "Message too large"})
                await websocket.close(code=MESSAGE_TOO_BIG)
                break
            except (ValueError, json.JSONDecodeError):
                await websocket.send_json({"type": "error", "message": "Malformed message"})
                continue

            if not frames.allow():
                await websocket.send_json({"type": "error", "message": "Too many messages. Disconnecting."})
                await websocket.close(code=POLICY_VIOLATION)
                break
            if manager.active_connections.get(player_id) is not websocket:
                break  # replaced by a newer login

            msg_type = data.get("type")
            if msg_type == "command":
                manager.last_activity[player_id] = datetime.utcnow()
                command = str(data.get("command", "")).strip()
                if not command:
                    continue
                if not rate_limiter.is_allowed(str(player_id), "command"):
                    await websocket.send_json({"type": "error",
                                               "message": "You're sending commands too fast. Please slow down."})
                    continue
                is_valid, error = input_validator.validate_command(command)
                if not is_valid:
                    await websocket.send_json({"type": "error", "message": error})
                    continue
                async with AsyncSessionLocal() as session:
                    current = await session.get(DBObject, player_id)
                    if current is None:
                        break
                    output = await CommandParser(session).parse(current, command)
                if output:
                    await websocket.send_json({"type": "output",
                                               "message": str(output)[:settings.MAX_OUTPUT_LENGTH]})
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type == "disconnect":
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:  # never leak internals to the client
        log.warning("websocket error: %s", type(e).__name__)
    finally:
        manager.release(ip)
        if websocket in manager.session_map:
            disconnected_player_id = manager.disconnect(websocket)
            if disconnected_player_id and disconnected_player_id not in manager.active_connections:
                try:
                    async with AsyncSessionLocal() as session:
                        player = await session.get(DBObject, disconnected_player_id)
                        if player:
                            player.is_connected = False
                            await session.commit()
                            if player.location_id:
                                await manager.broadcast_to_room(f"{player.name} has disconnected.",
                                                                player.location_id)
                except Exception as e:
                    log.warning("cleanup error: %s", type(e).__name__)
