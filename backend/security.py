"""
Web-Pennmush Security Module
Author: Jordan Koch (GitHub: kochj23)

Security utilities including rate limiting, input validation, and protection.
"""
from typing import Optional, Dict
from datetime import datetime, timedelta
from collections import OrderedDict, deque
import html
import re
import time


class RateLimiter:
    """
    In-memory sliding-window rate limiter.

    Previously this persisted to a JSON file on every call (a synchronous disk
    write per command - a DoS amplifier). State is now process memory only:
    a restart clears it, which is acceptable because the proxy and the
    per-IP connection caps bound abuse anyway. Memory is bounded by MAX_KEYS
    (oldest-touched keys are evicted first).
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


class SecurityLogger:
    """
    Logs security-relevant events.
    In production, send to proper logging system (ELK, Splunk, etc.)
    """

    @staticmethod
    def log_failed_login(username: str, ip: str):
        """Log failed login attempt"""
        print(f"[SECURITY] Failed login: username={username}, ip={ip}, time={datetime.utcnow()}")

    @staticmethod
    def log_rate_limit_exceeded(key: str, limit_type: str):
        """Log rate limit violation"""
        print(f"[SECURITY] Rate limit exceeded: key={key}, type={limit_type}, time={datetime.utcnow()}")

    @staticmethod
    def log_suspicious_input(input_type: str, content: str, player_id: Optional[int] = None):
        """Log suspicious input detected"""
        print(f"[SECURITY] Suspicious input: type={input_type}, player={player_id}, content={content[:100]}, time={datetime.utcnow()}")

    @staticmethod
    def log_command_execution(player_id: int, command: str):
        """Log command execution (verbose, for debugging)"""
        # Only log in debug mode to avoid spam
        # print(f"[DEBUG] Command: player={player_id}, command={command[:50]}, time={datetime.utcnow()}")
        pass

    @staticmethod
    def log_admin_action(player_id: int, action: str):
        """Log admin command execution"""
        print(f"[AUDIT] Admin action: player={player_id}, action={action}, time={datetime.utcnow()}")


# Global instances
rate_limiter = RateLimiter()
input_validator = InputValidator()
security_logger = SecurityLogger()
