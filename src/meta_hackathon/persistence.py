"""LangGraph persistence in Postgres (DB_URI):

- `checkpointer()`: conversation state (messages, tool results) per thread,
  so conversations survive restarts. Tables checkpoints*, made by setup().
- `store()`: long-term memory across conversations: what KrishiBondhu learned
  about a farmer (tools/memory.py), under the namespace ("memories", <phone>).
  Tables store*, made by setup().

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
from psycopg_pool import AsyncConnectionPool

from meta_hackathon.config import settings

# What langgraph-checkpoint-postgres needs: autocommit, and no server-side
# prepared statements (they break behind poolers).
_KWARGS = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}


@asynccontextmanager
async def _pool(name: str, max_size: int) -> AsyncIterator[AsyncConnectionPool]:
    async with AsyncConnectionPool(
        settings.DB_URI, min_size=1, max_size=max_size, kwargs=_KWARGS, open=False, name=name
    ) as pool:
        yield pool


@asynccontextmanager
async def checkpointer(max_size: int = 4) -> AsyncIterator[AsyncPostgresSaver]:
    async with _pool("checkpointer", max_size) as pool:
        saver = AsyncPostgresSaver(pool)
        await saver.setup()
        yield saver


@asynccontextmanager
async def store(max_size: int = 2) -> AsyncIterator[AsyncPostgresStore]:
    async with _pool("store", max_size) as pool:
        memory = AsyncPostgresStore(pool)
        await memory.setup()
        yield memory
