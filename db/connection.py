import asyncpg
import os
import json
import asyncio
from dotenv import load_dotenv

load_dotenv()

_pool = None
_main_loop = None

async def init_connection(conn):
    await conn.set_type_codec(
        'jsonb',
        encoder=json.dumps,
        decoder=json.loads,
        schema='pg_catalog'
    )

async def get_pool(dsn: str | None = None):
    global _pool, _main_loop
    try:
        _main_loop = asyncio.get_running_loop()
    except RuntimeError:
        pass

    if _pool is None:
        target_dsn = dsn or os.environ.get("DATABASE_URL")
        _pool = await asyncpg.create_pool(
            dsn=target_dsn,
            init=init_connection,
            min_size=1,
            max_size=10,
        )
    return _pool

async def create_pool(dsn: str | None = None):
    return await get_pool(dsn)

def get_main_loop():
    return _main_loop