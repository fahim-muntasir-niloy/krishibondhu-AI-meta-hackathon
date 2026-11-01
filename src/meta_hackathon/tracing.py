"""LangSmith detail inside the tools. LangChain traces the agent, the main model and
each tool call by itself, but a tool's own API calls and steps are invisible to it, so
they are declared here. Pixels and mask payloads stay out of the trace's text: an image
worth seeing is attached to its run instead.

All of it does nothing when tracing is off, and a tracing failure never reaches a farmer.
"""

from langsmith.run_helpers import get_current_run_tree


def model_metadata(model: str) -> dict:
    """What LangSmith shows as the model of an `llm` run."""
    return {"ls_provider": "meta", "ls_model_name": model}


def attach_jpeg(name: str, data: bytes) -> None:
    """Shows an image on the current run, in the LangSmith UI. No periods in `name`:
    LangSmith drops such an attachment with only a warning."""
    if run := get_current_run_tree():
        run.attachments[name] = ("image/jpeg", data)


def no_inputs(_: dict) -> dict:
    """For steps whose arguments are images or masks."""
    return {}
