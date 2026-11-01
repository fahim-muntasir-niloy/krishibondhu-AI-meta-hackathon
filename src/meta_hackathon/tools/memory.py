"""Long-term memory: lasting facts about a farmer (their land, crops and
varieties, past problems, what they prefer), kept across conversations in the
LangGraph store (persistence.py, Postgres).

Memories live under ("memories", <phone>). The phone always comes from the
request's identity, never from the model, so a farmer's memories can only be
read or written in that farmer's own runs.

The system prompt lists the farmer's memories every turn
(middlewares/system_prompt.py); fetch_user_memory is for searching them.
"""

import uuid
from typing import Literal

from langchain.tools import ToolException, ToolRuntime, tool

from meta_hackathon.agent.context import UserContext, phone_number

NAMESPACE = "memories"
MAX_MEMORIES = 40
MAX_CHARS = 300
Category = Literal["farm", "crops", "history", "preference", "other"]


def memory_namespace(phone: str) -> tuple[str, str]:
    return (NAMESPACE, phone)


def _where(runtime: ToolRuntime):
    phone = phone_number(runtime)
    if not phone:
        raise ToolException("No farmer identity on this request, so there is no memory to use.")
    if runtime.store is None:
        raise ToolException("Long-term memory is not available on this server.")
    return runtime.store, memory_namespace(phone)


def memory_line(item) -> str:
    v = item.value
    return f"- [{item.key}] ({v.get('category', 'other')}, {item.updated_at:%Y-%m-%d}) {v.get('content', '')}"


@tool
async def create_or_update_user_memory(
    content: str,
    *,
    runtime: ToolRuntime[UserContext],
    category: Category = "other",
    memory_id: str | None = None,
    forget: bool = False,
) -> str:
    """Remember a lasting fact about the farmer for future conversations, correct one, or forget one.

    Save any fact about the farmer, even one said in passing: their land (size in bigha,
    soil, irrigation, plots), crops and varieties they grow, have planted or plan to plant,
    fertiliser or pesticide they applied, past problems and what worked, animals and ponds,
    preferences (prefers non-chemical options, calls in the evening). Not today's symptoms or
    treatment, which the crop case keeps, not the profile, and nothing the farmer asked you
    not to keep.

    - content: one short fact, in Bangla, with real dates instead of words like "last month",
      e.g. "অক্টোবর ২০২৬-এ অল্প জমিতে তুলা লাগিয়েছেন", "৩ বিঘা জমিতে ব্রি ধান২৮ চাষ করেন".
    - category: farm, crops, history (past problems and outcomes), preference or other.
    - memory_id: to update a fact that changed (from the memory list), instead of adding a
      second one that contradicts it.
    - forget: true with memory_id deletes that memory, when the farmer asks you to forget it
      (content is then ignored).
    """
    store, ns = _where(runtime)
    if forget:
        if not memory_id or await store.aget(ns, memory_id) is None:
            raise ToolException("To forget a memory, pass its memory_id from the memory list.")
        await store.adelete(ns, memory_id)
        return f"Forgot memory {memory_id}."
    content = " ".join(content.split())[:MAX_CHARS]
    if not content:
        raise ToolException("content is empty.")
    if memory_id:
        if await store.aget(ns, memory_id) is None:
            raise ToolException(f"No memory {memory_id}; leave memory_id out to add a new one.")
        key = memory_id
    else:
        if len(await store.asearch(ns, limit=MAX_MEMORIES)) >= MAX_MEMORIES:
            raise ToolException(
                f"The farmer already has {MAX_MEMORIES} memories. Update an outdated one (memory_id) instead."
            )
        key = f"m{uuid.uuid4().hex[:8]}"
    await store.aput(ns, key, {"content": content, "category": category})
    return f"{'Updated' if memory_id else 'Saved'} memory {key}: {content}"


@tool
async def fetch_user_memory(
    *,
    runtime: ToolRuntime[UserContext],
    query: str | None = None,
    category: Category | None = None,
) -> str:
    """Look up what you remember about the farmer from earlier conversations.

    The memories are also listed in your instructions; use this to search them, e.g. before
    advising on a crop, check what they grew or what failed before.

    - query: words to look for (Bangla or English); leave out to list everything.
    - category: only this kind: farm, crops, history, preference or other.
    """
    store, ns = _where(runtime)
    items = await store.asearch(ns, filter={"category": category} if category else None, limit=MAX_MEMORIES)
    if not items:
        return "Nothing remembered about this farmer yet."
    if query:
        words = [w.lower() for w in query.split() if w.strip()]
        hits = [i for i in items if any(w in i.value.get("content", "").lower() for w in words)]
        if not hits:
            return f"No memory mentions {query!r}. Everything remembered:\n" + "\n".join(map(memory_line, items))
        items = hits
    return "\n".join(map(memory_line, items))


for _t in (create_or_update_user_memory, fetch_user_memory):
    _t.handle_tool_error = True
