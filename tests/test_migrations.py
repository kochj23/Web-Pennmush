"""
Alembic migrations: fresh install, stamping of pre-Alembic (create_all)
databases, and a sample follow-up revision - on SQLite and on a private
Postgres cluster (tests/pg_cluster.py; skipped when no Postgres binaries).
"""
import textwrap

import pytest
from sqlalchemy import inspect, text

from backend.database import (
    BASELINE_REVISION, _init_schema_and_seed, alembic_config, build_engine, run_migrations,
)
from backend.models import Base
from tests.pg_cluster import PgCluster


def _head():
    from alembic.script import ScriptDirectory
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def _snapshot(conn):
    """Everything about the schema except alembic's own table."""
    insp = inspect(conn)
    out = {}
    for t in sorted(insp.get_table_names()):
        if t == "alembic_version":
            continue
        out[t] = (
            [(c["name"], str(c["type"]), c["nullable"]) for c in insp.get_columns(t)],
            sorted((i["name"], tuple(i["column_names"]), bool(i["unique"])) for i in insp.get_indexes(t)),
            sorted((tuple(f["constrained_columns"]), f["referred_table"]) for f in insp.get_foreign_keys(t)),
        )
    return out


def _diff(conn):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    return compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)


async def _version(eng):
    async with eng.connect() as conn:
        return (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()


async def _run(eng, fn):
    async with eng.connect() as conn:
        return await conn.run_sync(fn)


def _sample_revision(dirpath, down):
    (dirpath / "9999_sample.py").write_text(textwrap.dedent(f'''
        from alembic import op
        import sqlalchemy as sa
        revision = "9999_sample"
        down_revision = {down!r}
        branch_labels = None
        depends_on = None

        def upgrade():
            with op.batch_alter_table("objects") as b:
                b.add_column(sa.Column("sample_note", sa.String(32), nullable=True))

        def downgrade():
            with op.batch_alter_table("objects") as b:
                b.drop_column("sample_note")
    '''))
    return dirpath


# ---------------------------------------------------------------------------
# Backends: a fresh SQLite file per test, or a wiped schema in the PG cluster
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pg_cluster():
    if not PgCluster.available():
        pytest.skip("no Postgres binaries / PG_TEST_URL")
    cluster = PgCluster().start()
    yield cluster
    cluster.stop()


async def _wipe_pg(eng):
    async with eng.begin() as conn:
        for (t,) in (await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"))).all():
            await conn.execute(text(f'DROP TABLE IF EXISTS "{t}" CASCADE'))
        await conn.execute(text("DROP TYPE IF EXISTS objecttype"))


@pytest.fixture(params=["sqlite", "postgres"])
async def ddl_engine(request, tmp_path):
    if request.param == "sqlite":
        eng = build_engine(f"sqlite+aiosqlite:///{tmp_path / 'mig.db'}")
        yield eng
        await eng.dispose()
        return
    cluster = request.getfixturevalue("pg_cluster")
    eng = build_engine(cluster.migrate_url)
    await _wipe_pg(eng)
    yield eng
    await _wipe_pg(eng)
    await eng.dispose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_baseline_is_the_current_schema(ddl_engine):
    assert await run_migrations(ddl_engine) == "upgraded"
    assert await _version(ddl_engine) == _head()
    assert await _run(ddl_engine, _diff) == []


async def test_fresh_database_gets_seeded(ddl_engine):
    await _init_schema_and_seed(ddl_engine)
    await _init_schema_and_seed(ddl_engine)  # restart is a no-op
    async with ddl_engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM objects"))).scalar() >= 5
    assert await _version(ddl_engine) == _head()


async def test_existing_create_all_database_is_stamped_not_altered(ddl_engine):
    async with ddl_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "INSERT INTO objects (id, name, type, flags, powers, created_at, modified_at) "
            "VALUES (42, 'Survivor', 'THING', '', '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    before = await _run(ddl_engine, _snapshot)

    assert await run_migrations(ddl_engine) == "stamped"

    assert await _run(ddl_engine, _snapshot) == before
    assert await _version(ddl_engine) == _head()
    async with ddl_engine.connect() as conn:
        assert (await conn.execute(text("SELECT name FROM objects WHERE id = 42"))).scalar() == "Survivor"
    # Second start: already versioned, nothing to stamp.
    assert await run_migrations(ddl_engine) == "upgraded"


async def test_stamped_database_then_upgrades_a_new_revision(ddl_engine, tmp_path):
    async with ddl_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    (tmp_path / "extra_versions").mkdir()
    extra = _sample_revision(tmp_path / "extra_versions", _head())

    await run_migrations(ddl_engine, extra_version_locations=[extra])

    cols = await _run(ddl_engine, lambda c: [col["name"] for col in inspect(c).get_columns("objects")])
    assert "sample_note" in cols
    assert await _version(ddl_engine) == "9999_sample"


def test_baseline_revision_is_the_root():
    from alembic.script import ScriptDirectory
    script = ScriptDirectory.from_config(alembic_config())
    assert script.get_base() == BASELINE_REVISION
