"""
Hardening tests (2026-10 security pass) in the seven project categories:
Security, Performance, Retry, Unit, Integration (real Postgres), Functional, Frame.
Author: Jordan Koch (GitHub: kochj23)
"""
import asyncio
import hashlib
import json
import os
import re
import stat
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend import auth
from backend.config import settings
from backend.relay import RelayJobQueue, sign, verify
from backend.security import RateLimiter

ROOT = Path(__file__).resolve().parent.parent
ORIGIN = {"origin": "http://testserver"}
PW = "correct-horse-1"  # test-only credential


@pytest.fixture
def client():
    from backend.main import app
    from backend.api.websocket import manager
    with TestClient(app) as c:
        yield c
    manager.ip_counts.clear()
    manager.total_sockets = 0


def _login(client, username, password, headers=None):
    return client.post("/api/auth/login", json={"username": username, "password": password},
                       headers=headers or ORIGIN)


def _register(client, username, pw=PW, **extra):
    body = {"username": username, "password": pw}
    body.update(extra)
    return client.post("/api/players/register", json=body, headers=ORIGIN)


def _god_token(client):
    r = _login(client, "One", os.environ["GOD_PASSWORD"])
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _signed(method, path, body=b"", secret="relay-secret", ts=None):
    ts = str(int(time.time()) if ts is None else ts)
    return {"x-relay-ts": ts, "x-relay-sig": sign(secret, ts, method, path, body)}


# =============================================================================
# SECURITY
# =============================================================================

class TestSecurityRestAuth:
    @pytest.mark.parametrize("path", ["/api/", "/api/players", "/api/players/1", "/api/objects/0",
                                      "/api/rooms/0/contents", "/api/rooms/map", "/api/stats",
                                      "/api/admin/players", "/api/admin/ai", "/api/auth/me"])
    def test_anonymous_is_refused(self, client, path):
        assert client.get(path).status_code == 401

    def test_non_admin_cannot_use_admin_routes(self, client):
        assert _register(client, "Plain").status_code == 200
        token = _login(client, "Plain", PW).json()["token"]
        h = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/stats", headers=h).status_code == 403
        assert client.get("/api/admin/players", headers=h).status_code == 403
        assert client.post("/api/admin/players/1/approve", headers={**h, **ORIGIN}).status_code == 403

    def test_admin_page_requires_admin_session(self, client):
        r = client.get("/admin", follow_redirects=False)
        assert r.status_code == 303
        _god_token(client)  # sets the HttpOnly cookie on the client
        r = client.get("/admin", follow_redirects=False)
        assert r.status_code == 200 and "Admin Dashboard" in r.text

    def test_docs_and_openapi_disabled(self, client):
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404

    def test_tampered_token_rejected(self, client):
        token = auth.issue_token(1)
        bad = token[:-2] + ("A" if token[-1] != "A" else "B") + token[-1]
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {bad}"}).status_code == 401

    def test_cross_origin_login_refused(self, client):
        r = _login(client, "One", os.environ["GOD_PASSWORD"], headers={"origin": "http://evil.example"})
        assert r.status_code == 403

    def test_login_requires_exact_username(self, client):
        # 'On' is a substring of 'One': the old ilike lookup would have matched it.
        assert _login(client, "On", os.environ["GOD_PASSWORD"]).status_code == 401

    def test_session_cookie_flags(self, client):
        r = _login(client, "One", os.environ["GOD_PASSWORD"])
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie

    def test_request_body_cap(self, client):
        r = client.post("/api/auth/login", content=b"x" * (70 * 1024),
                        headers={**ORIGIN, "content-type": "application/json"})
        assert r.status_code == 413


