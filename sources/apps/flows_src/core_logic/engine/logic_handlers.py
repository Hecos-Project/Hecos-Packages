"""
Hecos Flows — Native Logic Node Handlers
==========================================
Implements all built-in LOGIC__ and CONTROL__ node types that are executed
directly inside the engine without going through the action registry.

Adding a new native node: implement a _handle_xxx function with the signature
    (step: Dict, context: Dict, run_id: str, emit: Callable) -> Any
then add it to LOGIC_HANDLERS at the bottom of this file.
"""

import time
from typing import Any, Callable, Dict, List

from hecos.core.logging import logger
from .evaluator import render, render_params, eval_condition


class FlowLogger:
    def info(self, msg): logger.info("FLOWS", msg)
    def error(self, msg): logger.error("FLOWS", msg)
    def warning(self, msg): logger.debug("FLOWS", f"[WARN] {msg}")
    def debug(self, msg): logger.debug("FLOWS", msg)

log = FlowLogger()


# ── Branch execution helper ───────────────────────────────────────────────────

def _execute_branch(branch: Any, step_id_prefix: str, context: Dict, run_id: str, emit: Callable) -> Any:
    """Execute a branch value — may be a single action dict or a list of action dicts."""
    if not branch:
        return None
    # Import here to avoid circular dependency (runner ↔ logic_handlers)
    from .runner import _execute_step
    if isinstance(branch, list):
        res = None
        for i, b in enumerate(branch):
            if isinstance(b, dict):
                sub_step = {
                    "id":     f"{step_id_prefix}_{i}",
                    "action": b.get("action", ""),
                    "params": b.get("params", {}),
                }
                res = _execute_step(sub_step, context, run_id, emit)
        return res
    elif isinstance(branch, dict):
        sub_step = {
            "id":     step_id_prefix,
            "action": branch.get("action", ""),
            "params": branch.get("params", {}),
        }
        return _execute_step(sub_step, context, run_id, emit)
    return None


# ── Individual node handlers ──────────────────────────────────────────────────

def _handle_start(step: Dict, context: Dict, **_) -> Any:
    """CONTROL__start — pass-through entry point."""
    return True


def _handle_delay(step: Dict, context: Dict, **_) -> None:
    seconds = float(render(str(step["params"].get("seconds", 1)), context))
    time.sleep(seconds)


def _handle_set_variable(step: Dict, context: Dict, **_) -> None:
    name = step["params"].get("name", "")
    # Strip brackets in case the user used the variable picker for the name field
    clean_name = name.replace("{{", "").replace("}}", "").strip()
    value = step["params"].get("value", "")
    context[clean_name] = render(str(value), context)


def _handle_template(step: Dict, context: Dict, **_) -> str:
    template  = step["params"].get("template", "")
    output_as = step["params"].get("output_as", "template_result")
    result    = render(template, context)
    context[output_as] = result
    return result


def _handle_if_else(step: Dict, context: Dict, run_id: str, emit: Callable) -> Any:
    if "_branch_results" not in context:
        context["_branch_results"] = {}

    # Backward compatibility: legacy condition schema
    if "condition" in step["params"]:
        condition = step["params"].get("condition", "false")
        result    = eval_condition(condition, context)
        branch_key = "true_branch" if result else "false_branch"
        context["_branch_results"][step["id"]] = branch_key
        branch = step["params"].get(branch_key)
        return _execute_branch(branch, f"{step['id']}_{branch_key}", context, run_id, emit)
    
    # New schema: branches list
    branches = step["params"].get("branches", [])
    
    if isinstance(branches, list):
        for i, condition in enumerate(branches):
            if eval_condition(str(condition), context):
                branch_key = f"branch_{i}"
                context["_branch_results"][step["id"]] = branch_key
                return None  # Node purely routes execution via depends_on in visual builder
    
    # Fallback to default/false
    context["_branch_results"][step["id"]] = "false_branch"
    return None





