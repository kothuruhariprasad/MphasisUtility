from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from src.security.shared_auth import (
    AuthUser,
    authenticate_password,
    clear_cookie_settings,
    cookie_settings,
    create_session_token,
    require_rate_limit,
    require_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str = Field(min_length=1)


class AuthResponse(BaseModel):
    token: str
    email: str
    role: str


@router.post("/login", response_model=AuthResponse)
async def login(request: Request, response: Response, payload: LoginRequest) -> AuthResponse:
    await require_rate_limit(request, "login")
    email, role = authenticate_password(payload.password)
    token = create_session_token(email, role)
    settings = cookie_settings(request)
    response.set_cookie(settings.pop("key"), token, **settings)
    return AuthResponse(token=token, email=email, role=role)


@router.get("/me")
async def me(request: Request, user: AuthUser = Depends(require_user)) -> dict[str, str]:
    _ = request
    return {"email": user.email, "role": user.role}


@router.post("/logout")
async def logout(request: Request, response: Response, user: AuthUser = Depends(require_user)) -> dict[str, bool]:
    _ = user
    settings = clear_cookie_settings(request)
    response.set_cookie(settings.pop("key"), "", **settings)
    return {"ok": True}
