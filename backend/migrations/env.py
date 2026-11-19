"""
Alembic environment for Web-Pennmush.

At startup the app passes an open connection (owner/DDL role) via
config.attributes["connection"]. From the CLI (`alembic upgrade head`,
`alembic revision --autogenerate`) the URL comes from settings.migrate_url(),
i.e. DATABASE_MIGRATE_URL or DATABASE_URL from the environment - never a file.
"""
import asyncio

from alembic import context

from backend.models import Base

config = context.config
target_metadata = Base.metadata


def _run(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_cli():
    from backend.config import settings
    from backend.database import build_engine
    eng = build_engine(settings.migrate_url())
    try:
        async with eng.begin() as conn:
            await conn.run_sync(_run)
    finally:
        await eng.dispose()


_conn = config.attributes.get("connection")
if _conn is not None:
    _run(_conn)
elif context.is_offline_mode():
    raise SystemExit("offline (--sql) mode is not supported; run against a database")
else:
    asyncio.run(_run_cli())