class TestSecurityRegistration:
    def test_closed_mode(self, client, monkeypatch):
        monkeypatch.setattr(settings, "REGISTRATION_MODE", "closed")
        assert _register(client, "Nope").status_code == 403

    def test_invite_mode(self, client, monkeypatch):
        monkeypatch.setattr(settings, "REGISTRATION_MODE", "invite")
        monkeypatch.setattr(settings, "INVITE_CODE", "lan-party-2026")
        assert _register(client, "NoCode").status_code == 403
        assert _register(client, "WrongCode", invite_code="guess").status_code == 403
        assert _register(client, "GoodCode", invite_code="lan-party-2026").status_code == 200

    def test_invite_mode_without_configured_code_refuses(self, client, monkeypatch):
        monkeypatch.setattr(settings, "REGISTRATION_MODE", "invite")
        monkeypatch.setattr(settings, "INVITE_CODE", "")
        assert _register(client, "Empty", invite_code="").status_code == 403

    def test_approval_mode_blocks_login_until_approved(self, client, monkeypatch):
        monkeypatch.setattr(settings, "REGISTRATION_MODE", "approval")
        pid = _register(client, "Waiting").json()["id"]
        r = _login(client, "Waiting", PW)
        assert r.status_code == 403 and "approval" in r.json()["detail"]
        god = {"Authorization": f"Bearer {_god_token(client)}", **ORIGIN}
        assert client.post(f"/api/admin/players/{pid}/approve", headers=god).status_code == 200
        assert _login(client, "Waiting", PW).status_code == 200

    def test_registration_rate_limited_per_ip(self, client):
        codes = [_register(client, f"Bot{i}").status_code for i in range(5)]
        assert codes[:3] == [200, 200, 200]
        assert codes[3] == 429

    def test_weak_or_overlong_password_rejected(self, client):
        assert _register(client, "Shorty", pw="short").status_code == 400
        assert _register(client, "Longy", pw="x" * 100).status_code == 400


class TestSecurityLoginLimits:
    def test_per_ip_limit(self, client):
        codes = [_login(client, f"user{i}", "wrong-password").status_code for i in range(22)]
        assert codes[0] == 401
        assert 429 in codes[19:]

    def test_per_account_limit(self, client):
        limiter_key_hits = []
        for i in range(12):
            # vary the IP via trusted X-Forwarded-For is not possible here; reset ip bucket instead
            from backend.security import rate_limiter
            rate_limiter.reset("testclient", "login_ip")
            limiter_key_hits.append(_login(client, "One", "wrong-password").status_code)
        assert limiter_key_hits[:10] == [401] * 10
        assert limiter_key_hits[10] == 429


