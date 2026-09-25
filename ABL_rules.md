# Reasoning Agent — ABL Rules & Format (Concise)

> Source: Kore.ai Artemis docs (`/agent-platform/abl-reference/*`). No invented tags.
> A **Reasoning Agent** = an ABL agent with **no `FLOW:` section**. The LLM (Agentic Brain)
> autonomously chooses tools/responses to pursue `GOAL:`. `MODE:` keyword is deprecated (parser error).

## 1. File Basics
- Required: `AGENT:` (PascalCase_With_Underscores, unique) and `GOAL:` (string or `|` block).
- Formats: `.agent.abl` (UPPERCASE keys) or `.agent.yaml` (lowercase keys) — same AST/IR.
- Indent with spaces. `#` = full-line comments only (no inline). Strings: `"quoted"`, unquoted, or `|` block.
- Lists: `- item`. `TESTS:` section is parsed but ignored.
- Template interpolation: `{{var}}`, conditionals `{{#if x}}...{{/if}}`.
- `VERSION: "1.0.0"` (default), semver string.
- Pipeline: ABL → Parser(AST) → Compiler(AgentIR, validates refs/contracts) → Runtime (Agentic Brain).

## 2. Top-Level Sections (Reasoning Agent)
`AGENT, VERSION, DESCRIPTION, LANGUAGE, GOAL, PERSONA, LIMITATIONS, IDENTITY, INSTRUCTIONS,
SYSTEM_PROMPT, EXECUTION, TOOLS, GATHER, MEMORY, CONSTRAINTS, GUARDRAILS, DELEGATE, HANDOFF,
ESCALATE, COMPLETE, ON_ERROR, ON_START, MESSAGES, TEMPLATES, HOOKS, NLU, MULTI_INTENT, INTENTS,
ENTITIES, LOOKUP_TABLES, ATTACHMENTS, DESTINATIONS, TRANSFER_FLOW_POLICIES, RETURN_HANDLERS,
ACTION_HANDLERS, CONVERSATION, RICH_CONTENT/ACTIONS (top-level allowed w/o FLOW)`.
Omit `FLOW:` entirely — its presence makes it a flow-based agent (see companion doc).

## 2a. Flow Agent Requirement (when FLOW is present)
- A flow agent MUST include a top-level `FLOW:` with `steps:` and step blocks.
- Every step block MUST declare `REASONING: true` or `REASONING: false` directly inside that step.

## 3. Identity & Goals
```
AGENT: Wire_Transfer_Specialist
GOAL: |
  Process the customer's wire transfer accurately and securely.
PERSONA: "Precise, methodical, transparent about fees."
LIMITATIONS:
  - "Cannot process wires to sanctioned countries"
INSTRUCTIONS: "Verify identity before collecting wire details."
```
- `GOAL` (required): agent's objective, drives reasoning & completion. State from agent's POV.
- `PERSONA`: tone/style; default = neutral if omitted.
- `LIMITATIONS`: LLM-enforced boundaries (state what agent *cannot* do). Complements `CONSTRAINTS`.
- `INSTRUCTIONS`: appended under the goal.
- `IDENTITY:` (compact alt.): `{role→GOAL, persona→PERSONA, expertise→appended to PERSONA, limitations→LIMITATIONS}`.
- `SYSTEM_PROMPT:` full custom prompt — **replaces** auto-generated GOAL/PERSONA/LIMITATIONS prompt.

## 4. EXECUTION
```
EXECUTION:
  model: "claude-sonnet-4-5-20250929"
  temperature: 0.3
  max_tokens: 4096
  tool_timeout: 30000
  max_reasoning_iterations: 8      # key for reasoning agents (no FLOW)
  fallback_model: "claude-haiku-4-5-20251001"
  enable_thinking: true
  thinking_budget: 4000
  compaction_threshold: 0.8
  concurrency: serial               # serial | preemptive | parallel
  models: { extraction: "...", response_gen: "...", reasoning: "..." }
```
All optional; platform defaults apply. Other keys: `top_p, top_k, frequency_penalty,
presence_penalty, seed, stop_sequences, reasoning_effort, verbosity, llm_timeout,
session_idle_timeout, inline_gather, max_queue_depth, max_concurrent_messages,
conversation_history_window, voice, pipeline`. `compaction:` sub-block allows fine-grained
`tool_results/prior_turns/prompt_context` overrides (see full ref if needed).

