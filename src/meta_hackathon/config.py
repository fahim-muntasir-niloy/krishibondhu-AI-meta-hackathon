import os

from pydantic import Field
from pydantic_settings import BaseSettings


def _default_public_base_url() -> str:
    """Only local images use this (gallery.py). On Vercel: the deployment's own origin."""
    production = os.environ.get("VERCEL_ENV") == "production"
    host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL" if production else "VERCEL_URL")
    return f"https://{host}" if host else "http://localhost:2024"


class Config(BaseSettings):
    # "production" hides the API docs (main.py).
    ENVIRONMENT: str = "development"

    META_API_KEY: str
    META_BASE_URL: str
    MODEL_NAME: str
    SEGMENT_MODEL_NAME: str = "sam-3.1"
    TRANSCRIBE_MODEL_NAME: str = "muse-voice-transcribe-1.0"
    IMAGE_MODEL_NAME: str = "muse-image-1.0"

    # Postgres: the app's records (db.py), conversation checkpoints and long-term memory
    # (persistence.py), and the reference data in the `agri` schema. `uv run krishi-db migrate`.
    DB_URI: str

    # Without Blob, images are saved here and served at {PUBLIC_BASE_URL}/media/<file>.
    # Also the picture cards' cache. A Vercel function can only write under /tmp.
    MEDIA_DIR: str = "/tmp/krishi-media" if os.environ.get("VERCEL") else ".media"
    # Vercel Blob (gallery.py), for running locally against a store. On Vercel a connected
    # store sets its own credentials.
    BLOB_READ_WRITE_TOKEN: str | None = None
    PUBLIC_BASE_URL: str = Field(default_factory=_default_public_base_url)
    # The old SQLite file, read once by `krishi-db import-sqlite`.
    DATA_DIR: str = ".data"

    LANGSMITH_TRACING: str
    LANGSMITH_ENDPOINT: str
    LANGSMITH_API_KEY: str
    LANGSMITH_AGENT_ID: str
    LANGSMITH_AGENT_ENVIRONMENT: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


settings = Config()

# The Blob SDK reads the environment, not pydantic-settings' .env.
if settings.BLOB_READ_WRITE_TOKEN:
    os.environ.setdefault("BLOB_READ_WRITE_TOKEN", settings.BLOB_READ_WRITE_TOKEN)


def setup_langsmith() -> None:
    """LangSmith reads its settings from os.environ, not from pydantic-settings,
    so export them before any LangChain object runs.

    Runs are addressed to the LangSmith agent (LANGSMITH_AGENT_ID + _ENVIRONMENT).
    Don't also set LANGSMITH_PROJECT: with both in the environment the SDK
    traces nothing ("neither outranks the other")."""
    for key in (
        "LANGSMITH_TRACING",
        "LANGSMITH_ENDPOINT",
        "LANGSMITH_API_KEY",
        "LANGSMITH_AGENT_ID",
        "LANGSMITH_AGENT_ENVIRONMENT",
    ):
        os.environ.setdefault(key, getattr(settings, key))
    os.environ.pop("LANGSMITH_PROJECT", None)
