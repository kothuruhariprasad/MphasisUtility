from __future__ import annotations

import re
from typing import Dict, List


def _extract_flow_step_names(abl: str) -> List[str]:
    lines = (abl or "").splitlines()
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


def _step_has_reasoning(abl: str, step_name: str) -> bool:
    pattern = re.compile(
        rf"(?ms)^(\s+){re.escape(step_name)}:\s*\n(.*?)(?=^\s+[A-Za-z_][A-Za-z0-9_\-]*:\s*$|\Z)"
    )
    m = pattern.search(abl)
    if not m:
        return False
    indent = m.group(1)
    block = m.group(2)
    return bool(re.search(rf"(?m)^{re.escape(indent)}\s{{2}}REASONING:\s*(true|false)\s*$", block))


def validate_abl_text(abl: str, agent_style: str = "flow") -> List[str]:
    """Lightweight structural checks aligned with ABL_rules.md.

    Full grammar validation happens via the LLM verification pass; this is
    a cheap sanity net for the handful of hard, unambiguous requirements.
    """
    issues: List[str] = []

    if "AGENT:" not in abl:
        issues.append("Missing AGENT section.")
    if "GOAL:" not in abl:
        issues.append("Missing GOAL section.")

    has_flow = bool(re.search(r"(?m)^\s*FLOW:\s*$", abl))
    if agent_style == "flow" and not has_flow:
        issues.append("Missing FLOW section (required for a flow agent).")
    if agent_style in ("reasoning", "supervisor") and has_flow:
        issues.append("FLOW section present but this agent style must not declare FLOW.")

    if agent_style == "supervisor":
        if "INTENTS:" not in abl:
            issues.append("Missing INTENTS section (required for a supervisor agent).")
        if "HANDOFF:" not in abl:
            issues.append("Missing HANDOFF section (required for a supervisor agent).")

    if agent_style == "flow" and has_flow:
        for step_name in _extract_flow_step_names(abl):
            if not _step_has_reasoning(abl, step_name):
                issues.append(f"Step '{step_name}' must declare REASONING: true or REASONING: false.")

    if "```" in abl:
        issues.append("ABL contains Markdown code fences.")

    return issues