## 5. TOOLS
```
TOOLS:
  search_flights(origin: string, destination: string, date: date) -> {flights: {id: string, price: number}[]}
    description: "Search available flights"   # critical: LLM picks tools by this text
    type: http
    endpoint: "https://api.flights.com/v1/search"
    method: POST
    auth: bearer
    timeout: 10000
    retry: 3
    confirmation: { require: always, immutable_params: [amount] }
```
- Signature: `name(param: type, opt?: type, def: type = val) -> ReturnType`. Types: string, number,
  boolean, date, object (nested `parameters:`), `type[]`.
- Return: `-> type | {f: t} | type[] | {f?: t} | {f: t}[]`.
- Tool names must be lowercase and use only `a-z`, `0-9`, and underscores.
- **Binding types**: `http`, `mcp` (`server`, `server_tool`), `sandbox` (`runtime: javascript|python`,
  `code:`), `lambda` (`function:`), `async_webhook` (`callback_url_field`), `workflow`
  (`workflow_id`, `mode: sync|async`, `param_mapping`), `searchai` (`index_id`), `table`
  (`table`, `scope`, `operations`).
- HTTP extras: `auth_config`, `auth_profile/tls_profile/auth_jit/consent/connection`,
  `retry_policy`, `circuit_breaker`, `protocol: soap` (+`soap_version/soap_action/wsdl_*`),
  `request_variants`, `on_result:`/`on_error:` (with `set:` or ordered `do:` actions).
- Features: `hints: {cacheable, latency, side_effects, requires_auth, timeout}`, `effect:
  read_only|state_write|side_effect`, `provides: [...]`, `pii_access`, `scrub_secrets: false`,
  `context_access: {read, write}` (must match `MEMORY:`), `store_result: false`,
  `RESULT_SECRETS:` / `SECRET_ACCESS:` (SecretRef vault; HTTP-only consumers).
- Import shared tools: `TOOLS: file: "./x.tools.abl" [tool_a, tool_b]`.
- SSRF protection is always enforced on HTTP endpoints.

## 6. GATHER (top-level)
```
GATHER:
  amount:
    prompt: "How much would you like to transfer?"
    type: number
    required: true
    validate: min(1)
    infer: true
    infer_confidence: 0.9
```
- Types: string, text, free_text, number, integer, float, currency, boolean, date, datetime,
  email, phone, enum, pattern, location.
- Key properties: `prompt`(req), `type`, `required`(default true), `default`, `entity_ref`
  (bind to `ENTITIES:`), `options` (enum), `validate` (`min/max/enum/email/pattern`),
  `validation_process: REGEX|CODE|LLM`, `retry_prompt`, `max_retries`, `infer`/`infer_confidence`
  /`infer_confirm`, `range`(→{low,high}), `list`(→array), `preferences`(→{accept,desire,avoid,refuse}),
  `activation`("required"|"optional"|"progressive"|`{when:cond}`), `depends_on`, `satisfied_by`
  (`user_input|authoritative_tool|system`), `sensitive`+`sensitive_display`(redact/mask/replace)
  +`mask_config`+`pii_type`, `transient`, `extraction_pattern`+`extraction_group`, `strategy`
  (auto/ml/llm/hybrid/pattern), `semantics` (`format, unit, lookup, convert_to, locale, temporal,
  enum_set`).

## 7. MEMORY
```
MEMORY:
  session:
    - customer_id
    - order_total: { TYPE: number, INITIAL: 0, RESET: per_session }
  persistent:
    - user.wire_history_30d: { SCOPE: user, ACCESS: readwrite, TYPE: array }
  remember:
    - WHEN: user_language IS SET
      STORE: user_language -> user.language
      TTL: "90d"
  recall:
    - ON: session:start
      ACTION: inject_context
      PATHS: [user.preferred_language]
```
- Session `RESET`: `per_session`(default)|`per_activation`|`per_step`|`never`.
- Persistent `SCOPE`: `user`(default)|`project`|`execution_tree`; `ACCESS`: read/write/readwrite.
  Shorthand `READS:`/`WRITES:` sub-blocks.
