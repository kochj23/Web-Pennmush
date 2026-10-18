"""
Web-Pennmush play-history logger (Nova Games schema `play`)
Author: Jordan Koch (GitHub: kochj23)

One play.sessions row per authenticated WebSocket (game 'mush', client 'web',
player = character name) plus a few play.events rows for notable moments:
rooms entered, quests started/advanced/completed, credits earned/spent.
Says, poses and pages are only counted, never their text.

Rules: it must never block, slow down or break a command. Hooks only touch
memory; database writes run in background tasks on their own short
connection, errors are logged and swallowed, and unsent events are retried on
the next flush. Writes happen only on Postgres (the platform owns the `play`
tables; they are never part of Base.metadata / create_all). On SQLite every
call is an in-memory no-op as far as the database is concerned.
"""
import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from sqlalchemy import text

log = logging.getLogger("webpennmush.play")

GAME = "mush"
CLIENT = "web"
BUMP_INTERVAL_S = 30.0      # last_seen_at / actions bump at most this often
WRITE_TIMEOUT_S = 5.0       # one flush never holds a pooled connection longer
MAX_EVENTS = 300            # per session; counters keep counting after the cap
MAX_PENDING = 200           # unsent events kept across failed flushes
LIST_CAP = 50               # lists in the summary
TEXT_CAP = 120              # names in events / summary
END_RETRIES = 3

_UPSERT = text("""
INSERT INTO play.sessions (id, game, client, player, started_at, last_seen_at, ended_at, outcome, actions, summary)
VALUES (CAST(:id AS uuid), :game, :client, :player, :started_at, :last_seen_at, :ended_at, :outcome, :actions,
        CAST(:summary AS jsonb))
ON CONFLICT (id) DO UPDATE SET
  last_seen_at = GREATEST(play.sessions.last_seen_at, EXCLUDED.last_seen_at),
  actions = GREATEST(play.sessions.actions, EXCLUDED.actions),
  ended_at = EXCLUDED.ended_at, outcome = EXCLUDED.outcome, summary = EXCLUDED.summary
WHERE play.sessions.ended_at IS NULL
""")

_EVENT = text("""
INSERT INTO play.events (session_id, seq, ts, kind, detail)
VALUES (CAST(:sid AS uuid), :seq, :ts, :kind, CAST(:detail AS jsonb))
ON CONFLICT (session_id, seq) DO NOTHING
""")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clip(value) -> str:
    return str(value or "")[:TEXT_CAP]


