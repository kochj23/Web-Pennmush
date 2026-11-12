"""
Spectator mode (+watch) in the seven project categories:
Security, Performance, Retry, Unit, Integration, Functional, UI-state.

The MUSH plays itself (autonomous NPC scene) while spectators watch read-only.
Hard rules covered here: nothing is written to play history, spectators cannot
issue game commands, AI toggles / NO_AI are respected and relay use is capped.
Author: Jordan Koch (GitHub: kochj23)
"""
import asyncio
import random
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.testclient import TestClient

from backend.config import settings
from backend.engine import spectate
from backend.engine.ai_manager import AIReply, SOURCE_AI, SOURCE_SCRIPTED, ai_manager
from backend.engine.spectate import PACES, SceneDirector, director
from backend.models import NPC, DBObject, ObjectType
from backend.play_log import play_log
from backend.security import rate_limiter
from tests.test_play_log import FakeEngine, _register_and_token, _wait_for

ROOT = Path(__file__).resolve().parent.parent
ORIGIN = {"origin": "http://testserver"}


class Roll(random.Random):
    """Deterministic turn type: random() is fixed (<0.2 move, <0.45 emote, else speak)."""

    def __init__(self, roll):
        super().__init__(7)
        self.roll, self._r = roll, random.Random(7)

    def choice(self, seq):  # overriding random() would otherwise bias choice() too
        return self._r.choice(seq)

    def random(self):
        return self.roll


class FakeWS:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def send_json(self, data):
        if self.fail:
            raise ConnectionError("gone")
        self.sent.append(data)


@pytest.fixture(autouse=True)
def _reset_director(monkeypatch):
    monkeypatch.setattr(ai_manager, "enabled", True)
    yield
    for pid in list(director.spectators):
        director.remove(pid)
    director.pace = "normal"
    director.history.clear()


