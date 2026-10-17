"""
Web-Pennmush REST API
Author: Jordan Koch (GitHub: kochj23)

Every /api route requires a session except login/logout/register. Data routes
only reveal what the caller could see in-game; admin routes need GOD/WIZARD/ROYAL.
"""
import hmac
from collections import deque
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import auth
from backend.auth import current_player, require_admin
from backend.config import settings
from backend.database import get_db
from backend.engine.objects import ObjectManager
from backend.models import DBObject, ObjectType
from backend.passwords import pwd_context, MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH
from backend.security import input_validator, rate_limiter

router = APIRouter(prefix="/api", tags=["api"])

MAX_MAP_NODES = 200


# ==================== MODELS ====================

class PlayerCreate(BaseModel):
    """Request model for creating a new player"""
    username: str = Field(min_length=1, max_length=30)
    password: str = Field(min_length=1, max_length=256)
    email: Optional[EmailStr] = None
    invite_code: Optional[str] = Field(default=None, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class LinkAccountRequest(BaseModel):
    site_account_id: Optional[str] = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_.:-]*$")


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


def _player_info(p: DBObject) -> PlayerInfo:
    return PlayerInfo(id=p.id, name=p.name, is_connected=bool(p.is_connected),
                      created_at=p.created_at.isoformat() if p.created_at else "")


def _object_info(o: DBObject) -> ObjectInfo:
    return ObjectInfo(id=o.id, name=o.name, type=o.type.value, description=o.description,
                      owner_id=o.owner_id, location_id=o.location_id)


def _flags(o: DBObject) -> set:
    return {f.strip().upper() for f in (o.flags or "").split(",") if f.strip()}


def same_origin(request: Request):
    """CSRF guard for cookie-authenticated state changes: a browser Origin must match."""
    from backend.api.websocket import origin_allowed
    if not origin_allowed(request.headers.get("origin"), request.headers.get("host")):
        raise HTTPException(status_code=403, detail="Cross-origin request refused")


def _set_session_cookie(response: Response, token: str):
    response.set_cookie(auth.COOKIE_NAME, token, max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                        httponly=True, samesite="strict", secure=settings.COOKIE_SECURE, path=settings.COOKIE_PATH)


# ==================== AUTH ====================

