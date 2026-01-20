"""
Web-Pennmush WebSocket Handler
Author: Jordan Koch (GitHub: kochj23)

Manages real-time WebSocket connections for MUSH gameplay.
"""
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import AsyncSessionLocal
from backend.models import DBObject, ObjectType
from backend.engine.commands import CommandParser
from backend.engine.objects import ObjectManager
from backend.security import rate_limiter, input_validator, security_logger
from passlib.context import CryptContext
from datetime import datetime, timedelta
import json


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class ConnectionManager:
    """
    Manages active WebSocket connections.
    Maps player IDs to WebSocket connections for real-time messaging.
    """

    def __init__(self):
        # Active connections: player_id -> WebSocket
        self.active_connections: Dict[int, WebSocket] = {}
        # Track sessions: websocket -> player_id
        self.session_map: Dict[WebSocket, int] = {}
        # Track last activity: player_id -> datetime
        self.last_activity: Dict[int, datetime] = {}

    async def connect(self, websocket: WebSocket, player_id: int):
        """Register a new connection"""
        await websocket.accept()
        self.active_connections[player_id] = websocket
        self.session_map[websocket] = player_id

    def disconnect(self, websocket: WebSocket):
        """Remove a connection"""
        player_id = self.session_map.get(websocket)
        if player_id:
            self.active_connections.pop(player_id, None)
            self.session_map.pop(websocket, None)
        return player_id

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
        """Send a message to all players in a room"""
        async with AsyncSessionLocal() as session:
            obj_mgr = ObjectManager(session)
            players = await obj_mgr.get_players_in_room(room_id)

            for player in players:
                if player.id != exclude_player_id and player.id in self.active_connections:
                    await self.send_personal_message(message, player.id)

    async def broadcast_global(self, message: str):
        """Send a message to all connected players"""
        for player_id, websocket in list(self.active_connections.items()):
            await self.send_personal_message(message, player_id)

    def get_connected_count(self) -> int:
        """Get number of connected players"""
        return len(self.active_connections)


# Global connection manager
manager = ConnectionManager()


async def handle_websocket(websocket: WebSocket):
    """
    Handle WebSocket connection lifecycle.
    Manages authentication, command processing, and disconnection.
    """
    player_id = None
    session: AsyncSession = None

    try:
        # Wait for authentication
        await websocket.accept()
        await websocket.send_json({"type": "auth_required", "message": "Please authenticate"})

        # Receive authentication credentials
        auth_data = await websocket.receive_json()

        if auth_data.get("type") != "auth":
            await websocket.send_json({"type": "error", "message": "Authentication required"})
            await websocket.close()
            return

        username = auth_data.get("username")
        password = auth_data.get("password")

        if not username or not password:
            await websocket.send_json({"type": "error", "message": "Username and password required"})
            await websocket.close()
            return

        # Rate limiting for login attempts
        if not rate_limiter.is_allowed(username, "login"):
            security_logger.log_rate_limit_exceeded(username, "login")
            await websocket.send_json({"type": "error", "message": "Too many login attempts. Please wait a minute."})
            await websocket.close()
            return

        # Validate username format
        is_valid, error = input_validator.validate_name(username)
        if not is_valid:
            await websocket.send_json({"type": "error", "message": f"Invalid username: {error}"})
            await websocket.close()
            return

        # Authenticate player
        session = AsyncSessionLocal()
        obj_mgr = ObjectManager(session)

        player = await obj_mgr.get_object_by_name(username)

        if not player or player.type != ObjectType.PLAYER:
            security_logger.log_failed_login(username, "websocket")
            await websocket.send_json({"type": "error", "message": "Invalid username or password"})
            await websocket.close()
            return

        # Verify password
        if not pwd_context.verify(password, player.password_hash):
            security_logger.log_failed_login(username, "websocket")
            await websocket.send_json({"type": "error", "message": "Invalid username or password"})
            await websocket.close()
            return

        # Authentication successful
        player_id = player.id
        player.is_connected = True
        player.last_login = datetime.utcnow()
        await session.commit()

        # Register connection
        await manager.connect(websocket, player_id)
        manager.last_activity[player_id] = datetime.utcnow()

        # Send welcome message
        welcome_msg = {
            "type": "welcome",
            "message": f"Welcome back, {player.name}!",
            "player_id": player.id,
            "player_name": player.name
        }
        await websocket.send_json(welcome_msg)

        # Show initial room
        cmd_parser = CommandParser(session)
        look_output = await cmd_parser.cmd_look(player, "")
        await websocket.send_json({"type": "output", "message": look_output})

        # Announce connection to room
        if player.location_id:
            await manager.broadcast_to_room(
                f"{player.name} has connected.",
                player.location_id,
                exclude_player_id=player.id
            )

        # Main message loop
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "command":
                # Update activity timestamp
                manager.last_activity[player_id] = datetime.utcnow()

                # Process MUSH command
                command = data.get("command", "").strip()
                if command:
                    # Rate limiting for commands
                    if not rate_limiter.is_allowed(str(player_id), "command"):
                        await websocket.send_json({
                            "type": "error",
                            "message": "You're sending commands too fast. Please slow down."
                        })
                        continue

                    # Validate command
                    is_valid, error = input_validator.validate_command(command)
                    if not is_valid:
                        await websocket.send_json({"type": "error", "message": error})
                        continue

                    output = await cmd_parser.parse(player, command)
                    if output:
                        await websocket.send_json({"type": "output", "message": output})

            elif msg_type == "ping":
                # Respond to ping for keepalive
                await websocket.send_json({"type": "pong"})

            elif msg_type == "disconnect":
                # Graceful disconnect
                break

    except WebSocketDisconnect:
        # Client disconnected
        pass

    except Exception as e:
        # Log error
        print(f"WebSocket error: {e}")

    finally:
        # Clean up connection
        if websocket in manager.session_map:
            disconnected_player_id = manager.disconnect(websocket)

            if disconnected_player_id and session:
                try:
                    player = await obj_mgr.get_object(disconnected_player_id)
                    if player:
                        player.is_connected = False
                        await session.commit()

                        # Announce disconnection
                        if player.location_id:
                            await manager.broadcast_to_room(
                                f"{player.name} has disconnected.",
                                player.location_id
                            )
                except Exception as e:
                    print(f"Error during cleanup: {e}")

        if session:
            await session.close()
