import asyncio
import logging

from langchain.agents.middleware import ModelRequest, dynamic_prompt

from meta_hackathon import bookings
from meta_hackathon.cases import case_for_model, case_view, list_cases_in, summary_line
from meta_hackathon.db import farmer
from meta_hackathon.farmers import save_profile
from meta_hackathon.prompts.date_block import date_block
from meta_hackathon.prompts.system import OPENUI_SECTION, SYSTEM_PROMPT, ReplyFormat, profile_block
from meta_hackathon.tools.memory import MAX_MEMORIES, memory_line, memory_namespace

logger = logging.getLogger(__name__)

_PROFILE_FIELDS = ("name", "area", "district", "division")


def _phone(request: ModelRequest) -> str | None:
    return getattr(request.runtime.context, "phone_number", None)


def _profile(request: ModelRequest) -> str:
    ctx = request.runtime.context
    return profile_block(**{f: getattr(ctx, f, None) for f in _PROFILE_FIELDS}, phone=_phone(request))


def _cases_block(cases: list[dict], focused: dict | None) -> str:
    """The farmer's open crop cases, one line each, and the one open in the
    tracker pane in full, so a message or a photo is matched to the right case."""
    if not cases and not focused:
        return ""
    block = "# Farmer's crop cases\nOpen plans you are tracking with this farmer (treatment and cultivation):\n"
    block += "\n".join(summary_line(c) for c in cases) or "(none open)"
    if focused:
        block += (
            "\n\nThe farmer has this case open beside the chat; their message is about it unless they say otherwise:\n"
            + case_for_model(case_view(focused))
        )
    return block + "\n"


def _bookings_block(upcoming: list[dict]) -> str:
    if not upcoming:
        return ""
    return "# Farmer's officer sessions\nUpcoming:\n" + "\n".join(bookings.summary_line(b) for b in upcoming) + "\n"


def _records(phone: str | None, focus_id: str | None, profile: dict) -> str:
    """Cases and bookings, in one transaction (one round of trips to the database)."""
    if not phone:
        return ""
    try:
        save_profile(phone, **profile)
    except Exception:
        logger.exception("Could not save the profile of %s", phone)
    try:
        with farmer(phone) as conn:
            cases = list_cases_in(conn)
            upcoming = bookings.list_bookings_in(conn, upcoming_only=True)
    except Exception:
        logger.exception("Could not load the records of %s", phone)
        return (
            "# Farmer's crop cases and officer sessions\nUnknown: they could not be loaded. "
            "Use get_crop_case to list the cases.\n"
        )
    focused = next((c for c in cases if c["id"] == focus_id), None) if focus_id else None
    open_cases = [c for c in cases if c["stage"] not in ("resolved", "abandoned")]
    return _cases_block(open_cases, focused) + _bookings_block(upcoming)


async def _memories(request: ModelRequest, phone: str | None) -> str:
    store = request.runtime.store
    if not phone or store is None:
        return ""
    try:
        items = await store.asearch(memory_namespace(phone), limit=MAX_MEMORIES)
    except Exception:
        logger.exception("Could not load the memories of %s", phone)
        return ""
    if not items:
        return "# What you remember about this farmer\nNothing yet.\n"
    return "# What you remember about this farmer\n" + "\n".join(map(memory_line, items)) + "\n"


def system_prompt(reply_format: ReplyFormat):
    """Builds the system prompt per model call, so the date block, the cases,
    the bookings and the memories are always current."""
    base_prompt = SYSTEM_PROMPT + (OPENUI_SECTION if reply_format == "openui" else "")

    @dynamic_prompt
    async def prompt(request: ModelRequest) -> str:
        ctx = request.runtime.context
        phone = _phone(request)
        # The database calls block; keep them off the event loop that serves every farmer.
        records, memories = await asyncio.gather(
            asyncio.to_thread(
                _records, phone, getattr(ctx, "case_id", None), {f: getattr(ctx, f, None) for f in _PROFILE_FIELDS}
            ),
            _memories(request, phone),
        )
        # Date, profile and records first: the openui-lang reference makes the prompt long, and the
        # model must not miss them for "কালকে কি বৃষ্টি হবে?"-style questions.
        return f"{date_block()}\n{_profile(request)}\n{memories}\n{records}\n{base_prompt}"

    return prompt