@router.post("/auth/login", dependencies=[Depends(same_origin)])
async def login(body: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Password login. Rate limited per client IP and per account."""
    result = await auth.authenticate(db, body.username, body.password, auth.client_ip(request))
    if not result.ok:
        raise HTTPException(status_code=result.status, detail=result.error)
    token = auth.issue_token(result.player.id)
    _set_session_cookie(response, token)
    return {"token": token, "player": {"id": result.player.id, "name": result.player.name,
                                       "is_admin": auth.is_admin(result.player)}}


@router.post("/auth/logout", dependencies=[Depends(same_origin)])
async def logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME, path=settings.COOKIE_PATH)
    return {"ok": True}


@router.get("/auth/me")
async def me(player: DBObject = Depends(current_player)):
    return {"id": player.id, "name": player.name, "is_admin": auth.is_admin(player)}


@router.get("/")
async def root(player: DBObject = Depends(current_player)):
    """API root endpoint"""
    return {"name": "Web-Pennmush API", "version": settings.APP_VERSION,
            "description": "REST API for Web-Pennmush server"}


# ==================== REGISTRATION ====================

@router.post("/players/register", response_model=PlayerInfo, dependencies=[Depends(same_origin)])
async def register_player(player_data: PlayerCreate, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Register a new player account.

    REGISTRATION_MODE: invite (valid INVITE_CODE required), approval (account is
    PENDING until an admin approves), closed (refused), open (dev only).
    Rate limited per client IP.
    """
    mode = settings.REGISTRATION_MODE.lower()
    if mode == "closed":
        raise HTTPException(status_code=403, detail="Registration is closed. Ask an admin for an account.")
    ip = auth.client_ip(request)
    if not rate_limiter.is_allowed(ip, "register_ip"):
        raise HTTPException(status_code=429, detail="Too many registrations from your address. Try later.")
    if mode == "invite":
        code = player_data.invite_code or ""
        if not settings.INVITE_CODE or not hmac.compare_digest(code.encode(), settings.INVITE_CODE.encode()):
            raise HTTPException(status_code=403, detail="A valid invite code is required.")

    ok, err = input_validator.validate_name(player_data.username)
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    pw = player_data.password
    if len(pw) < MIN_PASSWORD_LENGTH or len(pw.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise HTTPException(status_code=400,
                            detail=f"Password must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_BYTES} bytes long")

    obj_mgr = ObjectManager(db)
    if await obj_mgr.get_player_by_exact_name(player_data.username):
        raise HTTPException(status_code=400, detail="Username already exists")

    password_hash = await pwd_context.ahash(pw)
    player = await obj_mgr.create_object(
        name=player_data.username,
        obj_type=ObjectType.PLAYER,
        owner_id=1,  # God owns new players
        location_id=2,  # Central Plaza (starting room)
        home_id=2,
        description=f"A player named {player_data.username}.",
        password_hash=password_hash,
        email=player_data.email,
        is_connected=False,
        flags=auth.PENDING_FLAG if mode == "approval" else "",
    )
    return _player_info(player)


# ==================== PLAYER-SCOPED DATA ====================

@router.get("/players", response_model=List[PlayerInfo])
async def list_players(player: DBObject = Depends(current_player), db: AsyncSession = Depends(get_db)):
    """Connected players (the in-game WHO list). Admins see every account."""
    query = select(DBObject).where(DBObject.type == ObjectType.PLAYER)
    if not auth.is_admin(player):
        query = query.where(DBObject.is_connected == True)  # noqa: E712
    result = await db.execute(query.order_by(DBObject.id).limit(500))
    return [_player_info(p) for p in result.scalars().all()
            if auth.is_admin(player) or "DARK" not in _flags(p)]


@router.get("/players/{player_id}", response_model=PlayerInfo)
async def get_player(player_id: int, player: DBObject = Depends(current_player), db: AsyncSession = Depends(get_db)):
    """Get information about a player"""
    target = await db.get(DBObject, player_id)
    if not target or target.type != ObjectType.PLAYER:
        raise HTTPException(status_code=404, detail="Player not found")
    return _player_info(target)


async def _can_see(viewer: DBObject, obj: DBObject) -> bool:
    if auth.is_admin(viewer):
        return True
    if obj.id in (viewer.id, viewer.location_id) or obj.owner_id == viewer.id:
        return True
    if "DARK" in _flags(obj):
        return False
    return obj.location_id is not None and obj.location_id in (viewer.id, viewer.location_id)


@router.get("/objects/{object_id}", response_model=ObjectInfo)
async def get_object(object_id: int, player: DBObject = Depends(current_player), db: AsyncSession = Depends(get_db)):
    """An object you own, carry, stand in, or can see in your room."""
    obj = await db.get(DBObject, object_id)
    if not obj or obj.type == ObjectType.GARBAGE or not await _can_see(player, obj):
        raise HTTPException(status_code=404, detail="Object not found")
    return _object_info(obj)


@router.get("/rooms/{room_id}/contents", response_model=List[ObjectInfo])
async def get_room_contents(room_id: int, player: DBObject = Depends(current_player),
                            db: AsyncSession = Depends(get_db)):
    """Contents of your current room (any room for admins)."""
    obj_mgr = ObjectManager(db)
    room = await obj_mgr.get_object(room_id)
    if not room or room.type != ObjectType.ROOM:
        raise HTTPException(status_code=404, detail="Room not found")
    admin = auth.is_admin(player)
    if not admin and room_id != player.location_id:
        raise HTTPException(status_code=404, detail="Room not found")
    contents = await obj_mgr.get_contents(room_id)
    return [_object_info(o) for o in contents if admin or "DARK" not in _flags(o)]


@router.get("/rooms/map")
async def get_room_map(center_room_id: int = 0, radius: int = 10, player: DBObject = Depends(current_player),
                       db: AsyncSession = Depends(get_db)):
    """
    Rooms/exits graph for the minimap. Players get a small radius around their
    own location; admins may pick any centre. Bounded BFS (no recursion).
    """
    admin = auth.is_admin(player)
    if not admin:
        center_room_id = player.location_id if player.location_id is not None else 0
        radius = min(radius, 3)
    radius = max(0, min(radius, 10))
    obj_mgr = ObjectManager(db)
    visited, nodes, edges = set(), [], []
    queue = deque([(center_room_id, 0)])
    while queue and len(nodes) < MAX_MAP_NODES:
        room_id, depth = queue.popleft()
        if room_id in visited or depth > radius:
            continue
        visited.add(room_id)
        room = await obj_mgr.get_object(room_id)
        if not room or room.type != ObjectType.ROOM:
            continue
        if not admin and "DARK" in _flags(room) and room_id != center_room_id:
            continue
        nodes.append({"id": room.id, "name": room.name,
                      "description": room.description or "No description", "type": "room"})
        for exit_obj in await obj_mgr.get_exits(room.id):
            if exit_obj.home_id is not None:
                edges.append({"id": exit_obj.id, "source": room.id, "target": exit_obj.home_id,
                              "name": exit_obj.name, "type": "exit"})
                queue.append((exit_obj.home_id, depth + 1))
    node_ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["target"] in node_ids]
    return {"nodes": nodes, "edges": edges, "center": center_room_id}


# ==================== ADMIN ====================

@router.get("/stats")
async def get_stats(admin: DBObject = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Server statistics (admin)."""
    stats = {}
    for obj_type in [ObjectType.ROOM, ObjectType.THING, ObjectType.EXIT, ObjectType.PLAYER]:
        result = await db.execute(select(func.count()).where(DBObject.type == obj_type))
        stats[obj_type.value.lower() + "s"] = result.scalar()
    result = await db.execute(select(func.count()).where(
        DBObject.type == ObjectType.PLAYER, DBObject.is_connected == True))  # noqa: E712
    stats["connected_players"] = result.scalar()
    return stats


@router.get("/admin/players")
async def admin_list_players(admin: DBObject = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBObject).where(DBObject.type == ObjectType.PLAYER).order_by(DBObject.id))
    return [{"id": p.id, "name": p.name, "is_connected": bool(p.is_connected),
             "pending": auth.PENDING_FLAG in _flags(p), "is_admin": auth.is_admin(p),
             "site_account_id": p.site_account_id,
             "created_at": p.created_at.isoformat() if p.created_at else ""}
            for p in result.scalars().all()]


@router.post("/admin/players/{player_id}/approve", dependencies=[Depends(same_origin)])
async def admin_approve(player_id: int, admin: DBObject = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    target = await db.get(DBObject, player_id)
    if not target or target.type != ObjectType.PLAYER:
        raise HTTPException(status_code=404, detail="Player not found")
    target.flags = ",".join(sorted(_flags(target) - {auth.PENDING_FLAG}))
    await db.commit()
    return {"approved": True, "id": target.id}


@router.post("/admin/players/{player_id}/link-account", dependencies=[Depends(same_origin)])
async def admin_link_account(player_id: int, body: LinkAccountRequest, admin: DBObject = Depends(require_admin),
                             db: AsyncSession = Depends(get_db)):
    """Data hook: link (or unlink with null) a character to a Nova Games site account id."""
    target = await db.get(DBObject, player_id)
    if not target or target.type != ObjectType.PLAYER:
        raise HTTPException(status_code=404, detail="Player not found")
    target.site_account_id = body.site_account_id or None
    await db.commit()
    return {"id": target.id, "site_account_id": target.site_account_id}


@router.get("/admin/ai")
async def admin_ai_status(admin: DBObject = Depends(require_admin)):
    from backend.engine.ai_manager import ai_manager
    return ai_manager.get_status()
