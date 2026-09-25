from __future__ import annotations

import json
from typing import Any, Dict

ABL_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "abl": {"type": "string"},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "unresolved_references": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["abl", "warnings", "unresolved_references"],
}

VERIFY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "valid": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "corrected_abl": {"type": "string"},
    },
    "required": ["valid", "issues", "corrected_abl"],
}


_STYLE_GUIDANCE = {
    "reasoning": """
AGENT STYLE: REASONING AGENT
- Do NOT include a `FLOW:` section. A reasoning agent has no FLOW — the
  Agentic Brain autonomously decides which TOOLS to call and when to
  GATHER/RESPOND/COMPLETE in order to satisfy GOAL.
- Model the X011 flow's entities as top-level `GATHER:` fields (with
  `prompt`, `type`, `required`, `validate`/`validation_process` when a
  regex/validation exists in the source) instead of scripted step-by-step
  GATHER blocks.
- Model service/API nodes as `TOOLS:` entries with a clear `description:`
  (the LLM selects tools autonomously based on this text) plus `type: http`
  and any other binding details available from the IR.
- Encode the important business rules / hard constraints (e.g. required
  order of operations, values that must be present before calling a tool)
  as `CONSTRAINTS:` using REQUIRE / RESTRICT / IMPLIES, not as scripted flow.
- Use `INSTRUCTIONS:`/`LIMITATIONS:`/`PERSONA:` to capture guidance that in
  the X011 source was enforced procedurally (ordering, do-not-invent rules,
  what the agent must/must not do).
- Use `COMPLETE:` with a deterministic `WHEN:` (never plain English) to
  describe how the conversation ends, mirroring the X011 'end' node(s).
- Only add `GUARDRAILS:` if the sample ABL below does, matching its shape.
""".strip(),
    "flow": """
AGENT STYLE: FLOW AGENT
- Include a top-level `FLOW:` section with an ordered `steps:` list and one
  block per step, mirroring the sample ABL structure below.
- Every step declared in `FLOW: steps:` MUST include an explicit
  `REASONING: true` or `REASONING: false` field in that step block. This is
  a strict platform requirement; do not omit it.
- Entity node = user input collection -> `GATHER:` inside the owning step
  (use `validation`/`validation_process: REGEX` and `retry_prompt` when the
  source enforces a pattern).
- Message node = display output -> `RESPOND:`.
- Service/API node = external call -> `CALL: tool_name(args) AS: output`,
  with the service declared in top-level `TOOLS:` (clear `description:`).
- Preserve every meaningful transition condition and branch as explicit
  `ON_SUCCESS:` / `ON_FAIL:` blocks with `THEN:` pointing at the next step
  name, exactly as service calls in the sample ABL do.
- Logic/intent nodes are useful only for their transition conditions; do not
  recreate their internal implementation, only the branching they cause.
- Terminate every branch that reaches the X011 'end' node with `THEN: COMPLETE`
  and a final `COMPLETE:` step block containing a `RESPOND:`.
- Step names must be readable, deterministic, and referenced consistently in
  `steps:` and every `THEN:`.
""".strip(),
    "supervisor": """
AGENT STYLE: SUPERVISOR AGENT
- Do NOT include a `FLOW:` section.
- Include a top-level `INTENTS:` section that maps each intent key to a clear
  one-sentence description of what the agent should handle.
- Include a top-level `HANDOFF:` section that routes to each agent based on
  `intent.category == "<intent_key>"`.
- For each handoff entry, include `TO`, `WHEN`, `EXPECT_RETURN`, and a
  `CONTEXT` block with a concise `summary`.
- Use only the supervisor context provided below to decide which intents and
  agent names to include. Do not invent extra agents.
- If supervisor context entries include `intent_description`, use it as the
  INTENTS description. Otherwise, derive a short description from the intent
  name without adding new scope.
""".strip(),
}


def build_generation_prompt(
    ir: Dict[str, Any],
    sample_abl: str,
    abl_rules: str,
    agent_style: str,
    supervisor_context: str | None = None,
  user_instructions: str | None = None,
) -> str:
    style_guidance = _STYLE_GUIDANCE.get(agent_style, _STYLE_GUIDANCE["flow"])

    supervisor_block = ""
    if agent_style == "supervisor":
        supervisor_block = f"""

SUPERVISOR CONTEXT (authoritative)
----------------
{supervisor_context or "[]"}
----------------
"""

    instructions_block = ""
    if user_instructions and user_instructions.strip():
      instructions_block = f"""

  USER INSTRUCTIONS (authoritative, highest priority for this agent)
  ----------------
  {user_instructions.strip()}
  ----------------
  """

    return f"""
You are an expert Artemis (Kore.ai) ABL author converting a Kore.ai X011
dialog flow into a valid Artemis ABL agent definition.

You MUST author strictly valid Artemis ABL as defined by the platform rules
below. These rules are authoritative — if anything in the sample ABL or the
IR conflicts with them, the rules below win. Do NOT invent sections, keys,
or syntax that are not covered by these rules.

ARTEMIS ABL PLATFORM RULES (authoritative reference)
================================================================
{abl_rules}
================================================================

{style_guidance}

USER INSTRUCTION RULES
- If USER INSTRUCTIONS are provided, they override or augment the existing
  dialog flow for this specific agent. Preserve the dialog flow unless it
  conflicts with the instructions.
- Apply instruction changes by modifying the ABL flow/sections as needed.
- Do NOT invent new tools, APIs, or entity details unless the user
  instructions explicitly require them.

The sample ABL below shows the expected organization/style for this agent
style on this project. Match its section ordering and formatting
conventions, but never violate the platform rules above.

CONVERSION RULES
1. Convert the FLOW/intent behavior, not the X011 implementation code.
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
11. Tool names must be lowercase and use only a-z, 0-9, and underscores. If a
  source tool name violates this, normalize it (invalid chars -> underscore)
  and use the normalized name everywhere (TOOLS and CALL).
12. When the source contains a content.X reference but not the underlying
    content text, keep the reference explicitly and report it in
    unresolved_references.
13. Do not output Markdown fences around the ABL.
14. Use COMPLETE to terminate branches that reach the X011 'end' node.
15. Keep node/step names readable and deterministic.
16. Prefer explicit ON_SUCCESS / ON_FAIL branches for service calls when
    the X011 source contains distinct success/failure paths.
17. The resulting ABL must describe behavior from start to end, with no
    disconnected source nodes.
18. Follow the AGENT STYLE guidance above exactly — do not mix reasoning-agent
    and flow-agent structure.
19. For flow agents, each FLOW step block must explicitly declare
  `REASONING: true` or `REASONING: false`.
20. Only include `HOOKS:` or `ON_START:` when the IR explicitly requires them.
  If you include a `SET:` block, it must contain at least one assignment in
  the form `name = expression` or `name: expression`. Otherwise omit `SET:`.

SAMPLE ABL
----------------
{sample_abl}
----------------
{supervisor_block}
{instructions_block}

NORMALIZED X011 FLOW IR
----------------
{json.dumps(ir, ensure_ascii=False, indent=2)}
----------------
""".strip()
