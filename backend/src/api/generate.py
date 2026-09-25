from __future__ import annotations

import asyncio
import io
import json
import re
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from src.config import settings
from src.orchestrator.credential_store import CredentialStore
from src.orchestrator.session_store import SessionStore
from src.pipeline.llm_client import LLMRuntimeConfig, call_llm, verify_abl
from src.pipeline.prompt import ABL_JSON_SCHEMA, build_generation_prompt
from src.pipeline.validator import validate_abl_text
from src.security.shared_auth import AuthUser, require_rate_limit, require_user

router = APIRouter(prefix="/generate", tags=["generate"])

SUPERVISOR_INTENT_ID = "__supervisor__"


class SelectionItem(BaseModel):
    intentId: str
    agentStyle: Literal["reasoning", "flow", "supervisor"]
    instructions: Optional[str] = None


class GenerateRequest(BaseModel):
    sessionId: str = Field(min_length=1)
    credentialId: str = Field(min_length=1)
    selections: List[SelectionItem] = Field(default_factory=list)
    addSupervisor: bool = False


@dataclass
class IntentResult:
    id: str
    name: str
    status: Literal["pending", "processing", "success", "needs_review", "failed"]
    warnings: List[str] = field(default_factory=list)
    unresolved_references: List[str] = field(default_factory=list)
    abl: str = ""
    message: str = ""
    duration_ms: Optional[int] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    node_count: int = 0
    service_node_count: int = 0
    entity_node_count: int = 0
    condition_count: int = 0
    estimated_manual_minutes: int = 0


@dataclass
class JobState:
    id: str
    created_at: float
    session_id: str
    selections: List[SelectionItem]
    credential_id: str
    intent_results: Dict[str, IntentResult]
    done: bool = False
    aborted: bool = False
    total_duration_ms: Optional[int] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    stream_finished: bool = False


session_store: SessionStore | None = None
credential_store: CredentialStore | None = None
jobs: Dict[str, JobState] = {}
jobs_lock = asyncio.Lock()


def init_generate_routes(store: SessionStore, creds: CredentialStore) -> None:
    global session_store, credential_store
    session_store = store
    credential_store = creds


