"""Picture cards (Muse Image): how to mix a spray, what to wear, for farmers who
cannot read well.

Muse draws the pictures and is told to draw no text at all: a generated dose
cannot be checked, and generated Bangla is unreliable. The captions, and so
every number on the card, are drawn here from the tool's arguments with the
bundled font. The safety content of the standard scenes is fixed in this file,
not written by the agent, so protective gear cannot be left out of the picture.
"""

import asyncio
import base64
import binascii
import hashlib
import io
from pathlib import Path
from typing import Literal

from langchain.tools import ToolException, ToolRuntime, tool
from openai import AsyncOpenAI, OpenAIError
from PIL import Image, ImageDraw, ImageFont

from meta_hackathon.agent.context import phone_number
from meta_hackathon.config import settings
from meta_hackathon.gallery import record_image, save_image
from meta_hackathon.utils.bangla import bn_digits

_client = AsyncOpenAI(base_url=settings.META_BASE_URL, api_key=settings.META_API_KEY, timeout=120)
_FONT = Path(__file__).parent.parent / "assets" / "fonts" / "HindSiliguri-SemiBold.ttf"

Scene = Literal["mix_spray", "protective_gear", "custom"]

_FARMER = (
    "a Bangladeshi farmer standing on dry bare ground at the edge of a field, well away from any water, wearing a long-sleeved shirt with no skin showing on the arms, long trousers, "
    "rubber boots, rubber gloves and a face mask"
)
_SCENES: dict[str, list[str]] = {
    "mix_spray": [
        f"{_FARMER} carefully pouring liquid from a small plain bottle into a small measuring cup, held away from the face",
        f"{_FARMER} pouring the measuring cup into a backpack sprayer tank that stands on the dry ground and is half full of water",
        f"{_FARMER} adding water from a bucket to the backpack sprayer tank, then closing its lid",
    ],
    "protective_gear": [
        "a Bangladeshi farmer dressed in full-length trousers (not a lungi) and a shirt with sleeves buttoned down to the wrists, pulling on rubber boots before spraying a field",
        "a close-up of the same farmer, sleeves down to the wrists, wearing rubber gloves, a face mask and protective goggles, with a backpack sprayer",
        "the same farmer in the same full-length trousers after spraying, gloves off, washing their bare hands and arms with a bar of soap under a tube well spout, on dry ground",
    ],
}

_MAX_PANELS = 4
_MAX_CAPTION = 90
_WIDTH = 1280
_MARGIN = 28
_INK = "#08130d"
_GREEN = "#1f7a4d"


def _prompt(panels: list[str]) -> str:
    layout = "A single scene" if len(panels) == 1 else f"Exactly {len(panels)} equal-width panels side by side, left to right"
    scenes = " ".join(f"Panel {i}: {p}." for i, p in enumerate(panels, 1))
    return (
        f"{layout}, a simple instruction card for farmers who cannot read. Flat, friendly illustration with bold shapes, "
        f"high contrast and a plain light background. {scenes} Show each action clearly. Absolutely no text, letters, "
        "numbers, labels, logos or measurement marks anywhere in the image, including on bottles and containers."
    )


async def _generate(prompt: str) -> bytes:
    """The picture for this prompt. Kept outside the served folder and reused: the same
    scene (the protective gear card) is asked for again and again, and each takes a while."""
    cache = Path(settings.MEDIA_DIR) / "card-cache" / f"{hashlib.sha256(f'{settings.IMAGE_MODEL_NAME}:{prompt}'.encode()).hexdigest()}.img"
    if await asyncio.to_thread(cache.is_file):
        return await asyncio.to_thread(cache.read_bytes)
    resp = await _client.responses.create(model=settings.IMAGE_MODEL_NAME, input=prompt)
    encoded = next((item.result for item in resp.output if item.type == "image_generation_call" and item.result), None)
    if not encoded:
        raise ValueError("the model returned no image")
    data = base64.b64decode(encoded)

    def save() -> None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)

    await asyncio.to_thread(save)
    return data


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """Greedy word wrap; a word wider than the line stays whole rather than breaking a Bangla cluster."""
    lines: list[str] = []
    for word in text.split():
        joined = f"{lines[-1]} {word}" if lines else word
        if lines and draw.textlength(joined, font=font) <= width:
            lines[-1] = joined
        else:
            lines.append(word)
    return lines


