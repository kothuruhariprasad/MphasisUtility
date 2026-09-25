from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests

from src.config import settings
from src.pipeline.prompt import VERIFY_SCHEMA


@dataclass
class LLMRuntimeConfig:
    provider: str
    api_key: str
    model: str
    azure_domain: Optional[str] = None
    azure_api_version: Optional[str] = None
    cookie: Optional[str] = None


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


def _parse_usage(usage: Any) -> TokenUsage:
    if not isinstance(usage, dict):
        return TokenUsage()
    return TokenUsage(
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        total_tokens=int(usage.get("total_tokens") or 0),
    )


def _extract_json_object(text: str) -> Dict[str, Any]:
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
        parsed = json.loads(cleaned[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON must be an object")
    return parsed


def _azure_endpoint_url(domain: str, model: str, api_version: str) -> str:
    return f"https://{domain}.openai.azure.com/openai/deployments/{model}/chat/completions?api-version={api_version}"


def _resolve_default_config(model: str) -> LLMRuntimeConfig:
    if not settings.llm_api_key:
        raise RuntimeError("LLM API key is not configured")
    if not settings.azure_openai_domain or not settings.azure_openai_api_version:
        raise RuntimeError("Azure OpenAI configuration is incomplete")
    return LLMRuntimeConfig(
        provider="azure_openai",
        api_key=settings.llm_api_key,
        model=model,
        azure_domain=settings.azure_openai_domain,
        azure_api_version=settings.azure_openai_api_version,
        cookie=settings.llm_cookie,
    )


def call_llm(
    model: str,
    system_text: str,
    user_text: str,
    schema: Dict[str, Any],
    schema_name: str,
    llm_config: Optional[LLMRuntimeConfig] = None,
) -> Tuple[Dict[str, Any], TokenUsage]:
    schema_instruction = (
        "Return ONLY a valid JSON object. Do not use Markdown fences. "
        "The JSON object must conform to this schema:\n"
        + json.dumps(schema, ensure_ascii=False)
        + "\nSchema name: "
        + schema_name
    )

    resolved = llm_config or _resolve_default_config(model)
    payload = {
        "model": resolved.model,
        "top_p": 1,
        "frequency_penalty": 0,
        "presence_penalty": 0,
        "messages": [
            {"role": "system", "content": system_text + "\n\n" + schema_instruction},
            {"role": "user", "content": user_text},
        ],
    }

    headers: Dict[str, str] = {"Content-Type": "application/json"}
    url = ""

    if resolved.provider == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        headers["Authorization"] = f"Bearer {resolved.api_key}"
    elif resolved.provider == "claude":
        url = "https://api.anthropic.com/v1/messages"
        headers["x-api-key"] = resolved.api_key
        headers["anthropic-version"] = "2023-06-01"
        payload = {
            "model": resolved.model,
            "max_tokens": 2048,
            "temperature": 0,
            "system": system_text + "\n\n" + schema_instruction,
            "messages": [{"role": "user", "content": [{"type": "text", "text": user_text}]}],
        }
    else:
        if not resolved.azure_domain or not resolved.azure_api_version:
            raise RuntimeError("Azure OpenAI configuration is incomplete")
        url = _azure_endpoint_url(resolved.azure_domain, resolved.model, resolved.azure_api_version)
        headers["api-key"] = resolved.api_key
        if resolved.cookie:
            headers["Cookie"] = resolved.cookie

    print(
        f"[LLM] REQUEST provider='{resolved.provider}' deployment='{resolved.model}' schema='{schema_name}' userChars={len(user_text)}",
        flush=True,
    )

    response = requests.post(url, headers=headers, json=payload, timeout=settings.llm_timeout_seconds)

    if not response.ok:
        body_preview = response.text[:2000]
        print(
            f"[LLM] RESPONSE_ERROR provider='{resolved.provider}' deployment='{resolved.model}' http={response.status_code}",
            flush=True,
        )
        raise RuntimeError(f"LLM API request failed with HTTP {response.status_code}: {body_preview}")

    try:
        response_json = response.json()
    except ValueError as exc:
        raise RuntimeError("LLM API returned a non-JSON HTTP response") from exc

    content = ""
    usage = TokenUsage()

    if resolved.provider == "claude":
        try:
            content_blocks = response_json.get("content") or []
            content = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content_blocks
            )
        except (AttributeError, TypeError) as exc:
            raise RuntimeError("Unexpected Claude response shape; expected content[]") from exc
        usage = TokenUsage(
            prompt_tokens=int(response_json.get("usage", {}).get("input_tokens") or 0),
            completion_tokens=int(response_json.get("usage", {}).get("output_tokens") or 0),
        )
        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
    else:
        try:
            content = response_json["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Unexpected LLM API response shape; expected choices[0].message.content") from exc

        if isinstance(content, list):
            content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
        usage = _parse_usage(response_json.get("usage"))

    result = _extract_json_object(str(content))
    print(
        f"[LLM] RESPONSE_OK provider='{resolved.provider}' deployment='{resolved.model}' schema='{schema_name}' keys={list(result.keys())}",
        flush=True,
    )

    required = schema.get("required", [])
    missing = [key for key in required if key not in result]
    if missing:
        raise RuntimeError("LLM JSON response is missing required field(s): " + ", ".join(missing))

    return result, usage


def verify_abl(
    model: str,
    sample_abl: str,
    ir: Dict[str, Any],
    abl: str,
    abl_rules: str = "",
    agent_style: str = "flow",
    llm_config: Optional[LLMRuntimeConfig] = None,
) -> Tuple[Dict[str, Any], TokenUsage]:
    if agent_style == "reasoning":
        style_rule = (
            "This must be a REASONING agent: it must NOT contain a top-level "
            "`FLOW:` section; behavior must be expressed via GOAL, GATHER, "
            "TOOLS, CONSTRAINTS, and COMPLETE instead."
        )
    elif agent_style == "supervisor":
        style_rule = (
            "This must be a SUPERVISOR agent: it must NOT contain a top-level "
            "`FLOW:` section and must include top-level `INTENTS:` and "
            "`HANDOFF:` sections that route by intent.category."
        )
    else:
        style_rule = (
            "This must be a FLOW agent: it must contain a top-level `FLOW:` "
            "section with an ordered `steps:` list and explicit ON_SUCCESS/"
            "ON_FAIL/THEN transitions between named steps."
        )

    system = f"""
You are a strict Artemis (Kore.ai) ABL conversion verifier.
Compare the generated ABL against the normalized X011 flow IR and against
the authoritative Artemis ABL platform rules below.

ARTEMIS ABL PLATFORM RULES (authoritative reference)
================================================================
{abl_rules}
================================================================

AGENT STYLE REQUIREMENT
{style_rule}

Check:
- the ABL uses only sections/keys/syntax defined in the platform rules above
- the agent style requirement above is satisfied
- all reachable flow branches are represented
- entity nodes are represented as user-input collection
- message nodes are represented as responses
- service nodes are represented as tool/API calls
- transition conditions are retained
- end branches terminate correctly (COMPLETE with deterministic WHEN, not
  plain English)
- no script implementation logic has been invented
- no missing source detail has been hallucinated
- output remains in the sample ABL style
- output contains no Markdown code fences
- `HOOKS:` and `ON_START:` are only present when required by the IR
- any `SET:` block includes at least one assignment (`name = expression` or
    `name: expression`), otherwise `SET:` is omitted

If issues exist, correct the ABL so it complies with the platform rules
above. Do not redesign the flow.
""".strip()

    user = f"""
SAMPLE ABL:
{sample_abl}

NORMALIZED X011 IR:
{json.dumps(ir, ensure_ascii=False, indent=2)}

GENERATED ABL:
{abl}
""".strip()

    return call_llm(model, system, user, VERIFY_SCHEMA, "abl_verification", llm_config=llm_config)
