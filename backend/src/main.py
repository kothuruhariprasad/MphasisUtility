from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.admin import router as admin_router
from src.api.auth import router as auth_router
from src.api.generate import init_generate_routes, router as generate_router
from src.api.llm_config import init_llm_config_routes, router as llm_config_router
from src.api.upload import init_upload_routes, router as upload_router
from src.config import settings
from src.orchestrator.credential_store import CredentialStore
from src.orchestrator.session_store import SessionStore


def _load_template(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI):
    session_store = SessionStore(ttl_seconds=settings.session_ttl_seconds)
    credential_store = CredentialStore(ttl_seconds=settings.credential_ttl_seconds)
    init_upload_routes(session_store)
    init_generate_routes(session_store, credential_store)
    init_llm_config_routes(credential_store)

    templates_dir = Path(__file__).resolve().parents[1] / "templates"
    app.state.reasoning_agent_sample = _load_template(templates_dir / "reasoning_agent_sample.abl")
    app.state.flow_agent_sample = _load_template(templates_dir / "flow_agent_sample.abl")
    app.state.supervisor_agent_sample = _load_template(templates_dir / "supervisor_agent_sample.abl")

    repo_root = Path(__file__).resolve().parents[2]
    app.state.abl_rules_doc = _load_template(repo_root / "ABL_rules.md")

    stop_event = asyncio.Event()

    async def cleanup_worker() -> None:
        while not stop_event.is_set():
            await session_store.cleanup()
            await credential_store.cleanup()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=60)
            except asyncio.TimeoutError:
                continue

    task = asyncio.create_task(cleanup_worker())
    try:
        yield
    finally:
        stop_event.set()
        await task


app = FastAPI(title="AppDef to ABL Converter API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router, prefix="/api")
app.include_router(generate_router, prefix="/api")
app.include_router(llm_config_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(admin_router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
