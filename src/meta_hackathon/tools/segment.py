"""SAM 3.1 on the farmer's photo: mark what the agent recognised, and measure how
much of the leaf is diseased.

The main model looks at the photo and names what it sees; this tool asks SAM for
that name. SAM responds to what things look like, not to diagnoses: "brown
planthopper" and "brown spot" are found, "rice blast" and "late blight" are not.
So each target tries its name, then what it looks like, then a generic word.

The measurement (lesions.py) never depends on the model's wording: lesions always
come from the same fixed queries, so a day-0 and a day-3 photo are comparable. It
is stored server side and cases refer to it by id, so the percentages the agent
quotes are ones this tool measured.
"""

import asyncio
import base64
import io
from pathlib import Path
from typing import Literal

import httpx
from langchain.messages import HumanMessage
from langchain.tools import ToolRuntime, tool
from meta_sam_parser import (
    ResponsesStreamError,
    decode_mask_to_raster,
    image_segmentation_format,
    parse_responses_stream,
)
from openai import AsyncOpenAI, OpenAIError
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
from pydantic import BaseModel, Field

from meta_hackathon.agent.context import phone_number
from meta_hackathon.config import settings
from meta_hackathon.gallery import record_image, save_image
from meta_hackathon.lesions import Instance, Measurement, measure, pixels, seeds, union
from meta_hackathon.utils.bangla import bn_digits

_client = AsyncOpenAI(base_url=settings.META_BASE_URL, api_key=settings.META_API_KEY)
_FONT = Path(__file__).parent.parent / "assets" / "fonts" / "HindSiliguri-SemiBold.ttf"

# Distinct on green fields; white text stays readable on each.
_COLORS = ["#e11d48", "#2563eb", "#d97706", "#7c3aed"]
_LEAF_OUTLINE = "#facc15"
_TINT = 0.45
# Many small marks (e.g. 30 spots) are drawn, but only this many carry a label.
_MAX_LABELS_PER_TARGET = 3
# Fixed so that measurements are comparable; a union, as each misses some lesions.
_LESION_QUERIES = ("spot", "lesion", "diseased area")
_FALLBACKS = {"disease": _LESION_QUERIES, "pest": ("insect", "caterpillar")}


class Target(BaseModel):
    name: str = Field(
        description='What you recognised, the common English name: "brown planthopper", "aphid", "rice blast". '
        "Not a scientific name; SAM does not know those."
    )
    label: str = Field(description='Bangla name to write on the image, e.g. "বাদামি গাছফড়িং".')
    kind: Literal["disease", "pest"] = Field(
        default="disease", description='"disease" for lesions, spots, rot or other damage on the plant; "pest" for an insect you can see.'
    )
    looks_like: str = Field(
        default="", description='What it looks like in 1-3 plain English words, tried if the name finds nothing: "brown spot", "white powder".'
    )


def _photos(runtime: ToolRuntime) -> list[str]:
    """Image URLs of the farmer's most recent message that has any."""
    for m in reversed(runtime.state.get("messages", [])):
        if not isinstance(m, HumanMessage) or isinstance(m.content, str):
            continue
        urls = []
        for b in m.content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "image_url":
                url = b["image_url"]
                urls.append(url if isinstance(url, str) else url.get("url", ""))
            elif b.get("type") == "image":
                urls.append(b.get("url") or f"data:{b.get('mime_type', 'image/jpeg')};base64,{b.get('base64', '')}")
        if urls := [u for u in urls if u]:
            return urls
    return []


async def _fetch(url: str) -> bytes:
    if url.startswith("data:"):
        return base64.b64decode(url.split(",", 1)[1])
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


