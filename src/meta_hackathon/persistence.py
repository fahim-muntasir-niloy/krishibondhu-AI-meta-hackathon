"""LangGraph persistence in Postgres (DB_URI):

- `checkpointer()`: conversation state (messages, tool results) per thread,
  so conversations survive restarts. Tables checkpoints*.
- `store()`: long-term memory across conversations: what KrishiBondhu learned
  about a farmer (tools/memory.py), under the namespace ("memories", <phone>).
  Tables store*.

`krishi-db migrate` makes both sets of tables (dbcli.py), not startup: setup() on
every cold start cost connections just when an instance had none to spare.

main.py enters both for the app's lifetime. Each is an async context manager
owning its own connection pool, opened on the server's event loop.

These run as the login role, not krishi_app (db.py): the app role has no grant
on them. Who may read a thread is enforced by the threads table (threads.py);
the memory namespace comes from the caller's phone (tools/memory.py).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, AsyncNullConnectionPool

from meta_hackathon.config import SERVERLESS, settings

# What langgraph-checkpoint-postgres needs: autocommit, and no server-side
# prepared statements (they break behind poolers).
_KWARGS = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}


@asynccontextmanager
async def _pool(name: str, max_size: int) -> AsyncIterator[AsyncConnectionPool]:
    pool_class, min_size = (AsyncNullConnectionPool, 0) if SERVERLESS else (AsyncConnectionPool, 1)
    async with pool_class(
        settings.DB_URI, min_size=min_size, max_size=max_size, kwargs=_KWARGS, open=False, name=name
    ) as pool:
        yield pool


@asynccontextmanager
async def checkpointer(max_size: int = 4) -> AsyncIterator[AsyncPostgresSaver]:
    async with _pool("checkpointer", max_size) as pool:
        yield AsyncPostgresSaver(pool)


@asynccontextmanager
async def store(max_size: int = 2) -> AsyncIterator[AsyncPostgresStore]:
    async with _pool("store", max_size) as pool:
        yield AsyncPostgresStore(pool)
