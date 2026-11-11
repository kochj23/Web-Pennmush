"""
Web-Pennmush AI Manager
Author: Jordan Koch (GitHub: kochj23)

NPC dialogue and the in-game guide via the Nova Games LLM relay (template
`mush.npc`). The server never talks to a model: it enqueues a template job
that the relay pulls (see backend/relay.py). There are no model clients, API
keys or outbound connections here.

Every failure path - AI switched off (server, staff toggle or player opt-out),
relay not configured or not polling, queue full, timeout, rejected or
nonsensical output - degrades to a scripted line, so play never blocks.
"""
import asyncio
import random
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.relay import RelayJobQueue


class AIBackend(str, Enum):
    """`AI_BACKEND` values. The relay is the only LLM path."""
    RELAY = "relay"
    NONE = "none"


NPC_MAX_TOKENS = 150
MAX_LINE_CHARS = 600
MAX_RETRIES = 3  # hard cap whatever AI_RETRIES says
PLAYER_OPT_OUT_FLAG = "NO_AI"

# Contract var caps for template mush.npc
_CAPS = {"npc_name": 40, "npc_description": 400, "room_name": 80, "player_name": 40, "player_says": 200}

# Where a reply came from
SOURCE_AI = "ai"                  # relay status ok, output passed validation
SOURCE_RELAY_FALLBACK = "relay-fallback"  # relay's own scripted text (busy, quota, model down, filtered)
SOURCE_SCRIPTED = "scripted"      # local scripted line

# Health states reported by get_status()
STATE_HEALTHY = "healthy"            # enabled, configured, relay polled within relay_stale_s
STATE_UNREACHABLE = "unreachable"    # enabled and configured, relay not polling
STATE_DISABLED = "disabled"          # staff switched AI off at runtime
STATE_NOT_CONFIGURED = "not_configured"  # AI_BACKEND=none or no RELAY_SECRET_MUSH

_ROLE_PREFIX = re.compile(r"^\s*(assistant|npc|system|narrator)\s*:\s*", re.IGNORECASE)
# Output that must never reach a player (prompt/template leakage, AI disclaimers)
_BAD_OUTPUT = re.compile(
    r"(as an ai\b|language model|<\|[a-z_]+\|>|\{(npc_name|npc_description|room_name|player_name|player_says|history)\}"
    r"|<<<|>>>|```)",
    re.IGNORECASE,
)

_SCRIPTED_LINES = [
    "Hmm. Give me a moment to think on that.",
    "The fog in my head is thick today. Ask me again later?",
    "Interesting. Tell me more about that.",
    "I've heard rumours, but nothing I'd stake my reputation on.",
    "Ah, a question for the ages. Perhaps the Plaza notice board knows.",
]

# Scripted guide: (keywords, answer). First match wins.
_GUIDE_ANSWERS = [
    (("room", "dig", "build"), "Use '@dig <room name>' to make a room, then '@open <exit>=<room #>' to connect it. "
                               "'@describe here=<text>' sets the description."),
    (("exit", "open", "link"), "Use '@open <exit name>=<room #>' to create an exit to an existing room."),
    (("create", "object", "thing", "item"), "Use '@create <name>' to make an object, 'drop <name>' to leave it here "
                                            "and '@describe <name>=<text>' to describe it."),
    (("talk", "npc", "ask"), "Use 'talk to <npc>=<message>' or 'ask <npc>=<question>' to speak with NPCs."),
    (("say", "chat", "speak", "player", "page"), "Use 'say <text>' (or \"text) to speak in the room, ':<action>' to "
                                                 "pose, and 'page <player>=<message>' to message someone."),
    (("channel",), "Use 'channel/list' to see channels and 'channel/join <name>' to join one."),
    (("move", "go", "walk", "where", "lost"), "Use 'look' to see the room and its exits, then type an exit name or "
                                              "'go <exit>' to move."),
    (("get", "take", "drop", "inventory", "carry"), "Use 'get <thing>', 'drop <thing>' and 'inventory' (or 'i')."),
    (("mail",), "Use '@mail <player>=<subject>/<message>', '@mail/list' and '@mail/read <#>'."),
    (("quest",), "Use 'quest/list' to see quests, 'quest/start <name>' to begin and 'quest/progress' to check."),
    (("money", "credit", "balance", "give"), "Use 'balance' to see your credits and 'give <player>=<amount>'."),
    (("softcode", "code", "function"), "Softcode is MUSHcode like [add(1,2)]. See SOFTCODE_REFERENCE.md or "
                                       "'help softcode'."),
    (("ai", "guide", "narrator"), "'@ai/status' shows whether AI replies are on. '@ai/me off' turns them off for you "
                                  "and '@ai/me on' turns them back on."),
]
_GUIDE_DEFAULT = "Try 'help' for the command list or 'help <command>' for details. 'look', 'say', 'go' and 'inventory' are good places to start."


