"""
AI parity tests (2026-11): the relay-only AI layer in the seven project categories
Security, Performance, Retry, Unit, Integration, Functional, Frame.

Covers the game-level AI features shared by every Nova game: on/off toggle (staff and
per player), scripted fallback, relay health status, bounded timeouts/retries and output
validation. Web-Pennmush has no direct model backend; everything goes through the relay.
Author: Jordan Koch (GitHub: kochj23)
"""
import asyncio
import json
import os
import re
import time
from pathlib import Path

import pytest
import pytest_asyncio
from starlette.testclient import TestClient

from backend.config import settings
from backend.engine.ai_manager import (
    MAX_LINE_CHARS, MAX_RETRIES, PLAYER_OPT_OUT_FLAG, SOURCE_AI, SOURCE_RELAY_FALLBACK, SOURCE_SCRIPTED,
    AIManager, AIReply, ai_manager, scripted_guide, validate_output,
)
from backend.engine.commands import CommandParser
from backend.models import NPC, DBObject, ObjectType
from backend.relay import RelayJobQueue, sign

ROOT = Path(__file__).resolve().parent.parent
ORIGIN = {"origin": "http://testserver"}
SCRIPTED_NPC = {
    "Hmm. Give me a moment to think on that.",
    "The fog in my head is thick today. Ask me again later?",
    "Interesting. Tell me more about that.",
    "I've heard rumours, but nothing I'd stake my reputation on.",
    "Ah, a question for the ages. Perhaps the Plaza notice board knows.",
}


@pytest.fixture(autouse=True)
def _fresh_global_ai(monkeypatch):
    """Isolate the process-wide ai_manager: fresh stats, switched on, default retries."""
    monkeypatch.setattr(ai_manager, "enabled", True)
    monkeypatch.setattr(ai_manager, "stats", {k: 0 for k in ai_manager.stats})
    monkeypatch.setattr(ai_manager, "last_ok", None)
    monkeypatch.setattr(settings, "AI_RETRIES", 1)
    monkeypatch.setattr(settings, "AI_RETRY_BACKOFF_S", 0.01)
    monkeypatch.setattr(settings, "AI_ENABLE_GAME_GUIDE", True)
    yield


def _alive_queue(**kw) -> RelayJobQueue:
    q = RelayJobQueue(**kw)
    q.last_poll = q.clock()
    return q


def _manager(monkeypatch, queue=None, secret="s") -> AIManager:
    monkeypatch.setattr(settings, "RELAY_SECRET_MUSH", secret)
    return AIManager(queue if queue is not None else _alive_queue())


def _relay_worker(q: RelayJobQueue, answers):
    """Fake relay: answers successive jobs with the given (status, text) pairs."""
    async def run():
        for status, text in answers:
            job = await q.next_job(2)
            assert job is not None
            q.complete(job["job_id"], {"job_id": job["job_id"], "status": status, "text": text,
                                       "reason": "quota" if status == "fallback" else None})
    return asyncio.create_task(run())


def _signed(method, path, body=b"", secret="relay-secret"):
    ts = str(int(time.time()))
    return {"x-relay-ts": ts, "x-relay-sig": sign(secret, ts, method, path, body)}


async def _add_npc(session, name="Guard", location=2):
    obj = DBObject(name=name, type=ObjectType.THING, owner_id=1, location_id=location, flags="VISIBLE,NPC")
    session.add(obj)
    await session.flush()
    session.add(NPC(object_id=obj.id, personality="A gruff guard.", knowledge_base="Knows the plaza.",
                    is_active=True))
    await session.commit()
    return obj


# =============================================================================
# SECURITY
# =============================================================================