class TestSecurityWebSocket:
    def test_foreign_origin_rejected(self, client):
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws", headers={"origin": "http://evil.example"}) as ws:
                ws.receive_json()
        assert exc.value.code == 1008

    def test_per_ip_connection_cap(self, client, monkeypatch):
        monkeypatch.setattr(settings, "WS_MAX_PER_IP", 2)
        with client.websocket_connect("/ws", headers=ORIGIN) as a, \
                client.websocket_connect("/ws", headers=ORIGIN) as b:
            a.receive_json()
            b.receive_json()
            with client.websocket_connect("/ws", headers=ORIGIN) as c:
                msg = c.receive_json()
                assert msg["type"] == "error" and "Too many connections" in msg["message"]
            a.send_json({"type": "disconnect"})
            b.send_json({"type": "disconnect"})

    def test_oversized_message_closes(self, client):
        token = _god_token(client)
        with client.websocket_connect("/ws", headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json({"type": "auth", "token": token})
            assert ws.receive_json()["type"] == "welcome"
            ws.receive_json()  # look
            ws.send_text(json.dumps({"type": "command", "command": "say " + "x" * 20000}))
            assert ws.receive_json()["message"] == "Message too large"

    def test_frame_flood_disconnects(self, client, monkeypatch):
        monkeypatch.setattr(settings, "WS_FRAMES_PER_10S", 5)
        token = _god_token(client)
        with client.websocket_connect("/ws", headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json({"type": "auth", "token": token})
            ws.receive_json(); ws.receive_json()
            for _ in range(6):
                ws.send_json({"type": "ping"})
            msgs = [ws.receive_json() for _ in range(6)]
            assert msgs[-1]["type"] == "error" and "Too many messages" in msgs[-1]["message"]

    def test_bad_token_refused(self, client):
        with client.websocket_connect("/ws", headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json({"type": "auth", "token": "garbage.token"})
            assert ws.receive_json()["type"] == "error"


class TestSecurityRelayEndpoints:
    def test_disabled_without_secret(self, client, monkeypatch):
        monkeypatch.setattr(settings, "RELAY_SECRET_MUSH", "")
        assert client.get("/relay/jobs?wait=0").status_code == 404

    def test_bad_signature_and_skew(self, client, monkeypatch):
        monkeypatch.setattr(settings, "RELAY_SECRET_MUSH", "relay-secret")
        assert client.get("/relay/jobs?wait=0", headers=_signed("GET", "/relay/jobs?wait=0", secret="nope")).status_code == 401
        old = _signed("GET", "/relay/jobs?wait=0", ts=int(time.time()) - 600)
        assert client.get("/relay/jobs?wait=0", headers=old).status_code == 401
        assert client.get("/relay/jobs?wait=0", headers=_signed("GET", "/relay/jobs?wait=0")).status_code == 204


class TestSecurityMisc:
    @pytest.mark.asyncio
    async def test_hostname_not_leaked(self, seeded_session):
        from backend.engine.softcode import SoftcodeInterpreter
        import socket
        out = await SoftcodeInterpreter(seeded_session).eval("[hostname()]")
        assert socket.gethostname() not in out

    def test_god_password_never_printed(self):
        src = (ROOT / "backend" / "database.py").read_text()
        assert "password: {god_password}" not in src
        assert not re.search(r"print\(.*god_password", src)

    def test_god_password_file_is_private(self, tmp_path, monkeypatch):
        from backend import database
        monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
        path = database._store_god_password("s3cret")
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

    def test_x_forwarded_for_only_from_trusted_proxy(self):
        assert auth.client_ip_from("203.0.113.9", "1.2.3.4") == "203.0.113.9"
        assert auth.client_ip_from("172.30.11.2", "1.2.3.4") == "1.2.3.4"
        assert auth.client_ip_from("172.30.11.2", "9.9.9.9, 1.2.3.4") == "1.2.3.4"

    def test_security_headers(self, client):
        r = client.get("/")
        assert "script-src 'self'" in r.headers["content-security-policy"]
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["referrer-policy"] == "no-referrer"
        assert "server" not in {k.lower() for k in r.headers if k.lower() == "server" and "uvicorn" in r.headers[k]}


# =============================================================================
# PERFORMANCE
# =============================================================================

class TestPerformance:
    def test_rate_limiter_does_no_disk_io(self):
        limiter = RateLimiter()
        with patch("builtins.open", side_effect=AssertionError("disk I/O in rate limiter")):
            for i in range(2000):
                limiter.is_allowed(f"user{i % 50}", "command")

    def test_rate_limiter_is_fast(self):
        limiter = RateLimiter()
        start = time.perf_counter()
        for i in range(20000):
            limiter.is_allowed(str(i % 100), "api")
        assert time.perf_counter() - start < 1.0

    def test_rate_limiter_memory_bounded(self):
        limiter = RateLimiter()
        limiter.MAX_KEYS = 100
        for i in range(1000):
            limiter.is_allowed(f"k{i}", "command")
        assert len(limiter.requests) <= 100

    @pytest.mark.asyncio
    async def test_softcode_cpu_bomb_is_bounded(self, seeded_session):
        from backend.engine.softcode import SoftcodeInterpreter
        interp = SoftcodeInterpreter(seeded_session)
        start = time.perf_counter()
        out = await interp.eval("[loop(100,[loop(100,[loop(100,[add(1,1)])])])]")
        assert time.perf_counter() - start < 2.0
        assert "BUDGET EXCEEDED" in out or len(out) <= settings.SOFTCODE_MAX_OUTPUT

    @pytest.mark.asyncio
    async def test_huge_lnum_and_repeat_rejected_fast(self, seeded_session):
        from backend.engine.softcode import SoftcodeInterpreter
        interp = SoftcodeInterpreter(seeded_session)
        start = time.perf_counter()
        assert "#-1" in await interp.eval("[lnum(1,100000000)]")
        assert "#-1" in await interp.eval("[repeat(x,999999999)]")
        assert "#-1" in await interp.eval("[space(99999999999999999999999999)]")
        assert time.perf_counter() - start < 0.5

    @pytest.mark.asyncio
    async def test_redos_pattern_is_bounded(self, seeded_session):
        from backend.engine.softcode import SoftcodeInterpreter
        interp = SoftcodeInterpreter(seeded_session)
        start = time.perf_counter()
        await interp.eval("[regmatch(" + "a" * 60 + "!,(a|aa)+$)]")
        assert time.perf_counter() - start < 1.0


# =============================================================================
# RETRY
# =============================================================================

class _FlakyConn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, *a, **k):
        return None


class _FlakyEngine:
    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.calls = 0

    def connect(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionRefusedError("db not up")
        return _FlakyConn()


class TestRetry:
    @pytest.mark.asyncio
    async def test_wait_for_db_retries_with_backoff(self):
        from backend.database import wait_for_db
        eng = _FlakyEngine(fail_times=3)
        sleeps = []

        async def fake_sleep(d):
            sleeps.append(d)

        with patch("backend.database.asyncio.sleep", fake_sleep):
            attempt = await wait_for_db(eng, retries=6, base_delay=0.5, max_delay=1.5)
        assert attempt == 4
        assert sleeps == [0.5, 1.0, 1.5]

    @pytest.mark.asyncio
    async def test_wait_for_db_gives_up(self):
        from backend.database import wait_for_db
        eng = _FlakyEngine(fail_times=99)

        async def fake_sleep(d):
            return None

        with patch("backend.database.asyncio.sleep", fake_sleep):
            with pytest.raises(ConnectionRefusedError):
                await wait_for_db(eng, retries=3)
        assert eng.calls == 3

    @pytest.mark.asyncio
    async def test_relay_timeout_falls_back(self, monkeypatch):
        from backend.engine.ai_manager import AIManager
        monkeypatch.setattr(settings, "RELAY_SECRET_MUSH", "s")
        monkeypatch.setattr(settings, "AI_RESULT_TIMEOUT_S", 0.05)
        mgr = AIManager(RelayJobQueue())
        line = await mgr.generate_response("hello?", npc_name="Bob", player_id=1)
        assert line and mgr.queue.stats["timeouts"] == 1

    @pytest.mark.asyncio
    async def test_relay_queue_full_falls_back_immediately(self, monkeypatch):
        from backend.engine.ai_manager import AIManager
        monkeypatch.setattr(settings, "RELAY_SECRET_MUSH", "s")
        mgr = AIManager(RelayJobQueue(max_pending=0))
        start = time.perf_counter()
        assert await mgr.generate_response("hi", npc_name="Bob")
        assert time.perf_counter() - start < 0.2
        assert mgr.queue.stats["rejected_full"] == 1

    @pytest.mark.asyncio
    async def test_relay_rejected_result_uses_fallback(self, monkeypatch):
        from backend.engine.ai_manager import AIManager
        monkeypatch.setattr(settings, "RELAY_SECRET_MUSH", "s")
        q = RelayJobQueue()
        mgr = AIManager(q)

        async def worker():
            job = await q.next_job(2)
            q.complete(job["job_id"], {"job_id": job["job_id"], "status": "rejected", "text": ""})

        t = asyncio.create_task(worker())
        line = await mgr.generate_response("hi", npc_name="Bob")
        await t
        assert line in [
            "Hmm. Give me a moment to think on that.",
            "The fog in my head is thick today. Ask me again later?",
            "Interesting. Tell me more about that.",
            "I've heard rumours, but nothing I'd stake my reputation on.",
            "Ah, a question for the ages. Perhaps the Plaza notice board knows.",
        ]


# =============================================================================
# UNIT
# =============================================================================

class TestUnit:
    def test_token_roundtrip_and_expiry(self):
        t = auth.issue_token(42, ttl_seconds=60, now=1000)
        assert auth.verify_token(t, now=1030) == 42
        assert auth.verify_token(t, now=1061) is None
        assert auth.verify_token("", now=1030) is None
        assert auth.verify_token("a.b.c") is None

    def test_password_context(self):
        from backend.passwords import pwd_context
        h = pwd_context.hash(PW)
        assert pwd_context.verify(PW, h)
        assert not pwd_context.verify("wrong", h)
        assert not pwd_context.verify("x" * 100, h)
        with pytest.raises(ValueError):
            pwd_context.hash("x" * 100)

    def test_split_pg_url_verify_full(self, tmp_path):
        import ssl
        from backend.database import split_pg_url
        url, ssl_arg = split_pg_url("postgresql://mush:p%40ss@games-pg:5432/games?sslmode=verify-full")
        assert url == "postgresql+asyncpg://mush:p%40ss@games-pg:5432/games"
        assert isinstance(ssl_arg, ssl.SSLContext)
        assert ssl_arg.check_hostname and ssl_arg.verify_mode == ssl.CERT_REQUIRED
        url2, ssl2 = split_pg_url("postgresql+asyncpg://u:p@h/db")
        assert url2 == "postgresql+asyncpg://u:p@h/db" and ssl2 is None

    def test_relay_signature_matches_contract(self):
        body = b'{"x":1}'
        expected_msg = "\n".join(["1700000000", "POST", "/relay/jobs/abc/result", hashlib.sha256(body).hexdigest()])
        import hmac as _h
        expected = _h.new(b"k", expected_msg.encode(), hashlib.sha256).hexdigest()
        assert sign("k", "1700000000", "post", "/relay/jobs/abc/result", body) == expected
        assert verify("k", "1700000000", expected, "POST", "/relay/jobs/abc/result", body, now=1700000030)
        assert not verify("k", "1700000000", expected, "POST", "/relay/jobs/abc/result", body, now=1700000100)

    def test_size_arg_guard(self):
        from backend.engine.softcode_budget import check_size_args
        assert check_size_args("repeat", ["x", "10"]) is None
        assert check_size_args("repeat", ["x", "5000"]) == "#-1 ARGUMENT TOO LARGE"
        assert check_size_args("add", ["99999999"]) is None

    def test_budget_limits(self):
        from backend.engine.softcode_budget import EvalBudget, SoftcodeBudgetExceeded
        b = EvalBudget(max_calls=3)
        b.tick(); b.tick(); b.tick()
        with pytest.raises(SoftcodeBudgetExceeded):
            b.tick()
        with pytest.raises(SoftcodeBudgetExceeded):  # sticky
            b.enter()
        clock = iter([0.0, 1.0])
        b2 = EvalBudget(max_ms=250, clock=lambda: next(clock))
        with pytest.raises(SoftcodeBudgetExceeded, match="time"):
            b2.tick()
        b3 = EvalBudget(max_depth=2)
        b3.enter(); b3.enter()
        with pytest.raises(SoftcodeBudgetExceeded, match="recursion"):
            b3.enter()
        with pytest.raises(SoftcodeBudgetExceeded, match="output"):
            EvalBudget(max_output=5).check_output("123456")

    def test_npc_vars_clipped_to_contract(self):
        from backend.engine.ai_manager import AIManager
        v = AIManager.build_npc_vars("N" * 99, "d" * 999, "r" * 99, "p" * 99, "s" * 999,
                                     [{"speaker": "a" * 99, "text": "t" * 999}] * 9)
        assert len(v["npc_name"]) == 40 and len(v["npc_description"]) == 400
        assert len(v["room_name"]) == 80 and len(v["player_says"]) == 200
        assert len(v["history"]) == 5 and len(v["history"][0]["text"]) == 200

    def test_origin_matrix(self, monkeypatch):
        from backend.api.websocket import origin_allowed
        monkeypatch.setattr(settings, "ALLOWED_ORIGINS", [])
        assert origin_allowed(None, "192.168.1.5:8088")
        assert origin_allowed("http://192.168.1.5:8088", "192.168.1.5:8088")
        assert not origin_allowed("http://evil.example", "192.168.1.5:8088")
        assert not origin_allowed("null", "192.168.1.5:8088")
        monkeypatch.setattr(settings, "ALLOWED_ORIGINS", ["http://192.168.1.5:8088"])
        assert origin_allowed("http://192.168.1.5:8088/", "whatever")

    def test_frame_limiter(self):
        from backend.api.websocket import FrameLimiter
        f = FrameLimiter(2, window_s=10)
        assert f.allow(0) and f.allow(1) and not f.allow(2)
        assert f.allow(11.5)


# =============================================================================
# INTEGRATION (real Postgres: private initdb cluster or PG_TEST_URL)
# =============================================================================

from tests.pg_cluster import PgCluster  # noqa: E402

pg_required = pytest.mark.skipif(not PgCluster.available(), reason="no Postgres binaries / PG_TEST_URL")


@pytest.fixture(scope="module")
def pg():
    cluster = PgCluster().start()
    yield cluster
    cluster.stop()


@pg_required
class TestIntegrationPostgres:
    @pytest.mark.asyncio
    async def test_schema_owner_migrates_app_role_dml_only(self, pg):
        from sqlalchemy import text
        from backend.database import build_engine, _init_schema_and_seed
        owner = build_engine(pg.migrate_url)
        app = build_engine(pg.url)
        try:
            await _init_schema_and_seed(owner)
            await _init_schema_and_seed(owner)  # idempotent restart
            async with app.connect() as conn:
                n = (await conn.execute(text("SELECT count(*) FROM objects"))).scalar()
                assert n >= 5
                with pytest.raises(Exception):
                    await conn.execute(text("CREATE TABLE evil (id int)"))
        finally:
            await owner.dispose()
            await app.dispose()

    @pytest.mark.asyncio
    async def test_sequences_synced_after_seed(self, pg):
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        from backend.database import build_engine, _init_schema_and_seed
        from backend.engine.objects import ObjectManager
        from backend.models import ObjectType
        owner = build_engine(pg.migrate_url)
        app = build_engine(pg.url)
        try:
            await _init_schema_and_seed(owner)
            async with async_sessionmaker(app, class_=AsyncSession, expire_on_commit=False)() as s:
                obj = await ObjectManager(s).create_object("PgThing", ObjectType.THING, owner_id=1, location_id=2)
                assert obj.id > 5
        finally:
            await owner.dispose()
            await app.dispose()

    @pytest.mark.asyncio
    async def test_statement_timeout_enforced(self, pg, monkeypatch):
        from sqlalchemy import text
        from backend.database import build_engine
        monkeypatch.setattr(settings, "DB_STATEMENT_TIMEOUT_MS", 300)
        app = build_engine(pg.url)
        try:
            start = time.perf_counter()
            with pytest.raises(Exception):
                async with app.connect() as conn:
                    await conn.execute(text("SELECT pg_sleep(5)"))
            assert time.perf_counter() - start < 3
        finally:
            await app.dispose()

    @pytest.mark.asyncio
    async def test_rest_login_and_register_on_postgres(self, pg):
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        from backend.database import build_engine, _init_schema_and_seed, get_db
        from backend.main import app as fastapi_app
        owner = build_engine(pg.migrate_url)
        app_engine = build_engine(pg.url)
        factory = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)

        async def _db():
            async with factory() as s:
                yield s

        fastapi_app.dependency_overrides[get_db] = _db
        try:
            await _init_schema_and_seed(owner)
            async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://testserver") as c:
                r = await c.post("/api/players/register", json={"username": "PgUser", "password": "pg-password-1"},
                                 headers=ORIGIN)
                assert r.status_code == 200, r.text
                r = await c.post("/api/auth/login", json={"username": "pguser", "password": "pg-password-1"},
                                 headers=ORIGIN)
                assert r.status_code == 200
                me = await c.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
                assert me.json()["name"] == "PgUser"
        finally:
            fastapi_app.dependency_overrides.clear()
            await owner.dispose()
            await app_engine.dispose()


# =============================================================================
# FUNCTIONAL
# =============================================================================

class TestFunctional:
    def test_register_login_play_over_websocket(self, client):
        assert _register(client, "Walker").status_code == 200
        token = _login(client, "Walker", PW).json()["token"]
        with client.websocket_connect("/ws", headers=ORIGIN) as ws:
            assert ws.receive_json()["type"] == "auth_required"
            ws.send_json({"type": "auth", "token": token})
            welcome = ws.receive_json()
            assert welcome["type"] == "welcome" and welcome["player_name"] == "Walker"
            assert ws.receive_json()["type"] == "output"
            ws.send_json({"type": "command", "command": "look"})
            assert "Central Plaza" in ws.receive_json()["message"]

    def test_password_login_over_websocket_still_supported(self, client):
        with client.websocket_connect("/ws", headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json({"type": "auth", "username": "One", "password": os.environ["GOD_PASSWORD"]})
            assert ws.receive_json()["type"] == "welcome"

    def test_second_login_replaces_first(self, client):
        token = _god_token(client)
        with client.websocket_connect("/ws", headers=ORIGIN) as first:
            first.receive_json()
            first.send_json({"type": "auth", "token": token})
            first.receive_json(); first.receive_json()
            with client.websocket_connect("/ws", headers=ORIGIN) as second:
                second.receive_json()
                second.send_json({"type": "auth", "token": token})
                assert second.receive_json()["type"] == "welcome"
                kicked = first.receive_json()
                assert kicked["type"] == "error" and "another session" in kicked["message"]

    def test_relay_round_trip_over_http(self, client, monkeypatch):
        monkeypatch.setattr(settings, "RELAY_SECRET_MUSH", "relay-secret")
        from backend.engine.ai_manager import ai_manager
        loop_result = {}

        def ask():
            async def go():
                return await ai_manager.queue.submit("mush.npc", {"player_says": "hi"}, "p1", 150, timeout=5)
            return client.portal.call(go)

        import threading
        t = threading.Thread(target=lambda: loop_result.setdefault("r", ask()))
        t.start()
        job = None
        for _ in range(50):
            r = client.get("/relay/jobs?wait=1", headers=_signed("GET", "/relay/jobs?wait=1"))
            if r.status_code == 200:
                job = r.json()
                break
        assert job and job["template_id"] == "mush.npc" and job["max_tokens"] == 150
        body = json.dumps({"job_id": job["job_id"], "status": "ok", "text": "Well met!", "model": "llama3.2:3b",
                           "latency_ms": 10, "reason": None}).encode()
        path = f"/relay/jobs/{job['job_id']}/result"
        assert client.post(path, content=body, headers=_signed("POST", path, body)).status_code == 204
        t.join(5)
        assert loop_result["r"]["text"] == "Well met!"

    def test_link_site_account_hook(self, client):
        god = {"Authorization": f"Bearer {_god_token(client)}", **ORIGIN}
        r = client.post("/api/admin/players/1/link-account", json={"site_account_id": "acct_123"}, headers=god)
        assert r.status_code == 200 and r.json()["site_account_id"] == "acct_123"
        rows = client.get("/api/admin/players", headers=god).json()
        assert any(p["id"] == 1 and p["site_account_id"] == "acct_123" for p in rows)
        bad = client.post("/api/admin/players/1/link-account", json={"site_account_id": "<script>"}, headers=god)
        assert bad.status_code == 422

    @pytest.mark.asyncio
    async def test_password_command(self, seeded_session):
        from backend.engine.commands import CommandParser
        from backend.models import DBObject
        from backend.passwords import pwd_context
        player = await seeded_session.get(DBObject, 1)
        parser = CommandParser(seeded_session)
        assert await parser.parse(player, "@password wrong=new-password-9") == "Incorrect password."
        assert await parser.parse(player, "@password potrzebie=new-password-9") == "Password changed."
        assert pwd_context.verify("new-password-9", player.password_hash)


# =============================================================================
# FRAME (served HTML frames + WebSocket frame shapes)
# =============================================================================

class TestFrame:
    @pytest.mark.parametrize("page", ["index.html", "admin.html"])
    def test_pages_are_strict_csp_clean(self, page):
        html = (ROOT / "frontend" / page).read_text()
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "inline <script>"
        assert "<style" not in html
        assert not re.search(r"\son[a-z]+=", html), "inline event handler"
        assert "style=" not in html
        assert not re.search(r'(src|href)="/(?!/)', html), "absolute path breaks the /mush/ prefix"
        assert "potrzebie" not in html

    def test_js_uses_relative_urls(self):
        for js in (ROOT / "frontend" / "js").glob("*.js"):
            src = js.read_text()
            assert "fetch('/" not in src and 'fetch("/' not in src and "fetch(`/" not in src, js.name

    def test_broadcast_frames_are_json(self):
        from backend.api.websocket import _as_output
        frame = json.loads(_as_output("Bob has connected."))
        assert frame == {"type": "output", "message": "Bob has connected."}
        assert _as_output('{"type":"pong"}') == '{"type":"pong"}'

    def test_malformed_frame_gets_error_not_crash(self, client):
        token = _god_token(client)
        with client.websocket_connect("/ws", headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json({"type": "auth", "token": token})
            ws.receive_json(); ws.receive_json()
            ws.send_text("{not json")
            assert ws.receive_json() == {"type": "error", "message": "Malformed message"}
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}

    def test_auth_frame_must_come_first(self, client):
        with client.websocket_connect("/ws", headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json({"type": "command", "command": "look"})
            assert ws.receive_json()["message"] == "Authentication required"

    def test_healthz_frame(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200 and r.json() == {"status": "ok"}
