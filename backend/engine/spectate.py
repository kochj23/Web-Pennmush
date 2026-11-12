"""
Web-Pennmush spectator mode (+watch)
Author: Jordan Koch (GitHub: kochj23)

The MUSH plays itself: active NPCs wander through exits, emote and talk to each
other while spectators watch read-only. NPC lines use the same relay path as
`talk` (ai_manager.npc_reply, template mush.npc) under one shared relay identity
(`mush-watch`), with scripted lines whenever AI is off, opted out or unavailable.

Bounds: one scene task, one turn in flight, at most `watch_turn` turns per minute
and `watch_ai` relay jobs per 10 minutes (security.rate_limiter, kept under the
relay's 30 jobs/10 min per player). The task stops by itself when the last
spectator leaves. Nothing here touches play_log: spectating and the autonomous
scene are never written to Nova Games play history.
"""
import asyncio
import random
from collections import deque
from typing import Deque, Dict, Optional, Tuple

from sqlalchemy import select

from backend.models import NPC, DBObject, ObjectType

PACES = {"slow": 20.0, "normal": 10.0, "fast": 5.0}  # seconds between turns
RELAY_ID = "watch"  # relay job player_id becomes "mush-watch"

_EMOTES = [
    "looks around thoughtfully.",
    "hums a few bars of an old tune.",
    "stretches and stifles a yawn.",
    "studies the surroundings with quiet interest.",
    "mutters something under their breath.",
    "checks their pockets, then nods to themselves.",
]
_CHATTER = [
    "Quiet today, isn't it?",
    "I heard someone found something strange near the portal.",
    "Have you been to the far rooms lately? Everything feels different.",
    "If you ask me, the crystal hums louder at night.",
    "Busy, busy. Always somewhere to be.",
    "Tell me, what brings you here?",
]
# Default cast, created once (owner #1) only when the world has no NPCs at all.
_CAST = [
    ("Mira", "A curious cartographer who maps every room and loves gossip about new exits."),
    ("Old Tobin", "A grumpy retired guard who has seen everything and approves of nothing."),
    ("Pip", "A cheerful courier who is always in a hurry and talks too fast."),
]