class PlaySession:
    """In-memory state of one play session. All mutators are synchronous and cheap."""

    def __init__(self, player_id: int, player_name: str, start_room: Optional[str] = None):
        self.id = uuid.uuid4()
        self.player_id = player_id
        self.player = (str(player_name or "").strip() or f"#{player_id}")[:64]
        self.started_at = _now()
        self.last_seen_at = self.started_at
        self.ended_at: Optional[datetime] = None
        self.outcome: Optional[str] = None
        self.actions = 0
        self.start_room = _clip(start_room) or None
        self.end_room = self.start_room
        self.room_entries = 0
        self.rooms: List[str] = [self.start_room] if self.start_room else []
        self.quests_started: List[str] = []
        self.quests_completed: List[str] = []
        self.quest_steps = 0
        self.credits_earned = 0
        self.credits_spent = 0
        self.says = 0
        self.poses = 0
        self.pages = 0
        self.seq = 0
        self.pending: List[dict] = []
        self.dropped_events = 0
        self.last_flush = time.monotonic()
        self.lock = asyncio.Lock()
        self.task: Optional[asyncio.Task] = None   # the one in-flight flush (coalesces hooks)
        self.again = False

    # -- recording -----------------------------------------------------
    def _event(self, kind: str, **detail):
        self.last_seen_at = _now()
        if self.seq >= MAX_EVENTS:
            self.dropped_events += 1
            return
        self.pending.append({"sid": str(self.id), "seq": self.seq, "ts": self.last_seen_at, "kind": kind,
                             "detail": json.dumps(detail, separators=(",", ":"))})
        self.seq += 1
        if len(self.pending) > MAX_PENDING:  # DB unreachable for a long time: keep the newest
            self.dropped_events += len(self.pending) - MAX_PENDING
            del self.pending[:-MAX_PENDING]

    def room(self, name: str):
        name = _clip(name)
        self.room_entries += 1
        self.end_room = name
        if name not in self.rooms and len(self.rooms) < LIST_CAP:
            self.rooms.append(name)
        self._event("room", room=name)

    def quest(self, action: str, name: str, step: Optional[int] = None):
        name = _clip(name)
        if action == "started" and len(self.quests_started) < LIST_CAP:
            self.quests_started.append(name)
        elif action == "completed" and len(self.quests_completed) < LIST_CAP:
            self.quests_completed.append(name)
        elif action == "advanced":
            self.quest_steps += 1
        detail = {"action": action, "quest": name}
        if step is not None:
            detail["step"] = int(step)
        self._event("quest", **detail)

    def credits(self, amount: int, reason: str):
        amount = int(amount)
        if amount >= 0:
            self.credits_earned += amount
        else:
            self.credits_spent += -amount
        self._event("credits", amount=amount, reason=_clip(reason))

    def social(self, kind: str):
        if kind == "say":
            self.says += 1
        elif kind == "pose":
            self.poses += 1
        elif kind == "page":
            self.pages += 1

    def command(self):
        self.actions += 1
        self.last_seen_at = _now()

    # -- output --------------------------------------------------------
    def summary(self) -> dict:
        end = self.ended_at or self.last_seen_at
        s = {
            "character": self.player,
            "duration_s": max(0, int((end - self.started_at).total_seconds())),
            "commands": self.actions,
            "start_room": self.start_room,
            "end_room": self.end_room,
            "rooms_entered": self.room_entries,
            "unique_rooms": len(self.rooms),
            "rooms_visited": self.rooms,
            "quests_started": self.quests_started,
            "quests_completed": self.quests_completed,
            "quest_steps": self.quest_steps,
            "credits_earned": self.credits_earned,
            "credits_spent": self.credits_spent,
            "credits_delta": self.credits_earned - self.credits_spent,
            "says": self.says,
            "poses": self.poses,
            "pages": self.pages,
        }
        if self.outcome:
            s["outcome"] = self.outcome
        if self.dropped_events:
            s["events_dropped"] = self.dropped_events
        return s

    def row(self) -> dict:
        return {"id": str(self.id), "game": GAME, "client": CLIENT, "player": self.player,
                "started_at": self.started_at, "last_seen_at": max(self.last_seen_at, self.started_at),
                "ended_at": self.ended_at, "outcome": self.outcome, "actions": min(self.actions, 10_000_000),
                "summary": json.dumps(self.summary(), separators=(",", ":"))}


