from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from src.config import settings
from src.orchestrator.session_store import SessionStore
from src.pipeline.ir import preprocess
from src.security.shared_auth import AuthUser, require_rate_limit, require_user

router = APIRouter()

session_store: SessionStore | None = None


def init_upload_routes(store: SessionStore) -> None:
    global session_store
    session_store = store


def _sanitize_intent_filename(name: str) -> str:
    lowered = name.lower().strip()
    lowered = re.sub(r"\s+", "_", lowered)
    lowered = re.sub(r"[^a-z0-9_\.]+", "", lowered)
    return lowered or "intent"


def _normalize_tool_name(name: str) -> str:
    lowered = str(name or "").strip().lower()
    lowered = re.sub(r"[^a-z0-9_]+", "_", lowered)
    lowered = re.sub(r"_+", "_", lowered).strip("_")
    return lowered or "tool"


def _resolve_display_name(dialog: Dict[str, Any]) -> str:
    entry_nodes = set(dialog.get("entry_nodes") or [])
    for node in dialog.get("nodes") or []:
        if node.get("node_id") in entry_nodes:
            comp = node.get("component") or {}
            if comp.get("type") == "intent" and comp.get("intent"):
                return str(comp["intent"])
            if comp.get("name"):
                return str(comp["name"])
            if comp.get("label"):
                return str(comp["label"])
    if dialog.get("ref_id"):
        return str(dialog["ref_id"])
    if dialog.get("name"):
        return str(dialog["name"])
    if dialog.get("displayName"):
        return str(dialog["displayName"])
    return str(dialog.get("dialog_id") or "intent")


def _has_agent_node(dialog: Dict[str, Any]) -> bool:
    for node in dialog.get("nodes") or []:
        comp = node.get("component") or {}
        if comp.get("type") == "aiassist":
            return True
    return False


def _find_definition_file(zip_obj: zipfile.ZipFile) -> Optional[tuple[str, str]]:
    candidates: List[tuple[str, str]] = []
    preferred = {"appdefinition.json", "botdefinition.json"}
    for item in zip_obj.namelist():
        normalized = item.replace("\\", "/").strip("/")
        if not normalized or normalized.endswith("/"):
            continue
        parts = normalized.split("/")
        filename = parts[-1].lower()
        if filename in preferred and len(parts) <= 2:
            platform = "x010" if filename == "botdefinition.json" else "x011"
            candidates.append((item, platform))
    if not candidates:
        return None
    candidates.sort(key=lambda entry: entry[0].lower().endswith("appdefinition.json"), reverse=True)
    return candidates[0]


def _safe_extract(zip_obj: zipfile.ZipFile, extract_path: Path) -> None:
    base_path = extract_path.resolve()
    max_entries = max(1, settings.max_zip_entries)
    max_uncompressed = max(1, settings.max_zip_uncompressed_mb) * 1024 * 1024

    total_uncompressed = 0
    entries = 0
    for member in zip_obj.infolist():
        if member.is_dir():
            continue
        entries += 1
        if entries > max_entries:
            raise HTTPException(
                status_code=413,
                detail={
                    "error": "ARCHIVE_TOO_LARGE",
                    "message": "Archive has too many files.",
                },
            )
        total_uncompressed += int(member.file_size or 0)
        if total_uncompressed > max_uncompressed:
            raise HTTPException(
                status_code=413,
                detail={
                    "error": "ARCHIVE_TOO_LARGE",
                    "message": "Archive uncompressed size exceeds the limit.",
                },
            )
        target_path = (extract_path / member.filename).resolve()
        if base_path not in target_path.parents and target_path != base_path:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "UNSAFE_ARCHIVE",
                    "message": "Archive contains unsafe paths.",
                },
            )

    zip_obj.extractall(extract_path)


def _extract_tools(app: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_tools = app.get("tools") if isinstance(app.get("tools"), list) else []
    extracted: List[Dict[str, Any]] = []
    seen_names: Dict[str, int] = {}
    for item in raw_tools:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("toolName") or "").strip()
        if not name:
            continue
        normalized = _normalize_tool_name(name)
        base_name = normalized
        if base_name in seen_names:
            seen_names[base_name] += 1
            normalized = f"{base_name}_{seen_names[base_name]}"
        else:
            seen_names[base_name] = 1
        tool: Dict[str, Any] = {
            "name": normalized,
            "description": str(item.get("description") or "").strip(),
            "type": str(item.get("type") or "http").strip() or "http",
        }
        for key in (
            "method",
            "endpoint",
            "body_mode",
            "headers",
            "query_params",
            "params",
            "server",
            "server_tool",
            "path_params",
            "body",
        ):
            if item.get(key) is not None:
                tool[key] = item.get(key)
        extracted.append(tool)
    return extracted


@router.post("/upload")
async def upload(
    request: Request,
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_user),
) -> Dict[str, Any]:
    _ = user
    await require_rate_limit(request, "upload")
    if session_store is None:
        raise HTTPException(status_code=500, detail="Session store not initialized")

    original_name = file.filename or ""
    lowered_name = original_name.lower()
    if not lowered_name.endswith(".zip"):
        raise HTTPException(status_code=400, detail={"error": "UNSUPPORTED_ARCHIVE", "message": "Only .zip archives are supported."})

    raw_bytes = await file.read()
    max_upload_bytes = max(1, settings.max_upload_mb) * 1024 * 1024
    if len(raw_bytes) > max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "ARCHIVE_TOO_LARGE",
                "message": "Uploaded archive exceeds the size limit.",
            },
        )
    try:
        zip_obj = zipfile.ZipFile(io.BytesIO(raw_bytes))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail={"error": "INVALID_ARCHIVE", "message": "Uploaded file is not a valid zip archive."}) from exc

    definition_entry = _find_definition_file(zip_obj)
    if not definition_entry:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "MISSING_APPDEF",
                "message": "appDefinition.json or botDefinition.json not found in the uploaded archive.",
            },
        )
    appdef_member, platform = definition_entry

    with TemporaryDirectory() as tmp_dir:
        extract_path = Path(tmp_dir)
        _safe_extract(zip_obj, extract_path)
        target_path = extract_path / appdef_member
        try:
            app = json.loads(target_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "INVALID_JSON",
                    "message": "Definition JSON is malformed (appDefinition.json or botDefinition.json).",
                },
            ) from exc

    ir = preprocess(app, platform)
    intents: List[Dict[str, Any]] = []
    for dialog in ir.get("dialogs") or []:
        display_name = _resolve_display_name(dialog)
        has_agent = _has_agent_node(dialog)
        intents.append(
            {
                "id": str(dialog.get("dialog_id") or display_name),
                "name": display_name,
                "fileSafeName": _sanitize_intent_filename(display_name),
                "nodeCount": int(dialog.get("reachable_node_count") or 0),
                "hasAgentNode": has_agent,
                "suggestedAgentStyle": "reasoning" if has_agent else "flow",
            }
        )

    tools = _extract_tools(app)
    session_id = await session_store.create(
        ir_dialogs=ir.get("dialogs") or [],
        intents=intents,
        tools=tools,
        platform=platform,
        uploaded_file_name=original_name,
    )
    return {"sessionId": session_id, "intents": intents, "platform": platform}