class SceneDirector:
    """Shared autonomous NPC scene. Spectators: player_id -> (websocket, NO_AI opt-out)."""

    def __init__(self, rng: Optional[random.Random] = None):
        self.spectators: Dict[int, Tuple[object, bool]] = {}
        self.pace = "normal"
        self.home_room: Optional[int] = None
        self.task: Optional[asyncio.Task] = None
        self.history: Dict[int, Deque[dict]] = {}
        self.rng = rng or random.Random()

    # ---------------- spectators ----------------

    def state(self, watching: bool = True) -> dict:
        return {"type": "watch", "watching": watching, "pace": self.pace, "spectators": len(self.spectators)}

    async def add(self, player_id: int, websocket, opted_out: bool, room_id: Optional[int]):
        self.spectators[player_id] = (websocket, opted_out)
        if room_id is not None:
            self.home_room = room_id
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._loop())
        await websocket.send_json(self.state())

    def remove(self, player_id: int, websocket=None):
        cur = self.spectators.get(player_id)
        if cur and (websocket is None or cur[0] is websocket):
            del self.spectators[player_id]
        if not self.spectators and self.task is not None and not self.task.done():
            self.task.cancel()  # auto-stop: nobody is watching

    def set_pace(self, pace: str) -> bool:
        if pace not in PACES:
            return False
        self.pace = pace
        return True

    async def _send(self, line: str):
        for pid, (ws, _) in list(self.spectators.items()):
            try:
                await ws.send_json({"type": "output", "message": line})
            except Exception:
                self.remove(pid, ws)

    async def _loop(self):
        from backend.security import rate_limiter
        while self.spectators:
            await asyncio.sleep(PACES[self.pace])
            if not self.spectators:
                break
            if not rate_limiter.is_allowed("scene", "watch_turn"):
                continue
            try:
                line = await self.turn()
            except asyncio.CancelledError:
                raise
            except Exception:
                line = None
            if line:
                await self._send(line)

    # ---------------- one turn ----------------

    async def turn(self) -> Optional[str]:
        """Pick an active NPC and have it move, emote or speak. Returns the line spectators see."""
        from backend.database import AsyncSessionLocal
        from backend.engine.objects import ObjectManager
        async with AsyncSessionLocal() as session:
            om = ObjectManager(session)
            if await self._seed_cast(session, om):
                return "A few locals wander in. The scene begins..."
            rows = (await session.execute(
                select(NPC, DBObject).join(DBObject, NPC.object_id == DBObject.id)
                .where(NPC.is_active.is_(True), DBObject.location_id.isnot(None),
                       DBObject.type != ObjectType.GARBAGE))).all()
            if not rows:
                return None
            npc, obj = self.rng.choice(rows)
            room = await om.get_object(obj.location_id)
            room_name = room.name if room else "somewhere"
            others = [o.name for _, o in rows if o.location_id == obj.location_id and o.id != obj.id]
            roll = self.rng.random()
            if roll < 0.2:
                exits = [e for e in await om.get_exits(obj.location_id) if e.home_id is not None]
                if exits:
                    ex = self.rng.choice(exits)
                    if await om.move_object(obj.id, ex.home_id):
                        return f"[{room_name}] {obj.name} leaves through {ex.name}."
            if roll < 0.45:
                return f"[{room_name}] {obj.name} {self.rng.choice(_EMOTES)}"
            name, desc = obj.name, " ".join(filter(None, [npc.personality, npc.knowledge_base]))
            no_ai = om.has_flag(obj, "NO_AI")
            room_id = obj.location_id
        # Speak (DB session closed: a relay wait must not hold a pooled connection)
        partner = self.rng.choice(others) if others else None
        hist = self.history.setdefault(room_id, deque(maxlen=5))
        last = hist[-1] if hist else None
        prompt = (last["text"] if last and last["speaker"] != name
                  else f"{partner} is here. Say something to them." if partner
                  else "You are alone. Think aloud about this place.")
        text = await self._line(name, desc, room_name, partner or "the room", prompt, list(hist), no_ai)
        hist.append({"speaker": name, "text": text})
        return f'[{room_name}] {name} says{" to " + partner if partner else ""}, "{text}"'

    async def _line(self, name, desc, room_name, partner, prompt, hist, no_ai) -> str:
        """Relay line when AI is allowed for everyone watching and within budget; scripted otherwise."""
        from backend.engine.ai_manager import ai_manager, SOURCE_SCRIPTED
        from backend.security import rate_limiter
        if (not no_ai and not any(opt for _, opt in self.spectators.values()) and ai_manager.is_healthy()
                and rate_limiter.is_allowed("scene", "watch_ai")):
            reply = await ai_manager.npc_reply(RELAY_ID, ai_manager.build_npc_vars(
                name, desc, room_name, partner, prompt, hist))
            if reply.source != SOURCE_SCRIPTED:
                return reply.text
        return self.rng.choice(_CHATTER)

    async def _seed_cast(self, session, om) -> bool:
        """Create the default cast once, in the spectator's room, when the world has no NPCs at all."""
        if self.home_room is None or (await session.execute(select(NPC.id).limit(1))).first():
            return False
        if not await om.get_object(self.home_room):
            return False
        for name, personality in _CAST:
            obj = await om.create_object(name=name, obj_type=ObjectType.THING, owner_id=1,
                                         location_id=self.home_room, description=personality,
                                         flags="VISIBLE,NPC")
            session.add(NPC(object_id=obj.id, personality=personality, knowledge_base="", is_active=True))
        await session.commit()
        return True


director = SceneDirector()
