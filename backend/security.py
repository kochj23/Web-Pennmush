"""
Web-Pennmush Security Module
Author: Jordan Koch (GitHub: kochj23)

Security utilities including rate limiting, input validation, and protection.
"""
from typing import Optional, Dict
from collections import OrderedDict, deque
import html
import logging
import re
import time


class RateLimiter:
    """
    Sliding-window rate limiter, decided in process memory.

    Login and registration limits (PERSISTENT) also survive a restart: their
    counted hits are written to the `rate_limit_hits` table through the async
    check()/areset() API and reloaded by load() at startup, so restarting (or
    crashing) the server does not hand a password guesser a fresh budget. One
    small insert per attempt is cheap next to the bcrypt verify every attempt
    already costs. All other limits (commands, API, WebSocket, AI) stay
    memory-only: they are per-second abuse brakes where a write per call would
    be the amplifier. Memory is bounded by MAX_KEYS (oldest keys evicted).
    """

    MAX_KEYS = 50000

    def __init__(self, persist_path: Optional[str] = None):
        # persist_path is accepted for backward compatibility and ignored.
        self.requests: "OrderedDict[str, deque]" = OrderedDict()
        self.limits = {
            "login": (5, 60),  # 5 attempts per 60 seconds (legacy key)
            "login_ip": (20, 600),  # 20 login attempts per IP per 10 min
            "login_user": (10, 600),  # 10 attempts per account per 10 min
            "register_ip": (3, 3600),  # 3 registrations per IP per hour
            "ws_connect_ip": (20, 60),  # 20 WebSocket handshakes per IP per minute
            "command": (30, 60),  # 30 commands per 60 seconds
            "api": (100, 60),  # 100 API requests per 60 seconds
            "channel": (10, 60),  # 10 channel messages per 60 seconds
            "ai": (5, 60),  # 5 AI requests per 60 seconds
            "ai_hour": (20, 3600),  # 20 NPC lines per player per hour
            "watch_turn": (6, 60),  # autonomous +watch scene: 6 NPC turns per minute
            "watch_ai": (20, 600),  # +watch relay jobs per 10 min (relay allows 30 per player)
        }

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    def _window(self, identifier: str, window_seconds: float, now: float) -> deque:
        q = self.requests.get(identifier)
        if q is None:
            q = deque()
            self.requests[identifier] = q
            if len(self.requests) > self.MAX_KEYS:
                self.requests.popitem(last=False)
        else:
            self.requests.move_to_end(identifier)
        cutoff = now - window_seconds
        while q and q[0] <= cutoff:
            q.popleft()
        return q

    def is_allowed(self, key: str, limit_type: str = "command") -> bool:
        """
        Check if request is allowed under rate limit (and record it if so).

        Args:
            key: Identifier (player_id, IP address, etc.)
            limit_type: Type of limit (see self.limits)

        Returns:
            True if allowed, False if rate limit exceeded
        """
        if limit_type not in self.limits:
            return True
        max_requests, window_seconds = self.limits[limit_type]
        now = self._now()
        q = self._window(f"{limit_type}:{key}", window_seconds, now)
        if len(q) >= max_requests:
            return False
        q.append(now)
        return True

    def get_remaining(self, key: str, limit_type: str = "command") -> int:
        """Get remaining requests in current window"""
        if limit_type not in self.limits:
            return 999
        max_requests, window_seconds = self.limits[limit_type]
        identifier = f"{limit_type}:{key}"
        if identifier not in self.requests:
            return max_requests
        q = self._window(identifier, window_seconds, self._now())
        return max(0, max_requests - len(q))

    def reset(self, key: str, limit_type: str = "command"):
        """Reset rate limit for a key"""
        self.requests.pop(f"{limit_type}:{key}", None)

    def clear(self):
        """Drop all state (tests / admin)."""
        self.requests.clear()

    # ---------------- persistence (login / registration only) ----------------
    # Memory stays the decision point (and the fallback if the DB is down);
    # every counted hit of a PERSISTENT type is also written to
    # rate_limit_hits, and startup reloads the hits still inside their window.

    PERSISTENT = ("login_ip", "login_user", "register_ip")
    PRUNE_EVERY = 200

    async def check(self, db, key: str, limit_type: str) -> bool:
        """is_allowed() plus a durable record of the hit for PERSISTENT types."""
        allowed = self.is_allowed(key, limit_type)
        if allowed and limit_type in self.PERSISTENT:
            await self._persist(db, "add", f"{limit_type}:{key}")
        return allowed

    async def areset(self, db, key: str, limit_type: str):
        """reset() in memory and in the database."""
        self.reset(key, limit_type)
        if limit_type in self.PERSISTENT:
            await self._persist(db, "reset", f"{limit_type}:{key}")

    def _max_window(self) -> float:
        return max(self.limits[t][1] for t in self.PERSISTENT)

    async def _persist(self, db, op: str, bucket: str):
        """Write on a short session of its own, so the caller's transaction is untouched."""
        from sqlalchemy import delete
        from sqlalchemy.ext.asyncio import AsyncSession
        from backend.models import RateLimitHit
        try:
            async with AsyncSession(db.bind, expire_on_commit=False) as s:
                if op == "add":
                    s.add(RateLimitHit(bucket=bucket[:160], hit_at=time.time()))
                    self._writes = getattr(self, "_writes", 0) + 1
                    if self._writes % self.PRUNE_EVERY == 0:
                        await s.execute(delete(RateLimitHit).where(
                            RateLimitHit.hit_at < time.time() - self._max_window()))
                else:
                    await s.execute(delete(RateLimitHit).where(RateLimitHit.bucket == bucket[:160]))
                await s.commit()
        except Exception as exc:  # never fail a login because the counter could not be stored
            logging.getLogger("webpennmush.security").warning(
                "rate limit hit not persisted (%s); memory limit still applies", type(exc).__name__)

    async def load(self, session_factory) -> int:
        """Startup: prune expired rows and reload live hits into memory. Returns hits loaded."""
        from sqlalchemy import delete, select
        from backend.models import RateLimitHit
        wall, mono = time.time(), self._now()
        loaded = 0
        async with session_factory() as s:
            await s.execute(delete(RateLimitHit).where(RateLimitHit.hit_at < wall - self._max_window()))
            rows = (await s.execute(select(RateLimitHit.bucket, RateLimitHit.hit_at)
                                    .order_by(RateLimitHit.hit_at))).all()
            await s.commit()
        for bucket, hit_at in rows:
            limit_type = bucket.split(":", 1)[0]
            if limit_type not in self.PERSISTENT or hit_at <= wall - self.limits[limit_type][1]:
                continue
            q = self._window(bucket, self.limits[limit_type][1], mono)
            q.append(mono - max(0.0, wall - hit_at))  # wall-clock age -> monotonic timestamp
            loaded += 1
        return loaded