- `remember`: `WHEN` + `STORE: val -> path` (or block form w/ `operation: overwrite|append`,
  `unique`, `maxSize`) + optional `TTL` (`s/m/h/d`).
- `recall` events: `session:start/end`, `agent:<n>:before/after`, `tool:<n>:after` (no `:before`),
  `entity:<f>:extracted`, `step:enter/exit:<n>`. Actions: `inject_context`, `load_memory`,
  `prompt_llm`(default). Legacy event names rejected at compile time.

## 7a. Script-to-ABL Mapping Rules (Both Platforms)
- When generating ABL from script logic (script node, message node, entity node, etc.), preserve behavior.
- Any reference like `context.session.BotUserSession.<var>` maps to `MEMORY.session` in ABL; do not treat as transient.
- Channel handling:
  - `rtm` maps to `web` and uses the default message (no special casing required).
  - `IVR` messages are used only for the `IVR` channel; do not merge into the default message.
- Keep existing functionality intact; only add the mapping behavior above.

## 8. CONSTRAINTS (deterministic, runtime-enforced)
```
CONSTRAINTS:
  always:
    - REQUIRE customer_verified == true
      ON_FAIL: "Please verify your identity first."
    - RESTRICT beneficiary_country IN ["CU","IR","KP","SY"]
      ON_FAIL: "Transfers to that destination are prohibited."
    - REQUIRE transfer_type == "international" IMPLIES swift_code IS SET
      ON_FAIL: "International transfers require a SWIFT/BIC code."
```
- Phase names (`always`, etc.) are **labels only** — compiler flattens to one ordered list.
- Keywords: `REQUIRE` (must be true), `LIMIT` (numeric boundary), `RESTRICT` (fails if true).
- `WHEN:` gates applicability. `BEFORE calling <tool>` / `BEFORE returning results` are the only
  supported structural checkpoints. `IMPLIES` = inline `A IMPLIES B` → `NOT(A) OR B`.
- `ON_FAIL`: string message | `HANDOFF <Agent>` | `ESCALATE` | `BLOCK` | structured block
  (`RESPOND, CLEAR, COLLECT, GOTO, RETRY, THEN: continue|retry`).
- `severity: error`(default, blocks) `| warning`(logs, continues) — text ABL uses `WARN` keyword.
- Eval order: flattened list, declaration order, stops at first `error` failure.

## 9. GUARDRAILS (content safety, distinct from CONSTRAINTS)
```
GUARDRAILS:
  pii_output_prevention:
    kind: output               # input|output|both|tool_input|tool_output|handoff
    check: not_contains_ssn(response)     # Tier 1 CEL
    action: redact
    priority: 0
  toxicity:
    kind: input
    provider: openai_moderation           # Tier 2 model-based
    category: hate
    threshold: 0.7
    action: block
  medical_check:
    kind: output
    llm_check: "Does this give a medical diagnosis? YES/NO"   # Tier 3 LLM
    action: reask
    max_reasks: 3
```
- Actions: `block, warn, redact, escalate, fix(+fix_strategy: truncate|strip_html|redact_pii|
  normalize|custom), reask(+max_reasks), filter`. `severity_actions:` for graduated response.
- `streaming: true` + `streaming_interval: token|sentence|chunk_size` for mid-stream eval.
- Priority: lower evaluated first; `block` stops further checks; `warn` doesn't.
- Built-in Tier-1 templates: `detect_instruction_override`, `detect_role_manipulation`,
  `detect_system_prompt_extraction`, `detect_encoding_tricks` (all `warn`),
  `detect_credential_leak` (`redact`).

## 10. Multi-Agent: HANDOFF / DELEGATE / ESCALATE / COMPLETE
```
HANDOFF:
  - TO: Senior_Advisor_Agent
    WHEN: amount > 50000
    CONTEXT: { pass: [customer_id, amount], summary: "High-value transfer", history: full,
               memory_grants: [{path: user.notes, access: readwrite}] }
    EXPECT_RETURN: true
    ON_FAILURE: ESCALATE
    ON_RETURN: { action: continue, map: {user_id: auth_result.user_id} }
```
- `EXPECT_RETURN` (was `RETURN`) controls pause/resume. `history`: full(default)|auto|none|
  summary_only|`{mode:last_n,count:n}`. `memory_grants` (not legacy `grant_memory`, which errors).
