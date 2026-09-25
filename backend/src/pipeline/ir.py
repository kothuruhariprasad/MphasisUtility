from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.pipeline.decode import clean_message_expression

SCRIPT_TYPES = {"script"}
BOT_ACTION_TYPES = {"botaction"}
SERVICE_TYPES = {
    "service",
    "webhook",
    "api",
    "servicecall",
    "service_call",
    "integration",
    "http",
    "httpservice",
    "apicall",
}


def _find_first_list_by_key(data: Any, key: str, max_depth: int = 8) -> List[Any]:
    if max_depth < 0:
        return []
    if isinstance(data, dict):
        value = data.get(key)
        if isinstance(value, list):
            return value
        for child in data.values():
            found = _find_first_list_by_key(child, key, max_depth - 1)
            if found:
                return found
    elif isinstance(data, list):
        for child in data:
            found = _find_first_list_by_key(child, key, max_depth - 1)
            if found:
                return found
    return []


def _find_all_lists_by_key(data: Any, key: str, max_depth: int = 10) -> List[List[Any]]:
    results: List[List[Any]] = []
    if max_depth < 0:
        return results
    if isinstance(data, dict):
        value = data.get(key)
        if isinstance(value, list):
            results.append(value)
        for child in data.values():
            results.extend(_find_all_lists_by_key(child, key, max_depth - 1))
    elif isinstance(data, list):
        for child in data:
            results.extend(_find_all_lists_by_key(child, key, max_depth - 1))
    return results


def _extract_dialogs(data: Any) -> List[Dict[str, Any]]:
    dialogs: List[Dict[str, Any]] = []
    for items in _find_all_lists_by_key(data, "dialogs"):
        dialogs.extend([x for x in items if isinstance(x, dict)])

    # Some exports expose dialogs under botTasks/flows/automation lists.
    if not dialogs:
        for key in ("botTasks", "flows", "automation"):
            for items in _find_all_lists_by_key(data, key):
                dialogs.extend([x for x in items if isinstance(x, dict) and isinstance(x.get("nodes"), list)])

    return dialogs


def _extract_components(data: Any) -> List[Dict[str, Any]]:
    components: List[Dict[str, Any]] = []
    for key in ("dialogComponents", "components"):
        for items in _find_all_lists_by_key(data, key):
            components.extend([x for x in items if isinstance(x, dict)])
    return components