class PlayLog:
    """Registry of open play sessions (one per connected player) and the background writer."""

    def __init__(self, engine=None):
        self._engine = engine
        self.sessions: Dict[int, PlaySession] = {}
        self._tasks: Set[asyncio.Task] = set()

    @property
    def engine(self):
        if self._engine is None:
            from backend.database import engine
            return engine
        return self._engine

    @engine.setter
    def engine(self, value):
        self._engine = value

    @property
    def enabled(self) -> bool:
        try:
            return self.engine.dialect.name == "postgresql"
        except Exception:
            return False

    # -- lifecycle (called from the WebSocket handler) -----------------
    def start(self, player_id: int, player_name: str, start_room: Optional[str] = None) -> PlaySession:
        old = self.sessions.get(player_id)
        if old is not None:  # a newer login replaced the old socket
            self.end(old, "reconnected")
        s = PlaySession(player_id, player_name, start_room)
        self.sessions[player_id] = s
        self._kick(s)
        return s

    def command(self, s: Optional[PlaySession]):
        if s is None or s.ended_at is not None:
            return
        s.command()
        if time.monotonic() - s.last_flush >= BUMP_INTERVAL_S:
            s.last_flush = time.monotonic()
            self._kick(s)

    def end(self, s: Optional[PlaySession], outcome: str = "quit"):
        if s is None or s.ended_at is not None:
            return
        if self.sessions.get(s.player_id) is s:
            del self.sessions[s.player_id]
        s.ended_at = max(_now(), s.started_at)
        s.last_seen_at = max(s.last_seen_at, s.ended_at)
        s.outcome = outcome[:64]
        self._spawn(self._finish(s))

    async def close_all(self, outcome: str = "quit", timeout: float = 5.0):
        """App shutdown: end every open session and wait (bounded) for the writes."""
        for s in list(self.sessions.values()):
            self.end(s, outcome)
        await self.drain(timeout)

    async def drain(self, timeout: float = 5.0):
        tasks = [t for t in self._tasks if not t.done()]
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)

    # -- hooks (called from the engine; player may not be playing) -----
    def _get(self, player_id) -> Optional[PlaySession]:
        return self.sessions.get(player_id)

    def room(self, player_id: int, name: str):
        self._hook(player_id, "room", name)

    def quest(self, player_id: int, action: str, name: str, step: Optional[int] = None):
        self._hook(player_id, "quest", action, name, step)

    def credits(self, player_id: int, amount: int, reason: str):
        if amount:
            self._hook(player_id, "credits", amount, reason)

    def social(self, player_id: int, kind: str):
        s = self._get(player_id)
        if s is not None:
            s.social(kind)

    def _hook(self, player_id, method, *args):
        s = self._get(player_id)
        if s is None:
            return
        try:
            getattr(s, method)(*args)
        except Exception as exc:  # never let bookkeeping break a command
            log.warning("play log %s hook failed: %s", method, type(exc).__name__)
            return
        if s.pending:
            self._kick(s)

    # -- writer --------------------------------------------------------
    def _spawn(self, coro) -> Optional[asyncio.Task]:
        if not self.enabled:
            coro.close()
            return None
        try:
            task = asyncio.get_running_loop().create_task(coro)
        except RuntimeError:  # no loop (sync caller): nothing to do
            coro.close()
            return None
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _kick(self, s: PlaySession):
        """At most one flush task per session; hooks that arrive meanwhile ride on it."""
        if s.task is not None and not s.task.done():
            s.again = True
            return
        s.task = self._spawn(self._flush_loop(s))

    async def _flush_loop(self, s: PlaySession):
        while True:
            s.again = False
            if not await self._flush(s) or not s.again:
                return  # on failure the pending events wait for the next hook / the end

    async def _flush(self, s: PlaySession) -> bool:
        """Upsert the session row, then insert pending events. Returns True on success."""
        async with s.lock:
            events, s.pending = s.pending, []
            try:
                await asyncio.wait_for(self._write(s.row(), events), WRITE_TIMEOUT_S)
                s.last_flush = time.monotonic()
                return True
            except Exception as exc:
                log.warning("play log write failed (%s); %d event(s) kept for retry",
                            type(exc).__name__, len(events))
                s.pending = (events + s.pending)[-MAX_PENDING:]
                return False

    async def _write(self, row: dict, events: List[dict]):
        async with self.engine.begin() as conn:
            await conn.execute(_UPSERT, row)
            if events:
                await conn.execute(_EVENT, events)

    async def _finish(self, s: PlaySession, base_delay: float = 0.5):
        delay = base_delay
        for attempt in range(END_RETRIES):
            if await self._flush(s):
                return
            if attempt + 1 < END_RETRIES:
                await asyncio.sleep(delay)
                delay *= 2
        log.warning("play log: session end not recorded after %d attempts", END_RETRIES)


play_log = PlayLog()