- `ON_FAILURE`: `CONTINUE|ESCALATE|RESPOND "msg"` (pre-accept failures only).
- `EXPERIENCE_MODE`: shared_voice_handoff|visible_handoff|silent_delegate|human_escalation.
- Named reusable resume logic: top-level `RETURN_HANDLERS:` referenced via `ON_RETURN.handler`.

```
DELEGATE:
  - AGENT: Sanctions_Screening
    WHEN: beneficiary_name IS SET
    PURPOSE: "Screen beneficiary"
    INPUT: { name: beneficiary_name }
    RETURNS: { cleared: sanctions_clear }
    USE_RESULT: "Block if not cleared."
    TIMEOUT: "15s"
    ON_FAIL: escalate         # respond|continue|escalate|retry
```
⚠️ `DELEGATE` is synchronous/one-shot; if the sub-agent has **required** GATHER fields, map them in
`INPUT:` or compilation fails. No `FAN_OUT:` section exists — fan-out is a runtime-only capability.

```
ESCALATE:
  triggers:
    - WHEN: retry_count >= 2
      REASON: "Service unavailable"
      PRIORITY: critical        # low|medium(default)|high|critical
  context_for_human: [customer_id, amount]
  routing: { connection: livechat, queue: "l2", skills: [wire_transfer] }
  on_human_complete:
    - IF human.resolved == true: COMPLETE
```
Use `THEN: ESCALATE with REASON: "..."` inside `ON_ERROR` (no inline `ESCALATE:` there).

```
COMPLETE:
  - WHEN: confirmation_number IS SET      # must be a deterministic boolean expr
    RESPOND: "Transfer complete: {{confirmation_number}}"
    TERMINAL: false   # keep session open (e.g. to collect feedback)
```
⚠️ `WHEN` must NOT be plain-English text (compile error `PLAIN_ENGLISH_COMPLETE_WHEN`).
**Turn evaluation order:** ESCALATE → HANDOFF (priority) → DELEGATE (declared order) → COMPLETE.

## 11. NLU, ENTITIES, LOOKUP_TABLES (precision aids)
```
NLU:
  intents:
    - NAME: send_wire
      PATTERNS: ["wire transfer","send money"]
      EXAMPLES: ["I need to wire $50,000 to Germany"]
  entities:
    - NAME: currency_code
      TYPE: enum
      VALUES: [USD, EUR]
      SYNONYMS: { USD: [dollars, bucks] }
  embeddings: { enabled: true, threshold: 0.75 }
  glossary: ["SWIFT/BIC -- bank identifier code"]

ENTITIES:                      # top-level, reusable, 15 types, referenced by GATHER entity_ref
  request_type: { TYPE: enum, VALUES: [REQ_REFUND, REQ_EXCHANGE] }

LOOKUP_TABLES:
  airport_codes: { source: inline, values: [JFK, LAX], fuzzy_match: true, fuzzy_threshold: 0.85 }
```
- `NLU:entities:` supports only 6 types (enum/pattern/location/date/number/free_text); top-level
  `ENTITIES:` supports all 15 and is shared with GATHER via `entity_ref`.
- `MULTI_INTENT:` config: `strategy: primary_queue|sequential|parallel|disambiguate|auto`,
  `max_intents`(default 3), `confidence_threshold`(0.6).
- `LOOKUP_TABLES` sources: `inline`(values), `collection`(table_name+field),
  `api`(endpoint+field+timeout_ms). Referenced via GATHER `semantics.lookup: <table>`.

## 12. Rich Content & Expressions
- `VOICE:` (ssml, instructions, plain_text, provider, voice_id, speed).
- `FORMATS:` (keyword in `.agent.abl`) for `MARKDOWN, ADAPTIVE_CARD, HTML, SLACK, AG_UI, WHATSAPP`
  plus structured `CAROUSEL, QUICK_REPLIES, LIST, IMAGE, VIDEO, AUDIO, FILE, KPI, TABLE, CHART,
  FORM, PROGRESS, FEEDBACK`. A pure reasoning agent may declare top-level `FORMATS:`/`ACTIONS:`.
