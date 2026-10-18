"""
Play-history logging (Nova Games schema `play`) in the seven project categories:
Security, Performance, Retry, Unit, Integration (real Postgres), Functional, Frame.
Author: Jordan Koch (GitHub: kochj23)
"""
import asyncio
import json
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from backend import play_log as pl
from backend.play_log import PlayLog, PlaySession, play_log

ROOT = Path(__file__).resolve().parent.parent
ORIGIN = {"origin": "http://testserver"}
PW = "correct-horse-1"  # test-only credential
VENDORED_SQL = Path(__file__).with_name("play_schema.sql")
PLATFORM_SQL = Path(os.environ.get("NOVAGAMES_REPO", ROOT.parent / "NovaGames")) / "deploy" / "db" / "play.sql"
KIND_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,47}$")


class FakeEngine:
    """Records what the writer sends; can fail N times or hang (stands in for asyncpg)."""

    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, fail=0, hang=0.0):
        self.fail, self.hang = fail, hang
        self.sessions, self.events, self.writes = {}, [], 0

    @asynccontextmanager
    async def begin(self):
        if self.hang:
            await asyncio.sleep(self.hang)
        if self.fail:
            self.fail -= 1
            raise ConnectionError("db down")
        yield self

    async def execute(self, stmt, params):
        sql = str(stmt)
        if "play.sessions" in sql:
            self.writes += 1
            old = self.sessions.get(params["id"])
            if old is None or old["ended_at"] is None:
                self.sessions[params["id"]] = dict(params, summary=json.loads(params["summary"]))
        else:
            for e in params:
                self.events.append(dict(e, detail=json.loads(e["detail"])))


@pytest.fixture
def fake_log():
    """Point the process-wide play_log at a FakeEngine; restore afterwards."""
    fake = FakeEngine()
    play_log.engine = fake
    play_log.sessions.clear()
    yield fake
    play_log.engine = None
    play_log.sessions.clear()


@pytest.fixture
def client():
    from backend.main import app
    from backend.api.websocket import manager
    with TestClient(app) as c:
        yield c
    manager.ip_counts.clear()
    manager.total_sockets = 0