def _resolve_dialogs_and_components(app: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    dialogs = _extract_dialogs(app)
    components = _extract_components(app)
    return dialogs, components


def _expand_bot_action_nodes(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    expanded: List[Dict[str, Any]] = []
    redirect: Dict[str, str] = {}

    for node in nodes:
        node_type = str(node.get("type") or "").lower()
        inner_nodes = node.get("nodes") if node_type in BOT_ACTION_TYPES and isinstance(node.get("nodes"), list) else None
        if inner_nodes:
            inner = [n for n in inner_nodes if isinstance(n, dict) and n.get("nodeId")]
            if inner:
                redirect[str(node.get("nodeId"))] = str(inner[0].get("nodeId"))
                for inner_node in inner:
                    if inner_node.get("transitions") is None:
                        inner_node = dict(inner_node)
                        inner_node["transitions"] = []
                    expanded.append(inner_node)

                wrapper_transitions = node.get("transitions") or []
                if wrapper_transitions:
                    last_idx = len(expanded) - 1
                    last = expanded[last_idx]
                    last_transitions = last.get("transitions") or []
                    if not last_transitions or all(
                        (tr.get("then") or tr.get("default")) == "end" for tr in last_transitions
                    ):
                        last = dict(last)
                        last["transitions"] = list(wrapper_transitions)
                        expanded[last_idx] = last
                continue

        expanded.append(node)

    if redirect:
        for idx, node in enumerate(expanded):
            transitions = node.get("transitions") or []
            if not transitions:
                continue
            updated = []
            changed = False
            for tr in transitions:
                target = tr.get("then") or tr.get("default")
                if target in redirect:
                    tr = dict(tr)
                    if tr.get("then"):
                        tr["then"] = redirect[target]
                    if tr.get("default"):
                        tr["default"] = redirect[target]
                    changed = True
                updated.append(tr)
            if changed:
                node = dict(node)
                node["transitions"] = updated
                expanded[idx] = node

    return expanded


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

    if is_service_component(component, node_type):
        result = {
            "name": component.get("name"),
            "type": "service",
            "label": en.get("label"),
        }
        candidate_keys = [
            "serviceNodeType",
            "serviceType",
            "method",
            "url",
            "path",
            "request",
            "response",
            "headers",
            "params",
            "body",
            "auth",
            "connection",
            "service",
        ]
        for key in candidate_keys:
            if component.get(key) is not None:
                result[key] = component[key]
        return result

    if ctype == "entity":
        prompts = []
        for msg in component.get("message") or []:
            msg_en = ((msg.get("localeData") or {}).get("en") or {})
            prompts.append({"channel": msg.get("channel"), **clean_message_expression(msg_en.get("text"))})
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
            messages.append({"channel": msg.get("channel"), **clean_message_expression(msg_en.get("text"))})

        errors = []
        for msg in component.get("errorMessage") or []:
            msg_en = ((msg.get("localeData") or {}).get("en") or {})
            errors.append({"channel": msg.get("channel"), **clean_message_expression(msg_en.get("text"))})

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
        transitions.append(
            {
                "kind": "conditional" if t.get("if") else "default",
                "condition": condition_ir(t.get("if")),
                "next": target,
            }
        )

    return {
        "node_id": node.get("nodeId"),
        "type": node.get("type"),
        "component_name": component.get("name"),
        "component": component_ir(component, str(node.get("type") or "")),
        "preconditions": [condition_ir(x) for x in (node.get("preConditions") or [])],
        "transitions": transitions,
    }


def follow_script_chain(start: Optional[str], nodes: Dict[str, Dict[str, Any]]) -> Tuple[Optional[str], List[str]]:
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
            break

        current = defaults[0]["next"]

    return current, collapsed


def preprocess(app: Dict[str, Any], platform: str = "x011") -> Dict[str, Any]:
    dialogs, dialog_components = _resolve_dialogs_and_components(app)
    components = {c.get("_id"): c for c in dialog_components if c.get("_id")}

    source_label = "Kore.ai X011 app definition" if platform == "x011" else "Kore.ai X010 bot definition"

    output = {
        "source": source_label,
        "conversion_scope": [
            "conversation flow from entry to end",
            "conditions and transition branches",
            "message prompts when actually present",
            "entity/user-input collection",
            "service/API calls",
        ],
        "ignored_scope": [
            "script implementation/body",
            "UI positions and colors",
            "runtime metadata",
            "generative-AI provider metadata unless needed for flow semantics",
        ],
        "dialogs": [],
    }

    for dialog in dialogs:
        dialog_nodes = dialog.get("nodes") or []
        if platform == "x010":
            dialog_nodes = _expand_bot_action_nodes([n for n in dialog_nodes if isinstance(n, dict)])
        raw_nodes = {n.get("nodeId"): n for n in dialog_nodes if n.get("nodeId")}

        normalized = {}
        for node_id, node in raw_nodes.items():
            comp = components.get(node.get("componentId"), {})
            normalized[node_id] = normalize_node(node, comp)

        ignored_scripts = []
        for node_id, n in normalized.items():
            if n["type"] in SCRIPT_TYPES:
                ignored_scripts.append({"node_id": node_id, "component_name": n["component_name"]})

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

        entry_nodes = [
            s.get("nodeId")
            for s in (dialog.get("sequences") or [])
            if s.get("primaryIntent") and s.get("nodeId")
        ]

        if not entry_nodes:
            referenced = {
                tr["next"]
                for n in normalized.values()
                for tr in n["transitions"]
                if tr.get("next")
            }
            entry_nodes = [node_id for node_id in normalized if node_id not in referenced]

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
                continue
            functional_nodes.append(node)

        source_order = {node_id: i for i, node_id in enumerate(raw_nodes)}
        functional_nodes.sort(key=lambda x: source_order.get(x["node_id"], 10**9))

        output["dialogs"].append(
            {
                "dialog_id": dialog.get("_id") or dialog.get("dialogId") or dialog.get("id"),
                "ref_id": dialog.get("refId") or dialog.get("name") or dialog.get("displayName"),
                "entry_nodes": entry_nodes,
                "reachable_node_count": len(functional_nodes),
                "ignored_script_nodes": ignored_scripts,
                "nodes": functional_nodes,
            }
        )

    return output
