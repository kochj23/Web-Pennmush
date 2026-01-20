"""
Web-Pennmush REST API
Author: Jordan Koch (GitHub: kochj23)

REST endpoints for account management and information queries.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.models import DBObject, ObjectType
from backend.engine.objects import ObjectManager
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from typing import Optional, List


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter(prefix="/api", tags=["api"])


# ==================== MODELS ====================

class PlayerCreate(BaseModel):
    """Request model for creating a new player"""
    username: str
    password: str
    email: Optional[EmailStr] = None


class PlayerInfo(BaseModel):
    """Response model for player information"""
    id: int
    name: str
    is_connected: bool
    created_at: str


class ObjectInfo(BaseModel):
    """Response model for object information"""
    id: int
    name: str
    type: str
    description: Optional[str]
    owner_id: Optional[int]
    location_id: Optional[int]


# ==================== ENDPOINTS ====================

@router.get("/")
async def root():
    """API root endpoint"""
    return {
        "name": "Web-Pennmush API",
        "version": "1.0.0",
        "description": "REST API for Web-Pennmush server"
    }


@router.post("/players/register", response_model=PlayerInfo)
async def register_player(player_data: PlayerCreate, db: AsyncSession = Depends(get_db)):
    """
    Register a new player account.
    Creates a player object and places them in the starting room.
    """
    obj_mgr = ObjectManager(db)

    # Check if username already exists
    existing = await obj_mgr.get_object_by_name(player_data.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    # Hash password
    password_hash = pwd_context.hash(player_data.password)

    # Create player object
    player = await obj_mgr.create_object(
        name=player_data.username,
        obj_type=ObjectType.PLAYER,
        owner_id=1,  # God owns new players
        location_id=2,  # Central Plaza (starting room)
        home_id=2,
        description=f"A player named {player_data.username}.",
        password_hash=password_hash,
        email=player_data.email,
        is_connected=False
    )

    return PlayerInfo(
        id=player.id,
        name=player.name,
        is_connected=player.is_connected,
        created_at=player.created_at.isoformat()
    )


@router.get("/players/{player_id}", response_model=PlayerInfo)
async def get_player(player_id: int, db: AsyncSession = Depends(get_db)):
    """Get information about a player"""
    obj_mgr = ObjectManager(db)
    player = await obj_mgr.get_object(player_id)

    if not player or player.type != ObjectType.PLAYER:
        raise HTTPException(status_code=404, detail="Player not found")

    return PlayerInfo(
        id=player.id,
        name=player.name,
        is_connected=player.is_connected,
        created_at=player.created_at.isoformat()
    )


@router.get("/players", response_model=List[PlayerInfo])
async def list_players(db: AsyncSession = Depends(get_db)):
    """List all players"""
    from sqlalchemy import select
    query = select(DBObject).where(DBObject.type == ObjectType.PLAYER)
    result = await db.execute(query)
    players = result.scalars().all()

    return [
        PlayerInfo(
            id=p.id,
            name=p.name,
            is_connected=p.is_connected,
            created_at=p.created_at.isoformat()
        )
        for p in players
    ]


@router.get("/objects/{object_id}", response_model=ObjectInfo)
async def get_object(object_id: int, db: AsyncSession = Depends(get_db)):
    """Get information about an object"""
    obj_mgr = ObjectManager(db)
    obj = await obj_mgr.get_object(object_id)

    if not obj or obj.type == ObjectType.GARBAGE:
        raise HTTPException(status_code=404, detail="Object not found")

    return ObjectInfo(
        id=obj.id,
        name=obj.name,
        type=obj.type.value,
        description=obj.description,
        owner_id=obj.owner_id,
        location_id=obj.location_id
    )


@router.get("/rooms/{room_id}/contents", response_model=List[ObjectInfo])
async def get_room_contents(room_id: int, db: AsyncSession = Depends(get_db)):
    """Get all objects in a room"""
    obj_mgr = ObjectManager(db)
    room = await obj_mgr.get_object(room_id)

    if not room or room.type != ObjectType.ROOM:
        raise HTTPException(status_code=404, detail="Room not found")

    contents = await obj_mgr.get_contents(room_id)

    return [
        ObjectInfo(
            id=obj.id,
            name=obj.name,
            type=obj.type.value,
            description=obj.description,
            owner_id=obj.owner_id,
            location_id=obj.location_id
        )
        for obj in contents
    ]


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get server statistics"""
    from sqlalchemy import select, func

    stats = {}
    for obj_type in [ObjectType.ROOM, ObjectType.THING, ObjectType.EXIT, ObjectType.PLAYER]:
        query = select(func.count()).where(DBObject.type == obj_type)
        result = await db.execute(query)
        stats[obj_type.value.lower() + "s"] = result.scalar()

    # Get connected players count
    query = select(func.count()).where(
        DBObject.type == ObjectType.PLAYER,
        DBObject.is_connected == True
    )
    result = await db.execute(query)
    stats["connected_players"] = result.scalar()

    return stats


@router.get("/rooms/map")
async def get_room_map(center_room_id: int = 0, radius: int = 10, db: AsyncSession = Depends(get_db)):
    """
    Get a map of rooms connected by exits.
    Returns nodes (rooms) and edges (exits) for visualization.
    """
    obj_mgr = ObjectManager(db)

    visited = set()
    nodes = []
    edges = []

    async def traverse_rooms(room_id: int, depth: int):
        """Recursively traverse connected rooms"""
        if depth > radius or room_id in visited:
            return

        visited.add(room_id)
        room = await obj_mgr.get_object(room_id)

        if not room or room.type != ObjectType.ROOM:
            return

        # Add room node
        nodes.append({
            "id": room.id,
            "name": room.name,
            "description": room.description or "No description",
            "type": "room"
        })

        # Get exits
        exits = await obj_mgr.get_exits(room.id)
        for exit_obj in exits:
            if exit_obj.home_id:
                # Add edge
                edges.append({
                    "id": exit_obj.id,
                    "source": room.id,
                    "target": exit_obj.home_id,
                    "name": exit_obj.name,
                    "type": "exit"
                })

                # Traverse to connected room
                await traverse_rooms(exit_obj.home_id, depth + 1)

    # Start traversal from center room
    await traverse_rooms(center_room_id, 0)

    return {
        "nodes": nodes,
        "edges": edges,
        "center": center_room_id
    }