def _compose(data: bytes, title: str, captions: list[str]) -> bytes:
    """The picture with a Bangla title above and a numbered caption under each panel, as a JPEG."""
    art = Image.open(io.BytesIO(data)).convert("RGB")
    art = art.resize((_WIDTH, round(art.height * _WIDTH / art.width)), Image.Resampling.LANCZOS)

    measure = ImageDraw.Draw(art)
    title_font = ImageFont.truetype(str(_FONT), 44)
    font = ImageFont.truetype(str(_FONT), 32 if len(captions) < 4 else 27)
    badge = font.size + 16
    column = _WIDTH // len(captions)
    numbered = len(captions) > 1
    text_width = column - 2 * _MARGIN - (badge + 12 if numbered else 0)
    wrapped = [_wrap(measure, c, font, text_width) for c in captions]
    line = round(font.size * 1.5)
    title_lines = _wrap(measure, title, title_font, _WIDTH - 2 * _MARGIN)
    title_height = len(title_lines) * round(title_font.size * 1.45) + 2 * _MARGIN
    caption_height = max(max(map(len, wrapped)) * line, badge) + 2 * _MARGIN

    card = Image.new("RGB", (_WIDTH, title_height + art.height + caption_height), "white")
    draw = ImageDraw.Draw(card)
    draw.rectangle((0, 0, _WIDTH, title_height), fill=_GREEN)
    y = _MARGIN
    for text in title_lines:
        draw.text((_MARGIN, y), text, font=title_font, fill="white")
        y += round(title_font.size * 1.45)
    card.paste(art, (0, title_height))

    top = title_height + art.height + _MARGIN
    for i, lines in enumerate(wrapped):
        x = i * column + _MARGIN
        if numbered:
            draw.ellipse((x, top, x + badge, top + badge), fill=_GREEN)
            draw.text((x + badge / 2, top + badge / 2), bn_digits(i + 1), font=font, fill="white", anchor="mm")
            x += badge + 12
        for n, text in enumerate(lines):
            draw.text((x, top + n * line), text, font=font, fill=_INK)

    buf = io.BytesIO()
    card.save(buf, "JPEG", quality=88)
    return buf.getvalue()


@tool
async def make_picture_card(title: str, scene: Scene, captions: list[str], panels: list[str] | None = None, *, runtime: ToolRuntime) -> dict:
    """Make a picture card that shows a practical job in drawings, for a farmer who
    finds reading hard. Returns the URL of the card.

    Args:
        title: Short Bangla title, e.g. "স্প্রে মেশানোর নিয়ম".
        scene: "mix_spray" (3 panels: measure the medicine, pour it into a half-filled tank,
            top up with water and close the lid). "protective_gear" (3 panels: long clothes and
            boots, gloves + mask + goggles, wash with soap afterwards). "custom" for anything
            else (removing infected leaves, draining a field), with `panels`.
        captions: One short Bangla sentence per panel, in order, with the exact dose where one
            belongs ("১০ লিটার পানিতে ৬ গ্রাম"). Only these words appear on the card; doses must
            come from the advice you are giving, never from memory.
        panels: "custom" only. 1-4 descriptions in English of what each panel shows, one per
            caption. Describe the action only, with no numbers. Whenever a chemical is handled,
            show the person in gloves, mask and long sleeves.
    """
    if scene == "custom":
        if not panels:
            raise ToolException('scene "custom" needs `panels`.')
        scene_panels = panels[:_MAX_PANELS]
    else:
        scene_panels = _SCENES[scene]
    captions = [" ".join(c.split())[:_MAX_CAPTION] for c in captions if c.strip()]
    if len(captions) != len(scene_panels):
        raise ToolException(f"This card has {len(scene_panels)} panel(s), so give exactly that many captions, not {len(captions)}.")
    try:
        data = await _generate(_prompt(scene_panels))
        # Image work runs in a thread: the event loop serves every farmer.
        card = await asyncio.to_thread(_compose, data, " ".join(title.split())[:80], captions)
        name, url = await save_image(card)
    except (OpenAIError, OSError, ValueError, binascii.Error) as e:
        return {"error": f"The picture card could not be made: {e}. Carry on without it."}
    if phone := phone_number(runtime):
        thread_id = (runtime.config or {}).get("configurable", {}).get("thread_id")
        await asyncio.to_thread(record_image, phone, name, url=url, kind="card", thread_id=thread_id, labels=[])
    return {"card_image_url": url, "captions": captions}


make_picture_card.handle_tool_error = True
