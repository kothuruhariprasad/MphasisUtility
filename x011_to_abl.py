#!/usr/bin/env python3
"""
Kore.ai X011 app-definition -> Artemis ABL converter.

Pipeline:
1. Load X011 appDefinition.json.
2. Deterministically preprocess into a compact flow IR:
   - keep reachable dialog flow only
   - preserve transitions/conditions
   - map entity/message/service semantics
   - omit script bodies
   - collapse script-only hops through their default transition
   - omit UI/layout/runtime metadata
3. Ask an LLM to convert the IR + sample ABL into ABL.
4. Optionally run a verification pass against the same IR.
5. Write the final ABL and the IR/debug artifacts.

Usage:
  pip install -r requirements.txt
  export OPENAI_API_KEY="..."
  python x011_to_abl.py appDefinition.json sample_abl.yaml -o output.abl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse

try:
    import requests
except ImportError:
    requests = None
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCRIPT_TYPES = {"script"}

# X011 exports can use different spellings depending on node/component version.
SERVICE_TYPES = {
    "service", "webhook", "api", "servicecall", "service_call",
    "integration", "http", "httpservice", "apicall"
}


def decode_x011(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    current = value
    for _ in range(3):
        decoded = urllib.parse.unquote(current)
        if decoded == current:
            break
        current = decoded
    return current


def content_refs(text: str) -> List[str]:
    return sorted(set(re.findall(r"\bcontent\.([A-Za-z0-9_]+)", text or "")))


def clean_message_expression(value: Any) -> Dict[str, Any]:
    """
    Never executes X011 scripts.
    It only unwraps common print()/wrapper syntax and extracts content refs.
    """
    raw = decode_x011(value if value is not None else "").strip()

    # Common X011 wrappers.
    cleaned = raw
    cleaned = re.sub(
        r"^\s*print\((.*)\)\s*;\s*$", r"\1", cleaned, flags=re.S
    )
    cleaned = re.sub(
        r"replaceNewLines\((content\.[A-Za-z0-9_]+)\)", r"\1", cleaned
    )
    cleaned = re.sub(
        r"getMessageFeedbackTemplate\((.*?)\)", r"\1", cleaned, flags=re.S
    )
    cleaned = cleaned.strip().rstrip(";").strip()

    refs = content_refs(cleaned)

    # Literal quoted message.
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in ("'", '"'):
        return {
            "kind": "literal",
            "text": cleaned[1:-1],
            "content_refs": refs,
            "raw": raw,
        }

    # If there is executable code, keep only the fact that it is dynamic.
    code_markers = (
        "try {", "if (", "const ", "let ", "var ", "koreDebugger",
        "context.", "env.", "JSON.", "function ", "return "
    )
    if any(marker in cleaned for marker in code_markers):
        return {
            "kind": "dynamic_expression",
            "text": None,
            "content_refs": refs,
            "raw": raw,
        }

    return {
        "kind": "reference_or_expression",
        "text": cleaned or None,
        "content_refs": refs,
        "raw": raw,
    }


def condition_ir(condition: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if condition is None:
        return None

    if "conjoin" in condition and "tests" in condition:
        items = [condition_ir(x) for x in condition.get("tests", [])]
        key = "all" if condition.get("conjoin") == "and" else "any"
        return {key: items}

    if "field" in condition or "context" in condition:
        return {
            "left": condition.get("field", condition.get("context")),
            "op": condition.get("op"),
            "right": condition.get("value"),
        }

    return {"raw": condition}


def get_en(component: Dict[str, Any]) -> Dict[str, Any]:
    locale = component.get("localeData") or {}
    en = locale.get("en") if isinstance(locale, dict) else {}
    return en if isinstance(en, dict) else {}


def is_service_component(component: Dict[str, Any], node_type: str) -> bool:
    t = (node_type or "").lower()
    ctype = str(component.get("type") or "").lower()
    service_node_type = str(component.get("serviceNodeType") or "").lower()
    return t in SERVICE_TYPES or ctype in SERVICE_TYPES or service_node_type in SERVICE_TYPES


def component_ir(component: Dict[str, Any], node_type: str) -> Dict[str, Any]:
    en = get_en(component)
    ctype = str(component.get("type") or node_type or "").lower()

    # Service-like nodes are normalized to TOOL candidates.
    if is_service_component(component, node_type):
        result = {
            "name": component.get("name"),
            "type": "service",
            "label": en.get("label"),
        }
        candidate_keys = [
            "serviceNodeType", "serviceType", "method", "url", "path",
            "request", "response", "headers", "params", "body",
            "auth", "connection", "service"
        ]
        for key in candidate_keys:
            if component.get(key) is not None:
                result[key] = component[key]
        return result

    if ctype == "entity":
        prompts = []
        for msg in component.get("message") or []:
            msg_en = ((msg.get("localeData") or {}).get("en") or {})
            prompts.append({
                "channel": msg.get("channel"),
                **clean_message_expression(msg_en.get("text"))
            })
        return {
            "name": component.get("name"),
            "type": "entity",
            "label": en.get("label"),
            "entity_type": component.get("entityType"),
            "allowed_values": en.get("allowedValues"),
            "is_array": component.get("isArray"),
            "prompt_messages": prompts,
        }

    if ctype == "message":
        messages = []
        for msg in component.get("message") or []:
            msg_en = ((msg.get("localeData") or {}).get("en") or {})
            messages.append({
                "channel": msg.get("channel"),
                **clean_message_expression(msg_en.get("text"))
            })

        errors = []
        for msg in component.get("errorMessage") or []:
            msg_en = ((msg.get("localeData") or {}).get("en") or {})
            errors.append({
                "channel": msg.get("channel"),
                **clean_message_expression(msg_en.get("text"))
            })

        return {
            "name": component.get("name"),
            "type": "message",
            "label": en.get("label"),
            "messages": messages,
            "error_messages": errors,
        }

    if ctype == "intent":
        return {
            "name": component.get("name"),
            "type": "intent",
            "intent": en.get("intent"),
            "description": en.get("desc"),
        }

    if ctype == "logic":
        # Important: keep the node because its transitions/conditions are flow.
        # Ignore its implementation/script body.
        return {
            "name": component.get("name"),
            "type": "logic",
            "label": en.get("label"),
        }

    if ctype == "aiassist":
        return {
            "name": component.get("name"),
            "type": "aiassist",
            "label": en.get("label"),
        }

    return {
        "name": component.get("name"),
        "type": node_type or component.get("type"),
        "label": en.get("label"),
    }


def normalize_node(node: Dict[str, Any], component: Dict[str, Any]) -> Dict[str, Any]:
    transitions = []
    for t in node.get("transitions") or []:
        target = t.get("then") or t.get("default")
        if target is None:
            continue
        transitions.append({
            "kind": "conditional" if t.get("if") else "default",
            "condition": condition_ir(t.get("if")),
            "next": target,
        })

    return {
        "node_id": node.get("nodeId"),
        "type": node.get("type"),
        "component_name": component.get("name"),
        "component": component_ir(component, str(node.get("type") or "")),
        "preconditions": [
            condition_ir(x) for x in (node.get("preConditions") or [])
        ],
        "transitions": transitions,
    }


def follow_script_chain(
    start: Optional[str],
    nodes: Dict[str, Dict[str, Any]]
) -> Tuple[Optional[str], List[str]]:
    """
    Collapse only script nodes with exactly one default outgoing edge.
    This keeps flow while intentionally discarding script implementation logic.
    """
    current = start
    collapsed = []
    visited = set()

    while current in nodes and nodes[current]["type"] in SCRIPT_TYPES:
        if current in visited:
            break
        visited.add(current)
        collapsed.append(current)

        outgoing = nodes[current]["transitions"]
        defaults = [x for x in outgoing if x["kind"] == "default"]

        if len(outgoing) != 1 or len(defaults) != 1:
            # Cannot safely collapse a branching script node.
            break

        current = defaults[0]["next"]

    return current, collapsed


def preprocess(app: Dict[str, Any]) -> Dict[str, Any]:
    components = {
        c.get("_id"): c for c in (app.get("dialogComponents") or [])
        if c.get("_id")
    }

    output = {
        "source": "Kore.ai X011 app definition",
        "conversion_scope": [
            "conversation flow from entry to end",
            "conditions and transition branches",
            "message prompts when actually present",
            "entity/user-input collection",
            "service/API calls"
        ],
        "ignored_scope": [
            "script implementation/body",
            "UI positions and colors",
            "runtime metadata",
            "generative-AI provider metadata unless needed for flow semantics"
        ],
        "dialogs": []
    }

    for dialog in app.get("dialogs") or []:
        raw_nodes = {
            n.get("nodeId"): n for n in (dialog.get("nodes") or [])
            if n.get("nodeId")
        }

        normalized = {}
        for node_id, node in raw_nodes.items():
            comp = components.get(node.get("componentId"), {})
            normalized[node_id] = normalize_node(node, comp)

        ignored_scripts = []
        for node_id, n in normalized.items():
            if n["type"] in SCRIPT_TYPES:
                ignored_scripts.append({
                    "node_id": node_id,
                    "component_name": n["component_name"]
                })

        # Rewire all outgoing edges through collapsible script-only hops.
        for n in normalized.values():
            rewired = []
            for tr in n["transitions"]:
                target, collapsed = follow_script_chain(tr["next"], normalized)
                if collapsed:
                    tr = dict(tr)
                    tr["next"] = target
                    tr["collapsed_script_nodes"] = collapsed
                rewired.append(tr)
            n["transitions"] = rewired

        # Primary entry node(s).
        entry_nodes = [
            s.get("nodeId")
            for s in (dialog.get("sequences") or [])
            if s.get("primaryIntent") and s.get("nodeId")
        ]

        # Some exports may not mark the primary sequence. Fall back to
        # nodes not referenced as a transition target.
        if not entry_nodes:
            referenced = {
                tr["next"]
                for n in normalized.values()
                for tr in n["transitions"]
                if tr.get("next")
            }
            entry_nodes = [
                node_id for node_id in normalized
                if node_id not in referenced
            ]

        # Reachability gives a much smaller and safer LLM payload.
        reachable = set()
        stack = list(entry_nodes)
        while stack:
            node_id = stack.pop()
            if not node_id or node_id == "end" or node_id in reachable:
                continue
            if node_id not in normalized:
                continue
            reachable.add(node_id)
            for tr in normalized[node_id]["transitions"]:
                nxt = tr.get("next")
                if nxt and nxt != "end":
                    stack.append(nxt)

        functional_nodes = []
        for node_id in reachable:
            node = dict(normalized[node_id])
            if node["type"] in SCRIPT_TYPES:
                # Script nodes should normally be unreachable after rewiring,
                # but keep the fallback behavior explicit.
                continue
            functional_nodes.append(node)

        # Stable ordering follows source node order.
        source_order = {node_id: i for i, node_id in enumerate(raw_nodes)}
        functional_nodes.sort(key=lambda x: source_order.get(x["node_id"], 10**9))

        output["dialogs"].append({
            "dialog_id": dialog.get("_id"),
            "ref_id": dialog.get("refId"),
            "entry_nodes": entry_nodes,
            "reachable_node_count": len(functional_nodes),
            "ignored_script_nodes": ignored_scripts,
            "nodes": functional_nodes,
        })

    return output


ABL_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "abl": {"type": "string"},
        "warnings": {
            "type": "array",
            "items": {"type": "string"}
        },
        "unresolved_references": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": ["abl", "warnings", "unresolved_references"]
}


def build_generation_prompt(ir: Dict[str, Any], sample_abl: str) -> str:
    return f"""
