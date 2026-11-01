from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langgraph.store.base import BaseStore
from langgraph.types import Checkpointer

from meta_hackathon.agent.context import UserContext
from meta_hackathon.agent.model import llm
from meta_hackathon.middlewares.content_filter import content_filter_guard
from meta_hackathon.middlewares.system_prompt import system_prompt
from meta_hackathon.prompts.system import ReplyFormat
from meta_hackathon.tools import ALL_TOOLS


def build_agent(*, reply_format: ReplyFormat = "text", checkpointer: Checkpointer = None, store: BaseStore | None = None):
    """`text` for plain chat channels (WhatsApp, /v1/chat); `openui` for the web UI,
    where replies are openui-lang rendered by the OpenUI Renderer.

    main.py passes in the Postgres checkpointer and store (persistence.py)."""
    return create_agent(
        model=llm,
        tools=ALL_TOOLS,
        middleware=[
            system_prompt(reply_format),
            content_filter_guard(reply_format),
            # One search covers every subject of a reply; a second is for a retry with other words.
            ToolCallLimitMiddleware(tool_name="search_images", run_limit=2),
            # Slow and billed per image; a reply never needs more than a mixing card and a gear card.
            ToolCallLimitMiddleware(tool_name="make_picture_card", run_limit=2),
        ],
        context_schema=UserContext,
        checkpointer=checkpointer,
        store=store,
        name="krishi_advisor",
    )
