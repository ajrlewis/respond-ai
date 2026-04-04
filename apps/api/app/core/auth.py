"""Session-based authentication helpers for demo auth."""

from __future__ import annotations

from fastapi import HTTPException, Request, status
from pydantic import BaseModel

SESSION_USER_KEY = "demo_user"


class CurrentUser(BaseModel):
    """Minimal authenticated user payload."""

    username: str


def get_current_user(request: Request) -> CurrentUser | None:
    """Return authenticated user from the signed session cookie, if present."""

    username = request.session.get(SESSION_USER_KEY)
    if not isinstance(username, str) or not username.strip():
        return None

    return CurrentUser(username=username)


def require_current_user(request: Request) -> CurrentUser:
    """Enforce authenticated session and return current user."""

    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return user
