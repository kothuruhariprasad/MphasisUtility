"""In-memory, TTL'd store for encrypted BYOK LLM credentials.

Only encrypted bytes are ever held in this store. Plaintext API keys exist
transiently in memory only inside `resolve()` for the duration of building
an `LLMCredentials` object to pass to the LLM client, and are never logged
or returned to any caller.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.security.crypto import decrypt_json, encrypt_json


@dataclass
class _StoredCredential:
    created_at: float
    provider: str
    encrypted: bytes
    label: str


class CredentialStore:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._store: Dict[str, _StoredCredential] = {}
        self._lock = asyncio.Lock()

    async def save(self, provider: str, credential_fields: Dict[str, Any], label: str = "") -> str:
        credential_id = str(uuid.uuid4())
        encrypted = encrypt_json(credential_fields)
        async with self._lock:
            self._store[credential_id] = _StoredCredential(
                created_at=time.time(),
                provider=provider,
                encrypted=encrypted,
                label=label,
            )
        return credential_id

    async def resolve(self, credential_id: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            stored = self._store.get(credential_id)
            if not stored:
                return None
            if time.time() - stored.created_at > self._ttl_seconds:
                self._store.pop(credential_id, None)
                return None
            provider = stored.provider
            encrypted = stored.encrypted
        fields = decrypt_json(encrypted)
        return {"provider": provider, **fields}

    async def delete(self, credential_id: str) -> bool:
        async with self._lock:
            return self._store.pop(credential_id, None) is not None

    async def cleanup(self) -> None:
        now = time.time()
        async with self._lock:
            expired = [
                credential_id
                for credential_id, data in self._store.items()
                if now - data.created_at > self._ttl_seconds
            ]
            for credential_id in expired:
                self._store.pop(credential_id, None)