- `ACTIONS:` (`id, type: button|select|input, label, value, options, inputType, required`) +
  reusable `ACTION_HANDLERS:` (top-level, keyed by action id, `DO:` ordered actions).
- `TEMPLATES:` named reusable responses (`DEFAULT`, `MARKDOWN`, `ACTIONS`, `VOICE`), referenced via
  `RESPOND: TEMPLATE(name)`.
- **Expressions**: comparisons `== != > < >= <= IN NOT IN matches contains startsWith endsWith`;
  logic `AND OR NOT` (uppercase); unary `IS SET / IS NOT SET`; dot-paths `a.b[0].c`.
- **36 built-in functions** (UPPERCASE), e.g.: Math `ADD SUB MUL DIV ROUND ABS MIN MAX`; String
  `UPPER LOWER TRIM SUBSTRING REPLACE SPLIT JOIN PAD_START PAD_END REPEAT`; Format `MASK
  FORMAT_CURRENCY FORMAT_DATE ORDINAL`; Type `IS_ARRAY IS_NUMBER IS_STRING TO_NUMBER TO_STRING`;
  Array `LENGTH ARRAY_FIND ARRAY_FIND_INDEX`; Object `OBJECT_KEYS OBJECT_VALUES OBJECT_MERGE`;
  Utility `COALESCE NOW UNIQUE_ID`. Nesting max depth 32; string output capped at 100k chars.

## 13. Lifecycle
```
ON_START:
  SET: { transfer_status: "pending" }
  CALL: check_returning_user()
  BRANCHES:
    - IF: user.is_returning == true
      RESPOND: "Welcome back, {{user.name}}!"
    - ELSE:
      RESPOND: "Welcome! How can I help?"

HOOKS:
  before_turn: { SET: { turn_start: "NOW()" } }
  after_turn: { CALL: log_audit_event() }

ON_ERROR:
  tool_timeout: { RESPOND: "Retrying...", RETRY: 2, THEN: CONTINUE }
  unknown_error: ESCALATE

MESSAGES:
  error_default: "Sorry, something went wrong."
```
- `ON_START` fires once/session; `HOOKS` fire every `before_agent/after_agent/before_turn/after_turn`.
- `ON_ERROR` type is a free-form label (`tool_timeout, tool_error, invalid_input,
  validation_error, api_error, unknown_error` common); `THEN`: CONTINUE|ESCALATE|HANDOFF|COMPLETE.
- `MESSAGES:` overrides any system string key (`error_default, constraint_blocked, gather_prompt,
  escalation_format, conversation_complete, invalid_handoff, ...`).

## 14. Behavior Profiles (optional)
Standalone file `behavior_profiles/<name>.behavior_profile.abl`:
```
BEHAVIOR_PROFILE: voice_vip
PRIORITY: 100
WHEN: channel == "voice"
INSTRUCTIONS: "Speak concisely."
CONVERSATION: { speaking: { tone: warm, max_sentences: 2 } }
TOOLS: { HIDE: [internal_debug_tool] }
```
Attach: `USE BEHAVIOR_PROFILE: voice_vip` inside the agent. Inline (non-standalone) profiles only
support `PRIORITY, WHEN, INSTRUCTIONS, CONVERSATION`.

## 15. Authoring Checklist
1. `AGENT:` + specific `GOAL:`. 2. `PERSONA:`/`LIMITATIONS:` for tone/boundaries.
3. `TOOLS:` with clear `description:` (LLM selects tools autonomously). 4. `GATHER:` for structured
   fields. 5. `MEMORY:` for cross-turn/session state. 6. `CONSTRAINTS:` for hard business rules
   (never rely on `LIMITATIONS:` alone). 7. `GUARDRAILS:` for content safety. 8. `HANDOFF/DELEGATE/
   ESCALATE` for composition & human-in-the-loop. 9. `COMPLETE:` with a deterministic `WHEN:`.
10. `NLU/ENTITIES/LOOKUP_TABLES` if intent/entity precision matters. 11. `ON_START/HOOKS/ON_ERROR/
    MESSAGES` for polish. 12. Add `FLOW:` only when part of the process must be deterministic.