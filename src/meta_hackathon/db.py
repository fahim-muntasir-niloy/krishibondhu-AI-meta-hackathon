"""Postgres (DB_URI): the app's own records and the reference data.

Every pooled connection runs as `krishi_app`, a role row-level security
applies to (the login role, avnadmin on Aiven, bypasses RLS). Policies on the
farmers' tables compare each row's phone with the `app.phone` setting:

- `farmer(phone)`: a transaction with `app.phone` set to the caller. A query
  can only ever see or write that farmer's rows, even one that forgets
  `WHERE phone = ...`. The setting is transaction-local, so a pooled
  connection goes back clean.
- `reference_rows(sql)`: lookups in the shared reference data (the `agri`
  schema: pesticide register, Krishoker Janala advice; the officer roster).
  `app.phone` is unset here, so no farmer's row is visible at all.

The schema is in sql/schema.sql; `krishi-db migrate` applies it, as the login
role (dbcli.py).

Calls block, so async code runs them with asyncio.to_thread.
"""

import atexit
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, NullConnectionPool

from meta_hackathon.config import SERVERLESS, settings

APP_ROLE = "krishi_app"


def _as_app_role(conn: Connection) -> None:
    conn.execute(f"SET ROLE {APP_ROLE}")


@cache
def pool() -> ConnectionPool:
    # Small: Aiven's free plan allows few connections, and the checkpointer has its own pool.
    pool_class, min_size = (NullConnectionPool, 0) if SERVERLESS else (ConnectionPool, 1)
    app_pool = pool_class(
        settings.DB_URI,
        min_size=min_size,
        max_size=4,
        kwargs={"autocommit": True, "row_factory": dict_row},
        configure=_as_app_role,
        open=True,
        name="app",
    )
    atexit.register(app_pool.close)
    return app_pool


_known_farmers: set[str] = set()
_known_lock = threading.Lock()


@contextmanager
def farmer(phone: str) -> Iterator[Connection]:
    """One transaction as `phone`. Commits on exit, rolls back on an exception."""
    if not phone:
        raise ValueError("No farmer identity")
    with _known_lock:
        known = phone in _known_farmers
    with pool().connection() as conn, conn.transaction():
        conn.execute("SELECT set_config('app.phone', %s, true)", (phone,))
        if not known:
            # Every row a farmer owns references farmers(phone).
            conn.execute("INSERT INTO farmers (phone) VALUES (%s) ON CONFLICT DO NOTHING", (phone,))
        yield conn
    # Only once that transaction committed.
    with _known_lock:
        _known_farmers.add(phone)


def reference_rows(sql: str, params=()) -> list[dict]:
    """Rows from the shared reference data."""
    with pool().connection() as conn:
        return conn.execute(sql, params).fetchall()
