from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.security.shared_auth import AuthUser, require_admin, require_rate_limit

router = APIRouter(prefix="/admin", tags=["admin"])


class AllowlistEntry(BaseModel):
    email: str = Field(min_length=3)
    role: str = Field(default="user")
    enabled: bool = Field(default=True)
    created_at: Optional[str] = None


class AllowlistUpdate(BaseModel):
    role: Optional[str] = None
    enabled: Optional[bool] = None


_allowlist_lock = asyncio.Lock()
_allowlist: Dict[str, AllowlistEntry] = {}


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/allowlist")
async def list_allowlist(request: Request, user: AuthUser = Depends(require_admin)) -> list[AllowlistEntry]:
    _ = user
    await require_rate_limit(request, "admin_list")
    async with _allowlist_lock:
        return list(_allowlist.values())


@router.post("/allowlist")
async def upsert_allowlist(
    request: Request,
    payload: AllowlistEntry,
    user: AuthUser = Depends(require_admin),
) -> AllowlistEntry:
    _ = user
    await require_rate_limit(request, "admin_upsert")
    key = _normalize_email(payload.email)
    if not key:
        raise HTTPException(status_code=400, detail="Email is required")
    async with _allowlist_lock:
        existing = _allowlist.get(key)
        created_at = existing.created_at if existing and existing.created_at else _utc_now()
        entry = AllowlistEntry(email=key, role=payload.role, enabled=payload.enabled, created_at=created_at)
        _allowlist[key] = entry
        return entry


@router.patch("/allowlist/{email}")
async def update_allowlist(
    request: Request,
    email: str,
    payload: AllowlistUpdate,
    user: AuthUser = Depends(require_admin),
) -> AllowlistEntry:
    _ = user
    await require_rate_limit(request, "admin_update")
    key = _normalize_email(email)
    async with _allowlist_lock:
        existing = _allowlist.get(key)
        if not existing:
            raise HTTPException(status_code=404, detail="Allowlist entry not found")
        role = payload.role or existing.role
        enabled = existing.enabled if payload.enabled is None else payload.enabled
        entry = AllowlistEntry(email=key, role=role, enabled=enabled, created_at=existing.created_at)
        _allowlist[key] = entry
        return entry


@router.delete("/allowlist/{email}")
async def delete_allowlist(
    request: Request,
    email: str,
    user: AuthUser = Depends(require_admin),
) -> dict[str, bool]:
    _ = user
    await require_rate_limit(request, "admin_delete")
    key = _normalize_email(email)
    async with _allowlist_lock:
        removed = _allowlist.pop(key, None)
    return {"deleted": removed is not None}
