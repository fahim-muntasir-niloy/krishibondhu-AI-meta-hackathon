"""The web chat: the farmer's conversations and one streaming route per turn.

The stream is server-sent events, one JSON object per `data:` line:

    {"type": "message", "message": {...}}   a finished message, as LangChain dumps it
    {"type": "token", "text": "..."}        reply text so far, replaced by its `message`
    {"type": "error", "message": "..."}     then `end`
    {"type": "end"}

The run belongs to the request: when the client stops or goes away, it is cancelled.
"""

import asyncio
import base64
import binascii
import json
import logging
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import openai
from fastapi import APIRouter, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from langchain.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field, field_validator

from meta_hackathon import threads
from meta_hackathon.agent.context import UserContext
from meta_hackathon.api.deps import PhoneNumber, WebAgent
from meta_hackathon.gallery import blob_enabled, record_image, save_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/threads", tags=["threads"])

HEARTBEAT_SECONDS = 15.0
# Text plus the composer's 2 photos.
_MAX_BLOCKS = 4
_MAX_TITLE = 200
_SSE_HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}


class ThreadCreate(BaseModel):
    title: str | None = Field(default=None, max_length=_MAX_TITLE)


class ThreadPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=_MAX_TITLE)
    pinned: bool | None = None


class TurnContext(BaseModel):
    """The web profile, and the case open beside the chat."""

    name: str | None = None
    area: str | None = None
    district: str | None = None
    division: str | None = None
    case_id: str | None = None


class TurnRequest(BaseModel):
    content: str | list[dict[str, Any]]
    context: TurnContext = TurnContext()

    @field_validator("content")
    @classmethod
    def _check_content(cls, content: str | list[dict[str, Any]]) -> str | list[dict[str, Any]]:
        if not content:
            raise ValueError("Empty message")
        if isinstance(content, str):
            return content
        if len(content) > _MAX_BLOCKS:
            raise ValueError("Too many content blocks")
        for block in content:
            if block.get("type") == "text":
                continue
            # Photos come as data URLs only: tools fetch image URLs from the server,
            # so one chosen by the client could point it anywhere.
            if block.get("type") != "image_url" or not _image_url(block).startswith("data:image/"):
                raise ValueError("Only text and photos as data URLs")
        return content


def _image_url(block: dict[str, Any]) -> str:
    url = block.get("image_url")
    return str(url.get("url", "") if isinstance(url, dict) else url or "")


def _config(phone: str, thread_id: str) -> dict:
    return {
        "configurable": {"thread_id": thread_id},
        "metadata": {"phone_number": phone},
        "tags": ["web"],
    }


def _dump(message: BaseMessage) -> dict:
    return jsonable_encoder(message.model_dump())


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _chunk_text(chunk: AIMessageChunk) -> str:
    return chunk.text if isinstance(chunk.text, str) else chunk.text()


async def _link_photos(content: str | list[dict[str, Any]], phone: str, thread_id: str) -> str | list[dict[str, Any]]:
    """Moves the turn's photos to Blob, so the checkpoint and the model hold links and
    Postgres records each. Without Blob (local dev) a local link would be out of the
    model's reach, so the data URLs stay in the message."""
    if isinstance(content, str) or not blob_enabled():
        return content
    linked = []
    for block in content:
        if block.get("type") != "image_url":
            linked.append(block)
            continue
        try:
            data = base64.b64decode(_image_url(block).split(",", 1)[1], validate=True)
            name, url = await save_image(data)
            await asyncio.to_thread(record_image, phone, name, url=url, kind="upload", thread_id=thread_id, labels=[])
        except (binascii.Error, IndexError) as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid photo") from e
        linked.append({"type": "image_url", "image_url": {"url": url}})
    return linked


async def _unanswered_calls(agent, config: dict) -> list[ToolMessage]:
    """A turn cut off during a tool (Stop, a dropped connection, the platform's time limit)
    leaves calls with no result, and the model rejects a history like that."""
    state = await agent.aget_state(config)
    messages = state.values.get("messages", []) if state.values else []
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    return [
        ToolMessage(content="Cancelled: the farmer's connection ended before this finished.", tool_call_id=call["id"], status="error")
        for m in messages
        if isinstance(m, AIMessage)
        for call in m.tool_calls
        if call["id"] not in answered
    ]