You are converting a Kore.ai X011 dialog flow into Artemis ABL.

The target syntax is represented by the sample ABL below. Preserve its
organization and style. Do NOT invent a different DSL.

CONVERSION RULES
1. Convert the FLOW, not the X011 implementation code.
2. Ignore all script-node bodies and script business logic.
3. Entity node = user input collection. Prefer GATHER.
4. Message node = display output. Prefer RESPOND.
5. Service/API node = external call. Prefer CALL and put the service in TOOLS.
6. Preserve every meaningful transition condition and branch.
7. Preserve successful and failure paths when they exist in the source.
8. Intent nodes represent routing/task boundaries. Preserve them as flow steps
   or routing semantics only when needed to retain the source flow.
9. Logic nodes are useful only for their transition conditions. Do not recreate
   their internal implementation.
10. Never hallucinate a prompt or API detail that is not in the supplied IR.
11. When the source contains a content.X reference but not the underlying
    content text, keep the reference explicitly and report it in
    unresolved_references.
12. Do not output Markdown fences around the ABL.
13. Use COMPLETE to terminate branches that reach the X011 'end' node.
14. Keep node/step names readable and deterministic.
15. Prefer explicit ON_SUCCESS / ON_FAIL branches for service calls when
    the X011 source contains distinct success/failure paths.
