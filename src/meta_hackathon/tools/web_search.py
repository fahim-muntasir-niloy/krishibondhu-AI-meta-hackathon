from langchain.tools import tool
from langsmith.wrappers import wrap_openai
from openai import AsyncOpenAI, OpenAIError

from meta_hackathon.config import settings

# Muse's built-in `web_search` only runs through the Responses API, and there it
# interleaves progress text ("খুঁজছি…") with the answer. Calling it from inside a
# tool keeps the agent's own reply clean openui-lang and lets the UI narrate the step.
_client = wrap_openai(AsyncOpenAI(base_url=settings.META_BASE_URL, api_key=settings.META_API_KEY), chat_name="Muse web search")

_INSTRUCTIONS = (
    "You are a research helper for an agriculture assistant in Bangladesh. Search the web and "
    "answer the query in at most 150 words of plain English: concrete facts, figures with units, "
    "places and the date each fact refers to. Say clearly if nothing recent was found. No greetings."
)


@tool
async def search_internet(query: str) -> dict:
    """Search the live web for recent information the knowledge base does not have:
    market prices (ধান/চালের দাম), news, government announcements, new pest or disease
    outbreaks. Returns a short summary and its sources. Never take pesticide doses from it.

    Args:
        query: What to find, with place and time if relevant (e.g. "Bogura Aman paddy price this week").
    """
    try:
        resp = await _client.responses.create(
            model=settings.MODEL_NAME,
            instructions=_INSTRUCTIONS,
            input=query,
            tools=[{"type": "web_search"}],
        )
    except OpenAIError as e:
        return {"query": query, "error": f"Web search failed: {e}"}

    # Only the last message is the answer; earlier ones are progress notes.
    messages = [item for item in resp.output if item.type == "message"]
    blocks = [c for c in messages[-1].content if c.type == "output_text"] if messages else []
    sources: dict[str, dict] = {}
    for block in blocks:
        for a in block.annotations or []:
            if a.type == "url_citation" and a.url not in sources:
                sources[a.url] = {"title": a.title or a.url, "url": a.url}
    return {
        "query": query,
        "summary": "".join(b.text for b in blocks).strip() or "No answer found.",
        "sources": list(sources.values())[:5],
    }
