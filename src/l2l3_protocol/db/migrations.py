from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from l2l3_protocol.config import Settings


def alembic_config(settings: Settings) -> Config:
    config_path = Path("alembic.ini")
    config = Config(str(config_path))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def run_upgrade_head(settings: Settings) -> None:
    import asyncio

    asyncio.run(stamp_existing_schema_if_needed(settings))
    command.upgrade(alembic_config(settings), "head")


async def stamp_existing_schema_if_needed(settings: Settings) -> None:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            process_runs = await conn.scalar(text("select to_regclass('public.process_runs')"))
            alembic_version = await conn.scalar(text("select to_regclass('public.alembic_version')"))
            if process_runs and not alembic_version:
                await conn.execute(text("create table alembic_version (version_num varchar(32) not null primary key)"))
                await conn.execute(text("insert into alembic_version (version_num) values ('20260524_0001')"))
    finally:
        await engine.dispose()
