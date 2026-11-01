from dataclasses import dataclass

from langchain.tools import ToolRuntime


@dataclass
class UserContext:
    """Per-request runtime context, available to tools via `ToolRuntime`."""

    phone_number: str | None = None
    # Farmer profile from the web UI's sign-in form; unset on other channels.
    name: str | None = None
    area: str | None = None
    district: str | None = None
    division: str | None = None
    # The crop case open in the web UI's tracker pane: the message is about it.
    case_id: str | None = None


def phone_number(runtime: ToolRuntime) -> str | None:
    return runtime.context.phone_number if runtime.context else None