def _clip(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    text = "".join(ch for ch in text if ch == "\n" or ch >= " ")
    return text[:limit]


@dataclass(frozen=True)
class AIReply:
    """A line for the player plus where it came from."""
    text: str
    source: str
    reason: str = ""

    @property
    def is_ai(self) -> bool:
        return self.source == SOURCE_AI


def validate_output(text: Any, max_chars: int = MAX_LINE_CHARS) -> Optional[str]:
    """Sanity-check model output before it reaches a player or the stored history.

    Returns a cleaned single line, or None when the text must be replaced by a fallback.
    """
    if not isinstance(text, str):
        return None
    cleaned = "".join(ch if ch >= " " else " " for ch in text)  # drops ESC/ANSI, NUL, CR, newlines
    cleaned = cleaned.replace("\x7f", "")
    cleaned = " ".join(cleaned.split())
    cleaned = _ROLE_PREFIX.sub("", cleaned)
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in "\"'":
        cleaned = cleaned[1:-1].strip()
    if _BAD_OUTPUT.search(cleaned):
        return None
    if sum(ch.isalpha() for ch in cleaned) < 2:
        return None
    if len(cleaned) > max_chars:
        cut = cleaned[:max_chars]
        space = cut.rfind(" ")
        cleaned = (cut[:space] if space > max_chars // 2 else cut).rstrip() + "..."
    return cleaned


def scripted_guide(query: str) -> str:
    """Keyword-matched guide answer used whenever the relay can't answer."""
    words = set(re.findall(r"[a-z]+", (query or "").lower()))
    for keys, answer in _GUIDE_ANSWERS:
        if any(k in words or k + "s" in words for k in keys):
            return answer
    return _GUIDE_DEFAULT


class AIManager:
    """Builds bounded relay jobs for NPC lines, validates results and supplies scripted fallbacks."""

    def __init__(self, queue: Optional[RelayJobQueue] = None, clock=time.monotonic):
        from backend.config import settings
        self.settings = settings
        self.queue = queue or RelayJobQueue(max_pending=settings.AI_MAX_PENDING)
        self.backend = AIBackend.RELAY if settings.AI_BACKEND == "relay" else AIBackend.NONE
        self.clock = clock
        self.enabled = True  # staff runtime toggle (@ai/on, @ai/off, POST /api/admin/ai)
        self.last_ok: Optional[float] = None
        self.stats = {"ai": 0, "relay_fallback": 0, "scripted": 0, "invalid_output": 0, "retries": 0}

    # ---------------- configuration and health ----------------

    def relay_secret(self) -> str:
        """Secret for the signed relay endpoints. Independent of the staff toggle so health stays visible."""
        return self.settings.RELAY_SECRET_MUSH if self.backend == AIBackend.RELAY else ""

    def is_configured(self) -> bool:
        return bool(self.relay_secret())

    def is_available(self) -> bool:
        """True when AI replies may be attempted (configured and switched on). The relay may still be down."""
        return self.enabled and self.is_configured()

    def is_healthy(self) -> bool:
        """True when AI replies are on and the relay is actually polling."""
        return self.is_available() and self.queue.relay_alive()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def state(self) -> str:
        if not self.is_configured():
            return STATE_NOT_CONFIGURED
        if not self.enabled:
            return STATE_DISABLED
        return STATE_HEALTHY if self.queue.relay_alive() else STATE_UNREACHABLE

    def get_status(self) -> Dict[str, Any]:
        now = self.clock()
        last_poll = self.queue.last_poll
        return {
            "backend": self.backend.value if self.is_configured() else AIBackend.NONE.value,
            "state": self.state(),
            "enabled": self.enabled,
            "relay_configured": self.is_configured(),
            "relay_alive": self.queue.relay_alive(),
            "healthy": self.is_healthy(),
            "last_poll_age_s": None if last_poll is None else round(self.queue.clock() - last_poll, 1),
            "last_ok_age_s": None if self.last_ok is None else round(now - self.last_ok, 1),
            "timeout_s": self.settings.AI_RESULT_TIMEOUT_S,
            "retries": self.settings.AI_RETRIES,
            "guide_enabled": self.settings.AI_ENABLE_GAME_GUIDE,
            "queue_depth": self.queue.depth,
            "stats": dict(self.queue.stats),
            "replies": dict(self.stats),
            "is_configured": self.is_configured(),
        }

    def fallback_hint(self, reply: AIReply) -> str:
        """Short player-visible note when a line did not come from the model ('' when it did)."""
        if reply.is_ai or reply.reason == "opted_out":
            return ""
        if reply.reason == "disabled":
            return "(scripted reply - AI narration is switched off)"
        return "(scripted reply - the narrator is away)"

    # ---------------- relay jobs ----------------

    @staticmethod
    def build_npc_vars(npc_name: str, npc_description: str, room_name: str, player_name: str,
                       player_says: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """Template vars for mush.npc, clipped to the contract caps."""
        hist = []
        for item in (history or [])[-5:]:
            hist.append({"speaker": _clip(item.get("speaker", ""), 40), "text": _clip(item.get("text", ""), 200)})
        return {
            "npc_name": _clip(npc_name, _CAPS["npc_name"]),
            "npc_description": _clip(npc_description, _CAPS["npc_description"]),
            "room_name": _clip(room_name, _CAPS["room_name"]),
            "player_name": _clip(player_name, _CAPS["player_name"]),
            "player_says": _clip(player_says, _CAPS["player_says"]),
            "history": hist,
        }

    def _unavailable_reason(self) -> str:
        if not self.is_configured():
            return "not_configured"
        return "disabled" if not self.enabled else ""

    def scripted(self, reason: str) -> AIReply:
        self.stats["scripted"] += 1
        return AIReply(self._generate_placeholder("", ""), SOURCE_SCRIPTED, reason)

    async def npc_reply(self, player_id: int, vars: Dict[str, Any]) -> AIReply:
        """One NPC line from the relay, or a fallback.

        AI_RESULT_TIMEOUT_S is the total budget. Within it, up to AI_RETRIES extra attempts are made for
        transient failures that return quickly (queue full, output that fails validation). A timeout uses
        the whole budget and is not retried; a dead relay answers at once.
        """
        why = self._unavailable_reason()
        if why:
            return self.scripted(why)
        deadline = self.clock() + self.settings.AI_RESULT_TIMEOUT_S
        attempts = 1 + min(MAX_RETRIES, max(0, int(self.settings.AI_RETRIES)))
        backoff = max(0.0, self.settings.AI_RETRY_BACKOFF_S)
        reason = "no_result"
        for attempt in range(attempts):
            remaining = deadline - self.clock()
            if remaining <= 0:
                reason = "timeout"
                break
            if attempt:
                self.stats["retries"] += 1
            result, reason = await self.queue.submit_detailed(
                "mush.npc", vars, f"mush-{player_id}", NPC_MAX_TOKENS, timeout=remaining)
            if result is None:
                if reason == "queue_full" and attempt + 1 < attempts:
                    await asyncio.sleep(min(backoff * (2 ** attempt), max(0.0, deadline - self.clock())))
                    continue
                break
            status = result.get("status")
            text = validate_output(result.get("text"))
            if status == "ok":
                if text:
                    self.stats["ai"] += 1
                    self.last_ok = self.clock()
                    return AIReply(text, SOURCE_AI)
                self.stats["invalid_output"] += 1
                reason = "invalid_output"
                continue
            if status == "fallback" and text:
                self.stats["relay_fallback"] += 1
                return AIReply(text, SOURCE_RELAY_FALLBACK, str(result.get("reason") or "relay_fallback")[:40])
            reason = str(status or "bad_result")[:40]
            break
        return self.scripted(reason)

    async def reply(self, prompt: str, personality: str = "a friendly local", knowledge_base: str = "",
                    conversation_history: Optional[List[Dict[str, str]]] = None, npc_name: str = "Someone",
                    room_name: str = "", player_name: str = "", player_id: int = 0) -> AIReply:
        """NPC reply from a chat-style history (role user/assistant)."""
        history = []
        for msg in (conversation_history or [])[-5:]:
            speaker = (player_name or "Player") if msg.get("role") == "user" else npc_name
            history.append({"speaker": speaker, "text": msg.get("content", "")})
        desc = personality if not knowledge_base else f"{personality}. {knowledge_base}"
        vars = self.build_npc_vars(npc_name, desc, room_name, player_name or "Player", prompt, history)
        return await self.npc_reply(player_id, vars)

    async def generate_response(self, prompt: str, **kwargs) -> str:
        """Text-only form of reply()."""
        return (await self.reply(prompt, **kwargs)).text

    def _generate_placeholder(self, prompt: str, personality: str) -> str:
        """Scripted line used whenever the relay can't answer."""
        return random.choice(_SCRIPTED_LINES)

    async def get_game_guidance(self, player_query: str, game_context: Dict[str, Any], player_id: int = 0) -> AIReply:
        """The in-game guide speaks through the same NPC template; scripted keyword answers otherwise."""
        why = "guide_disabled" if not self.settings.AI_ENABLE_GAME_GUIDE else self._unavailable_reason()
        if not why:
            vars = self.build_npc_vars(
                "The Guide",
                "A patient, helpful guide to Web-Pennmush. Explains commands like look, say, pose, go, get, drop, "
                "inventory, who, help, channel/list, @create, @dig and @open in 2-3 sentences.",
                str(game_context.get("location", "unknown")), "Player", player_query, [])
            got = await self.npc_reply(player_id, vars)
            if got.is_ai:
                return got
            why = got.reason
        # A generic NPC fallback line is no help to someone asking how to play: answer from the keyword table.
        return AIReply(scripted_guide(player_query), SOURCE_SCRIPTED, why)


# Global AI manager instance
ai_manager = AIManager()