async def _emit(job: JobState, payload: Dict[str, Any]) -> None:
    print(f"[JOB {job.id}] SSE_EMIT {json.dumps(payload, ensure_ascii=False)}", flush=True)
    await job.queue.put(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n")


def _complexity_counts(ir: Dict[str, Any]) -> Dict[str, int]:
    nodes = ir.get("nodes") if isinstance(ir, dict) else []
    if not isinstance(nodes, list):
        nodes = []

    node_count = 0
    service_count = 0
    entity_count = 0
    condition_count = 0

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_count += 1
        component = node.get("component") if isinstance(node.get("component"), dict) else {}
        comp_type = str(component.get("type") or node.get("type") or "").lower()
        if comp_type == "service":
            service_count += 1
        elif comp_type == "entity":
            entity_count += 1

        transitions = node.get("transitions") if isinstance(node.get("transitions"), list) else []
        for transition in transitions:
            if isinstance(transition, dict) and transition.get("kind") == "conditional":
                condition_count += 1

    return {
        "node_count": node_count,
        "service_node_count": service_count,
        "entity_node_count": entity_count,
        "condition_count": condition_count,
    }


def _estimate_manual_minutes(
    counts: Dict[str, int],
    agent_style: str,
    routed_intents: int,
) -> int:
    if agent_style == "supervisor":
        total = settings.manual_estimate_supervisor_base_minutes
        total += settings.manual_estimate_supervisor_per_intent_minutes * max(routed_intents, 1)
        return max(0, int(round(total)))

    node_count = counts.get("node_count", 0)
    service_count = counts.get("service_node_count", 0)
    entity_count = counts.get("entity_node_count", 0)
    condition_count = counts.get("condition_count", 0)
    generic_nodes = max(0, node_count - service_count - entity_count)

    total = settings.manual_estimate_base_minutes
    total += generic_nodes * settings.manual_estimate_per_node_minutes
    total += entity_count * settings.manual_estimate_per_entity_minutes
    total += service_count * settings.manual_estimate_per_service_minutes
    total += condition_count * settings.manual_estimate_per_condition_minutes
    return max(0, int(round(total)))


def _build_final_results(job: JobState) -> List[Dict[str, Any]]:
    return [
        {
            "intentId": item.id,
            "name": item.name,
            "status": item.status,
            "message": item.message,
            "durationMs": item.duration_ms,
        }
        for item in job.intent_results.values()
    ]


def _pick_sample_abl(app_state: Any, style: Literal["reasoning", "flow", "supervisor"]) -> str:
    if style == "reasoning":
        return getattr(app_state, "reasoning_agent_sample", "") or ""
    if style == "supervisor":
        return getattr(app_state, "supervisor_agent_sample", "") or ""
    return getattr(app_state, "flow_agent_sample", "") or ""


def _get_abl_rules(app_state: Any) -> str:
    return getattr(app_state, "abl_rules_doc", "") or ""


def _sanitize_filename(name: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "_" for ch in (name or "intent")).strip("_")
    while "__" in out:
        out = out.replace("__", "_")
    return out or "intent"


def _build_export_name(uploaded_name: str, platform: str) -> str:
    base = (uploaded_name or "export").rsplit(".", 1)[0]
    base = base.strip() or "export"
    detected = platform or "x011"
    return f"{base}_{detected}_to_artemis.zip"


def _normalize_tool_name(name: str) -> str:
    lowered = str(name or "").strip().lower()
    lowered = re.sub(r"[^a-z0-9_]+", "_", lowered)
    lowered = re.sub(r"_+", "_", lowered).strip("_")
    return lowered or "tool"


def _to_pascal_case(value: str) -> str:
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", value or "") if part]
    return "".join(part[:1].upper() + part[1:] for part in parts) or "Agent"


def _intent_agent_name(intent: Dict[str, Any]) -> str:
    base = str(intent.get("fileSafeName") or intent.get("name") or intent.get("id") or "agent")
    name = _to_pascal_case(base)
    if name.lower().endswith("agent"):
        return name
    return f"{name}Agent"


def _build_supervisor_context(
    intents: List[Dict[str, Any]],
    selections: List[SelectionItem],
    supervisor_intent_id: str,
) -> str:
    by_id = {str(intent.get("id")): intent for intent in intents}
    entries: List[Dict[str, str]] = []
    for selection in selections:
        if selection.agentStyle == "supervisor" or selection.intentId == supervisor_intent_id:
            continue
        intent = by_id.get(selection.intentId)
        if not intent:
            continue
        intent_key = str(intent.get("fileSafeName") or _normalize_tool_name(intent.get("name") or intent.get("id")))
        intent_name = str(intent.get("name") or intent.get("id") or intent_key)
        description = (selection.instructions or "").strip() or f"Handle user requests related to {intent_name}."
        entries.append(
            {
                "intent_key": intent_key,
                "intent_name": intent_name,
                "intent_description": description,
                "agent_name": _intent_agent_name(intent),
            }
        )
    return json.dumps(entries, ensure_ascii=False, indent=2)


def _model_for_style(style: Literal["reasoning", "flow", "supervisor"], override_model: Optional[str] = None) -> str:
    if override_model and override_model.strip():
        return override_model.strip()
    default_model = (settings.llm_model_name or settings.abl_model).strip()
    if style in ("reasoning", "supervisor"):
        return (settings.reasoning_model or default_model).strip()
    return (settings.flow_model or default_model).strip()


def _extract_tool_blocks(abl_text: str) -> Dict[str, str]:
    lines = (abl_text or "").splitlines()
    tool_blocks: Dict[str, str] = {}
    tools_header_idx = -1

    for i, line in enumerate(lines):
        if re.match(r"^\s*TOOLS:\s*$", line):
            tools_header_idx = i
            break

    if tools_header_idx < 0:
        return tool_blocks

    current_name: Optional[str] = None
    current_lines: List[str] = []

    for line in lines[tools_header_idx + 1 :]:
        if not line.strip():
            if current_name is not None:
                current_lines.append(line)
            continue

        if re.match(r"^[A-Z][A-Z_]+:\s*$", line):
            break

        if re.match(r"^\S", line):
            break

        header_match = re.match(r"^\s{2}([A-Za-z0-9_][A-Za-z0-9_\-]*)\s*\(.*", line)
        if header_match:
            if current_name and current_lines:
                tool_blocks[current_name] = "\n".join(current_lines).rstrip() + "\n"
            current_name = header_match.group(1)
            current_lines = [line]
            continue

        if current_name is not None:
            current_lines.append(line)

    if current_name and current_lines:
        tool_blocks[current_name] = "\n".join(current_lines).rstrip() + "\n"

    return tool_blocks


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return '""'
    text = str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _append_yaml_lines(out: List[str], key: str, value: Any, indent: int = 4) -> None:
    pad = " " * indent
    if isinstance(value, dict):
        out.append(f"{pad}{key}:")
        for child_key, child_value in value.items():
            _append_yaml_lines(out, str(child_key), child_value, indent + 2)
        return

    if isinstance(value, list):
        out.append(f"{pad}{key}:")
        for item in value:
            if isinstance(item, (dict, list)):
                out.append(f"{pad}  -")
                if isinstance(item, dict):
                    for child_key, child_value in item.items():
                        _append_yaml_lines(out, str(child_key), child_value, indent + 4)
                else:
                    for sub_item in item:
                        out.append(f"{pad}    - {_yaml_scalar(sub_item)}")
            else:
                out.append(f"{pad}  - {_yaml_scalar(item)}")
        return

    out.append(f"{pad}{key}: {_yaml_scalar(value)}")


def _tool_to_abl(tool: Dict[str, Any]) -> str:
    name = _normalize_tool_name(tool.get("name") or "tool")
    description = str(tool.get("description") or "").strip()
    tool_type = str(tool.get("type") or "http").strip() or "http"

    lines: List[str] = [
        "TOOLS:",
        f"  {name}() -> object",
        f"    description: {_yaml_scalar(description)}",
        f"    type: {tool_type}",
    ]

    for field_name in (
        "params",
        "endpoint",
        "method",
        "query_params",
        "body_mode",
        "headers",
        "path_params",
        "body",
        "server",
        "server_tool",
    ):
        if tool.get(field_name) is not None:
            _append_yaml_lines(lines, field_name, tool.get(field_name), indent=4)

    return "\n".join(lines).rstrip() + "\n"


def _normalize_tool_names_in_abl(abl_text: str) -> str:
    tool_blocks = _extract_tool_blocks(abl_text)
    if not tool_blocks:
        return abl_text

    name_map: Dict[str, str] = {}
    for tool_name in tool_blocks.keys():
        normalized = _normalize_tool_name(tool_name)
        if normalized != tool_name:
            name_map[tool_name] = normalized

    if not name_map:
        return abl_text

    output = abl_text
    for old, new in name_map.items():
        output = re.sub(
            rf"(?m)^(\s{{2}}){re.escape(old)}(\s*\()",
            rf"\1{new}\2",
            output,
        )
        output = re.sub(
            rf"(?m)^(\s*CALL:\s*){re.escape(old)}(\s*\()",
            rf"\1{new}\2",
            output,
        )

    return output


def _extract_flow_step_names(abl_text: str) -> List[str]:
    lines = (abl_text or "").splitlines()
    in_steps = False
    step_names: List[str] = []

    for line in lines:
        if re.match(r"^\s*steps:\s*$", line):
            in_steps = True
            continue

        if in_steps:
            if re.match(r"^\s*[A-Za-z_][A-Za-z0-9_\-]*:\s*$", line):
                break
            m = re.match(r"^\s*\-\s*([A-Za-z_][A-Za-z0-9_\-]*)\s*$", line)
            if m:
                step_names.append(m.group(1))

    return step_names


def _ensure_step_reasoning_flags(abl_text: str) -> str:
    step_names = _extract_flow_step_names(abl_text)
    if not step_names:
        return abl_text

    output = abl_text
    for step_name in step_names:
        pattern = re.compile(
            rf"(?ms)^(\s+){re.escape(step_name)}:\s*\n(.*?)(?=^\s+[A-Za-z_][A-Za-z0-9_\-]*:\s*$|\Z)"
        )
        m = pattern.search(output)
        if not m:
            continue

        indent = m.group(1)
        block = m.group(2)
        if re.search(r"(?m)^\s+REASONING:\s*(true|false)\s*$", block):
            continue

        replacement = f"{indent}{step_name}:\n{indent}  REASONING: false\n" + block
        output = output[: m.start()] + replacement + output[m.end() :]

    return output


async def _run_job(job: JobState, app_state: Any) -> None:
    if session_store is None:
        return
    if credential_store is None:
        return

    job_start = time.perf_counter()

    session = await session_store.get(job.session_id)
    if not session:
        for s in job.selections:
            result = job.intent_results.get(s.intentId)
            if result:
                result.status = "failed"
                result.message = "Session expired or not found"
        await _emit(job, {"type": "log", "level": "ERR", "text": "Session expired or missing."})
        await _emit(
            job,
            {
                "type": "done",
                "summary": {
                    "total": len(job.intent_results),
                    "success": 0,
                    "needsReview": 0,
                    "failed": len(job.intent_results),
                    "pending": 0,
                },
            },
        )
        job.total_duration_ms = int((time.perf_counter() - job_start) * 1000)
        job.done = True
        return

    by_dialog_id = {str(d.get("dialog_id")): d for d in session.ir_dialogs}
    by_ref_id = {str(d.get("ref_id")): d for d in session.ir_dialogs if d.get("ref_id")}
    dialog_to_selected: Dict[str, str] = {}
    ref_to_selected: Dict[str, str] = {}
    for selected_id in job.intent_results:
        dialog_to_selected[selected_id] = selected_id
        ref_to_selected[selected_id] = selected_id
    for ir in session.ir_dialogs:
        selected_id = str(ir.get("dialog_id") or ir.get("ref_id") or "")
        if selected_id not in job.intent_results:
            continue
        dialog_id = str(ir.get("dialog_id") or "")
        ref_id = str(ir.get("ref_id") or "")
        if dialog_id:
            dialog_to_selected[dialog_id] = selected_id
        if ref_id:
            ref_to_selected[ref_id] = selected_id

    llm_config: Optional[LLMRuntimeConfig] = None
    resolved = await credential_store.resolve(job.credential_id)
    if not resolved:
        for s in job.selections:
            result = job.intent_results.get(s.intentId)
            if result:
                result.status = "failed"
                result.message = "LLM credential expired or missing"
        await _emit(job, {"type": "log", "level": "ERR", "text": "LLM credential expired or missing."})
        await _emit(
            job,
            {
                "type": "done",
                "summary": {
                    "total": len(job.intent_results),
                    "success": 0,
                    "needsReview": 0,
                    "failed": len(job.intent_results),
                    "pending": 0,
                },
            },
        )
        job.total_duration_ms = int((time.perf_counter() - job_start) * 1000)
        job.done = True
        return

    provider = str(resolved.get("provider") or "").strip()
    api_key = str(resolved.get("api_key") or "").strip()
    model_name = str(resolved.get("model") or "").strip()
    if not provider or not api_key or not model_name:
        for s in job.selections:
            result = job.intent_results.get(s.intentId)
            if result:
                result.status = "failed"
                result.message = "LLM credential missing required fields"
        await _emit(job, {"type": "log", "level": "ERR", "text": "LLM credential missing required fields."})
        await _emit(
            job,
            {
                "type": "done",
                "summary": {
                    "total": len(job.intent_results),
                    "success": 0,
                    "needsReview": 0,
                    "failed": len(job.intent_results),
                    "pending": 0,
                },
            },
        )
        job.total_duration_ms = int((time.perf_counter() - job_start) * 1000)
        job.done = True
        return

    if provider not in ("openai", "azure_openai", "claude"):
        for s in job.selections:
            result = job.intent_results.get(s.intentId)
            if result:
                result.status = "failed"
                result.message = "Unsupported LLM provider"
        await _emit(job, {"type": "log", "level": "ERR", "text": "Unsupported LLM provider."})
        await _emit(
            job,
            {
                "type": "done",
                "summary": {
                    "total": len(job.intent_results),
                    "success": 0,
                    "needsReview": 0,
                    "failed": len(job.intent_results),
                    "pending": 0,
                },
            },
        )
        job.total_duration_ms = int((time.perf_counter() - job_start) * 1000)
        job.done = True
        return

    llm_config = LLMRuntimeConfig(
        provider=provider,
        api_key=api_key,
        model=model_name,
        azure_domain=resolved.get("azure_domain"),
        azure_api_version=resolved.get("azure_api_version"),
        cookie=resolved.get("cookie"),
    )

    await _emit(job, {"type": "log", "level": "INIT", "text": f"Starting generation for {len(job.selections)} intents"})
    print(f"[JOB {job.id}] INIT generation started selections={len(job.selections)}", flush=True)

    for selection in job.selections:
        if job.aborted:
            break

        selected_key = dialog_to_selected.get(selection.intentId) or ref_to_selected.get(selection.intentId) or selection.intentId
        result = job.intent_results[selected_key]
        start = time.perf_counter()
        result.status = "processing"
        result.message = "Generating ABL..."
        await _emit(
            job,
            {
                "type": "log",
                "level": "RUN",
                "text": f"{result.name}: state=processing",
            },
        )
        await _emit(
            job,
            {
                "intentId": result.id,
                "name": result.name,
                "status": result.status,
                "message": result.message,
            },
        )

        ir = by_dialog_id.get(selection.intentId)
        if ir is None:
            ir = by_ref_id.get(selection.intentId)
        if ir is None:
            ir = by_dialog_id.get(result.id) or by_ref_id.get(result.id)
        if ir is None and selection.agentStyle == "supervisor":
            ir = {"dialog_id": selection.intentId, "nodes": []}

        if ir is None:
            result.status = "failed"
            result.message = "Intent flow IR not found in session"
            result.duration_ms = int((time.perf_counter() - start) * 1000)
            await _emit(
                job,
                {
                    "intentId": result.id,
                    "name": result.name,
                    "status": result.status,
                    "message": result.message,
                    "durationMs": result.duration_ms,
                },
            )
            await _emit(
                job,
                {
                    "type": "log",
                    "level": "ERR",
                    "text": f"{result.name}: state=failed reason='Intent flow IR not found in session'",
                },
            )
            continue

        counts = _complexity_counts(ir)
        result.node_count = counts["node_count"]
        result.service_node_count = counts["service_node_count"]
        result.entity_node_count = counts["entity_node_count"]
        result.condition_count = counts["condition_count"]
        result.estimated_manual_minutes = _estimate_manual_minutes(
            counts,
            selection.agentStyle,
            len(job.selections),
        )

        sample_abl = _pick_sample_abl(app_state, selection.agentStyle)
        abl_rules = _get_abl_rules(app_state)
        supervisor_context = None
        if selection.agentStyle == "supervisor":
            supervisor_context = _build_supervisor_context(session.intents, job.selections, selection.intentId)
        prompt = build_generation_prompt(
            ir,
            sample_abl,
            abl_rules,
            selection.agentStyle,
            supervisor_context,
            selection.instructions,
        )
        model = _model_for_style(selection.agentStyle, llm_config.model)

        if not model:
            result.status = "failed"
            result.message = "Model deployment is not configured"
            result.duration_ms = int((time.perf_counter() - start) * 1000)
            await _emit(
                job,
                {
                    "intentId": result.id,
                    "name": result.name,
                    "status": result.status,
                    "message": result.message,
                    "durationMs": result.duration_ms,
                },
            )
            await _emit(
                job,
                {
                    "type": "log",
                    "level": "ERR",
                    "text": f"{result.name}: state=failed reason='Model deployment is not configured'",
                },
            )
            continue

        await _emit(
            job,
            {
                "type": "log",
                "level": "RUN",
                "text": f"{result.name}: using deployment '{model}'",
            },
        )
        print(f"[JOB {job.id}] LLM_REQUEST intent='{result.name}' deployment='{model}' stage='generation'", flush=True)

        try:
            generated, gen_usage = await asyncio.to_thread(
                call_llm,
                model,
                "You are an expert Artemis (Kore.ai) ABL author. Strictly follow the "
                "Artemis ABL platform rules and agent-style guidance provided in the prompt.",
                prompt,
                ABL_JSON_SCHEMA,
                "abl_generation",
                llm_config,
            )
            result.prompt_tokens = gen_usage.prompt_tokens
            result.completion_tokens = gen_usage.completion_tokens
            result.total_tokens = gen_usage.total_tokens

            abl_text = str(generated.get("abl") or "").strip()
            warnings = [str(x) for x in (generated.get("warnings") or []) if str(x).strip()]
            unresolved = [str(x) for x in (generated.get("unresolved_references") or []) if str(x).strip()]

            local_issues = validate_abl_text(abl_text, selection.agentStyle)
            warnings.extend(local_issues)

            verify, verify_usage = await asyncio.to_thread(
                verify_abl, model, sample_abl, ir, abl_text, abl_rules, selection.agentStyle, llm_config
            )
            result.prompt_tokens += verify_usage.prompt_tokens
            result.completion_tokens += verify_usage.completion_tokens
            result.total_tokens += verify_usage.total_tokens
            verify_issues = [str(x) for x in (verify.get("issues") or []) if str(x).strip()]
            corrected_abl = str(verify.get("corrected_abl") or abl_text).strip()
            if selection.agentStyle == "flow":
                corrected_abl = _ensure_step_reasoning_flags(corrected_abl)
            corrected_abl = _normalize_tool_names_in_abl(corrected_abl)
            valid = bool(verify.get("valid"))
            print(
                f"[JOB {job.id}] LLM_RESPONSE intent='{result.name}' valid={valid} warnings={len(warnings)} verifyIssues={len(verify_issues)}",
                flush=True,
            )

            warnings.extend(verify_issues)
            result.abl = corrected_abl
            result.warnings = sorted(set(warnings))
            result.unresolved_references = sorted(set(unresolved))

            if not corrected_abl:
                result.status = "failed"
                result.message = "Empty ABL output"
            elif valid and not result.warnings:
                result.status = "success"
                result.message = "Converted successfully"
            else:
                result.status = "needs_review"
                result.message = "Converted with review notes"

        except Exception as exc:
            result.status = "failed"
            result.message = f"Generation failed: {exc}"
            print(f"[JOB {job.id}] LLM_ERROR intent='{result.name}' error={exc}", flush=True)

        result.duration_ms = int((time.perf_counter() - start) * 1000)
        await _emit(
            job,
            {
                "intentId": result.id,
                "name": result.name,
                "status": result.status,
                "message": result.message,
                "durationMs": result.duration_ms,
            },
        )
        await _emit(
            job,
            {
                "type": "log",
                "level": "INFO",
                "text": f"{result.name}: state={result.status} durationMs={result.duration_ms}",
            },
        )

    if job.aborted:
        await _emit(job, {"type": "log", "level": "WARN", "text": "Generation aborted by user."})
        for item in job.intent_results.values():
            if item.status == "processing":
                item.status = "failed"
                item.message = "Aborted"

    job.total_duration_ms = int((time.perf_counter() - job_start) * 1000)
    summary = _build_summary(job)
    await _emit(
        job,
        {
            "type": "log",
            "level": "INFO",
            "text": (
                "Generation summary "
                f"total={summary['total']} success={summary['success']} "
                f"needsReview={summary['needsReview']} failed={summary['failed']} pending={summary['pending']}"
            ),
        },
    )
    final_results = _build_final_results(job)
    await _emit(job, {"type": "done", "summary": summary, "results": final_results})
    job.done = True


async def _create_job(
    session_id: str,
    selections: List[SelectionItem],
    intents: List[Dict[str, Any]],
    app_state: Any,
    add_supervisor: bool,
    credential_id: str,
) -> str:
    supervisor_count = sum(1 for selection in selections if selection.agentStyle == "supervisor")
    if add_supervisor:
        supervisor_count += 1
    if supervisor_count > 1:
        raise HTTPException(status_code=400, detail="Only one supervisor agent can be selected")

    selected_ids: Set[str] = {s.intentId for s in selections}
    selected_intents = [i for i in intents if str(i.get("id")) in selected_ids]

    if not selected_intents:
        raise HTTPException(status_code=400, detail="No selected intents found for this session")

    job_id = str(uuid.uuid4())
    intent_results: Dict[str, IntentResult] = {
        str(it["id"]): IntentResult(
            id=str(it["id"]),
            name=str(it.get("name") or it["id"]),
            status="pending",
            message="Waiting in queue...",
        )
        for it in selected_intents
    }

    resolved_selections = list(selections)
    if add_supervisor:
        intent_results[SUPERVISOR_INTENT_ID] = IntentResult(
            id=SUPERVISOR_INTENT_ID,
            name="Supervisor Agent",
            status="pending",
            message="Waiting in queue...",
        )
        resolved_selections.append(SelectionItem(intentId=SUPERVISOR_INTENT_ID, agentStyle="supervisor"))

    job = JobState(
        id=job_id,
        created_at=time.time(),
        session_id=session_id,
        selections=resolved_selections,
        credential_id=credential_id,
        intent_results=intent_results,
    )

    async with jobs_lock:
        jobs[job_id] = job

    asyncio.create_task(_run_job(job, app_state))
    return job_id


def _build_summary(job: JobState) -> Dict[str, int]:
    total = len(job.intent_results)
    success = sum(1 for r in job.intent_results.values() if r.status == "success")
    needs_review = sum(1 for r in job.intent_results.values() if r.status == "needs_review")
    failed = sum(1 for r in job.intent_results.values() if r.status == "failed")
    pending = sum(1 for r in job.intent_results.values() if r.status in ("pending", "processing"))
    return {
        "total": total,
        "success": success,
        "needsReview": needs_review,
        "failed": failed,
        "pending": pending,
    }


def _build_metrics(job: JobState) -> Dict[str, Any]:
    total_prompt = sum(r.prompt_tokens for r in job.intent_results.values())
    total_completion = sum(r.completion_tokens for r in job.intent_results.values())
    total_tokens = sum(r.total_tokens for r in job.intent_results.values())
    estimated_manual_minutes = sum(r.estimated_manual_minutes for r in job.intent_results.values())
    total_duration_ms = job.total_duration_ms or 0
    total_duration_minutes = total_duration_ms / 60000 if total_duration_ms > 0 else 0
    time_saved_minutes = max(0, int(round(estimated_manual_minutes - total_duration_minutes)))
    if estimated_manual_minutes > 0 and total_duration_minutes > 0:
        speedup = round(estimated_manual_minutes / max(total_duration_minutes, 1 / 60), 1)
    else:
        speedup = 0

    return {
        "totalDurationMs": total_duration_ms,
        "tokens": {
            "prompt": total_prompt,
            "completion": total_completion,
            "total": total_tokens,
        },
        "estimatedManualMinutes": estimated_manual_minutes,
        "timeSavedMinutes": time_saved_minutes,
        "speedupFactor": speedup,
    }


@router.post("")
async def generate(
    request: Request,
    payload: GenerateRequest,
    user: AuthUser = Depends(require_user),
) -> Dict[str, str]:
    _ = user
    await require_rate_limit(request, "generate")
    if session_store is None:
        raise HTTPException(status_code=500, detail="Session store not initialized")
    if credential_store is None:
        raise HTTPException(status_code=500, detail="Credential store not initialized")

    session = await session_store.get(payload.sessionId)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    if not payload.selections:
        raise HTTPException(status_code=400, detail="No intent selections provided")
    if not payload.credentialId:
        raise HTTPException(status_code=400, detail="LLM credential is required")

    resolved = await credential_store.resolve(payload.credentialId)
    if not resolved:
        raise HTTPException(status_code=400, detail="LLM credential not found or expired")

    app_state = request.app.state

    job_id = await _create_job(
        payload.sessionId,
        payload.selections,
        session.intents,
        app_state,
        payload.addSupervisor,
        payload.credentialId,
    )
    return {"jobId": job_id}


@router.get("/stream/{job_id}")
async def stream_generation(
    request: Request,
    job_id: str,
    token: Optional[str] = None,
) -> StreamingResponse:
    _ = require_user(request, authorization=request.headers.get("Authorization"), token=token)
    async with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_stream() -> AsyncGenerator[bytes, None]:
        print(f"[JOB {job_id}] STREAM_OPEN", flush=True)

        if job.done and job.queue.empty():
            summary = _build_summary(job)
            replay = {"type": "done", "summary": summary, "results": _build_final_results(job)}
            print(f"[JOB {job_id}] STREAM_REPLAY_DONE", flush=True)
            yield f"data: {json.dumps(replay, ensure_ascii=False)}\n\n".encode("utf-8")
            print(f"[JOB {job_id}] STREAM_DONE_AND_EMPTY", flush=True)
            print(f"[JOB {job_id}] STREAM_CLOSE", flush=True)
            return

        try:
            while True:
                if job.done and job.queue.empty():
                    print(f"[JOB {job_id}] STREAM_DONE_AND_EMPTY", flush=True)
                    break

                try:
                    item = await asyncio.wait_for(job.queue.get(), timeout=15)
                    yield item.encode("utf-8")
                except asyncio.TimeoutError:
                    # Keep the SSE connection alive while generation is still running.
                    yield b": keep-alive\n\n"
                    continue
        except asyncio.CancelledError:
            print(f"[JOB {job_id}] STREAM_CANCELLED", flush=True)
            raise
        finally:
            print(f"[JOB {job_id}] STREAM_CLOSE", flush=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/abort/{job_id}")
async def abort_generation(
    request: Request,
    job_id: str,
    user: AuthUser = Depends(require_user),
) -> Dict[str, bool]:
    _ = user
    await require_rate_limit(request, "abort")
    async with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.aborted = True
    return {"ok": True}


@router.get("/report/{job_id}")
async def generation_report(
    request: Request,
    job_id: str,
    token: Optional[str] = None,
) -> JSONResponse:
    _ = require_user(request, authorization=request.headers.get("Authorization"), token=token)
    async with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    intents = [
        {
            "id": item.id,
            "name": item.name,
            "status": item.status,
            "warnings": item.warnings,
            "unresolvedReferences": item.unresolved_references,
            "durationMs": item.duration_ms,
            "tokens": {
                "prompt": item.prompt_tokens,
                "completion": item.completion_tokens,
                "total": item.total_tokens,
            },
            "estimatedManualMinutes": item.estimated_manual_minutes,
        }
        for item in job.intent_results.values()
    ]
    return JSONResponse({"summary": _build_summary(job), "metrics": _build_metrics(job), "intents": intents})


@router.get("/download/{job_id}")
async def generation_download(
    request: Request,
    job_id: str,
    token: Optional[str] = None,
) -> StreamingResponse:
    _ = require_user(request, authorization=request.headers.get("Authorization"), token=token)
    async with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if session_store is None:
        raise HTTPException(status_code=500, detail="Session store not initialized")

    session = await session_store.get(job.session_id)
    tools_by_name: Dict[str, Dict[str, Any]] = {}
    if session:
        for tool in session.tools:
            if not isinstance(tool, dict):
                continue
            name = _normalize_tool_name(tool.get("name") or "")
            if name:
                tool_copy = dict(tool)
                tool_copy["name"] = name
                tools_by_name[name] = tool_copy
    export_name = _build_export_name(session.uploaded_file_name if session else "", session.platform if session else "x011")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        report = {
            "summary": _build_summary(job),
            "metrics": _build_metrics(job),
            "intents": [
                {
                    "id": item.id,
                    "name": item.name,
                    "status": item.status,
                    "warnings": item.warnings,
                    "unresolvedReferences": item.unresolved_references,
                    "durationMs": item.duration_ms,
                    "tokens": {
                        "prompt": item.prompt_tokens,
                        "completion": item.completion_tokens,
                        "total": item.total_tokens,
                    },
                    "estimatedManualMinutes": item.estimated_manual_minutes,
                }
                for item in job.intent_results.values()
            ],
        }
        zf.writestr("report.json", json.dumps(report, ensure_ascii=False, indent=2))

        combined_tool_blocks: Dict[str, str] = {}

        for item in job.intent_results.values():
            if not item.abl:
                continue
            safe = _sanitize_filename(item.name)
            zf.writestr(f"agents/{safe}.abl", item.abl)

            for tool_name, tool_block in _extract_tool_blocks(item.abl).items():
                combined_tool_blocks[tool_name] = tool_block

        for tool_name, tool_block in combined_tool_blocks.items():
            normalized_name = _normalize_tool_name(tool_name)
            tool_meta = tools_by_name.get(normalized_name)
            if tool_meta:
                zf.writestr(f"tools/{normalized_name}.tools.abl", _tool_to_abl(tool_meta))
            else:
                if normalized_name != tool_name:
                    tool_block = re.sub(
                        rf"(?m)^(\s{{2}}){re.escape(tool_name)}(\s*\()",
                        rf"\1{normalized_name}\2",
                        tool_block,
                    )
                zf.writestr(f"tools/{normalized_name}.tools.abl", f"TOOLS:\n{tool_block}")

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{export_name}"'},
    )