16. The resulting ABL must describe behavior from start to end, with no
    disconnected source nodes.

SAMPLE ABL
----------------
{sample_abl}
----------------

NORMALIZED X011 FLOW IR
----------------
{json.dumps(ir, ensure_ascii=False, indent=2)}
----------------
""".strip()


VERIFY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "valid": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "corrected_abl": {"type": "string"}
    },
    "required": ["valid", "issues", "corrected_abl"]
}


def get_llm_config() -> Dict[str, str]:
    """Read the custom Azure OpenAI-compatible endpoint configuration."""
    domain = "mphasisailab"
    api_key = ""
    cookie = "nspatoken="

    missing = []
    if not domain:
        missing.append("AZURE_OPENAI_DOMAIN")
    if not api_key:
        missing.append("LLM_KEY")
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): " + ", ".join(missing)
        )

    model = os.getenv("ABL_MODEL", "gpt-5.6-luna-2")
    base_url = (
        f"https://{domain}.openai.azure.com"
        f"/openai/deployments/{model}/chat/completions"
        f"?api-version={os.getenv('AZURE_OPENAI_API_VERSION', '2024-10-21')}"
    )
    return {
        "url": base_url,
        "api_key": api_key,
        "cookie": cookie,
        "model": model,
    }


def _extract_json_object(text: str) -> Dict[str, Any]:
    """Parse JSON even if the custom model adds Markdown fences or whitespace."""
    if not text or not text.strip():
        raise ValueError("LLM returned an empty response")

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("LLM response did not contain a valid JSON object")
        parsed = json.loads(cleaned[start:end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON must be an object")
    return parsed


def call_llm(
    model: str,
    system_text: str,
    user_text: str,
    schema: Dict[str, Any],
    schema_name: str
) -> Dict[str, Any]:
    """
    Call the user's custom Azure OpenAI-compatible chat/completions endpoint.

    The supplied custom endpoint/body does not use the Responses API or the
    structured-output `response_format` field, so the schema is converted into
    explicit instructions in the system prompt and the response is parsed as JSON.
    The rest of the converter behavior is unchanged.
    """
    if requests is None:
        raise RuntimeError(
            "Missing dependency: requests. Run `pip install -r requirements.txt`."
        )

    config = get_llm_config()

    schema_instruction = (
        "Return ONLY a valid JSON object. Do not use Markdown fences. "
        "The JSON object must conform to this schema:\n"
        + json.dumps(schema, ensure_ascii=False)
        + "\nSchema name: " + schema_name
    )

    headers = {
        "Content-Type": "application/json",
        "api-key": config["api_key"],
    }
    if config["cookie"]:
        headers["Cookie"] = config["cookie"]

    payload = {
        "model": config["model"],
        "top_p": 1,
        "frequency_penalty": 0,
        "presence_penalty": 0,
        "messages": [
            {
                "role": "system",
                "content": system_text + "\n\n" + schema_instruction,
            },
            {
                "role": "user",
                "content": user_text,
            },
        ],
    }

    timeout = int(os.getenv("LLM_TIMEOUT_SECONDS", "180"))
    response = requests.post(
        config["url"],
        headers=headers,
        json=payload,
        timeout=timeout,
    )

    if not response.ok:
        body_preview = response.text[:2000]
        raise RuntimeError(
            f"LLM API request failed with HTTP {response.status_code}: {body_preview}"
        )

    try:
        response_json = response.json()
    except ValueError as exc:
        raise RuntimeError("LLM API returned a non-JSON HTTP response") from exc

    try:
        content = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            "Unexpected LLM API response shape; expected choices[0].message.content"
        ) from exc

    # Some compatible endpoints may return content as an array of parts.
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )

    result = _extract_json_object(str(content))

    # Basic schema contract validation. The original code relied on strict
    # structured output; this restores the same safety check client-side.
    required = schema.get("required", [])
    missing = [key for key in required if key not in result]
    if missing:
        raise RuntimeError(
            "LLM JSON response is missing required field(s): " + ", ".join(missing)
        )

    return result


def verify_abl(
    model: str,
    sample_abl: str,
    ir: Dict[str, Any],
    abl: str
) -> Dict[str, Any]:
    system = """
