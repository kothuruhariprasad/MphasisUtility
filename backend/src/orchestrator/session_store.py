from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class SessionData:
    created_at: float
    ir_dialogs: List[Dict[str, Any]]
    intents: List[Dict[str, Any]]
    tools: List[Dict[str, Any]]
    platform: str
    uploaded_file_name: str


class SessionStore:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._store: Dict[str, SessionData] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        ir_dialogs: List[Dict[str, Any]],
        intents: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        platform: str = "x011",
        uploaded_file_name: str = "",
    ) -> str:
        session_id = str(uuid.uuid4())
        async with self._lock:
            self._store[session_id] = SessionData(
                created_at=time.time(),
                ir_dialogs=ir_dialogs,
                intents=intents,
                tools=tools or [],
                platform=platform,
                uploaded_file_name=uploaded_file_name,
            )
        return session_id

    async def get(self, session_id: str) -> Optional[SessionData]:
        async with self._lock:
            session = self._store.get(session_id)
            if not session:
                return None
            if time.time() - session.created_at > self._ttl_seconds:
                self._store.pop(session_id, None)
                return None
            return session

    async def cleanup(self) -> None:
        now = time.time()
        async with self._lock:
            expired = [
                session_id
                for session_id, data in self._store.items()
                if now - data.created_at > self._ttl_seconds
            ]
            for session_id in expired:
                self._store.pop(session_id, None)
