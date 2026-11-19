"""
Login and registration rate limits survive a restart (rate_limit_hits table);
other limits stay memory-only.
"""
import logging
import os
import time

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.models import RateLimitHit
from backend.security import RateLimiter
from tests.pg_cluster import PgCluster


@pytest.fixture
def factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _rows(factory, bucket=None):
    async with factory() as s:
        q = select(func.count()).select_from(RateLimitHit)
        if bucket:
            q = q.where(RateLimitHit.bucket == bucket)
        return (await s.execute(q)).scalar()


async def _hit(limiter, factory, key, limit_type, n):
    async with factory() as s:
        return [await limiter.check(s, key, limit_type) for _ in range(n)]


class TestSurvivesRestart:
    async def test_login_ip_limit_survives_restart(self, factory):
        before = RateLimiter()
        assert await _hit(before, factory, "203.0.113.5", "login_ip", 21) == [True] * 20 + [False]
        assert await _rows(factory, "login_ip:203.0.113.5") == 20

        after = RateLimiter()  # new process: empty memory
        assert await after.load(factory) == 20
        assert not after.is_allowed("203.0.113.5", "login_ip")
        assert after.is_allowed("198.51.100.7", "login_ip")

    async def test_login_user_limit_survives_restart(self, factory):
        await _hit(RateLimiter(), factory, "one", "login_user", 10)
        after = RateLimiter()
        await after.load(factory)
        assert await _hit(after, factory, "one", "login_user", 1) == [False]

    async def test_registration_limit_survives_restart(self, factory):
        await _hit(RateLimiter(), factory, "203.0.113.9", "register_ip", 3)
        after = RateLimiter()
        await after.load(factory)
        assert await _hit(after, factory, "203.0.113.9", "register_ip", 1) == [False]

    async def test_successful_login_reset_is_persisted(self, factory):
        before = RateLimiter()
        await _hit(before, factory, "one", "login_user", 9)
        async with factory() as s:
            await before.areset(s, "one", "login_user")
        assert await _rows(factory, "login_user:one") == 0
        after = RateLimiter()
        assert await after.load(factory) == 0
        assert after.get_remaining("one", "login_user") == 10


class TestWindowsAndScope:
    async def test_expired_hits_are_not_reloaded_and_are_pruned(self, factory):
        now = time.time()
        async with factory() as s:
            s.add_all([
                RateLimitHit(bucket="register_ip:a", hit_at=now - 4000),  # older than every window: pruned
                RateLimitHit(bucket="login_user:b", hit_at=now - 700),    # outside its 600 s window
                RateLimitHit(bucket="login_user:b", hit_at=now - 30),     # live
            ])
            await s.commit()
        limiter = RateLimiter()
        assert await limiter.load(factory) == 1
        assert limiter.get_remaining("b", "login_user") == 9
        assert await _rows(factory, "register_ip:a") == 0

    async def test_reloaded_hits_keep_their_age(self, factory, monkeypatch):
        async with factory() as s:
            s.add_all([RateLimitHit(bucket="register_ip:c", hit_at=time.time() - 3500) for _ in range(3)])
            await s.commit()
        limiter = RateLimiter()
        await limiter.load(factory)
        assert not limiter.is_allowed("c", "register_ip")
        real = limiter._now()
        monkeypatch.setattr(limiter, "_now", lambda: real + 120)  # 100 s later the window has passed
        assert limiter.is_allowed("c", "register_ip")

    async def test_other_limits_stay_memory_only(self, factory):
        limiter = RateLimiter()
        for t in ("command", "api", "ws_connect_ip", "ai"):
            await _hit(limiter, factory, "p1", t, 3)
        assert await _rows(factory) == 0

    async def test_database_failure_falls_back_to_memory(self, caplog):
        bare = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)  # no tables
        try:
            f = async_sessionmaker(bare, class_=AsyncSession, expire_on_commit=False)
            limiter = RateLimiter()
            with caplog.at_level(logging.WARNING, logger="webpennmush.security"):
                assert await _hit(limiter, f, "x", "register_ip", 4) == [True, True, True, False]
            assert "not persisted" in caplog.text
        finally:
            await bare.dispose()


class TestEndToEnd:
    def test_registration_limit_survives_app_restart(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        from backend.security import rate_limiter
        origin = {"origin": "http://testserver"}

        def register(c, name):
            return c.post("/api/players/register", json={"username": name, "password": "correct-horse-1"},
                          headers=origin).status_code

        with TestClient(app) as c:
            assert [register(c, f"Persist{i}") for i in range(3)] == [200, 200, 200]
        rate_limiter.clear()  # the process memory is gone...
        with TestClient(app) as c:  # ...and startup reloads the hits from the database
            assert register(c, "Persist3") == 429


pg_required = pytest.mark.skipif(not PgCluster.available(), reason="no Postgres binaries / PG_TEST_URL")


@pg_required
async def test_app_role_can_persist_hits_on_postgres():
    from backend.database import build_engine, _init_schema_and_seed
    cluster = PgCluster().start()
    owner, app_engine = build_engine(cluster.migrate_url), build_engine(cluster.url)
    try:
        await _init_schema_and_seed(owner)
        f = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
        await _hit(RateLimiter(), f, "203.0.113.1", "login_ip", 2)
        assert await _rows(f, "login_ip:203.0.113.1") == 2  # DML-only role: insert + sequence granted
        after = RateLimiter()
        assert await after.load(f) == 2
    finally:
        await owner.dispose()
        await app_engine.dispose()
        cluster.stop()