class InputValidator:
    """Validates and sanitizes user input"""

    # Maximum lengths for various inputs
    MAX_NAME_LENGTH = 100
    MAX_DESCRIPTION_LENGTH = 4000
    MAX_COMMAND_LENGTH = 8192
    MAX_MESSAGE_LENGTH = 2000

    # Allowed characters in names (alphanumeric, space, dash, underscore)
    NAME_PATTERN = re.compile(r'^[a-zA-Z0-9 \-_]+$')

    # Detect potential SQL injection (belt and suspenders - we use ORM)
    SQL_INJECTION_PATTERN = re.compile(
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)|"
        r"(--)|"
        r"(/\*)|"
        r"(\*/)|"
        r"(;)",
        re.IGNORECASE
    )

    # Detect script tags and event handlers (XSS)
    XSS_PATTERN = re.compile(
        r"(<script|javascript:|onerror=|onload=|onclick=|<iframe)",
        re.IGNORECASE
    )

    @staticmethod
    def validate_name(name: str) -> tuple[bool, Optional[str]]:
        """
        Validate object/player name.

        Returns:
            (is_valid, error_message)
        """
        if not name or not name.strip():
            return False, "Name cannot be empty"

        if len(name) > InputValidator.MAX_NAME_LENGTH:
            return False, f"Name too long (max {InputValidator.MAX_NAME_LENGTH} characters)"

        if not InputValidator.NAME_PATTERN.match(name):
            return False, "Name contains invalid characters (use only letters, numbers, spaces, hyphens, underscores)"

        # Check for suspicious patterns
        if InputValidator.SQL_INJECTION_PATTERN.search(name):
            return False, "Name contains suspicious content"

        return True, None

    @staticmethod
    def validate_description(description: str) -> tuple[bool, Optional[str]]:
        """Validate description text"""
        if len(description) > InputValidator.MAX_DESCRIPTION_LENGTH:
            return False, f"Description too long (max {InputValidator.MAX_DESCRIPTION_LENGTH} characters)"

        # Check for XSS attempts
        if InputValidator.XSS_PATTERN.search(description):
            return False, "Description contains suspicious content"

        return True, None

    @staticmethod
    def validate_command(command: str) -> tuple[bool, Optional[str]]:
        """Validate command input"""
        if len(command) > InputValidator.MAX_COMMAND_LENGTH:
            return False, f"Command too long (max {InputValidator.MAX_COMMAND_LENGTH} characters)"

        return True, None

    @staticmethod
    def validate_message(message: str) -> tuple[bool, Optional[str]]:
        """Validate chat/channel message"""
        if len(message) > InputValidator.MAX_MESSAGE_LENGTH:
            return False, f"Message too long (max {InputValidator.MAX_MESSAGE_LENGTH} characters)"

        # Check for XSS attempts
        if InputValidator.XSS_PATTERN.search(message):
            return False, "Message contains suspicious content"

        return True, None

    @staticmethod
    def sanitize_output(text: str) -> str:
        """
        Sanitize text for safe display.
        Escapes HTML entities to prevent XSS.
        """
        return html.escape(text)

    @staticmethod
    def sanitize_ai_prompt(prompt: str) -> str:
        """
        Sanitize AI prompt to prevent prompt injection.

        Detects common jailbreak attempts:
        - "Ignore previous instructions"
        - "Disregard all above"
        - "Forget your role"
        - etc.
        """
        # Common jailbreak phrases
        jailbreak_patterns = [
            r"ignore\s+(previous|all|prior|above)",
            r"disregard\s+(previous|all|prior|above)",
            r"forget\s+(your|the)\s+(role|instructions|rules)",
            r"new\s+instructions",
            r"system\s+prompt",
            r"reveal\s+your\s+(prompt|instructions|system)",
            r"you\s+are\s+now",
            r"act\s+as\s+if",
            r"pretend\s+(to\s+be|you\s+are)",
        ]

        prompt_lower = prompt.lower()
        for pattern in jailbreak_patterns:
            if re.search(pattern, prompt_lower):
                # Detected jailbreak attempt - sanitize aggressively
                return "[Sanitized: potential prompt injection detected]"

        # Limit prompt length to prevent token exhaustion attacks
        if len(prompt) > 1000:
            return prompt[:1000] + "... [truncated]"

        return prompt


