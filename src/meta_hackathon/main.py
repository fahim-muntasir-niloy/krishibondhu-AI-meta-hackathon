from contextlib import asynccontextmanager

import logging
import re
from pathlib import Path

import openai
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from meta_hackathon.config import settings, setup_langsmith

# Must run before any LangChain object is created so tracing picks up the env.
setup_langsmith()

# Every outbound HTTP call at INFO otherwise.
logging.getLogger("httpx").setLevel(logging.WARNING)

from meta_hackathon.agent.build_agent import build_agent  # noqa: E402
from meta_hackathon.api.bookings import router as bookings_router  # noqa: E402
from meta_hackathon.api.cases import router as cases_router  # noqa: E402
from meta_hackathon.api.chat import router as chat_router  # noqa: E402
from meta_hackathon.api.images import router as images_router  # noqa: E402
from meta_hackathon.api.pesticides import router as pesticides_router  # noqa: E402
from meta_hackathon.api.threads import router as threads_router  # noqa: E402
from meta_hackathon.api.voice import router as voice_router  # noqa: E402
from meta_hackathon.persistence import checkpointer, store  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Same conversations and memory, two reply formats. Small pools: Aiven's free plan
    # allows few connections, and every running instance opens its own.
    async with checkpointer(max_size=3) as saver, store(max_size=1) as memory:
        app.state.agent = build_agent(checkpointer=saver, store=memory)  # plain text: /v1/chat
        app.state.web_agent = build_agent(reply_format="openui", checkpointer=saver, store=memory)
        yield


_production = settings.ENVIRONMENT.lower() == "production"

app = FastAPI(
    title="KrishiBondhu.AI",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if _production else "/docs",
    redoc_url=None if _production else "/redoc",
    openapi_url=None if _production else "/openapi.json",
)
# Only for `next dev`; everywhere else the frontend is served from this origin (main.py).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(threads_router)
app.include_router(chat_router)
app.include_router(cases_router)
app.include_router(bookings_router)
app.include_router(images_router)
app.include_router(pesticides_router)
app.include_router(voice_router)


@app.exception_handler(openai.BadRequestError)
async def model_bad_request(request: Request, exc: openai.BadRequestError) -> JSONResponse:
    code = (exc.body or {}).get("code") if isinstance(exc.body, dict) else None
    if code == "content_policy_violation":
        return JSONResponse(
            status_code=422,
            content={"detail": "Message was blocked by the model provider's content filter."},
        )
    return JSONResponse(status_code=502, content={"detail": f"Model request failed: {exc.message}"})


@app.get("/media/{name}", tags=["meta"])
async def media(name: str) -> FileResponse:
    """Images saved to MEDIA_DIR when Blob is not configured (gallery.py). Public, but
    names are unguessable random ids."""
    if not re.fullmatch(r"[a-f0-9]{32}\.jpg", name):
        raise HTTPException(status_code=404)
    path = Path(settings.MEDIA_DIR) / name
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok", "model": settings.MODEL_NAME}