def _register_and_token(client, name):
    r = client.post("/api/players/register", json={"username": name, "password": PW}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    r = client.post("/api/auth/login", json={"username": name, "password": PW}, headers=ORIGIN)
    return r.json()["token"]


def _wait_for(pred, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.02)
    return pred()


async def _quest_world(session):
    from backend.engine.quests import QuestManager
    qm = QuestManager(session)
    quest = await qm.create_quest("Crystal Hunt", "Find the crystal", creator_id=1, reward_credits=5)
    await qm.add_quest_step(quest.id, 1, "Go to the plaza")
    return qm, quest


# =============================================================================
# SECURITY
# =============================================================================

class TestSecurity:
    @pytest.mark.asyncio
    async def test_say_and_page_text_never_logged(self, seeded_session, fake_log):
        from backend.engine.commands import CommandParser
        from backend.models import DBObject
        god = await seeded_session.get(DBObject, 1)
        s = play_log.start(1, "One")
        parser = CommandParser(seeded_session)
        await parser.parse(god, "say the-secret-say-text")
        await parser.parse(god, ":waves the-secret-pose-text")
        play_log.end(s)
        await play_log.drain()
        blob = json.dumps([fake_log.sessions, fake_log.events], default=str)
        assert "secret" not in blob
        row = fake_log.sessions[str(s.id)]
        assert row["summary"]["says"] == 1 and row["summary"]["poses"] == 1

    def test_summary_has_no_ip_or_paths_and_player_is_capped(self):
        s = PlaySession(7, "x" * 200)
        assert len(s.player) == 64
        blob = json.dumps(s.row(), default=str)
        assert not re.search(r"\d+\.\d+\.\d+\.\d+", blob) and "/" not in json.dumps(s.summary())

    def test_writer_is_never_set_by_the_app(self):
        assert "writer" not in str(pl._UPSERT) and "writer" not in str(pl._EVENT)
        assert "writer" not in PlaySession(1, "a").row()

    def test_only_qualified_play_tables(self):
        assert "INSERT INTO play.sessions" in str(pl._UPSERT)
        assert "INSERT INTO play.events" in str(pl._EVENT)

    def test_play_tables_not_in_app_metadata(self):
        from backend.models import Base
        assert not any(t.schema == "play" or t.name in ("sessions", "events") for t in Base.metadata.sorted_tables)


# =============================================================================
# PERFORMANCE
# =============================================================================

class TestPerformance:
    @pytest.mark.asyncio
    async def test_hooks_are_cheap_when_nobody_is_playing(self):
        start = time.perf_counter()
        for i in range(20000):
            play_log.room(99999, "Nowhere")
            play_log.credits(99999, 5, "x")
            play_log.social(99999, "say")
        assert time.perf_counter() - start < 0.5

    @pytest.mark.asyncio
    async def test_hanging_database_never_blocks_a_command(self, monkeypatch):
        monkeypatch.setattr(pl, "WRITE_TIMEOUT_S", 0.2)
        log = PlayLog(FakeEngine(hang=10))
        s = log.start(1, "One")
        t0 = time.perf_counter()
        for _ in range(100):
            log.room(1, "Central Plaza")
            log.command(s)
        assert time.perf_counter() - t0 < 0.1  # hooks only touch memory
        t1 = time.perf_counter()
        await log.drain(timeout=3)
        assert time.perf_counter() - t1 < 2  # each write is bounded by WRITE_TIMEOUT_S
        assert s.pending  # kept for a later retry

    @pytest.mark.asyncio
    async def test_session_bump_is_throttled(self):
        fake = FakeEngine()
        log = PlayLog(fake)
        s = log.start(1, "One")
        await log.drain()
        for _ in range(500):
            log.command(s)
        await log.drain()
        assert fake.writes == 1 and s.actions == 500  # only the start write inside the 30 s window
        s.last_flush -= pl.BUMP_INTERVAL_S
        log.command(s)
        await log.drain()
        assert fake.writes == 2 and fake.sessions[str(s.id)]["actions"] == 501


# =============================================================================
# RETRY
# =============================================================================

class TestRetry:
    @pytest.mark.asyncio
    async def test_failed_events_are_resent_on_next_flush(self):
        fake = FakeEngine(fail=2)  # start write and first event write fail
        log = PlayLog(fake)
        s = log.start(1, "One")
        await log.drain()
        log.room(1, "Room Zero")
        await log.drain()
        assert fake.events == [] and len(s.pending) == 1
        log.room(1, "Central Plaza")
        await log.drain()
        assert [e["seq"] for e in fake.events] == [0, 1]
        assert [e["detail"]["room"] for e in fake.events] == ["Room Zero", "Central Plaza"]

    @pytest.mark.asyncio
    async def test_end_retries_with_backoff(self):
        fake = FakeEngine(fail=2)
        log = PlayLog(fake)
        s = PlaySession(1, "One")
        s.ended_at, s.outcome = s.started_at, "quit"
        await log._finish(s, base_delay=0.01)
        assert fake.sessions[str(s.id)]["outcome"] == "quit"

    @pytest.mark.asyncio
    async def test_end_gives_up_quietly(self):
        fake = FakeEngine(fail=99)
        log = PlayLog(fake)
        s = PlaySession(1, "One")
        await log._finish(s, base_delay=0.001)  # no exception
        assert fake.sessions == {}

    @pytest.mark.asyncio
    async def test_pending_events_are_bounded_while_db_is_down(self, monkeypatch):
        monkeypatch.setattr(pl, "MAX_PENDING", 10)
        s = PlaySession(1, "One")
        for i in range(25):
            s.room(f"R{i}")
        assert len(s.pending) == 10 and s.dropped_events == 15
        assert s.pending[-1]["detail"] == json.dumps({"room": "R24"}, separators=(",", ":"))


# =============================================================================
# UNIT
# =============================================================================

class TestUnit:
    def test_summary_math(self):
        s = PlaySession(1, "One", "Central Plaza")
        for name in ["Room Zero", "Central Plaza", "Room Zero"]:
            s.room(name)
        s.quest("started", "Crystal Hunt")
        s.quest("advanced", "Crystal Hunt", 1)
        s.quest("completed", "Crystal Hunt")
        s.credits(50, "quest_reward")
        s.credits(-20, "transfer_send")
        for k in ("say", "say", "pose", "page", "shout"):
            s.social(k)
        s.command(); s.command()
        sm = s.summary()
        assert sm["rooms_entered"] == 3 and sm["rooms_visited"] == ["Central Plaza", "Room Zero"]
        assert sm["start_room"] == "Central Plaza" and sm["end_room"] == "Room Zero"
        assert sm["quests_started"] == ["Crystal Hunt"] and sm["quests_completed"] == ["Crystal Hunt"]
        assert sm["quest_steps"] == 1
        assert (sm["credits_earned"], sm["credits_spent"], sm["credits_delta"]) == (50, 20, 30)
        assert (sm["says"], sm["poses"], sm["pages"], sm["commands"]) == (2, 1, 1, 2)
        assert [e["seq"] for e in s.pending] == list(range(8))

    def test_lists_and_events_are_capped(self):
        s = PlaySession(1, "One")
        for i in range(pl.MAX_EVENTS + 40):
            s.room(f"Room {i}")
        sm = s.summary()
        assert len(sm["rooms_visited"]) == pl.LIST_CAP and sm["rooms_entered"] == pl.MAX_EVENTS + 40
        # 40 over the per-session cap, plus the oldest unsent ones beyond MAX_PENDING (no DB here)
        assert s.seq == pl.MAX_EVENTS and sm["events_dropped"] == 40 + pl.MAX_EVENTS - pl.MAX_PENDING
        assert len(json.dumps(sm).encode()) < 65536

    def test_event_kinds_and_details_fit_the_schema(self):
        s = PlaySession(1, "One")
        s.room("R" * 5000)
        s.quest("advanced", "Q" * 5000, 3)
        s.credits(7, "W" * 5000)
        for e in s.pending:
            assert KIND_RE.match(e["kind"]) and len(e["detail"].encode()) <= 4096

    def test_row_shape(self):
        s = PlaySession(3, "Walker")
        row = s.row()
        assert (row["game"], row["client"], row["player"], row["ended_at"]) == ("mush", "web", "Walker", None)
        assert row["started_at"].tzinfo is not None and row["last_seen_at"] >= row["started_at"]

    @pytest.mark.asyncio
    async def test_sqlite_is_a_no_op(self, engine):
        log = PlayLog(engine)
        assert not log.enabled
        s = log.start(1, "One")
        log.room(1, "Room Zero")
        log.end(s)
        assert not log._tasks and s.outcome == "quit"

    @pytest.mark.asyncio
    async def test_new_login_ends_previous_session_and_end_is_idempotent(self):
        fake = FakeEngine()
        log = PlayLog(fake)
        a = log.start(1, "One")
        b = log.start(1, "One")
        assert a.outcome == "reconnected" and log.sessions[1] is b
        log.end(a, "quit")  # the old socket's finally block: no change, b stays registered
        assert a.outcome == "reconnected" and log.sessions[1] is b
        log.end(b)
        log.end(b, "other")
        await log.drain()
        assert fake.sessions[str(b.id)]["outcome"] == "quit" and 1 not in log.sessions

    @pytest.mark.asyncio
    async def test_engine_hooks_record_quests_credits_rooms(self, seeded_session, fake_log):
        from backend.engine.economy import EconomyManager
        from backend.engine.objects import ObjectManager
        s = play_log.start(1, "One")
        qm, quest = await _quest_world(seeded_session)
        await qm.start_quest(quest.id, 1)
        await qm.advance_quest(quest.id, 1)
        await qm.advance_quest(quest.id, 1)
        eco = EconomyManager(seeded_session)
        await eco.add_credits(1, 100, "quest_reward")
        ok, _ = await eco.remove_credits(1, 30, "purchase")
        assert ok
        await ObjectManager(seeded_session).move_object(1, 2)  # player into a room: logged
        await ObjectManager(seeded_session).move_object(5, 1)  # a thing into a player: not logged
        play_log.end(s)
        await play_log.drain()
        kinds = [(e["kind"], e["detail"].get("action")) for e in fake_log.events]
        assert kinds == [("quest", "started"), ("quest", "advanced"), ("quest", "completed"),
                         ("credits", None), ("credits", None), ("room", None)]
        sm = fake_log.sessions[str(s.id)]["summary"]
        assert sm["credits_delta"] == 70 and sm["quests_completed"] == ["Crystal Hunt"]
        assert sm["rooms_visited"] == ["Central Plaza"]


# =============================================================================
# INTEGRATION (real Postgres with the platform `play` schema)
# =============================================================================

from tests.pg_cluster import PgCluster  # noqa: E402

pg_required = pytest.mark.skipif(
    not PgCluster.available() or bool(os.environ.get("PG_TEST_URL")),
    reason="needs a private initdb cluster (superuser) for the play schema")


@pytest.fixture(scope="module")
def pgplay():
    sql = PLATFORM_SQL if PLATFORM_SQL.exists() else VENDORED_SQL
    cluster = PgCluster().start()
    try:
        cluster.apply_play_schema(str(sql))
        yield cluster
    finally:
        cluster.stop()


async def _fetch(url, sql, **params):
    from sqlalchemy import text
    from backend.database import build_engine
    eng = build_engine(url)
    try:
        async with eng.connect() as conn:
            return (await conn.execute(text(sql), params)).mappings().all()
    finally:
        await eng.dispose()


@pg_required
class TestIntegrationPostgres:
    @pytest.mark.asyncio
    async def test_full_session_lands_as_mush_writer(self, pgplay):
        from backend.database import build_engine
        eng = build_engine(pgplay.url)
        log = PlayLog(eng)
        try:
            s = log.start(42, "Walker", "Central Plaza")
            log.room(42, "Room Zero")
            log.quest(42, "started", "Crystal Hunt")
            log.credits(42, 25, "quest_reward")
            log.social(42, "say")
            log.command(s); log.command(s)
            await log.drain()
            open_rows = await _fetch(pgplay.url, "SELECT ended_at, actions FROM play.sessions WHERE id = :i",
                                     i=s.id)
            assert open_rows[0]["ended_at"] is None
            log.end(s)
            await log.drain()
        finally:
            await eng.dispose()
        rows = await _fetch(pgplay.super_url, "SELECT * FROM play.sessions WHERE id = :i", i=s.id)
        r = rows[0]
        assert (r["game"], r["client"], r["player"], r["writer"], r["outcome"]) == ("mush", "web", "Walker",
                                                                                   "mush", "quit")
        assert r["actions"] == 2 and r["ended_at"] >= r["started_at"]
        assert r["summary"]["credits_delta"] == 25 and r["summary"]["rooms_visited"] == ["Central Plaza",
                                                                                        "Room Zero"]
        ev = await _fetch(pgplay.super_url, "SELECT seq, kind, detail, writer FROM play.events "
                                            "WHERE session_id = :i ORDER BY seq", i=s.id)
        assert [(e["seq"], e["kind"]) for e in ev] == [(0, "room"), (1, "quest"), (2, "credits")]
        assert {e["writer"] for e in ev} == {"mush"}

    @pytest.mark.asyncio
    async def test_ended_session_is_immutable_and_retries_idempotent(self, pgplay):
        from backend.database import build_engine
        eng = build_engine(pgplay.url)
        log = PlayLog(eng)
        try:
            s = log.start(43, "Rover")
            log.room(43, "Room Zero")
            log.end(s)
            await log.drain()
            assert await log._flush(s)  # same row and events again: no error, no duplicates
            s.outcome = "tampered"
            await log._flush(s)
        finally:
            await eng.dispose()
        r = (await _fetch(pgplay.super_url, "SELECT outcome FROM play.sessions WHERE id = :i", i=s.id))[0]
        assert r["outcome"] == "quit"
        n = await _fetch(pgplay.super_url, "SELECT count(*) AS n FROM play.events WHERE session_id = :i", i=s.id)
        assert n[0]["n"] == 1

    @pytest.mark.asyncio
    async def test_row_level_security_and_no_delete(self, pgplay):
        from sqlalchemy import text
        from backend.database import build_engine
        await _fetch(pgplay.super_url,
                     "INSERT INTO play.sessions (id, game, client, player, writer, started_at, last_seen_at) "
                     "VALUES (gen_random_uuid(), 'gtnw', 'mac', 'default', 'gtnw', now(), now()) RETURNING id")
        eng = build_engine(pgplay.url)
        try:
            async with eng.connect() as conn:
                seen = (await conn.execute(text("SELECT count(*) FROM play.sessions WHERE writer <> 'mush'")))
                assert seen.scalar() == 0
            with pytest.raises(Exception):
                async with eng.begin() as conn:
                    await conn.execute(text("DELETE FROM play.sessions"))
            with pytest.raises(Exception):
                async with eng.begin() as conn:
                    await conn.execute(text(
                        "INSERT INTO play.sessions (id, game, client, player, writer, started_at, last_seen_at) "
                        "VALUES (gen_random_uuid(), 'mush', 'web', 'x', 'gtnw', now(), now())"))
        finally:
            await eng.dispose()

    @pytest.mark.asyncio
    async def test_engine_hooks_on_postgres_game_db(self, pgplay, monkeypatch):
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        from backend.database import build_engine, _init_schema_and_seed
        from backend.engine.objects import ObjectManager
        owner = build_engine(pgplay.migrate_url)
        app = build_engine(pgplay.url)
        monkeypatch.setattr(play_log, "_engine", app)
        try:
            await _init_schema_and_seed(owner)
            s = play_log.start(1, "One")
            async with async_sessionmaker(app, class_=AsyncSession, expire_on_commit=False)() as db:
                await ObjectManager(db).move_object(1, 2)
                await ObjectManager(db).move_object(1, 0)
            play_log.end(s)
            await play_log.drain()
        finally:
            play_log.sessions.clear()
            await owner.dispose()
            await app.dispose()
        ev = await _fetch(pgplay.super_url, "SELECT detail->>'room' AS room FROM play.events "
                                            "WHERE session_id = :i ORDER BY seq", i=s.id)
        assert [e["room"] for e in ev] == ["Central Plaza", "Room Zero"]

    def test_vendored_schema_matches_platform(self):
        if not PLATFORM_SQL.exists():
            pytest.skip("NovaGames repo not checked out next to this one")
        assert VENDORED_SQL.read_text() == PLATFORM_SQL.read_text(), "refresh tests/play_schema.sql"


# =============================================================================
# FUNCTIONAL (WebSocket play session end to end)
# =============================================================================

class TestFunctional:
    def test_websocket_session_is_logged_from_auth_to_disconnect(self, client, fake_log):
        token = _register_and_token(client, "Rambler")
        with client.websocket_connect("/ws", headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json({"type": "auth", "token": token})
            assert ws.receive_json()["type"] == "welcome"
            ws.receive_json()
            for cmd in ("say hello there", "void", "portal", "look", "page Nobody=psst"):
                ws.send_json({"type": "command", "command": cmd})
                ws.receive_json()
            ws.send_json({"type": "disconnect"})
        assert _wait_for(lambda: any(r["ended_at"] for r in fake_log.sessions.values()))
        (row,) = fake_log.sessions.values()
        sm = row["summary"]
        assert (row["player"], row["outcome"], row["actions"]) == ("Rambler", "quit", 5)
        assert sm["rooms_visited"] == ["Central Plaza", "Room Zero"] and sm["rooms_entered"] == 2
        assert (sm["says"], sm["pages"]) == (1, 0)  # page to an unknown player is not counted
        assert [e["detail"]["room"] for e in fake_log.events] == ["Room Zero", "Central Plaza"]
        assert "psst" not in json.dumps(row, default=str) and "hello" not in json.dumps(row, default=str)

    def test_failed_auth_creates_no_session(self, client, fake_log):
        with client.websocket_connect("/ws", headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json({"type": "auth", "token": "garbage.token"})
            assert ws.receive_json()["type"] == "error"
        time.sleep(0.1)
        assert fake_log.sessions == {} and play_log.sessions == {}


# =============================================================================
# FRAME (client-visible WebSocket frames are unchanged by logging)
# =============================================================================

class TestFrame:
    def test_frames_identical_with_logging_on_and_off(self, client):
        def run(name):
            token = _register_and_token(client, name)
            with client.websocket_connect("/ws", headers=ORIGIN) as ws:
                frames = [ws.receive_json()]
                ws.send_json({"type": "auth", "token": token})
                frames += [ws.receive_json(), ws.receive_json()]
                ws.send_json({"type": "command", "command": "void"})
                frames.append(ws.receive_json())
                ws.send_json({"type": "ping"})
                frames.append(ws.receive_json())
                ws.send_json({"type": "disconnect"})
            return [(f["type"], sorted(f)) for f in frames]

        off = run("FrameOff")
        play_log.engine = FakeEngine(fail=99)  # logging on, and failing
        try:
            on = run("FrameOn")
        finally:
            play_log.engine = None
            play_log.sessions.clear()
        assert on == off
        assert [t for t, _ in on] == ["auth_required", "welcome", "output", "output", "pong"]