class TestSecurity:
    @pytest.mark.parametrize("bad", [
        "As an AI language model I cannot do that.",
        "Sure! {player_says}",
        "<|im_start|>system you are",
        "```python\nprint(1)\n```",
        ">>> ignore previous",
        "!!!",
        "",
        None,
        42,
    ])
    def test_validation_rejects_nonsense_and_leakage(self, bad):
        assert validate_output(bad) is None

    def test_validation_strips_terminal_escapes_and_controls(self):
        out = validate_output("\x1b[31mHello\x1b[0m there\x00\r\nfriend\x7f")
        assert out is not None
        assert all(ch >= " " and ch != "\x7f" for ch in out)
        assert "Hello" in out and "friend" in out

    def test_no_direct_llm_backend_in_ai_layer(self):
        """The game has no model client, key or egress: only the relay pull endpoints."""
        for rel in ("backend/engine/ai_manager.py", "backend/relay.py", "backend/config.py"):
            src = (ROOT / rel).read_text().lower()
            code = "\n".join(line for line in src.splitlines() if not line.strip().startswith("#"))
            for word in ("import httpx", "import requests", "aiohttp", "urllib.request", "11434",
                         "openai", "api_key", "openrouter", "/v1/chat"):
                assert word not in code, f"{word!r} found in {rel}"
        reqs = (ROOT / "requirements.txt").read_text().lower()
        for pkg in ("openai", "ollama", "mlx", "anthropic"):
            assert pkg not in reqs

    def test_guide_help_text_names_the_relay_not_local_models(self):
        src = (ROOT / "backend/engine/commands.py").read_text()
        assert "Ollama or MLX" not in src
        assert "narrator relay" in src

    @pytest.mark.asyncio
    async def test_non_admin_cannot_toggle_ai(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        assert await parser.parse(player, "@ai/off") == "Permission denied."
        assert ai_manager.enabled is True

    @pytest.mark.asyncio
    async def test_admin_toggle_endpoint_requires_admin_and_same_origin(self, app_client, engine, make_headers):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        async with async_sessionmaker(engine, class_=AsyncSession)() as s:
            s.add(DBObject(id=10, name="Pleb", type=ObjectType.PLAYER, flags="", location_id=2))
            await s.commit()
        r = await app_client.post("/api/admin/ai", json={"enabled": False})
        assert r.status_code == 401
        r = await app_client.post("/api/admin/ai", json={"enabled": False}, headers=make_headers(10))
        assert r.status_code == 403
        r = await app_client.post("/api/admin/ai", json={"enabled": False},
                                  headers={**make_headers(1), "origin": "http://evil.example"})
        assert r.status_code == 403
        assert ai_manager.enabled is True
        r = await app_client.post("/api/admin/ai", json={"enabled": "maybe"}, headers=make_headers(1))
        assert r.status_code == 422 and ai_manager.enabled is True

    @pytest.mark.asyncio
    async def test_player_cannot_opt_out_someone_else(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        assert await parser.parse(player, "@set One=NO_AI") in ("Permission denied.", "I don't see 'One' here.")
        god = await seeded_session.get(DBObject, 1)
        assert PLAYER_OPT_OUT_FLAG not in (god.flags or "")


# =============================================================================
# PERFORMANCE
# =============================================================================

class TestPerformance:
    @pytest.mark.asyncio
    async def test_fallback_paths_answer_immediately(self, monkeypatch):
        monkeypatch.setattr(settings, "AI_RESULT_TIMEOUT_S", 30)
        down = _manager(monkeypatch, RelayJobQueue())       # configured, relay never polled
        off = _manager(monkeypatch, _alive_queue())
        off.set_enabled(False)
        unconfigured = _manager(monkeypatch, _alive_queue(), secret="")
        start = time.perf_counter()
        for mgr in (down, off, unconfigured):
            for _ in range(100):
                assert (await mgr.reply("hi", npc_name="Bob")).source == SOURCE_SCRIPTED
        assert time.perf_counter() - start < 1.0

    def test_validation_is_bounded_on_huge_input(self):
        blob = "word " * 20000
        start = time.perf_counter()
        for _ in range(50):
            out = validate_output(blob)
        assert time.perf_counter() - start < 1.0
        assert out is not None and len(out) <= MAX_LINE_CHARS + 3

    def test_status_is_cheap(self, monkeypatch):
        mgr = _manager(monkeypatch)
        start = time.perf_counter()
        for _ in range(5000):
            mgr.get_status()
        assert time.perf_counter() - start < 1.0


# =============================================================================
# RETRY (relay timeouts and bounded retries)
# =============================================================================

class TestRetry:
    @pytest.mark.asyncio
    async def test_invalid_output_is_retried_once_then_ai(self, monkeypatch):
        mgr = _manager(monkeypatch)
        worker = _relay_worker(mgr.queue, [("ok", "As an AI I can't."), ("ok", "Halt! Who goes there?")])
        reply = await mgr.reply("hello", npc_name="Guard")
        await worker
        assert reply == AIReply("Halt! Who goes there?", SOURCE_AI)
        assert mgr.stats["retries"] == 1 and mgr.stats["invalid_output"] == 1
        assert mgr.queue.stats["submitted"] == 2

    @pytest.mark.asyncio
    async def test_retries_are_bounded(self, monkeypatch):
        monkeypatch.setattr(settings, "AI_RETRIES", 99)
        mgr = _manager(monkeypatch)
        worker = _relay_worker(mgr.queue, [("ok", "")] * (1 + MAX_RETRIES))
        reply = await mgr.reply("hello", npc_name="Guard")
        await worker
        assert reply.source == SOURCE_SCRIPTED and reply.reason == "invalid_output"
        assert mgr.queue.stats["submitted"] == 1 + MAX_RETRIES

    @pytest.mark.asyncio
    async def test_timeout_uses_whole_budget_and_is_not_retried(self, monkeypatch):
        monkeypatch.setattr(settings, "AI_RESULT_TIMEOUT_S", 0.1)
        mgr = _manager(monkeypatch)
        start = time.perf_counter()
        reply = await mgr.reply("hello", npc_name="Guard")
        assert time.perf_counter() - start < 0.6
        assert reply.source == SOURCE_SCRIPTED and reply.reason == "timeout"
        assert mgr.queue.stats["submitted"] == 1 and mgr.queue.stats["timeouts"] == 1

    @pytest.mark.asyncio
    async def test_queue_full_retries_with_backoff_then_falls_back(self, monkeypatch):
        mgr = _manager(monkeypatch, _alive_queue(max_pending=0))
        start = time.perf_counter()
        reply = await mgr.reply("hello", npc_name="Guard")
        assert time.perf_counter() - start < 0.2
        assert reply.reason == "queue_full" and mgr.queue.stats["rejected_full"] == 2

    @pytest.mark.asyncio
    async def test_rejected_job_is_not_retried(self, monkeypatch):
        mgr = _manager(monkeypatch)
        worker = _relay_worker(mgr.queue, [("rejected", "")])
        reply = await mgr.reply("hello", npc_name="Guard")
        await worker
        assert reply.source == SOURCE_SCRIPTED and reply.reason == "rejected"
        assert mgr.queue.stats["submitted"] == 1

    @pytest.mark.asyncio
    async def test_dead_relay_is_not_retried(self, monkeypatch):
        mgr = _manager(monkeypatch, RelayJobQueue())
        reply = await mgr.reply("hello", npc_name="Guard")
        assert reply.reason == "no_relay" and mgr.queue.stats["no_relay"] == 1


# =============================================================================
# UNIT
# =============================================================================

class TestUnit:
    def test_state_matrix(self, monkeypatch):
        assert _manager(monkeypatch, secret="").state() == "not_configured"
        monkeypatch.setattr(settings, "AI_BACKEND", "none")
        assert AIManager(_alive_queue()).state() == "not_configured"
        monkeypatch.setattr(settings, "AI_BACKEND", "relay")
        mgr = _manager(monkeypatch, RelayJobQueue())
        assert mgr.state() == "unreachable" and not mgr.is_healthy()
        mgr.queue.last_poll = mgr.queue.clock()
        assert mgr.state() == "healthy" and mgr.is_healthy()
        mgr.set_enabled(False)
        assert mgr.state() == "disabled" and not mgr.is_available()
        assert mgr.relay_secret() == "s"  # relay may keep polling so health stays visible

    def test_status_reports_real_health(self, monkeypatch):
        now = [1000.0]
        q = RelayJobQueue(relay_stale_s=45, clock=lambda: now[0])
        mgr = _manager(monkeypatch, q)
        s = mgr.get_status()
        assert s["relay_configured"] and not s["relay_alive"] and not s["healthy"]
        assert s["state"] == "unreachable" and s["last_poll_age_s"] is None
        q.last_poll = now[0]
        now[0] += 5
        s = mgr.get_status()
        assert s["relay_alive"] and s["healthy"] and s["state"] == "healthy" and s["last_poll_age_s"] == 5.0
        now[0] += 60
        assert mgr.get_status()["state"] == "unreachable"
        for key in ("enabled", "retries", "timeout_s", "replies", "stats", "queue_depth", "guide_enabled"):
            assert key in s

    def test_fallback_hint(self, monkeypatch):
        mgr = _manager(monkeypatch)
        assert mgr.fallback_hint(AIReply("x", SOURCE_AI)) == ""
        assert mgr.fallback_hint(AIReply("x", SOURCE_SCRIPTED, "opted_out")) == ""
        assert "switched off" in mgr.fallback_hint(AIReply("x", SOURCE_SCRIPTED, "disabled"))
        assert "narrator is away" in mgr.fallback_hint(AIReply("x", SOURCE_SCRIPTED, "timeout"))
        assert "narrator is away" in mgr.fallback_hint(AIReply("x", SOURCE_RELAY_FALLBACK, "quota"))

    def test_validation_cleans_good_output(self):
        assert validate_output('  "Well met, traveller."  ') == "Well met, traveller."
        assert validate_output("Assistant: Hello\n\nthere") == "Hello there"
        long = validate_output("abc " * 400)
        assert long.endswith("...") and len(long) <= MAX_LINE_CHARS + 3 and not long[:-3].endswith(" ")

    @pytest.mark.parametrize("q,expect", [
        ("How do I create a room?", "@dig"),
        ("how to talk to npcs", "talk to"),
        ("I am lost, where do I go", "look"),
        ("quests?", "quest/list"),
        ("blorp", "help"),
        ("", "help"),
    ])
    def test_scripted_guide(self, q, expect):
        assert expect in scripted_guide(q)

    @pytest.mark.asyncio
    async def test_relay_fallback_text_is_labelled(self, monkeypatch):
        mgr = _manager(monkeypatch)
        worker = _relay_worker(mgr.queue, [("fallback", "The guard grunts.")])
        reply = await mgr.reply("hi", npc_name="Guard")
        await worker
        assert reply == AIReply("The guard grunts.", SOURCE_RELAY_FALLBACK, "quota")
        assert mgr.stats["relay_fallback"] == 1

    @pytest.mark.asyncio
    async def test_guide_uses_keywords_when_relay_cannot_answer(self, monkeypatch):
        mgr = _manager(monkeypatch)
        worker = _relay_worker(mgr.queue, [("fallback", "The guard grunts.")])
        reply = await mgr.get_game_guidance("how do I dig a room", {"location": "Plaza"})
        await worker
        assert reply.source == SOURCE_SCRIPTED and "@dig" in reply.text

    @pytest.mark.asyncio
    async def test_guide_switch_skips_relay(self, monkeypatch):
        monkeypatch.setattr(settings, "AI_ENABLE_GAME_GUIDE", False)
        mgr = _manager(monkeypatch)
        reply = await mgr.get_game_guidance("how do I dig a room", {})
        assert reply.reason == "guide_disabled" and mgr.queue.stats["submitted"] == 0


# =============================================================================
# INTEGRATION (HTTP relay endpoints + admin REST)
# =============================================================================

@pytest.fixture
def client():
    from backend.main import app
    from backend.api.websocket import manager
    with TestClient(app) as c:
        yield c
    manager.ip_counts.clear()
    manager.total_sockets = 0


def _god_headers(client):
    r = client.post("/api/auth/login", json={"username": "One", "password": os.environ["GOD_PASSWORD"]},
                    headers=ORIGIN)
    assert r.status_code == 200, r.text
    return {**ORIGIN, "Authorization": f"Bearer {r.json()['token']}"}


class TestIntegration:
    def test_admin_status_turns_healthy_when_relay_polls(self, client, monkeypatch):
        monkeypatch.setattr(settings, "RELAY_SECRET_MUSH", "relay-secret")
        monkeypatch.setattr(ai_manager.queue, "last_poll", None)
        h = _god_headers(client)
        s = client.get("/api/admin/ai", headers=h).json()
        assert s["state"] == "unreachable" and s["relay_alive"] is False
        assert client.get("/relay/jobs?wait=0", headers=_signed("GET", "/relay/jobs?wait=0")).status_code == 204
        s = client.get("/api/admin/ai", headers=h).json()
        assert s["state"] == "healthy" and s["relay_alive"] is True and s["healthy"] is True

    def test_admin_toggle_round_trip(self, client, monkeypatch):
        monkeypatch.setattr(settings, "RELAY_SECRET_MUSH", "relay-secret")
        h = _god_headers(client)
        s = client.post("/api/admin/ai", json={"enabled": False}, headers=h).json()
        assert s["enabled"] is False and s["state"] == "disabled"
        assert client.get("/api/admin/ai", headers=h).json()["state"] == "disabled"
        # relay endpoints still answer so health stays visible while switched off
        assert client.get("/relay/jobs?wait=0", headers=_signed("GET", "/relay/jobs?wait=0")).status_code == 204
        s = client.post("/api/admin/ai", json={"enabled": True}, headers=h).json()
        assert s["enabled"] is True and s["state"] == "healthy"

    def test_npc_reply_over_signed_http_relay(self, client, monkeypatch):
        monkeypatch.setattr(settings, "RELAY_SECRET_MUSH", "relay-secret")
        assert client.get("/relay/jobs?wait=0", headers=_signed("GET", "/relay/jobs?wait=0")).status_code == 204
        out = {}

        def ask():
            async def go():
                return await ai_manager.reply("hi", npc_name="Guard", player_id=7)
            return client.portal.call(go)

        import threading
        t = threading.Thread(target=lambda: out.setdefault("r", ask()))
        t.start()
        job = None
        for _ in range(50):
            r = client.get("/relay/jobs?wait=1", headers=_signed("GET", "/relay/jobs?wait=1"))
            if r.status_code == 200:
                job = r.json()
                break
        assert job and job["template_id"] == "mush.npc" and job["player_id"] == "mush-7"
        body = json.dumps({"job_id": job["job_id"], "status": "ok", "text": "\x1b[1mWell met!\x1b[0m"}).encode()
        path = f"/relay/jobs/{job['job_id']}/result"
        assert client.post(path, content=body, headers=_signed("POST", path, body)).status_code == 204
        t.join(5)
        assert out["r"].source == SOURCE_AI and "\x1b" not in out["r"].text and "Well met!" in out["r"].text
        assert client.get("/api/admin/ai", headers=_god_headers(client)).json()["last_ok_age_s"] is not None


# =============================================================================
# FUNCTIONAL (in-game commands)
# =============================================================================

@pytest_asyncio.fixture
async def world(seeded_session, monkeypatch):
    monkeypatch.setattr(settings, "RELAY_SECRET_MUSH", "s")
    monkeypatch.setattr(ai_manager, "queue", RelayJobQueue())  # configured, relay not polling
    await _add_npc(seeded_session)
    parser = CommandParser(seeded_session)
    player = await seeded_session.get(DBObject, 10)
    god = await seeded_session.get(DBObject, 1)
    return parser, player, god


class TestFunctional:
    @pytest.mark.asyncio
    async def test_talk_with_relay_down_gives_scripted_line_and_hint(self, world):
        parser, player, _ = world
        out = await parser.parse(player, "talk to guard=hello")
        line, hint = out.split("\n")
        assert line.startswith('Guard says, "') and line[len('Guard says, "'):-1] in SCRIPTED_NPC
        assert hint == "(scripted reply - the narrator is away)"

    @pytest.mark.asyncio
    async def test_talk_with_healthy_relay_uses_ai_line(self, world, seeded_session):
        parser, player, _ = world
        ai_manager.queue.last_poll = ai_manager.queue.clock()
        worker = _relay_worker(ai_manager.queue, [("ok", '"Move along, citizen."')])
        out = await parser.parse(player, "talk to guard=hello")
        await worker
        assert out == 'Guard says, "Move along, citizen."'
        npc = (await seeded_session.execute(
            __import__("sqlalchemy").select(NPC))).scalars().first()
        assert json.loads(npc.conversation_history)[-1]["content"] == "Move along, citizen."

    @pytest.mark.asyncio
    async def test_player_opt_out_skips_relay(self, world):
        parser, player, _ = world
        ai_manager.queue.last_poll = ai_manager.queue.clock()
        assert "off for you" in await parser.parse(player, "@ai/me off")
        assert PLAYER_OPT_OUT_FLAG in player.flags
        out = await parser.parse(player, "talk to guard=hello")
        assert "\n" not in out and ai_manager.queue.stats["submitted"] == 0
        assert "Your AI replies: off" in await parser.parse(player, "@ai/status")
        assert "on for you" in await parser.parse(player, "@ai/me on")
        assert PLAYER_OPT_OUT_FLAG not in (player.flags or "")
        assert "Usage" in await parser.parse(player, "@ai/me maybe")

    @pytest.mark.asyncio
    async def test_staff_switch_off_and_on(self, world):
        parser, player, god = world
        assert "switched off" in await parser.parse(god, "@ai/off")
        out = await parser.parse(player, "talk to guard=hello")
        assert out.endswith("(scripted reply - AI narration is switched off)")
        assert "Off (switched off by staff)" in await parser.parse(player, "@ai/status")
        assert "switched on" in await parser.parse(god, "@ai/on")
        assert ai_manager.enabled is True

    @pytest.mark.asyncio
    async def test_ai_status_reflects_relay_health(self, world):
        parser, player, god = world
        assert "relay is not answering" in await parser.parse(player, "@ai/status")
        ai_manager.queue.last_poll = ai_manager.queue.clock()
        out = await parser.parse(player, "@ai/status")
        assert "On - relay reachable" in out and "Relay last polled" not in out
        assert "Relay last polled" in await parser.parse(god, "@ai/status")

    @pytest.mark.asyncio
    async def test_guide_scripted_answer_when_relay_down(self, world):
        parser, player, _ = world
        out = await parser.parse(player, "guide How do I create a room?")
        assert "@dig" in out and out.endswith("(scripted reply - the narrator is away)")
        help_text = await parser.parse(player, "guide")
        assert "Nova Games narrator relay" in help_text and "Ollama" not in help_text

    @pytest.mark.asyncio
    async def test_guide_uses_ai_when_healthy(self, world):
        parser, player, _ = world
        ai_manager.queue.last_poll = ai_manager.queue.clock()
        worker = _relay_worker(ai_manager.queue, [("ok", "Use @dig to make a room, traveller.")])
        out = await parser.parse(player, "ai how do rooms work")
        await worker
        assert "Use @dig to make a room, traveller." in out and "scripted reply" not in out

    @pytest.mark.asyncio
    async def test_game_fully_playable_with_ai_off(self, world):
        parser, player, god = world
        await parser.parse(god, "@ai/off")
        for cmd in ("look", "say hi", "inventory", "talk to guard=hi", "ask guard=where?", "guide help me",
                    "@ai/status"):
            out = await parser.parse(player, cmd)
            assert out and not out.startswith("Error executing command"), (cmd, out)
        assert ai_manager.queue.stats["submitted"] == 0


# =============================================================================
# FRAME (event loop keeps ticking; AI output is one well-formed socket frame)
# =============================================================================

class TestFrame:
    @pytest.mark.asyncio
    async def test_event_loop_not_blocked_while_waiting_for_relay(self, monkeypatch):
        monkeypatch.setattr(settings, "AI_RESULT_TIMEOUT_S", 0.3)
        mgr = _manager(monkeypatch)
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        t = asyncio.create_task(ticker())
        reply = await mgr.reply("hello", npc_name="Guard")
        t.cancel()
        assert reply.source == SOURCE_SCRIPTED and ticks >= 10

    def test_guide_output_is_one_json_frame_over_websocket(self, client, monkeypatch):
        monkeypatch.setattr(settings, "RELAY_SECRET_MUSH", "")
        r = client.post("/api/auth/login", json={"username": "One", "password": os.environ["GOD_PASSWORD"]},
                        headers=ORIGIN)
        token = r.json()["token"]
        with client.websocket_connect("/ws", headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json({"type": "auth", "token": token})
            assert ws.receive_json()["type"] == "welcome"
            ws.receive_json()  # look
            ws.send_json({"type": "command", "command": "guide how do I dig a room"})
            msg = ws.receive_json()
            assert msg["type"] == "output" and "@dig" in msg["message"]
            assert msg["message"].rstrip().endswith("(scripted reply - the narrator is away)")
            ws.send_json({"type": "command", "command": "@ai/status"})
            msg = ws.receive_json()
            assert msg["type"] == "output" and "not configured" in msg["message"]

    def test_validated_line_is_single_line(self):
        out = validate_output("Line one.\nLine two.\r\n\tLine three.")
        assert out == "Line one. Line two. Line three." and not re.search(r"[\r\n\t]", out)