def _decode(data: bytes) -> tuple[Image.Image, str]:
    """The photo, plus a JPEG data URL of exactly these pixels for SAM."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return img, "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _instances(records: list) -> list[Instance]:
    out = []
    for r in records:
        raster = decode_mask_to_raster(r.mask)
        mask = Image.frombytes("L", (r.mask.width, r.mask.height), bytes(255 * v for v in raster))
        out.append(Instance(int(r.bounds.left), int(r.bounds.top), mask, r.confidence))
    return out


async def _segment(data_url: str, prompt: str) -> list[Instance]:
    """Every object SAM finds for a text or point prompt. An empty list is a valid answer."""
    events = await _client.responses.create(
        model=settings.SEGMENT_MODEL_NAME,
        stream=True,
        metadata={"mask_encoding": "one_bit", "include_confidence": "true"},
        input=[
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": data_url},
                ],
            }
        ],
    )
    result = await parse_responses_stream(events, image_segmentation_format()).final_result()
    # Decoding a whole-leaf mask takes seconds of CPU.
    return await asyncio.to_thread(_instances, [r for r in result.records if r.kind == "mask"])


def _tint(img: Image.Image, mask: Image.Image, color: str, thickness: int) -> Image.Image:
    """The mask shaded in `color`, with a solid outline, so its real shape shows."""
    shaded = Image.composite(Image.blend(img, Image.new("RGB", img.size, color), _TINT), img, mask)
    shaded.paste(color, (0, 0), ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(2 * thickness + 1)), mask))
    return shaded


def _draw(img: Image.Image, found: list[tuple[Target, str, list[Instance]]], measured: Measurement | None) -> bytes:
    """The photo with its masks shaded, the labels and the measured share, as a JPEG."""
    scale = max(img.size) / 1000
    thickness = max(1, round(1.5 * scale))
    font = ImageFont.truetype(str(_FONT), max(16, round(26 * scale)))
    pad = round(6 * scale) + 2

    if measured:
        outline = ImageChops.subtract(measured.leaf.filter(ImageFilter.MaxFilter(2 * thickness + 1)), measured.leaf)
        img = img.copy()
        img.paste(_LEAF_OUTLINE, (0, 0), outline)
        if pixels(measured.lesions):
            color = next((c for t, c, _ in found if t.kind == "disease"), _COLORS[0])
            img = _tint(img, measured.lesions, color, thickness)
    for target, color, instances in found:
        img = _tint(img, union(img.size, instances), color, thickness)

    draw = ImageDraw.Draw(img)

    def tag(x: int, y: int, text: str, color: str) -> None:
        x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
        tw, th = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
        lx = min(max(0, x), img.width - tw)
        # Above the mark, or inside its top edge when there is no room above.
        ly = y - th if y - th >= 0 else y
        draw.rectangle((lx, ly, lx + tw, ly + th), fill=color)
        draw.text((lx + pad - x0, ly + pad - y0), text, font=font, fill="white")

    for target, color, instances in found:
        # Label the biggest marks; they are what the farmer looks at first.
        ranked = sorted(instances, key=lambda i: pixels(i.mask), reverse=True)
        for inst in ranked[:_MAX_LABELS_PER_TARGET]:
            tag(inst.left, inst.top, target.label, color)
    if measured:
        tag(0, 0, f"পাতার {bn_digits(measured.lesion_pct)}% আক্রান্ত", "#08130d")

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


@tool
async def segment_image(targets: list[Target], photo: int = 1, *, runtime: ToolRuntime) -> dict:
    """Mark what you recognised in the farmer's latest photo (SAM 3.1), and measure how
    much of the leaf is diseased. Look at the photo first, name what you see, then call this.

    Returns the URL of the photo with the marks. With a "disease" target it also returns
    `measurement`: lesion_pct (lesion area as a percentage of the leaf) and measurement_id,
    or `measurement_unavailable` saying why not. Quote only this number, never your own
    estimate, and pass measurement_id to start_crop_case or update_crop_case.

    Args:
        targets: 1-4 things you recognised.
        photo: Which photo of the latest message (1 or 2).
    """
    photos = _photos(runtime)
    if not photos:
        return {"error": "The farmer has not sent a photo."}
    if not 1 <= photo <= len(photos):
        return {"error": f"Only {len(photos)} photo(s) in the latest message."}
    targets = targets[:4]
    measuring = any(t.kind == "disease" for t in targets)
    # One request per distinct prompt: a target's fallback is often a lesion query too.
    asked: dict[str, asyncio.Task] = {}

    def ask(data_url: str, prompt: str) -> asyncio.Task:
        return asked.setdefault(prompt, asyncio.create_task(_segment(data_url, prompt)))

    async def find(data_url: str, target: Target) -> tuple[list[Instance], str]:
        for query in dict.fromkeys(q for q in (target.name.strip(), target.looks_like.strip(), *_FALLBACKS[target.kind]) if q):
            if instances := await ask(data_url, query):
                return instances, query
        return [], ""

    measured = None
    try:
        # Image work runs in a thread: it is CPU bound, and the event loop serves every farmer.
        img, data_url = await asyncio.to_thread(_decode, await _fetch(photos[photo - 1]))
        results = await asyncio.gather(*(find(data_url, t) for t in targets))
        if measuring:
            lesions = [i for group in await asyncio.gather(*(ask(data_url, q) for q in _LESION_QUERIES)) for i in group]
            points = await asyncio.to_thread(seeds, img, lesions)
            leaves = await asyncio.gather(
                *(ask(data_url, f"<0f>1<|point;x={x};y={y};w={img.width};h={img.height}|>") for x, y in points)
            )
            measured = await asyncio.to_thread(measure, img.size, lesions, [i for group in leaves for i in group])
    except (OpenAIError, ResponsesStreamError, httpx.HTTPError, OSError) as e:
        for task in asked.values():
            task.cancel()
        return {"error": f"Segmentation failed: {e}"}

    found = [(t, _COLORS[i % len(_COLORS)], r[0]) for i, (t, r) in enumerate(zip(targets, results)) if r[0]]
    queries = {t.label: r[1] for t, r in zip(targets, results)}

    def share(instances: list[Instance]) -> float:
        return round(100 * pixels(union(img.size, instances)) / (img.width * img.height), 1)

    shares = await asyncio.to_thread(lambda: {t.label: share(inst) for t, _, inst in found})
    out: dict = {
        "photo": photo,
        "found": [
            {"label": t.label, "searched_as": queries[t.label], "count": len(inst), "photo_area_pct": shares[t.label]}
            for t, _, inst in found
        ],
        "not_found": [t.label for t, r in zip(targets, results) if not r[0]],
    }
    if not found and not measured:
        if measuring:
            out["measurement_unavailable"] = "No leaf could be found. Ask for a closer photo of one affected leaf, in daylight."
        return out

    try:
        name, url = await save_image(await asyncio.to_thread(_draw, img, found, measured))
    except OSError as e:
        return {"error": f"Segmentation failed: {e}"}
    out["annotated_image_url"] = url
    record = None
    if measured:
        record = {
            "lesion_pct": measured.lesion_pct,
            "lesion_px": measured.lesion_px,
            "leaf_px": measured.leaf_px,
            "leaf_confidence": measured.leaf_confidence,
        }
        out["measurement"] = {"measurement_id": name.removesuffix(".jpg"), "lesion_pct": measured.lesion_pct}
        if not measured.lesion_px:
            out["measurement"]["note"] = (
                "SAM marked no lesions. That can be a miss, not proof of health: check the photo with your own eyes."
            )
    elif measuring:
        out["measurement_unavailable"] = "No leaf could be found. Ask for a closer photo of one affected leaf, in daylight."
    # Filed in the farmer's photo folder in the web UI.
    if phone := phone_number(runtime):
        thread_id = (runtime.config or {}).get("configurable", {}).get("thread_id")
        labels = [{"label": f["label"], "count": f["count"]} for f in out["found"]]
        await asyncio.to_thread(record_image, phone, name, url=url, thread_id=thread_id, labels=labels, measurement=record)
    return out