@pytest_asyncio.fixture
async def scene_db(engine, monkeypatch):
    """Point the director's AsyncSessionLocal at the per-test in-memory world."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    import backend.database as database
    monkeypatch.setattr(database, "AsyncSessionLocal", factory)
    async with factory() as s:
        s.add_all([
            DBObject(id=1, name="One", type=ObjectType.PLAYER, flags="GOD", location_id=0),
            DBObject(id=0, name="Room Zero", type=ObjectType.ROOM, owner_id=1),
            DBObject(id=2, name="Central Plaza", type=ObjectType.ROOM, owner_id=1),
            DBObject(id=4, name="void", type=ObjectType.EXIT, owner_id=1, location_id=2, home_id=0),
        ])
        await s.commit()
    return factory


async def _npc(factory, name, room=2, flags="VISIBLE,NPC"):
    async with factory() as s:
        obj = DBObject(name=name, type=ObjectType.THING, owner_id=1, location_id=room, flags=flags)
        s.add(obj)
        await s.flush()
        s.add(NPC(object_id=obj.id, personality=f"{name} is chatty.", is_active=True))
        await s.commit()
        return obj.id


@pytest.fixture
def client():
    from backend.main import app
    from backend.api.websocket import manager
    with TestClient(app) as c:
        yield c
        c.portal.call(asyncio.sleep, 0.3)  # let server-side disconnect cleanup finish before the loop closes
    manager.ip_counts.clear()
    manager.total_sockets = 0


def _login(ws, token, watch=False):
    assert ws.receive_json()["type"] == "auth_required"
    frame = {"type": "auth", "token": token}
    if watch:
        frame["watch"] = True
    ws.send_json(frame)
    assert ws.receive_json()["type"] == "welcome"
    return ws.receive_json()  # look output, or the watch state frame


def _cmd(ws, command):
    ws.send_json({"type": "command", "command": command})
    return ws.receive_json()


def _healthy_ai(monkeypatch, calls):
    async def fake_reply(player_id, vars):
        calls.append((player_id, vars))
        return AIReply("The plaza is lively tonight.", SOURCE_AI)
    monkeypatch.setattr(ai_manager, "is_healthy", lambda: True)
    monkeypatch.setattr(ai_manager, "npc_reply", fake_reply)


# =============================================================================
# SECURITY
# =============================================================================

class TestSecurity:
    def test_spectator_cannot_issue_game_commands(self, client):
        token = _register_and_token(client, "Peeker")
        with client.websocket_connect("/ws", headers=ORIGIN) as ws:
            state = _login(ws, token, watch=True)
            assert state == {"type": "watch", "watching": True, "pace": "normal", "spectators": 1}
            for cmd in ("say hi", "@dig Secret Room", "void", ":waves", "@ai/off", "talk to Mira=hi"):
                msg = _cmd(ws, cmd)
                assert msg["type"] == "error" and "spectating (read-only)" in msg["message"], cmd
        async def rooms():
            from backend.database import AsyncSessionLocal
            async with AsyncSessionLocal() as s:
                return (await s.execute(select(func.count()).select_from(DBObject)
                                        .where(DBObject.name == "Secret Room"))).scalar()
        assert client.portal.call(rooms) == 0
        assert ai_manager.enabled is True

    @pytest.mark.asyncio
    async def test_scene_respects_staff_toggle_no_ai_and_opt_out(self, monkeypatch):
        calls = []
        _healthy_ai(monkeypatch, calls)
        d = SceneDirector(rng=Roll(0.9))
        d.spectators[10] = (FakeWS(), False)
        assert await d._line("Mira", "", "Plaza", "Pip", "hi", [], no_ai=True) in spectate._CHATTER  # NPC NO_AI
        d.spectators[11] = (FakeWS(), True)  # a spectator opted out (@ai/me off)
        assert await d._line("Mira", "", "Plaza", "Pip", "hi", [], no_ai=False) in spectate._CHATTER
        assert calls == []
        del d.spectators[11]
        monkeypatch.setattr(ai_manager, "is_healthy", lambda: False)  # @ai/off or relay down
        assert await d._line("Mira", "", "Plaza", "Pip", "hi", [], no_ai=False) in spectate._CHATTER
        assert calls == []

    def test_watch_does_not_grant_ai_toggle(self, client):
        token = _register_and_token(client, "Lurker")
        with client.websocket_connect("/ws", headers=ORIGIN) as ws:
            _login(ws, token)
            assert _cmd(ws, "@ai/off")["message"] == "Permission denied."
            assert _cmd(ws, "+watch")["type"] == "watch"
            ws.receive_json()
            assert _cmd(ws, "+watch stop")["watching"] is False
            ws.receive_json()
            assert _cmd(ws, "@ai/off")["message"] == "Permission denied."
        assert ai_manager.enabled is True


# =============================================================================
# PERFORMANCE (strict caps: turns per minute, relay jobs per 10 minutes)
# =============================================================================

class TestPerformance:
    @pytest.mark.asyncio
    async def test_turns_capped_per_minute_even_at_zero_pace(self, monkeypatch):
        monkeypatch.setitem(PACES, "normal", 0.001)
        d = SceneDirector()
        turns = []

        async def turn():
            turns.append(1)
            return "line"
        monkeypatch.setattr(d, "turn", turn)
        ws = FakeWS()
        await d.add(1, ws, False, None)
        await asyncio.sleep(0.3)
        d.remove(1)
        assert len(turns) == rate_limiter.limits["watch_turn"][0] == 6

    @pytest.mark.asyncio
    async def test_relay_jobs_capped_below_relay_player_quota(self, monkeypatch):
        calls = []
        _healthy_ai(monkeypatch, calls)
        d = SceneDirector()
        d.spectators[1] = (FakeWS(), False)
        for _ in range(40):
            await d._line("Mira", "", "Plaza", "Pip", "hi", [], no_ai=False)
        assert len(calls) == rate_limiter.limits["watch_ai"][0] == 20 < 30  # relay: 30 jobs/10 min/player
        assert {pid for pid, _ in calls} == {"watch"}  # one shared relay identity (mush-watch)
        assert all(len(v["player_says"]) <= 200 for _, v in calls)


# =============================================================================
# RETRY / FALLBACK
# =============================================================================

class TestRetry:
    @pytest.mark.asyncio
    async def test_relay_unavailable_scene_still_moves(self, scene_db, monkeypatch):
        monkeypatch.setattr(settings, "RELAY_SECRET_MUSH", "")  # AI_BACKEND effectively none
        await _npc(scene_db, "Mira")
        d = SceneDirector(rng=Roll(0.9))
        d.spectators[1] = (FakeWS(), False)
        line = await d.turn()
        assert line.startswith('[Central Plaza] Mira says, "') and any(c in line for c in spectate._CHATTER)

    @pytest.mark.asyncio
    async def test_relay_scripted_reply_replaced_by_scene_chatter(self, monkeypatch):
        async def scripted(player_id, vars):
            return ai_manager.scripted("timeout")
        monkeypatch.setattr(ai_manager, "is_healthy", lambda: True)
        monkeypatch.setattr(ai_manager, "npc_reply", scripted)
        d = SceneDirector()
        assert await d._line("Mira", "", "Plaza", "Pip", "hi", [], no_ai=False) in spectate._CHATTER

    @pytest.mark.asyncio
    async def test_failing_turn_does_not_kill_the_scene(self, monkeypatch):
        monkeypatch.setitem(PACES, "normal", 0.001)
        d = SceneDirector()
        n = {"i": 0}

        async def turn():
            n["i"] += 1
            if n["i"] == 1:
                raise RuntimeError("db hiccup")
            return "still going"
        monkeypatch.setattr(d, "turn", turn)
        ws = FakeWS()
        await d.add(1, ws, False, None)
        await asyncio.sleep(0.1)
        d.remove(1)
        assert {"type": "output", "message": "still going"} in ws.sent


# =============================================================================
# UNIT
# =============================================================================

class TestUnit:
    def test_pace_values(self):
        d = SceneDirector()
        assert d.set_pace("fast") and d.pace == "fast"
        assert not d.set_pace("ludicrous") and d.pace == "fast"
        assert PACES["slow"] > PACES["normal"] > PACES["fast"] >= 5.0

    @pytest.mark.asyncio
    async def test_auto_stop_when_last_spectator_leaves(self):
        d = SceneDirector()
        a, b = FakeWS(), FakeWS()
        await d.add(1, a, False, None)
        await d.add(2, b, False, None)
        task = d.task
        d.remove(1, b)  # stale socket: no-op
        assert 1 in d.spectators
        d.remove(1)
        assert not task.done()
        d.remove(2)
        await asyncio.sleep(0)
        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_broken_spectator_socket_is_dropped(self):
        d = SceneDirector()
        d.spectators[1] = (FakeWS(fail=True), False)
        d.spectators[2] = (FakeWS(), False)
        await d._send("hello")
        assert list(d.spectators) == [2]

    @pytest.mark.asyncio
    async def test_default_cast_seeded_once_when_world_has_no_npcs(self, scene_db):
        d = SceneDirector(rng=Roll(0.3))
        d.home_room = 2
        assert await d.turn() == "A few locals wander in. The scene begins..."
        line = await d.turn()
        assert line.startswith("[Central Plaza] ")
        async with scene_db() as s:
            assert (await s.execute(select(func.count()).select_from(NPC))).scalar() == len(spectate._CAST)


# =============================================================================
# INTEGRATION (scene against the world DB)
# =============================================================================

class TestIntegration:
    @pytest.mark.asyncio
    async def test_npc_wanders_through_an_exit(self, scene_db):
        nid = await _npc(scene_db, "Pip")
        d = SceneDirector(rng=Roll(0.1))
        assert await d.turn() == "[Central Plaza] Pip leaves through void."
        async with scene_db() as s:
            assert (await s.get(DBObject, nid)).location_id == 0

    @pytest.mark.asyncio
    async def test_two_npcs_talk_to_each_other_with_history(self, scene_db, monkeypatch):
        calls = []
        _healthy_ai(monkeypatch, calls)
        await _npc(scene_db, "Mira")
        await _npc(scene_db, "Tobin")
        await _npc(scene_db, "Muted", flags="VISIBLE,NPC,NO_AI", room=0)
        d = SceneDirector(rng=Roll(0.9))
        d.spectators[1] = (FakeWS(), False)
        lines = [await d.turn() for _ in range(6)]
        talk = [ln for ln in lines if "Room Zero" not in ln]
        assert talk and all(" says to " in ln and "The plaza is lively tonight." in ln for ln in talk)
        assert calls and all(v["room_name"] == "Central Plaza" for _, v in calls)
        assert any(v["history"] for _, v in calls[1:]) or len(calls) == 1


# =============================================================================
# FUNCTIONAL (hard rule: nothing reaches play history)
# =============================================================================

class TestFunctional:
    def test_watch_login_and_scene_record_nothing(self, client, scene_db_app, monkeypatch):
        fake = FakeEngine()
        play_log.engine = fake
        play_log.sessions.clear()
        try:
            token = _register_and_token(client, "Watcher")
            with client.websocket_connect("/ws", headers=ORIGIN) as ws:
                assert _login(ws, token, watch=True)["watching"] is True
                lines = [client.portal.call(director.turn) for _ in range(8)]
                assert any(lines)
                ws.send_json({"type": "disconnect"})
            client.portal.call(play_log.drain)
        finally:
            play_log.engine = None
        assert fake.sessions == {} and fake.events == [] and fake.writes == 0
        assert play_log.sessions == {}
        assert _wait_for(lambda: director.spectators == {})

    def test_in_game_watch_ends_play_and_records_nothing_while_watching(self, client, scene_db_app):
        fake = FakeEngine()
        play_log.engine = fake
        play_log.sessions.clear()
        try:
            token = _register_and_token(client, "Switcher")
            with client.websocket_connect("/ws", headers=ORIGIN) as ws:
                _login(ws, token)
                _cmd(ws, "void")  # one real move while playing
                assert _cmd(ws, "+watch fast") == {"type": "watch", "watching": True, "pace": "fast",
                                                   "spectators": 1}
                assert "Now watching" in ws.receive_json()["message"]
                assert _wait_for(lambda: any(r["ended_at"] for r in fake.sessions.values()))
                before = (dict(fake.sessions), list(fake.events))
                for _ in range(8):
                    client.portal.call(director.turn)
                assert _cmd(ws, "say still here?")["type"] == "error"
                assert (fake.sessions, fake.events) == before
                (row,) = fake.sessions.values()
                assert row["outcome"] == "watch" and row["actions"] == 1
                assert _cmd(ws, "+watch stop")["watching"] is False
                assert ws.receive_json()["type"] == "output"  # look
                assert _cmd(ws, "look")["type"] == "output"  # playing again
            client.portal.call(play_log.drain)
        finally:
            play_log.engine = None
            play_log.sessions.clear()
        assert len(fake.sessions) == 2  # before watching, after stopping; none for the watch itself


@pytest.fixture
def scene_db_app(client):
    """Give the app world a talkative NPC pair in Central Plaza (app DB, shared by the TestClient)."""
    async def seed():
        from backend.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            if (await s.execute(select(func.count()).select_from(NPC))).scalar():
                return
            for name in ("Mira", "Tobin"):
                obj = DBObject(name=name, type=ObjectType.THING, owner_id=1, location_id=2, flags="VISIBLE,NPC")
                s.add(obj)
                await s.flush()
                s.add(NPC(object_id=obj.id, personality="Chatty.", is_active=True))
            await s.commit()
    client.portal.call(seed)
    return client


# =============================================================================
# UI-STATE (web client: Watch button, SPECTATING bar, read-only input)
# =============================================================================

class TestUIState:
    def test_client_has_watch_controls_and_indicator(self):
        html = (ROOT / "frontend/index.html").read_text()
        assert 'id="watch-button"' in html and 'id="login-watch"' in html
        assert 'id="watch-bar" class="watch-bar" hidden' in html and "SPECTATING" in html
        assert 'id="watch-pace"' in html and 'id="watch-stop"' in html
        assert all(f'value="{p}"' in html for p in PACES)
        assert "onclick" not in html.lower()  # strict CSP: no inline handlers

    def test_client_goes_read_only_on_watch_frame(self):
        app = (ROOT / "frontend/js/app.js").read_text()
        ws = (ROOT / "frontend/js/websocket.js").read_text()
        assert "wsManager.on('watch'" in app and "setWatching(data.watching, data.pace)" in app
        assert "setInputEnabled(!watching" in app and "bar.hidden = !watching" in app
        assert "sendCommand('+watch stop')" in app and "sendCommand('+watch ' + watchPace.value)" in app
        assert "frame.watch = true" in ws

    def test_watch_frames_over_websocket(self, client):
        token = _register_and_token(client, "Framer")
        with client.websocket_connect("/ws", headers=ORIGIN) as ws:
            _login(ws, token)
            frames = [_cmd(ws, "+watch"), ws.receive_json(), _cmd(ws, "+watch slow"), _cmd(ws, "+watch zoom"),
                      _cmd(ws, "+watch stop"), ws.receive_json(), _cmd(ws, "+watch stop")]
        assert [f["type"] for f in frames] == ["watch", "output", "watch", "output", "watch", "output", "output"]
        assert frames[2]["pace"] == "slow" and frames[4]["watching"] is False
        assert frames[3]["message"].startswith("Usage: +watch") and frames[6]["message"] == "You are not watching."