async def _events(agent, phone: str, thread_id: str, human: HumanMessage, context: TurnContext) -> AsyncIterator[str]:
    config = _config(phone, thread_id)
    yield _sse({"type": "message", "message": _dump(human)})
    try:
        messages = [*await _unanswered_calls(agent, config), human]
        async for mode, data in agent.astream(
            {"messages": messages},
            config=config,
            context=UserContext(phone_number=phone, **context.model_dump()),
            stream_mode=["messages", "updates"],
        ):
            if mode == "messages":
                chunk = data[0]
                if isinstance(chunk, AIMessageChunk) and (text := _chunk_text(chunk)):
                    yield _sse({"type": "token", "text": text})
                continue
            for update in data.values():
                new = update.get("messages") if isinstance(update, dict) else None
                for message in new if isinstance(new, list) else []:
                    if isinstance(message, BaseMessage):
                        yield _sse({"type": "message", "message": _dump(message)})
    except openai.BadRequestError as e:
        logger.warning("Model rejected a turn of thread %s: %s", thread_id, e)
        filtered = isinstance(e.body, dict) and e.body.get("code") == "content_policy_violation"
        yield _sse({"type": "error", "message": "content_policy" if filtered else "model_error"})
    except Exception:
        logger.exception("Turn failed in thread %s", thread_id)
        yield _sse({"type": "error", "message": "turn_failed"})
    yield _sse({"type": "end"})


async def _with_heartbeat(frames: AsyncIterator[str]) -> AsyncGenerator[str]:
    """Comment frames during quiet gaps (a slow tool, the model thinking), so nothing
    between here and the browser closes the connection as idle. The source is cancelled
    when the client goes away."""
    queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=256)

    async def produce() -> None:
        try:
            async for frame in frames:
                await queue.put(frame)
        finally:
            await queue.put(None)

    producer = asyncio.create_task(produce())
    try:
        while True:
            try:
                frame = await asyncio.wait_for(queue.get(), HEARTBEAT_SECONDS)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if frame is None:
                break
            yield frame
    finally:
        producer.cancel()
        await asyncio.gather(producer, return_exceptions=True)


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found")


@router.get("")
def list_threads(phone: PhoneNumber) -> dict:
    return {"threads": threads.list_threads(phone)}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_thread(body: ThreadCreate, phone: PhoneNumber) -> dict:
    return threads.create_thread(phone, body.title)


@router.get("/{thread_id}/messages")
async def thread_messages(thread_id: str, phone: PhoneNumber, agent: WebAgent) -> dict:
    if not await asyncio.to_thread(threads.owns_thread, phone, thread_id):
        raise _not_found()
    state = await agent.aget_state(_config(phone, thread_id))
    return {"messages": [_dump(m) for m in (state.values or {}).get("messages", [])]}


@router.patch("/{thread_id}")
def update_thread(thread_id: str, body: ThreadPatch, phone: PhoneNumber) -> dict:
    thread = threads.update_thread(phone, thread_id, title=body.title, pinned=body.pinned)
    if not thread:
        raise _not_found()
    return thread


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(thread_id: str, phone: PhoneNumber, agent: WebAgent) -> None:
    """The conversation with its messages. Plans, bookings and photos it produced stay."""
    if not await asyncio.to_thread(threads.delete_thread, phone, thread_id):
        raise _not_found()
    await agent.checkpointer.adelete_thread(thread_id)


@router.post("/{thread_id}/stream")
async def stream_turn(thread_id: str, body: TurnRequest, phone: PhoneNumber, agent: WebAgent) -> StreamingResponse:
    if not await asyncio.to_thread(threads.touch_thread, phone, thread_id):
        raise _not_found()
    content = await _link_photos(body.content, phone, thread_id)
    human = HumanMessage(content=content, id=str(uuid.uuid4()))
    return StreamingResponse(
        _with_heartbeat(_events(agent, phone, thread_id, human, body.context)),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
