"""Images: the file goes to Vercel Blob (MEDIA_DIR when Blob is not configured, in
local dev) and Postgres keeps the link, with whose it is, from which conversation
and what was marked on it.

kind is `annotated` (segment_image, the web UI's photo folder, api/images.py),
`upload` (a farmer's photo) or `card` (make_picture_card).

Row-level security per farmer (db.py). Database calls block, so async code runs
them with asyncio.to_thread.
"""

import asyncio
import os
import uuid
from pathlib import Path
from typing import Literal

from psycopg.types.json import Jsonb
from vercel import blob

from meta_hackathon.config import settings
from meta_hackathon.db import farmer

Kind = Literal["annotated", "upload", "card"]

_YEAR = 31_536_000


def blob_enabled() -> bool:
    """The Blob SDK's own credentials: a token, or the store a Vercel project is connected to."""
    return bool(os.environ.get("BLOB_READ_WRITE_TOKEN") or os.environ.get("BLOB_STORE_ID"))


def media_url(name: str) -> str:
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/media/{name}"


async def save_image(data: bytes) -> tuple[str, str]:
    """Stores a JPEG under a random name; returns the name and its public link."""
    name = f"{uuid.uuid4().hex}.jpg"
    if blob_enabled():
        uploaded = await blob.put_blob(
            f"images/{name}", data, access="public", content_type="image/jpeg", cache_control_max_age=_YEAR
        )
        return name, uploaded.url

    def write() -> None:
        media = Path(settings.MEDIA_DIR)
        media.mkdir(parents=True, exist_ok=True)
        (media / name).write_bytes(data)

    await asyncio.to_thread(write)
    return name, media_url(name)


def record_image(
    phone: str, name: str, *, url: str, kind: Kind = "annotated", thread_id: str | None, labels: list[dict], measurement: dict | None = None
) -> None:
    """labels: what was marked, e.g. [{"label": "বাদামি গাছফড়িং", "count": 3}].
    measurement: how much of the leaf is diseased (tools/segment.py), which cases refer to."""
    with farmer(phone) as conn:
        conn.execute(
            "INSERT INTO images (name, phone, thread_id, labels, url, kind, measurement) VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (name) DO UPDATE SET thread_id = EXCLUDED.thread_id, labels = EXCLUDED.labels, url = EXCLUDED.url, "
            "measurement = EXCLUDED.measurement",
            (name, phone, thread_id, Jsonb(labels), url, kind, Jsonb(measurement) if measurement else None),
        )


def list_images(phone: str, limit: int = 200) -> list[dict]:
    with farmer(phone) as conn:
        rows = conn.execute(
            "SELECT name, url, thread_id, labels, created_at FROM images WHERE kind = 'annotated' ORDER BY created_at DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return [
        {
            # Photos from before links were stored are still in MEDIA_DIR.
            "url": r["url"] or media_url(r["name"]),
            "thread_id": r["thread_id"],
            "labels": r["labels"],
            "created_at": r["created_at"].isoformat(timespec="seconds"),
        }
        for r in rows
    ]