You are a strict ABL conversion verifier.
Compare the generated ABL against the normalized X011 flow IR.

Check only:
- all reachable flow branches are represented
- entity nodes are represented as user-input collection
- message nodes are represented as responses
- service nodes are represented as tool/API calls
- transition conditions are retained
- end branches terminate correctly
- no script implementation logic has been invented
- no missing source detail has been hallucinated
- output remains in the sample ABL style

If issues exist, correct the ABL. Do not redesign the flow.
""".strip()

    user = f"""
SAMPLE ABL:
{sample_abl}

NORMALIZED X011 IR:
{json.dumps(ir, ensure_ascii=False, indent=2)}

GENERATED ABL:
{abl}
""".strip()

    return call_llm(model, system, user, VERIFY_SCHEMA, "abl_verification")


def validate_abl_text(abl: str) -> List[str]:
    issues = []
    if "AGENT:" not in abl:
        issues.append("Missing AGENT section.")
    if "GOAL:" not in abl:
        issues.append("Missing GOAL section.")
    if "FLOW:" not in abl:
        issues.append("Missing FLOW section.")
    if "BEHAVIOR:" not in abl:
        issues.append("Missing BEHAVIOR section.")
    if "```" in abl:
        issues.append("ABL contains Markdown code fences.")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("app_definition", type=Path)
    parser.add_argument("sample_abl", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("output.abl"))
    parser.add_argument(
        "--model",
        default=os.getenv("ABL_MODEL", "gpt-5.6-luna-2"),
        help="OpenAI model used for conversion"
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip the LLM verification/correction pass"
    )
    parser.add_argument(
        "--preprocess-only",
        action="store_true",
        help="Only create the normalized IR; do not call the LLM"
    )
    args = parser.parse_args()

    try:
        app = json.loads(args.app_definition.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Failed to read app definition: {exc}", file=sys.stderr)
        return 2

    sample = args.sample_abl.read_text(encoding="utf-8")
    ir = preprocess(app)

    ir_path = args.output.with_suffix(".preprocessed.json")
    ir_path.write_text(
        json.dumps(ir, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    if args.preprocess_only:
        print(f"Preprocessed IR: {ir_path}")
        return 0

    system = """
You are an expert in Kore.ai dialog-flow migration and Artemis ABL.
Produce high-fidelity ABL using only the provided normalized source IR.
Do not invent hidden business rules, script behavior, prompts, API contracts,
or branches. Preserve the source flow and conditions.
""".strip()

    user = build_generation_prompt(ir, sample)
    result = call_llm(
        args.model,
        system,
        user,
        ABL_JSON_SCHEMA,
        "abl_generation"
    )

    abl = result["abl"].strip()
    warnings = result.get("warnings", [])
    unresolved = result.get("unresolved_references", [])

    if not args.no_verify:
        verified = verify_abl(args.model, sample, ir, abl)
        if verified.get("corrected_abl"):
            abl = verified["corrected_abl"].strip()
        warnings.extend(verified.get("issues", []))

    local_issues = validate_abl_text(abl)
    warnings.extend(local_issues)

    # Make unresolved source references visible without changing the ABL.
    report_path = args.output.with_suffix(".report.json")
    report = {
        "warnings": warnings,
        "unresolved_references": unresolved,
        "preprocessed_ir": str(ir_path),
        "model": args.model,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    args.output.write_text(abl + "\n", encoding="utf-8")

    print(f"ABL: {args.output}")
    print(f"IR : {ir_path}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