def _handle_switch(step: Dict, context: Dict, run_id: str, emit: Callable) -> Any:
    expr     = render(step["params"].get("expression", ""), context)
    branches = step["params"].get("branches", {})
    branch   = branches.get(expr) if isinstance(branches, dict) else None
    if not branch:
        branch = step["params"].get("default")
    return _execute_branch(branch, f"{step['id']}_branch_{expr}", context, run_id, emit)


def _handle_loop(step: Dict, context: Dict, run_id: str, emit: Callable) -> List:
    over_ref = render(step["params"].get("over", ""), context)
    as_var   = step["params"].get("as_var", "item")
    body     = step["params"].get("body", {})

    iterable = context.get(over_ref.strip("{{ }}"), [])
    results  = []

    for i, item in enumerate(iterable):
        sub_ctx = dict(context)
        sub_ctx[as_var] = item
        res = _execute_branch(body, f"{step['id']}_iter_{i}", sub_ctx, run_id, emit)
        results.append(res)

    return results


def _handle_and_gate(step: Dict, context: Dict, run_id: str, emit: Callable) -> Any:
    conditions = step["params"].get("conditions", [])
    all_pass   = all(eval_condition(render(c, context), context) for c in conditions)
    branch_key = "on_success" if all_pass else "on_fail"
    branch     = step["params"].get(branch_key)
    if branch:
        return _execute_branch(branch, f"{step['id']}_{branch_key}", context, run_id, emit)
    return all_pass


def _handle_or_gate(step: Dict, context: Dict, run_id: str, emit: Callable) -> Any:
    conditions = step["params"].get("conditions", [])
    any_pass   = any(eval_condition(render(c, context), context) for c in conditions)
    branch_key = "on_success" if any_pass else "on_fail"
    branch     = step["params"].get(branch_key)
    if branch:
        return _execute_branch(branch, f"{step['id']}_{branch_key}", context, run_id, emit)
    return any_pass


def _handle_http_request(step: Dict, context: Dict, **_) -> Any:
    import urllib.request, urllib.error, json
    method    = step["params"].get("method", "GET").upper()
    url       = render(step["params"].get("url", ""), context)
    headers   = render_params(step["params"].get("headers", {}), context)
    body      = step["params"].get("body")
    output_as = step["params"].get("output_as", "http_response")

    req = urllib.request.Request(url, method=method)
    for k, v in headers.items():
        req.add_header(k, str(v))

    if body and method in ("POST", "PUT", "PATCH"):
        body_str = json.dumps(body) if isinstance(body, dict) else str(body)
        req.data = body_str.encode("utf-8")
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            try:
                result = json.loads(raw)
            except Exception:
                result = raw
        context[output_as] = result
        return result
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {e.reason} for {url}")


def _handle_abort(step: Dict, context: Dict, **_) -> None:
    from .event_bus import FlowAbortException
    reason = render(step["params"].get("reason", "Aborted by LOGIC__abort node"), context)
    log.info(f"[Flows.Engine] 🛑 LOGIC__abort executed: {reason}")
    raise FlowAbortException(reason)


# ── Dispatch table ────────────────────────────────────────────────────────────
# Maps action name → handler function.
# Add new built-in nodes here; the runner will pick them up automatically.

LOGIC_HANDLERS: Dict[str, Callable] = {
    "CONTROL__start":      _handle_start,
    "LOGIC__delay":        _handle_delay,
    "LOGIC__set_variable": _handle_set_variable,
    "LOGIC__template":     _handle_template,
    "LOGIC__if_else":      _handle_if_else,
    "LOGIC__switch":       _handle_switch,
    "LOGIC__loop":         _handle_loop,
    "LOGIC__and_gate":     _handle_and_gate,
    "LOGIC__or_gate":      _handle_or_gate,
    "LOGIC__http_request": _handle_http_request,
    "LOGIC__abort":        _handle_abort,
}
