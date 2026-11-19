"""
World-level seeded randomness: softcode rand()-style functions and scripted
NPC lines are reproducible from (seed, epoch, evaluation counter).
"""
import logging
import random

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.database import load_world_rng
from backend.engine.softcode import SoftcodeInterpreter
from backend.engine.world_rng import WorldRandom

CODE = "[rand(1000000)] [dice(5d20)] [shuffle(a b c d e f g h)] [choose(x y z w)] [coin()] [d20()]"


async def _run(session, world, n=5, code=CODE):
    interp = SoftcodeInterpreter(session, world=world)
    return [await interp.eval(code, executor_id=1) for _ in range(n)]


class TestSoftcodeDeterminism:
    async def test_same_seed_and_epoch_give_same_values(self, seeded_session):
        a = await _run(seeded_session, WorldRandom(seed=42, epoch=1))
        b = await _run(seeded_session, WorldRandom(seed=42, epoch=1))
        assert a == b

    async def test_values_vary_between_evaluations(self, seeded_session):
        out = await _run(seeded_session, WorldRandom(seed=42, epoch=1))
        assert len(set(out)) == len(out)

    async def test_different_seed_or_epoch_differ(self, seeded_session):
        base = await _run(seeded_session, WorldRandom(seed=42, epoch=1))
        assert await _run(seeded_session, WorldRandom(seed=43, epoch=1)) != base
        assert await _run(seeded_session, WorldRandom(seed=42, epoch=2)) != base

    async def test_replay_one_evaluation_from_its_ref(self, seeded_session):
        live = await _run(seeded_session, WorldRandom(seed=7, epoch=3))
        fresh = SoftcodeInterpreter(seeded_session, world=WorldRandom(seed=7, epoch=3))
        # The 4th evaluation of epoch 3, replayed alone on a new process/world.
        assert await fresh.eval(CODE, executor_id=1, rng_ref=(3, 4)) == live[3]

    async def test_nested_evaluation_shares_the_stream(self, seeded_session):
        from backend.models import Attribute
        seeded_session.add(Attribute(object_id=5, name="ROLL", value="[rand(1000000)]", flags=""))
        await seeded_session.commit()
        code = "[rand(1000000)] [ulocal(#5/ROLL)]"
        a = await _run(seeded_session, WorldRandom(seed=9, epoch=1), n=2, code=code)
        b = await _run(seeded_session, WorldRandom(seed=9, epoch=1), n=2, code=code)
        assert a == b and a[0] != a[1]
        outer, inner = a[0].split()
        assert inner.isdigit() and outer != inner  # ulocal() drew the next value of the same stream

    async def test_global_random_does_not_leak_in(self, seeded_session):
        random.seed(1)
        a = await _run(seeded_session, WorldRandom(seed=5, epoch=1))
        random.seed(2)
        b = await _run(seeded_session, WorldRandom(seed=5, epoch=1))
        assert a == b

    async def test_rng_ref_is_logged_without_the_seed(self, seeded_session, caplog):
        world = WorldRandom(seed=123456789, epoch=4)
        interp = SoftcodeInterpreter(seeded_session, world=world)
        with caplog.at_level(logging.INFO, logger="webpennmush.softcode.rng"):
            await interp.eval("[add(1,2)]", executor_id=1)  # no randomness: no line
            await interp.eval("[rand(10)]", executor_id=1)
        lines = [r.getMessage() for r in caplog.records if r.name == "webpennmush.softcode.rng"]
        assert lines == ["softcode rng epoch=4 n=2 executor=#1"]
        assert "123456789" not in caplog.text


class TestNpcDeterminism:
    def test_scripted_npc_lines_follow_the_world_seed(self):
        from backend.engine.ai_manager import AIManager

        def lines(seed):
            w = WorldRandom(seed=seed, epoch=1)
            m = AIManager(rng=w.npc)
            return [m._generate_placeholder("hi", "") for _ in range(20)]

        assert lines(11) == lines(11)
        assert lines(11) != lines(12)

    def test_configure_reseeds_npc_stream_in_place(self):
        w = WorldRandom(seed=1, epoch=1)
        held = w.npc  # what AIManager / SceneDirector keep
        first = [held.random() for _ in range(3)]
        w.configure(1, 1)
        assert w.npc is held and [held.random() for _ in range(3)] == first


class TestSeedPersistence:
    async def test_seed_created_once_epoch_bumps_each_start(self, engine):
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        w1 = await load_world_rng(factory, WorldRandom())
        w2 = await load_world_rng(factory, WorldRandom())
        assert w1.seed == w2.seed
        assert (w1.epoch, w2.epoch) == (1, 2)
        assert w2.counter == 0

    async def test_restart_does_not_repeat_values(self, engine, seeded_session):
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        first = await _run(seeded_session, await load_world_rng(factory, WorldRandom()), n=3)
        second = await _run(seeded_session, await load_world_rng(factory, WorldRandom()), n=3)
        assert first != second