_SECRET_FIELD = re.compile(r"(?i)pass(word|wd)?|pwd|token|secret|authorization|cookie|api[_-]?key")
# Inline secrets inside free text: "password=...", "Bearer ...", "connect <name> <password>",
# and our own session tokens (base64url payload "." base64url HMAC).
_SECRET_TEXT = [
    (re.compile(r"(?i)\b(pass(word|wd)?|pwd|token|secret|api[_-]?key)\b(\s*[=:]\s*|\s+)\S+"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)\bbearer\s+\S+"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)^(\s*connect\s+\S+\s+)\S+"), r"\1[REDACTED]"),
    (re.compile(r"[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{20,}"), "[REDACTED]"),
]
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def redact(value, limit: int = 100) -> str:
    """Make a value safe for a log line: no secrets, no control chars (log injection), bounded."""
    text = str(value)[:max(limit * 4, 400)]
    for pattern, repl in _SECRET_TEXT:
        text = pattern.sub(repl, text)
    text = _CONTROL.sub("?", text)
    return text[:limit]


class SecurityLogger:
    """
    Structured security events on the `webpennmush.security` logger (admin
    actions on `webpennmush.audit`). Each record has a readable message
    `security event=<name> k=v ...` and the same fields as a dict in
    `record.security_event`, for a JSON formatter or log shipper.

    Passwords and tokens are never logged: fields with secret-looking names
    are dropped to [REDACTED], and free text goes through redact().
    """

    log = logging.getLogger("webpennmush.security")
    audit = logging.getLogger("webpennmush.audit")

    @classmethod
    def event(cls, name: str, level: int = logging.WARNING, logger: Optional[logging.Logger] = None, **fields):
        clean = {"event": name}
        for k, v in fields.items():
            if v is None:
                continue
            clean[k] = "[REDACTED]" if _SECRET_FIELD.search(k) else (v if isinstance(v, (int, bool)) else redact(v))
        line = " ".join(f"{k}={v!r}" if isinstance(v, str) else f"{k}={v}" for k, v in clean.items())
        (logger or cls.log).log(level, "security %s", line, extra={"security_event": clean})
        return clean

    @classmethod
    def log_failed_login(cls, username: Optional[str], ip: str, player_id: Optional[int] = None,
                         reason: Optional[str] = None):
        """Failed login. Callers pass the player id when known; the password is never a parameter."""
        cls.event("failed_login", logging.INFO, username=username, ip=ip, player=player_id, reason=reason)

    @classmethod
    def log_rate_limit_exceeded(cls, key: str, limit_type: str):
        cls.event("rate_limited", key=key, limit=limit_type)

    @classmethod
    def log_suspicious_input(cls, input_type: str, content: str, player_id: Optional[int] = None):
        cls.event("suspicious_input", input_type=input_type, player=player_id, content=content)

    @classmethod
    def log_command_execution(cls, player_id: int, command: str):
        """Per-command trace, DEBUG only (spam otherwise)."""
        if cls.log.isEnabledFor(logging.DEBUG):
            cls.event("command", logging.DEBUG, player=player_id, command=redact(command, 50))

    @classmethod
    def log_admin_action(cls, player_id: int, action: str):
        cls.event("admin_action", logging.INFO, cls.audit, player=player_id, action=action)


# Global instances
rate_limiter = RateLimiter()
input_validator = InputValidator()
security_logger = SecurityLogger()
