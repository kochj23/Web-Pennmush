"""
Web-Pennmush AI Manager
Author: Jordan Koch (GitHub: kochj23)

NPC dialogue via the Nova Games LLM relay (template `mush.npc`). The server
never talks to Ollama/MLX/Nova directly: it enqueues a template job that the
relay pulls (see backend/relay.py). Every failure path - relay not configured,
queue full, timeout, quota, relay fallback - degrades to a scripted line.
"""
import random
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.relay import RelayJobQueue


class AIBackend(str, Enum):
    """Available AI backends"""
    RELAY = "relay"
    NONE = "none"


NPC_MAX_TOKENS = 150

# Contract var caps for template mush.npc
_CAPS = {"npc_name": 40, "npc_description": 400, "room_name": 80, "player_name": 40, "player_says": 200}


def _clip(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    text = "".join(ch for ch in text if ch == "\n" or ch >= " ")
    return text[:limit]


class AIManager:
    """Builds bounded relay jobs for NPC lines and supplies scripted fallbacks."""

    def __init__(self, queue: Optional[RelayJobQueue] = None):
        from backend.config import settings
        self.settings = settings
        self.queue = queue or RelayJobQueue(max_pending=settings.AI_MAX_PENDING)
        self.backend = AIBackend.RELAY if settings.AI_BACKEND == "relay" else AIBackend.NONE

    # ---------------- relay plumbing ----------------

    def relay_secret(self) -> str:
        return self.settings.RELAY_SECRET_MUSH if self.backend == AIBackend.RELAY else ""

    def is_available(self) -> bool:
        """True when a relay secret is configured (the relay may still be down)."""
        return bool(self.relay_secret())

    def get_status(self) -> Dict[str, Any]:
        return {
            "backend": self.backend.value if self.is_available() else AIBackend.NONE.value,
            "relay_configured": self.is_available(),
            "queue_depth": self.queue.depth,
            "stats": dict(self.queue.stats),
            "is_configured": self.is_available(),
        }

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

    async def npc_line(self, player_id: int, vars: Dict[str, Any]) -> str:
        """One NPC line from the relay, or a scripted fallback."""
        if not self.is_available():
            return self._generate_placeholder(vars.get("player_says", ""), vars.get("npc_name", "someone"))
        result = await self.queue.submit("mush.npc", vars, f"mush-{player_id}", NPC_MAX_TOKENS,
                                         timeout=self.settings.AI_RESULT_TIMEOUT_S)
        text = (result or {}).get("text") or ""
        status = (result or {}).get("status")
        if status in ("ok", "fallback") and text.strip():
            return text.strip()[:600]
        return self._generate_placeholder(vars.get("player_says", ""), vars.get("npc_name", "someone"))

    async def generate_response(self, prompt: str, personality: str = "a friendly local", knowledge_base: str = "",
                                model: str = None, temperature: float = 0.7, max_tokens: int = 150,
                                conversation_history: Optional[List[Dict[str, str]]] = None,
                                npc_name: str = "Someone", room_name: str = "", player_name: str = "",
                                player_id: int = 0) -> str:
        """Backward-compatible entry point (model/temperature are decided by the relay)."""
        history = []
        for msg in (conversation_history or [])[-5:]:
            speaker = player_name or "Player" if msg.get("role") == "user" else npc_name
            history.append({"speaker": speaker, "text": msg.get("content", "")})
        desc = personality if not knowledge_base else f"{personality}. {knowledge_base}"
        vars = self.build_npc_vars(npc_name, desc, room_name, player_name or "Player", prompt, history)
        return await self.npc_line(player_id, vars)

    def _generate_placeholder(self, prompt: str, personality: str) -> str:
        """Scripted line used whenever the relay can't answer."""
        responses = [
            "Hmm. Give me a moment to think on that.",
            "The fog in my head is thick today. Ask me again later?",
            "Interesting. Tell me more about that.",
            "I've heard rumours, but nothing I'd stake my reputation on.",
            "Ah, a question for the ages. Perhaps the Plaza notice board knows.",
        ]
        return random.choice(responses)

    async def get_game_guidance(self, player_query: str, game_context: Dict[str, Any], model: str = None,
                                player_id: int = 0) -> str:
        """The in-game guide speaks through the same NPC template."""
        vars = self.build_npc_vars(
            "The Guide",
            "A patient, helpful guide to Web-Pennmush. Explains commands like look, say, pose, go, get, drop, "
            "inventory, who, help, channel/list, @create, @dig and @open in 2-3 sentences.",
            str(game_context.get("location", "unknown")), "Player", player_query, [])
        if not self.is_available():
            return "The guide is resting. Try 'help' or 'help <command>' for documentation."
        return await self.npc_line(player_id, vars)

    async def list_available_models(self) -> List[str]:
        """Models are chosen by the relay; the game does not pick them."""
        return []


# Global AI manager instance
ai_manager = AIManager()
