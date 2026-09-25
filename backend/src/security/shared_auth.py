"""Shared-password access control with signed session tokens.

Lightweight shared-password auth for internal tools with server-validated
sessions and rate limiting.
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, Optional, Tuple

from fastapi import Depends, Header, HTTPException, Request
from jose import JWTError, jwt
from passlib.context import CryptContext

from src.config import settings


@dataclass(frozen=True)
class AuthUser:
    email: str
    role: str
    session_id: str


_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_rate_lock = asyncio.Lock()
_rate_events: Dict[str, Deque[float]] = {}


def _session_secret() -> str:
    secret = settings.session_secret
    if not secret:
        raise HTTPException(status_code=500, detail="SESSION_SECRET is not configured")
    return secret


def _client_id(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _allowed_origins() -> set[str]:
    return {origin for origin in settings.cors_origins if origin}


def _origin_allowed(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        referer = request.headers.get("referer")
        if not referer:
            return True
        parsed = urlparse(referer)
        if not parsed.scheme or not parsed.netloc:
            return False
        origin = f"{parsed.scheme}://{parsed.netloc}"
    return origin in _allowed_origins()


async def require_rate_limit(request: Request, action: str) -> None:
    limit = max(1, settings.rate_limit_per_minute)
    window_seconds = 60
    key = f"{action}:{_client_id(request)}"
    now = time.time()

    async with _rate_lock:
        events = _rate_events.setdefault(key, deque())
        while events and now - events[0] > window_seconds:
            events.popleft()
        if len(events) >= limit:
            raise HTTPException(status_code=429, detail="Too many requests")
        events.append(now)


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return _pwd_context.verify(password, password_hash)
    except Exception:
        return False


def authenticate_password(password: str) -> Tuple[str, str]:
    if not settings.app_password_hash and not settings.app_admin_password_hash:
        raise HTTPException(status_code=500, detail="APP_PASSWORD_HASH is not configured")

    if settings.app_admin_password_hash and _verify_password(password, settings.app_admin_password_hash):
        return settings.shared_admin_email, "admin"
    if settings.app_password_hash and _verify_password(password, settings.app_password_hash):
        return settings.shared_user_email, "user"

    raise HTTPException(status_code=401, detail="Invalid password")


def create_session_token(email: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=settings.auth_session_ttl_seconds)
    payload = {
        "sub": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    return jwt.encode(payload, _session_secret(), algorithm="HS256")


def _decode_token(token: str) -> AuthUser:
    try:
        payload = jwt.decode(token, _session_secret(), algorithms=["HS256"])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid session") from exc

    email = str(payload.get("sub") or "shared-user")
    role = str(payload.get("role") or "user")
    session_id = str(payload.get("jti") or "")
    return AuthUser(email=email, role=role, session_id=session_id)


def _extract_token(request: Request, authorization: Optional[str], token: Optional[str]) -> Tuple[Optional[str], bool]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip(), False
    if token:
        return token, False
    cookie_token = request.cookies.get(settings.auth_cookie_name)
    return cookie_token, True


def require_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    token: Optional[str] = None,
) -> AuthUser:
    raw_token, from_cookie = _extract_token(request, authorization, token)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Authentication required")

    if from_cookie and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if not _origin_allowed(request):
            raise HTTPException(status_code=403, detail="Origin not allowed")

    return _decode_token(raw_token)


def require_admin(user: AuthUser = Depends(require_user)) -> AuthUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def cookie_settings(request: Request) -> Dict[str, object]:
    secure = settings.auth_cookie_secure
    if secure is None:
        secure = request.url.scheme == "https"
    return {
        "key": settings.auth_cookie_name,
        "httponly": True,
        "secure": bool(secure),
        "samesite": settings.auth_cookie_same_site,
        "max_age": settings.auth_session_ttl_seconds,
        "path": "/",
    }


def clear_cookie_settings(request: Request) -> Dict[str, object]:
    base = cookie_settings(request)
    base["max_age"] = 0
    return base
