from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, List


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
    raw = decode_x011(value if value is not None else "").strip()

    cleaned = raw
    cleaned = re.sub(r"^\s*print\((.*)\)\s*;\s*$", r"\1", cleaned, flags=re.S)
    cleaned = re.sub(r"replaceNewLines\((content\.[A-Za-z0-9_]+)\)", r"\1", cleaned)
    cleaned = re.sub(r"getMessageFeedbackTemplate\((.*?)\)", r"\1", cleaned, flags=re.S)
    cleaned = cleaned.strip().rstrip(";").strip()

    refs = content_refs(cleaned)

    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in ("'", '"'):
        return {
            "kind": "literal",
            "text": cleaned[1:-1],
            "content_refs": refs,
            "raw": raw,
        }

    code_markers = (
        "try {",
        "if (",
        "const ",
        "let ",
        "var ",
        "koreDebugger",
        "context.",
        "env.",
        "JSON.",
        "function ",
        "return ",
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
