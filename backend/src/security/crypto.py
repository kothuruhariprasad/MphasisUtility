"""Symmetric encryption helpers for user-submitted LLM credentials.

API keys are never written to disk, never logged, and never echoed back to
the client. They are encrypted immediately on receipt with a server-side
Fernet key and held only in the in-memory credential store, decrypted only
transiently at the point of making an outbound LLM call.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Dict

from cryptography.fernet import Fernet, InvalidToken

from src.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    key = settings.credential_encryption_key
    if not key:
        # Dev-only fallback: ephemeral key generated once per process.
        # Anything encrypted with it is lost on restart (acceptable since
        # the credential store itself is in-memory only). Production
        # deployments must set CREDENTIAL_ENCRYPTION_KEY explicitly.
        key = Fernet.generate_key().decode("utf-8")
        logger.warning(
            "CREDENTIAL_ENCRYPTION_KEY not set; using an ephemeral in-process "
            "key. Set CREDENTIAL_ENCRYPTION_KEY in production so encrypted "
            "credentials remain valid across restarts."
        )
    return Fernet(key.encode("utf-8") if isinstance(key, str) else key)


def encrypt_json(data: Dict[str, Any]) -> bytes:
    fernet = _get_fernet()
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return fernet.encrypt(payload)


def decrypt_json(token: bytes) -> Dict[str, Any]:
    fernet = _get_fernet()
    try:
        payload = fernet.decrypt(token)
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt stored credential") from exc
    return json.loads(payload.decode("utf-8"))
