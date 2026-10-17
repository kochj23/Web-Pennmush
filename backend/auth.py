"""
Web-Pennmush authentication
Author: Jordan Koch (GitHub: kochj23)

- Session tokens: HMAC-SHA256 signed, expiring, stdlib only. Carried as an
  HttpOnly SameSite=Strict cookie (browser) or `Authorization: Bearer` (tools).
- Login is rate limited per client IP and per account, with constant-ish time
  for unknown users, and shared by REST and WebSocket logins.
- Client IP honours X-Forwarded-For only when the direct peer is a trusted proxy.
"""
import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.models import DBObject, ObjectType
from backend.passwords import pwd_context
from backend.security import rate_limiter, input_validator

log = logging.getLogger("webpennmush.auth")

COOKIE_NAME = "mush_session"
PENDING_FLAG = "PENDING"
ADMIN_FLAGS = {"GOD", "WIZARD", "ROYAL"}

_ephemeral_key: Optional[bytes] = None


def _secret() -> bytes:
    """SECRET_KEY from the environment; a random per-process key if unset (dev)."""
    global _ephemeral_key
    if settings.SECRET_KEY and settings.SECRET_KEY != "your-secret-key-change-this-in-production":
        return settings.SECRET_KEY.encode("utf-8")
    if _ephemeral_key is None:
        _ephemeral_key = secrets.token_bytes(32)
        log.warning("SECRET_KEY not set: using an ephemeral key (sessions reset on restart)")
    return _ephemeral_key


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def issue_token(player_id: int, ttl_seconds: Optional[int] = None, now: Optional[float] = None) -> str:
    """Create a signed session token for a player."""
    now = time.time() if now is None else now
    ttl = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60 if ttl_seconds is None else ttl_seconds
    payload = _b64(json.dumps({"pid": int(player_id), "exp": int(now + ttl),
                               "n": secrets.token_hex(4)}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify_token(token: str, now: Optional[float] = None) -> Optional[int]:
    """Return the player id for a valid, unexpired token, else None."""
    if not token or len(token) > 512 or token.count(".") != 1:
        return None
    payload, sig = token.split(".")
    expected = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(_unb64(payload))
        pid, exp = int(data["pid"]), int(data["exp"])
    except (ValueError, KeyError, TypeError):
        return None
    if (time.time() if now is None else now) >= exp:
        return None
    return pid


def _trusted(peer: str) -> bool:
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError:
        return False
    for cidr in settings.TRUSTED_PROXIES:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def client_ip_from(peer: Optional[str], forwarded_for: Optional[str]) -> str:
    """Resolve the real client IP (rightmost untrusted hop of X-Forwarded-For)."""
    peer = peer or "unknown"
    if forwarded_for and _trusted(peer):
        hops = [h.strip() for h in forwarded_for.split(",") if h.strip()]
        for hop in reversed(hops):
            if not _trusted(hop):
                return hop[:64]
        if hops:
            return hops[0][:64]
    return peer


def client_ip(conn) -> str:
    """Client IP for a Request or WebSocket."""
    peer = conn.client.host if conn.client else None
    return client_ip_from(peer, conn.headers.get("x-forwarded-for"))


def is_admin(player: DBObject) -> bool:
    flags = {f.strip().upper() for f in (player.flags or "").split(",") if f.strip()}
    return bool(flags & ADMIN_FLAGS)


def is_pending(player: DBObject) -> bool:
    flags = {f.strip().upper() for f in (player.flags or "").split(",") if f.strip()}
    return PENDING_FLAG in flags


@dataclass
class LoginResult:
    ok: bool
    player: Optional[DBObject] = None
    error: str = ""
    status: int = 200


async def authenticate(db: AsyncSession, username: str, password: str, ip: str) -> LoginResult:
    """Shared login check for REST and WebSocket. Never reveals which part was wrong."""
    if not username or not password or len(username) > 100 or len(password) > 1024:
        return LoginResult(False, error="Username and password required", status=400)
    if not rate_limiter.is_allowed(ip, "login_ip"):
        return LoginResult(False, error="Too many login attempts. Please wait a few minutes.", status=429)
    if not rate_limiter.is_allowed(username.lower(), "login_user"):
        return LoginResult(False, error="Too many login attempts. Please wait a few minutes.", status=429)
    ok, _ = input_validator.validate_name(username)
    if not ok:
        return LoginResult(False, error="Invalid username or password", status=401)

    from backend.engine.objects import ObjectManager
    player = await ObjectManager(db).get_player_by_exact_name(username)
    if not player or not player.password_hash:
        await _dummy_verify()
        log.info("failed login (unknown user) from %s", ip)
        return LoginResult(False, error="Invalid username or password", status=401)
    if not await pwd_context.averify(password, player.password_hash):
        log.info("failed login for #%s from %s", player.id, ip)
        return LoginResult(False, error="Invalid username or password", status=401)
    if is_pending(player):
        return LoginResult(False, error="Your account is awaiting admin approval.", status=403)
    from backend.engine.moderation import ModerationManager
    banned, _ban = await ModerationManager(db).is_banned(player.id)
    if banned:
        return LoginResult(False, error="This account is banned.", status=403)
    rate_limiter.reset(username.lower(), "login_user")
    return LoginResult(True, player=player)


async def _dummy_verify():
    import asyncio
    await asyncio.to_thread(pwd_context.dummy_verify)


def _token_from_request(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(COOKIE_NAME)


async def current_player(request: Request, db: AsyncSession = Depends(get_db)) -> DBObject:
    """FastAPI dependency: the logged-in player or 401."""
    pid = verify_token(_token_from_request(request) or "")
    if pid is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    player = await db.get(DBObject, pid)
    if not player or player.type != ObjectType.PLAYER or is_pending(player):
        raise HTTPException(status_code=401, detail="Authentication required")
    if not rate_limiter.is_allowed(str(pid), "api"):
        raise HTTPException(status_code=429, detail="Too many requests")
    return player


async def require_admin(player: DBObject = Depends(current_player)) -> DBObject:
    """FastAPI dependency: an admin (GOD/WIZARD/ROYAL) or 403."""
    if not is_admin(player):
        raise HTTPException(status_code=403, detail="Admin role required")
    return player
