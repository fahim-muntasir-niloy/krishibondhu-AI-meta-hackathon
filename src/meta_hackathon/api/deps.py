from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request

from meta_hackathon.utils.phone import normalize_phone


def get_phone_number(
    x_phone_number: Annotated[str, Header(description="User identity, E.164 phone number")],
) -> str:
    """No auth yet: the phone number header *is* the user identity."""
    try:
        return normalize_phone(x_phone_number)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid X-Phone-Number header")


def get_agent(request: Request):
    return request.app.state.agent


def get_web_agent(request: Request):
    return request.app.state.web_agent


PhoneNumber = Annotated[str, Depends(get_phone_number)]
Agent = Annotated[Any, Depends(get_agent)]
WebAgent = Annotated[Any, Depends(get_web_agent)]
