"""The farmer's conversations: the sidebar's list (title, pin, last activity).

The messages themselves are the checkpointer's (persistence.py), under the same
id. Row-level security per farmer (db.py) makes a thread of someone else's look
like one that does not exist. Calls block, so async code runs them with
asyncio.to_thread.
"""

import uuid

from meta_hackathon.db import farmer

_COLUMNS = "thread_id, title, pinned, created_at, updated_at"


def _view(row: dict) -> dict:
    return {
        **row,
        "created_at": row["created_at"].isoformat(timespec="seconds"),
        "updated_at": row["updated_at"].isoformat(timespec="seconds"),
    }


def create_thread(phone: str, title: str | None) -> dict:
    with farmer(phone) as conn:
        row = conn.execute(
            f"INSERT INTO threads (thread_id, phone, title) VALUES (%s, %s, %s) RETURNING {_COLUMNS}",
            (str(uuid.uuid4()), phone, title),
        ).fetchone()
    return _view(row)


def list_threads(phone: str, limit: int = 50) -> list[dict]:
    with farmer(phone) as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM threads ORDER BY pinned DESC, updated_at DESC LIMIT %s", (limit,)
        ).fetchall()
    return [_view(r) for r in rows]


def touch_thread(phone: str, thread_id: str) -> bool:
    """A new message: moves the thread up the list. False when it is not this farmer's."""
    with farmer(phone) as conn:
        cur = conn.execute("UPDATE threads SET updated_at = now() WHERE thread_id = %s", (thread_id,))
        return cur.rowcount > 0


def owns_thread(phone: str, thread_id: str) -> bool:
    with farmer(phone) as conn:
        return conn.execute("SELECT 1 FROM threads WHERE thread_id = %s", (thread_id,)).fetchone() is not None


def update_thread(phone: str, thread_id: str, *, title: str | None = None, pinned: bool | None = None) -> dict | None:
    """Rename and/or pin. Does not count as activity, so a pin keeps the thread's place among the pinned."""
    with farmer(phone) as conn:
        row = conn.execute(
            f"UPDATE threads SET title = COALESCE(%s, title), pinned = COALESCE(%s, pinned) "
            f"WHERE thread_id = %s RETURNING {_COLUMNS}",
            (title, pinned, thread_id),
        ).fetchone()
    return _view(row) if row else None


def delete_thread(phone: str, thread_id: str) -> bool:
    with farmer(phone) as conn:
        return conn.execute("DELETE FROM threads WHERE thread_id = %s", (thread_id,)).rowcount > 0
