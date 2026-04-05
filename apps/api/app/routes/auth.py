"""Authentication routes for demo cookie session auth."""

from __future__ import annotations

from secrets import compare_digest

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.auth import CurrentUser, SESSION_USER_KEY, require_current_user
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Login request payload."""

    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    """Minimal user payload returned to the client."""

    username: str


class AuthResponse(BaseModel):
    """Auth response payload."""

    authenticated: bool
    user: UserOut


class LogoutResponse(BaseModel):
    """Logout response payload."""

    authenticated: bool = False


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, request: Request) -> AuthResponse:
    """Validate demo credentials and create a session."""

    username_ok = compare_digest(payload.username, settings.app_demo_username)
    password_ok = compare_digest(payload.password, settings.app_demo_password)
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    request.session[SESSION_USER_KEY] = settings.app_demo_username
    return AuthResponse(authenticated=True, user=UserOut(username=settings.app_demo_username))


@router.post("/logout", response_model=LogoutResponse)
async def logout(request: Request) -> LogoutResponse:
    """Clear current session cookie."""

    request.session.clear()
    return LogoutResponse()


@router.get("/me", response_model=AuthResponse)
async def me(current_user: CurrentUser = Depends(require_current_user)) -> AuthResponse:
    """Return currently authenticated demo user."""

    return AuthResponse(authenticated=True, user=UserOut(username=current_user.username))
